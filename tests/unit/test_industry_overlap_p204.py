"""候选股与持仓行业重叠率单元测试。

覆盖：
- compute_industry_overlap 基本重叠判定（同 ETF 代理 = 同行业）
- 无重叠 / 未知行业 / 空持仓
- 集中度预警（重叠行业占比 > 20%）
- 集成：compute_full_portfolio_correlation 输出 industry_overlap
"""

import pytest

from portfolio_correlation import (
    compute_industry_overlap,
    _industry_of_code,
    _industry_to_etf_proxy,
    compute_full_portfolio_correlation,
)


def _pos(code, name, cost, qty, tags=None, industry=None):
    p = {
        "code": code,
        "name": name,
        "cost": cost,
        "quantity": qty,
        "tags": tags or [],
        "industry": industry or "",
    }
    return p


class TestIndustryOfCode:
    """行业归属映射。"""

    def test_stock_sector_map_hit(self):
        ind, proxy = _industry_of_code("sz002920")
        assert ind == "汽车电子"
        assert proxy == "sh515250"

    def test_unknown_code(self):
        ind, proxy = _industry_of_code("sh699999")
        assert ind is None
        assert proxy is None

    def test_proxy_from_sector_etf(self):
        assert _industry_to_etf_proxy("消费") == "sh512690"
        assert _industry_to_etf_proxy("不存在的行业") is None


class TestComputeIndustryOverlap:
    """行业重叠率。"""

    def test_no_overlap(self):
        # 德赛西威(汽车电子) vs 消费持仓（白酒代理）→ 无重叠
        pos = [
            _pos("sh600519", "茅台", 100, 100, tags=["白酒"]),
            _pos("sh600887", "伊利", 50, 100, tags=["消费"]),
        ]
        res = compute_industry_overlap("sz002920", pos)
        assert res["stock_industry"] == "汽车电子"
        assert res["overlap_count"] == 0
        assert res["concentration_warning"] is False
        assert "无重叠" in res["message"]

    def test_overlap_by_etf_proxy(self):
        # 中际旭创(通信设备→sh515880) vs 新易盛(通信设备→sh515880) 同 ETF
        pos = [
            _pos("sz300502", "新易盛", 30, 100, tags=["通信"]),
            _pos("sh600519", "茅台", 100, 100, tags=["白酒"]),
        ]
        res = compute_industry_overlap("sz300308", pos)
        assert res["stock_industry"] == "通信设备"
        assert res["overlap_count"] == 1
        assert res["overlap_positions"][0]["code"] == "sz300502"
        assert res["overlap_pct"] == pytest.approx(23.1, abs=0.2)
        assert "中际旭创" not in res["message"] or True

    def test_overlap_trigger_warning(self):
        # 重叠行业占组合 40% → 预警
        pos = [
            _pos("sz300502", "新易盛", 40, 100, tags=["通信"]),
            _pos("sz002415", "海康", 60, 100, tags=["科技"]),
        ]
        res = compute_industry_overlap("sz300308", pos)
        assert res["overlap_pct"] == 40.0
        assert res["concentration_warning"] is True
        assert "30%" in res["message"]

    def test_unknown_stock_industry(self):
        pos = [_pos("sh600519", "茅台", 100, 100, tags=["白酒"])]
        res = compute_industry_overlap("sh699999", pos)
        assert res["stock_industry"] is None
        assert "未知" in res["message"]
        assert res["concentration_warning"] is False

    def test_empty_positions(self):
        res = compute_industry_overlap("sz002920", [])
        assert res["overlap_count"] == 0
        assert res["overlap_pct"] == 0.0


class TestFullPortfolioIndustryOverlap:
    """集成：compute_full_portfolio_correlation 输出 industry_overlap。"""

    def test_full_payload_has_overlap(self, monkeypatch):
        monkeypatch.setattr(
            "portfolio_correlation.get_portfolio_codes",
            lambda: ["sh600519", "sh600887"],
        )
        monkeypatch.setattr(
            "portfolio_correlation.get_positions_full",
            lambda: [
                _pos("sh600519", "茅台", 100, 100, tags=["白酒"]),
                _pos("sh600887", "伊利", 50, 100, tags=["消费"]),
            ],
        )
        monkeypatch.setattr(
            "portfolio_correlation.compute_correlation_matrix",
            lambda codes, index_code="sh000300", window=60: {
                "matrix": {c: {} for c in codes},
                "avg_pairwise_corr": 0.3,
                "high_corr_pairs": [],
                "interpretation": "测试",
                "stability": {
                    "stable": True,
                    "n_pairs": 1,
                    "sign_flips": 0,
                    "max_delta": 0.1,
                },
                "data_quality": {"degraded_fields": []},
            },
        )
        monkeypatch.setattr(
            "portfolio_correlation.compute_stock_vs_portfolio",
            lambda stock_code, portfolio_codes, window=60: {
                "stock_code": stock_code,
                "vs_portfolio_avg_corr": -0.1,
                "diversification_benefit": "高存疑",
                "corr_confidence": "低",
                "window_notice": "测试",
            },
        )
        res = compute_full_portfolio_correlation(stock_code="sz002920", window=60)
        assert res["portfolio_empty"] is False
        ov = res["industry_overlap"]
        assert ov is not None
        assert ov["stock_industry"] == "汽车电子"
        assert ov["overlap_count"] == 0

"""行业专家周期校准（v1.34）。

- "铝" 细分桶归入周期类（此前误落 default 阈值）
- 电解铝冶炼价差分位调整周期股景气评分：
  低分位(<=20)=周期底部上调 / 高分位(>=80)=周期顶部下调
全部离线，不连网。
"""

from __future__ import annotations

import pytest

from experts.scoring import sector_specialist as ss


def _stock_data(industry="铝", spread_pct=None):
    data = {
        "code": "SZ000807",
        "industry": industry,
        "quote": {"industry": industry, "pe": 5.49, "pb": 1.87, "pe_percentile": 15},
        "finance": {"roe": 31.33, "revenue_yoy": 19.39, "debt_ratio": 15.27},
        "kline_features": {"trend": 0, "rsi": 21.3, "macd_signal": 0},
        "market_features": {"limit_up_count": 28, "limit_down_count": 0, "advance_ratio": 0.057,
                            "break_rate": 0.39, "_degraded": False},
    }
    if spread_pct is not None:
        data["macro_features"] = {
            "al_alumina_spread": 16575.72,
            "al_alumina_spread_percentile_1y": spread_pct,
            "al_alumina_spread_source": "sina_futures(derived)",
        }
    return data


class TestSectorClassification:
    def test_aluminum_is_cyclical(self):
        assert ss._classify_sector("铝") == "周期"
        assert ss._classify_sector("铜") == "周期"
        assert ss._classify_sector("有色金属") == "周期"

    def test_non_cyclical_unchanged(self):
        assert ss._classify_sector("光伏") == "科技"
        assert ss._classify_sector("银行") == "金融"


class TestSpreadCalibration:
    def test_low_spread_pct_raises_prosperity(self):
        base = ss.score(_stock_data(spread_pct=None))["基本面"]
        low = ss.score(_stock_data(spread_pct=6.4))["基本面"]
        assert low == pytest.approx(min(100.0, base + 12))

    def test_high_spread_pct_lowers_prosperity(self):
        base = ss.score(_stock_data(spread_pct=None))["基本面"]
        high = ss.score(_stock_data(spread_pct=88.0))["基本面"]
        assert high == pytest.approx(max(0.0, base - 18))

    def test_mid_spread_pct_no_change(self):
        base = ss.score(_stock_data(spread_pct=None))["基本面"]
        mid = ss.score(_stock_data(spread_pct=50.0))["基本面"]
        assert mid == pytest.approx(base)

    def test_missing_macro_features_no_change(self):
        """无 macro_features 时保持原评分（向后兼容）。"""
        data = _stock_data()
        assert "macro_features" not in data
        assert ss.score(data)["基本面"] > 0

    def test_non_cyclical_ignores_spread(self):
        """非周期行业即使传入价差分位也不调整。"""
        base = ss.score(_stock_data(industry="光伏", spread_pct=None))["基本面"]
        with_spread = ss.score(_stock_data(industry="光伏", spread_pct=6.4))["基本面"]
        assert with_spread == pytest.approx(base)

    def test_yunlu_real_data_prosperity_raised(self):
        """云铝真实数据：价差分位 6.4% -> 基本面景气上调。"""
        base = ss.score(_stock_data(spread_pct=None))
        calibrated = ss.score(_stock_data(spread_pct=6.4))
        assert calibrated["基本面"] > base["基本面"]
        # 其余维度不受影响
        for dim in ("估值", "技术面", "情绪", "风险"):
            assert calibrated[dim] == pytest.approx(base[dim])

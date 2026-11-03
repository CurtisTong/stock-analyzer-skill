"""mine_risk 排雷数据模块的单元测试（research 排雷数据源）。

回归背景（2026-11-02 skill 审查 P0）：research 排雷清单 6 信号中
商誉/质押/应收/非经常损益在数据层命中 0 次——"排雷"无数据支撑。
本模块经 akshare 补上商誉/净资产与大股东质押两个真实数据源。
接口行为 2026-11-03 实测（stock_sy_jz_em 20241231 期 2635 行、
stock_gpzy_pledge_ratio_em 2294 行）。
"""

from __future__ import annotations

import pandas as pd
import pytest

import business.mine_risk as mine_risk


def _goodwill_df(codes_with_ratio: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"股票代码": code, "商誉": 1e9, "商誉占净资产比例": ratio, "净利润": 5e8}
            for code, ratio in codes_with_ratio.items()
        ]
    )


def _pledge_df(ratios: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"股票代码": code, "质押比例": ratio, "交易日期": "2024-09-06"} for code, ratio in ratios.items()]
    )


@pytest.fixture
def mock_ak(monkeypatch):
    """单一入口同时配置商誉/质押两个接口（两个 fetch 共用 _ak，分开 patch 会互相覆盖）。"""

    class _Config:
        goodwill_by_date: dict = {}
        pledge_df: pd.DataFrame | None = None
        pledge_raises: bool = False
        zcfz_by_date: dict = {}  # YYYYMMDD -> DataFrame | None
        zcfz_raises: bool = False

    cfg = _Config()

    class _AK:
        @staticmethod
        def stock_sy_jz_em(date="20241231"):
            return cfg.goodwill_by_date.get(date)

        @staticmethod
        def stock_gpzy_pledge_ratio_em():
            if cfg.pledge_raises:
                raise RuntimeError("接口超时")
            return cfg.pledge_df

        @staticmethod
        def stock_zcfz_em(date="20250930"):
            if cfg.zcfz_raises:
                raise RuntimeError("接口超时")
            return cfg.zcfz_by_date.get(date)

    monkeypatch.setattr(mine_risk, "_ak", lambda: _AK)
    return cfg


def _gw(codes_with_ratio: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"股票代码": code, "商誉": 1e9, "商誉占净资产比例": ratio, "净利润": 5e8}
            for code, ratio in codes_with_ratio.items()
        ]
    )


def _pl(ratios: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"股票代码": code, "质押比例": ratio, "交易日期": "2024-09-06"} for code, ratio in ratios.items()]
    )


class TestFetchGoodwill:
    def test_found_with_ratio(self, mock_ak):
        mock_ak.goodwill_by_date = {"20241231": _gw({"600989": 0.42})}
        r = mine_risk.fetch_goodwill("sh600989")
        assert r is not None
        assert r["goodwill_to_net_assets"] == pytest.approx(0.42)
        assert r["report_date"] == "2024-12-31"

    def test_code_prefix_stripped(self, mock_ak):
        mock_ak.goodwill_by_date = {"20241231": _gw({"600989": 0.1})}
        assert mine_risk.fetch_goodwill("600989") is not None

    def test_falls_back_to_older_report_period(self, mock_ak):
        """最近报告期返回空时回退上一年年报。"""
        mock_ak.goodwill_by_date = {
            "20251231": None,
            "20241231": _gw({"600989": 0.2}),
        }
        r = mine_risk.fetch_goodwill("sh600989")
        assert r is not None and r["report_date"] == "2024-12-31"

    def test_absent_stock_returns_none(self, mock_ak):
        mock_ak.goodwill_by_date = {"20241231": _gw({"600989": 0.1})}
        assert mine_risk.fetch_goodwill("sz000858") is None


class TestFetchPledge:
    def test_found_ratio(self, mock_ak):
        mock_ak.pledge_df = _pl({"600989": 75.09})
        r = mine_risk.fetch_pledge_ratio("sh600989")
        assert r["pledge_ratio_pct"] == pytest.approx(75.09)

    def test_no_record_means_zero_not_missing(self, mock_ak):
        """接口只列质押中的公司：无记录按 0 处理（排雷语义正确）。"""
        mock_ak.pledge_df = _pl({"000567": 75.0})
        r = mine_risk.fetch_pledge_ratio("sh600989")
        assert r is not None and r["pledge_ratio_pct"] == 0.0

    def test_interface_failure_returns_none(self, mock_ak):
        mock_ak.pledge_raises = True
        assert mine_risk.fetch_pledge_ratio("sh600989") is None


class TestGetMineRisk:
    def test_flags_high_goodwill_and_pledge(self, mock_ak):
        mock_ak.goodwill_by_date = {"20241231": _gw({"600989": 0.423})}
        mock_ak.pledge_df = _pl({"600989": 65.0})
        out = mine_risk.get_mine_risk("sh600989")
        assert any("商誉/净资产 42.3%" in f for f in out["flags"])
        assert any("质押比例 65.0%" in f for f in out["flags"])
        assert "goodwill" not in out["degraded"] and "pledge" not in out["degraded"]

    def test_degraded_fields_when_both_fail(self, mock_ak):
        mock_ak.goodwill_by_date = {"20241231": None}
        mock_ak.pledge_raises = True
        out = mine_risk.get_mine_risk("sh600989")
        assert set(out["degraded"]) == {"goodwill", "pledge", "receivables"}
        assert out["flags"] == []


def _zcfz(rows: dict[str, dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"股票代码": code, "资产-应收账款": ar} for code, ar in rows.items()])


class TestFetchReceivables:
    def test_yoy_computed_against_prior_year_same_quarter(self, mock_ak):
        """本期 1.5 亿 vs 去年同期 1.0 亿 → +50%。"""
        mock_ak.zcfz_by_date = {
            "20250930": _zcfz({"600989": 1.5e8}),
            "20240930": _zcfz({"600989": 1.0e8}),
        }
        r = mine_risk.fetch_receivables("sh600989")
        assert r["receivables"] == pytest.approx(1.5e8)
        assert r["receivables_yoy_pct"] == pytest.approx(50.0)
        assert r["report_date"] == "20250930"

    def test_walks_back_to_latest_available_quarter(self, mock_ak):
        """最近期全失败/空时回退上一报告期。"""
        mock_ak.zcfz_by_date = {
            "20251231": None,
            "20250930": _zcfz({"600989": 1.5e8}),
            "20240930": _zcfz({"600989": 1.0e8}),
        }
        r = mine_risk.fetch_receivables("sh600989")
        assert r["report_date"] == "20250930"

    def test_all_fail_returns_none(self, mock_ak):
        mock_ak.zcfz_raises = True
        assert mine_risk.fetch_receivables("sh600989") is None

    def test_nan_receivables_skipped(self, mock_ak):
        """应收为 NaN 的记录跳过继续回退。"""
        import numpy as np

        mock_ak.zcfz_by_date = {
            "20250930": _zcfz({"600989": np.nan}),
            "20250630": _zcfz({"600989": 1.2e8}),
            "20240630": _zcfz({"600989": 1.0e8}),
        }
        r = mine_risk.fetch_receivables("sh600989")
        assert r["report_date"] == "20250630"
        assert r["receivables_yoy_pct"] == pytest.approx(20.0)


class TestReceivablesFlag:
    def test_flag_when_ar_growth_exceeds_2x_revenue(self, mock_ak):
        mock_ak.goodwill_by_date = {"20241231": _gw({"600989": 0.1})}
        mock_ak.pledge_df = _pl({})
        mock_ak.zcfz_by_date = {
            "20250930": _zcfz({"600989": 1.5e8}),
            "20240930": _zcfz({"600989": 1.0e8}),
        }
        out = mine_risk.get_mine_risk("sh600989", revenue_yoy=20.0)
        assert any("应收增速 50.0%" in f and "2×营收增速" in f for f in out["flags"])

    def test_no_flag_without_revenue_yoy(self, mock_ak):
        """未提供营收增速时只输出应收数据，不套 2× 规则。"""
        mock_ak.goodwill_by_date = {"20241231": _gw({"600989": 0.1})}
        mock_ak.pledge_df = _pl({})
        mock_ak.zcfz_by_date = {
            "20250930": _zcfz({"600989": 1.5e8}),
            "20240930": _zcfz({"600989": 1.0e8}),
        }
        out = mine_risk.get_mine_risk("sh600989")
        assert not any("应收增速" in f for f in out["flags"])
        assert out["receivables"]["receivables_yoy_pct"] == pytest.approx(50.0)

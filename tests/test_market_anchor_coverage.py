"""market_anchor.py 覆盖测试。

补充覆盖 _interpret_northbound 全分支、_fetch_northbound_pricer 数据/降级/异常、
_fetch_sector_rotation 异常、analyze regime 异常 + 各 fetch_* 降级传播、
to_markdown 各 section 完整渲染 + 降级字段、main JSON 输出。
所有网络/数据获取均 mock。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import market_anchor as ma


# ═══════════════════════════════════════════════════════════════
# _interpret_northbound
# ═══════════════════════════════════════════════════════════════


class TestInterpretNorthbound:
    def test_continuous_inflow(self):
        s = ma._interpret_northbound(125.3, "流入", "持续流入")
        assert "持续流入" in s
        assert "125.3" in s

    def test_continuous_outflow(self):
        s = ma._interpret_northbound(-80.0, "流出", "持续流出")
        assert "持续流出" in s
        assert "80.0" in s

    def test_short_term_inflow(self):
        s = ma._interpret_northbound(50.0, "流入", "震荡")
        assert "短期回流" in s

    def test_short_term_outflow(self):
        s = ma._interpret_northbound(-50.0, "流出", "震荡")
        assert "短期流出" in s

    def test_oscillation(self):
        s = ma._interpret_northbound(5.0, "持平", "震荡")
        assert "震荡" in s
        assert "方向不明" in s


# ═══════════════════════════════════════════════════════════════
# _fetch_northbound_pricer
# ═══════════════════════════════════════════════════════════════


class TestFetchNorthboundPricer:
    def test_empty_flow_data(self):
        with patch("market_anchor.get_northbound_flow", return_value=[]):
            result = ma._fetch_northbound_pricer(days=20)
        assert result["total_net_yi"] is None
        assert "northbound.flow_data" in result["data_quality"]["degraded_fields"]

    def test_with_data_continuous_inflow(self):
        flow_data = [
            {"net_buy": 500000, "sh_net": 300000, "sz_net": 200000}
        ] * 20  # 20 天，每天 50 亿
        with patch("market_anchor.get_northbound_flow", return_value=flow_data):
            result = ma._fetch_northbound_pricer(days=20)
        assert result["total_net_yi"] == 1000.0
        assert result["direction"] == "持续流入"
        assert result["recent_5d_slope"] == "流入"

    def test_with_data_continuous_outflow(self):
        flow_data = [
            {"net_buy": -500000, "sh_net": -300000, "sz_net": -200000}
        ] * 20
        with patch("market_anchor.get_northbound_flow", return_value=flow_data):
            result = ma._fetch_northbound_pricer(days=20)
        assert result["total_net_yi"] == -1000.0
        assert result["direction"] == "持续流出"

    def test_with_data_flat(self):
        flow_data = [
            {"net_buy": 50000, "sh_net": 30000, "sz_net": 20000}
        ] * 20  # 每天 5 亿，近 5 日 25 亿 > 10 -> 流入；但 total > 0 + 流入 = 持续流入
        # 改为小量让它持平
        flow_data = [
            {"net_buy": 10000, "sh_net": 5000, "sz_net": 5000}
        ] * 20  # 每天 1 亿，近 5 日 5 亿 < 10 -> 持平
        with patch("market_anchor.get_northbound_flow", return_value=flow_data):
            result = ma._fetch_northbound_pricer(days=20)
        assert result["recent_5d_slope"] == "持平"

    def test_insufficient_days(self):
        flow_data = [{"net_buy": 500000, "sh_net": 300000, "sz_net": 200000}] * 10
        with patch("market_anchor.get_northbound_flow", return_value=flow_data):
            result = ma._fetch_northbound_pricer(days=20)
        assert any("insufficient_days" in d for d in result["data_quality"]["degraded_fields"])

    def test_exception_returns_degraded(self):
        with patch("market_anchor.get_northbound_flow", side_effect=RuntimeError("err")):
            result = ma._fetch_northbound_pricer(days=20)
        assert result["total_net_yi"] is None
        assert "northbound_pricer" in result["data_quality"]["degraded_fields"]


# ═══════════════════════════════════════════════════════════════
# _fetch_sector_rotation
# ═══════════════════════════════════════════════════════════════


class TestFetchSectorRotation:
    def test_exception_returns_degraded(self):
        with patch("market_anchor.sector_etf_strength.compute_rotation_strength", side_effect=RuntimeError("err")):
            result = ma._fetch_sector_rotation(window=5)
        assert "sector_rotation" in result["data_quality"]["degraded_fields"]

    def test_success(self):
        mock_result = {"rotation_strength": 3.5, "window": 5}
        with patch("market_anchor.sector_etf_strength.compute_rotation_strength", return_value=mock_result):
            result = ma._fetch_sector_rotation(window=5)
        assert result["rotation_strength"] == 3.5


# ═══════════════════════════════════════════════════════════════
# analyze 降级传播
# ═══════════════════════════════════════════════════════════════


class TestAnalyzeDegradation:
    def _mock_all_fetches(self, monkeypatch):
        monkeypatch.setattr(ma, "_fetch_index_snapshot", lambda *a, **kw: {"change_pct": 1.5})
        monkeypatch.setattr(ma, "_fetch_index_kline", lambda *a, **kw: {"closes": [100]})
        monkeypatch.setattr(ma, "_fetch_breadth", lambda *a, **kw: {"up_count": 2000, "down_count": 1000})
        monkeypatch.setattr(ma, "_compute_multi_timeframe", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "_fetch_macro_anchor", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "_fetch_liquidity_volatility", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "_fetch_emotion_phase", lambda *a, **kw: "震荡")

    def test_regime_exception(self, monkeypatch):
        self._mock_all_fetches(monkeypatch)

        def _raise(**kw):
            raise RuntimeError("err")

        monkeypatch.setattr(ma, "detect_market_state", _raise)
        monkeypatch.setattr(ma, "sector_etf_strength", MagicMock(analyze=MagicMock(return_value=None)))
        result = ma.analyze()
        assert result["regime"] == "defensive"
        assert "regime" in result["data_quality"]["degraded_fields"]

    def test_all_fetch_disabled(self, monkeypatch):
        self._mock_all_fetches(monkeypatch)
        monkeypatch.setattr(ma, "detect_market_state", lambda **kw: {"state": "牛市", "long_weight": 0.8, "short_weight": 0.2, "reason": "up"})
        result = ma.analyze(fetch_sector=False, fetch_portfolio=False, fetch_rotation=False, fetch_northbound=False)
        assert result["sector_strength"] is None
        assert result["portfolio_correlation"] is None
        assert result["sector_rotation"] is None
        assert result["northbound_pricer"] is None
        assert result["regime"] == "bull"

    def test_sector_exception(self, monkeypatch):
        self._mock_all_fetches(monkeypatch)
        monkeypatch.setattr(ma, "detect_market_state", lambda **kw: {"state": "牛市", "long_weight": 0.8, "short_weight": 0.2, "reason": "up"})
        mock_sector = MagicMock()
        mock_sector.analyze.side_effect = RuntimeError("err")
        monkeypatch.setattr(ma, "sector_etf_strength", mock_sector)
        result = ma.analyze(fetch_portfolio=False, fetch_rotation=False, fetch_northbound=False)
        assert "sector" in result["data_quality"]["degraded_fields"]

    def test_multi_timeframe_degraded(self, monkeypatch):
        self._mock_all_fetches(monkeypatch)
        monkeypatch.setattr(ma, "detect_market_state", lambda **kw: {"state": "牛市", "long_weight": 0.8, "short_weight": 0.2, "reason": "up"})
        monkeypatch.setattr(ma, "_compute_multi_timeframe", lambda *a, **kw: {"data_quality": {"degraded_fields": ["mtf.ma250"]}})
        monkeypatch.setattr(ma, "sector_etf_strength", MagicMock(analyze=MagicMock(return_value=None)))
        result = ma.analyze(fetch_portfolio=False, fetch_rotation=False, fetch_northbound=False)
        assert "mtf.ma250" in result["data_quality"]["degraded_fields"]

    def test_emotion_phase_none(self, monkeypatch):
        self._mock_all_fetches(monkeypatch)
        monkeypatch.setattr(ma, "detect_market_state", lambda **kw: {"state": "牛市", "long_weight": 0.8, "short_weight": 0.2, "reason": "up"})
        monkeypatch.setattr(ma, "_fetch_emotion_phase", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "sector_etf_strength", MagicMock(analyze=MagicMock(return_value=None)))
        result = ma.analyze(fetch_portfolio=False, fetch_rotation=False, fetch_northbound=False)
        assert "emotion_phase" in result["data_quality"]["degraded_fields"]

    def test_with_stock_code(self, monkeypatch):
        self._mock_all_fetches(monkeypatch)
        monkeypatch.setattr(ma, "detect_market_state", lambda **kw: {"state": "牛市", "long_weight": 0.8, "short_weight": 0.2, "reason": "up"})
        monkeypatch.setattr(ma, "sector_etf_strength", MagicMock(analyze=MagicMock(return_value=None)))
        monkeypatch.setattr(ma, "_fetch_industry_beta", lambda *a, **kw: {"beta": 1.2, "data_quality": {"degraded_fields": []}})
        monkeypatch.setattr(ma, "_fetch_portfolio_correlation", lambda *a, **kw: None)
        result = ma.analyze(stock_code="sh600519", fetch_rotation=False, fetch_northbound=False)
        assert result["industry_beta"] is not None
        assert result["industry_beta"]["beta"] == 1.2


# ═══════════════════════════════════════════════════════════════
# to_markdown 完整 section 渲染
# ═══════════════════════════════════════════════════════════════


def _full_payload():
    return {
        "as_of": "2025-01-10T15:00:00",
        "regime": "bull",
        "regime_label_zh": "牛市",
        "regime_confidence": "high",
        "regime_reason": "趋势向上",
        "long_weight": 0.8,
        "short_weight": 0.2,
        "index_code": "sh000300",
        "index_change_pct": 1.5,
        "breadth": {"up_count": 2500, "down_count": 1500, "limit_up_count": 50, "limit_down_count": 5},
        "sector_strength": {
            "etfs": [
                {"code": "sh512010", "name": "医药ETF", "change_pct": 3.2},
                {"code": "sh512070", "name": "医药ETF2", "change_pct": None},
            ],
            "top": ["sh512010", "sh512070"],
            "bottom": [],
            "data_quality": None,
        },
        "stock_sector_compare": {
            "stock_code": "sh600519",
            "stock_sectors": ["白酒"],
            "matched_etf": "sh512690",
            "matched_etf_name": "酒ETF",
            "stock_change_pct": 2.5,
            "sector_change_pct": 1.8,
            "index_change_pct": 1.5,
            "rps_vs_sector": 0.7,
            "rps_vs_index": 1.0,
            "verdict": "跑赢板块",
            "data_quality": {"degraded_fields": ["sector.delayed"]},
        },
        "multi_timeframe": {
            "ma20": 4000, "ma60": 3900, "ma250": 3800,
            "ma_alignment": "多头排列", "ret_5d_pct": 2.5, "ret_20d_pct": 8.0,
            "atr_14": 50.5, "vs_ma250_pct": 5.2,
        },
        "macro": {
            "treasury_10y_pct": 4.2, "usd_index": 104.5, "usd_cny": 7.25,
            "vix": 15.3, "gold_usd_oz": 2000, "brent_oil_usd": 80, "lithium_carbonate_cny_t": 90000,
        },
        "leverage": {
            "margin_balance_total_yi": 16000, "margin_change_5d_pct": 2.5,
            "if_main_basis_pts": 10, "ic_main_basis_pts": -5, "ih_main_basis_pts": None,
        },
        "valuation_bridge": {"erp_sh300_pct": 5.5},
        "liquidity_volatility": {
            "sh300_atr_14": 50.5, "sh300_annualized_vol_pct": 18.2,
            "stock_avg_amount_20d_yi": 5.0, "stock_liquidity_ratio_pct": 1.2,
        },
        "emotion_phase": "主升",
        "industry_beta": {
            "beta": 1.15, "interpretation": "高弹性", "alpha_annual": 0.05,
            "r_squared": 0.65, "volatility_pct": 25.3, "window": 60,
            "n_observations": 60, "index_selection": "csi300", "stock_code": "sh600519", "index_code": "sh000300",
        },
        "portfolio_correlation": {
            "portfolio_empty": False, "portfolio_codes": ["sh600519", "sz000858", "sh600001", "sh600002"],
            "avg_pairwise_corr": 0.45, "high_corr_pairs": [["sh600519", "sz000858", 0.75]],
            "interpretation": "分散度尚可", "vs_portfolio": {"vs_portfolio_avg_corr": 0.5, "diversification_benefit": "中等"},
        },
        "sector_rotation": {
            "window": 5, "rotation_strength": 4.2, "rotation_std": 2.1,
            "biggest_risers": [["sh512010", "医药ETF", 3]],
            "biggest_fallers": [["sh512070", "地产ETF", 2]],
            "interpretation": "轮动剧烈",
        },
        "northbound_pricer": {
            "days": 20, "total_net_yi": 125.3, "total_net_sh_yi": 80.5, "total_net_sz_yi": 44.8,
            "latest_day_net_yi": 15.2, "recent_5d_net_yi": 45.6, "recent_5d_slope": "流入",
            "direction": "持续流入", "interpretation": "看多",
        },
        "data_quality": {"degraded_fields": ["breadth.delayed"]},
    }


class TestToMarkdownFull:
    def test_full_payload_all_sections(self):
        payload = _full_payload()
        md = ma.to_markdown(payload)
        assert "市场环境锚定" in md
        assert "牛市" in md
        assert "大盘指数" in md
        assert "市场宽度" in md
        assert "强势板块" in md
        assert "医药ETF" in md
        assert "个股 vs 板块" in md
        assert "白酒" in md
        assert "跑赢板块" in md
        assert "多时间框架" in md
        assert "多头排列" in md
        assert "宏观-估值桥" in md
        assert "10Y 美债" in md
        assert "两市两融余额" in md
        assert "IF 基差" in md
        assert "沪深 300 ERP" in md
        assert "流动性" in md
        assert "情绪周期" in md
        assert "主升" in md
        assert "行业 beta" in md
        assert "组合相关性" in md
        assert "持仓数" in md
        assert "题材轮动" in md
        assert "位次上升" in md
        assert "北向资金" in md
        assert "持续流入" in md
        assert "数据降级" in md

    def test_no_index_change(self):
        payload = _full_payload()
        payload["index_change_pct"] = None
        md = ma.to_markdown(payload)
        assert "数据缺失" in md

    def test_no_breadth(self):
        payload = _full_payload()
        payload["breadth"] = None
        md = ma.to_markdown(payload)
        assert "市场宽度" in md

    def test_portfolio_empty(self):
        payload = _full_payload()
        payload["portfolio_correlation"] = {"portfolio_empty": True, "interpretation": "无持仓"}
        md = ma.to_markdown(payload)
        assert "无持仓" in md

    def test_portfolio_many_codes(self):
        payload = _full_payload()
        payload["portfolio_correlation"]["portfolio_codes"] = ["c1", "c2", "c3", "c4", "c5"]
        md = ma.to_markdown(payload)
        assert "..." in md

    def test_no_degraded_fields(self):
        payload = _full_payload()
        payload["data_quality"]["degraded_fields"] = []
        md = ma.to_markdown(payload)
        assert "数据降级" not in md

    def test_sector_compare_degraded(self):
        payload = _full_payload()
        md = ma.to_markdown(payload)
        assert "降级字段" in md

    def test_empty_etf_change_pct_skipped(self):
        payload = _full_payload()
        # bottom 为空时不渲染弱势板块
        md = ma.to_markdown(payload)
        assert "弱势板块" not in md


# ═══════════════════════════════════════════════════════════════
# main() JSON 输出
# ═══════════════════════════════════════════════════════════════


class TestMainJson:
    def test_json_output(self, monkeypatch, capsys):
        payload = _full_payload()
        monkeypatch.setattr(ma, "analyze", lambda **kw: payload)
        monkeypatch.setattr(sys, "argv", ["market_anchor.py", "sh600519", "-j"])
        ma.main()
        out = capsys.readouterr().out
        assert '"regime"' in out
        assert '"bull"' in out

    def test_markdown_output(self, monkeypatch, capsys):
        payload = _full_payload()
        monkeypatch.setattr(ma, "analyze", lambda **kw: payload)
        monkeypatch.setattr(sys, "argv", ["market_anchor.py", "sh600519"])
        ma.main()
        out = capsys.readouterr().out
        assert "市场环境锚定" in out

    def test_no_args(self, monkeypatch, capsys):
        payload = _full_payload()
        monkeypatch.setattr(ma, "analyze", lambda **kw: payload)
        monkeypatch.setattr(sys, "argv", ["market_anchor.py"])
        ma.main()
        out = capsys.readouterr().out
        assert "市场环境锚定" in out

"""monitor/briefing.py 覆盖测试。

mock get_quote / get_northbound_flow / PortfolioManager / compute_key_levels，
覆盖 compute_briefing 各分支：市场/隔夜/北向/持仓/预警。
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import monitor.briefing as briefing_mod


class _FakeQuote:
    """模拟 Quote 对象。"""

    def __init__(self, price, change_pct):
        self.price = price
        self.change_pct = change_pct


@pytest.fixture
def mock_pm():
    """mock PortfolioManager，返回空持仓。"""
    pm = MagicMock()
    pm.get_positions.return_value = []
    return pm


class TestComputeBriefingBasic:
    def test_empty_portfolio(self, mock_pm):
        """空持仓时应返回完整结构（各字段都有）。"""
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert "timestamp" in result
        assert result["portfolio"]["count"] == 0
        assert result["portfolio"]["total_pnl"] == 0
        assert result["positions_count"] == 0
        assert result["alerts"] == []

    def test_market_lines_built(self, mock_pm):
        """市场指数行情应生成 market_lines。"""

        def _fake_quote(code):
            if code == "sh000001":
                return _FakeQuote(3200.0, 1.5)
            return None

        with (
            patch("data.get_quote", side_effect=_fake_quote),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert any("上证指数" in line for line in result["market_lines"])
        assert "sh000001" in result["market"]

    def test_market_get_quote_exception(self, mock_pm):
        """get_quote 异常时 market_lines 含失败提示。"""

        def _fake_quote(code):
            if code == "sh000001":
                raise RuntimeError("net error")
            return None

        with (
            patch("data.get_quote", side_effect=_fake_quote),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert any("获取失败" in line for line in result["market_lines"])


class TestOvernight:
    def test_overnight_indices(self, mock_pm):
        """隔夜美股指数应生成 overnight_lines。"""

        def _fake_quote(code):
            if code == "us:^gspc":
                return _FakeQuote(5000.0, 0.8)
            if code == "us:^vix":
                return _FakeQuote(15.0, -2.0)
            return None

        with (
            patch("data.get_quote", side_effect=_fake_quote),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert any("标普500" in line for line in result["overnight_lines"])
        assert "us:^gspc" in result["overnight"]
        # VIX 涨为恐慌
        assert any("VIX" in line for line in result["overnight_lines"])

    def test_overnight_vix_up_is_fear(self, mock_pm):
        """VIX 上涨显示为 🔴（恐慌）。"""

        def _fake_quote(code):
            if code == "us:^vix":
                return _FakeQuote(20.0, 5.0)
            return None

        with (
            patch("data.get_quote", side_effect=_fake_quote),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert any("🔴" in line and "VIX" in line for line in result["overnight_lines"])


class TestNorthbound:
    def test_northbound_positive(self, mock_pm):
        """北向资金净买入为正。"""
        nb_data = [{"net_buy": 1e8, "sh_net": 5e7, "sz_net": 5e7} for _ in range(5)]
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=nb_data),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert any("最新北向" in line for line in result["northbound_lines"])
        assert result["northbound"]["net_buy"] == 1e8

    def test_northbound_negative(self, mock_pm):
        """北向资金净卖出为负。"""
        nb_data = [{"net_buy": -1e8, "sh_net": -5e7, "sz_net": -5e7} for _ in range(5)]
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=nb_data),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert any("🔴" in line for line in result["northbound_lines"])

    def test_northbound_empty(self, mock_pm):
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert result["northbound"] == {}

    def test_northbound_exception(self, mock_pm):
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", side_effect=RuntimeError("net")),
            patch("portfolio.PortfolioManager", return_value=mock_pm),
        ):
            result = briefing_mod.compute_briefing()
        assert result["northbound"] == {}


class TestPortfolioSummary:
    def test_positions_with_valid_data(self):
        """有效持仓应生成 pos_lines 和 portfolio 汇总。"""
        pm = MagicMock()
        pm.get_positions.return_value = [
            {"code": "sh600519", "name": "茅台", "cost": 100, "quantity": 100},
        ]
        with (
            patch(
                "data.get_quote",
                side_effect=lambda c: _FakeQuote(120, 2.0) if c == "sh600519" else None,
            ),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=pm),
        ):
            result = briefing_mod.compute_briefing()
        assert len(result["pos_lines"]) == 1
        assert "茅台" in result["pos_lines"][0]
        assert result["portfolio"]["count"] == 1
        assert result["portfolio"]["total_value"] > 0
        assert result["positions_count"] == 1

    def test_positions_invalid_skipped(self):
        """无效持仓（code 空/cost<=0/qty<=0）被跳过。"""
        pm = MagicMock()
        pm.get_positions.return_value = [
            {"code": "", "name": "X", "cost": 100, "quantity": 100},
            {"code": "sh600519", "name": "A", "cost": 0, "quantity": 100},
            {"code": "sh600001", "name": "B", "cost": 100, "quantity": 0},
        ]
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=pm),
        ):
            result = briefing_mod.compute_briefing()
        assert result["pos_lines"] == []
        assert result["positions_count"] == 0

    def test_position_get_quote_exception(self):
        """持仓 get_quote 异常时 price=0，仍计入 pos_lines。"""
        pm = MagicMock()
        pm.get_positions.return_value = [
            {"code": "sh600519", "name": "茅台", "cost": 100, "quantity": 100},
        ]
        with (
            patch("data.get_quote", side_effect=RuntimeError("net")),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=pm),
        ):
            result = briefing_mod.compute_briefing()
        assert len(result["pos_lines"]) == 1
        assert result["portfolio"]["total_value"] == 0


class TestAlerts:
    def test_alerts_built_from_key_levels(self):
        """compute_key_levels 返回 alerts 时生成 alert_lines。"""
        pm = MagicMock()
        pm.get_positions.return_value = [
            {"code": "sh600519", "name": "茅台", "cost": 100, "quantity": 100},
        ]
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=pm),
            patch(
                "monitor.briefing.compute_key_levels",
                return_value={"alerts": [{"message": "突破前高"}]},
            ),
        ):
            result = briefing_mod.compute_briefing()
        assert len(result["alerts"]) == 1
        assert "茅台" in result["alerts"][0]

    def test_alerts_exception_skipped(self):
        """compute_key_levels 异常时不生成 alert。"""
        pm = MagicMock()
        pm.get_positions.return_value = [
            {"code": "sh600519", "name": "茅台", "cost": 100, "quantity": 100},
        ]
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=pm),
            patch(
                "monitor.briefing.compute_key_levels", side_effect=RuntimeError("err")
            ),
        ):
            result = briefing_mod.compute_briefing()
        assert result["alerts"] == []

    def test_empty_code_skipped_in_alerts(self):
        """code 为空的持仓不参与 alert 计算。"""
        pm = MagicMock()
        pm.get_positions.return_value = [
            {"code": "", "name": "X", "cost": 100, "quantity": 100},
        ]
        with (
            patch("data.get_quote", return_value=None),
            patch("data.get_northbound_flow", return_value=[]),
            patch("portfolio.PortfolioManager", return_value=pm),
            patch(
                "monitor.briefing.compute_key_levels",
                return_value={"alerts": [{"message": "x"}]},
            ),
        ):
            result = briefing_mod.compute_briefing()
        assert result["alerts"] == []

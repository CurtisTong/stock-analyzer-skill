"""monitor 模块测试补充（T25）。

覆盖 rules.py（预警规则引擎）和 briefing.py（盘前简报计算）。
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestBriefingCompute:
    """briefing.py compute_briefing 结构化数据。"""

    @patch("portfolio.PortfolioManager")
    @patch("data.get_northbound_flow")
    @patch("data.get_quote")
    @patch("monitor.briefing.compute_key_levels")
    def test_briefing_returns_required_keys(
        self, mock_levels, mock_quote, mock_nb, mock_pm
    ):
        """compute_briefing 返回所有必需字段。"""
        from monitor.briefing import compute_briefing

        mock_quote.return_value = MagicMock(price=3500.0, change_pct=0.5)
        mock_pm.return_value.get_positions.return_value = []
        mock_nb.return_value = []
        mock_levels.return_value = {"alerts": []}

        result = compute_briefing()
        assert "timestamp" in result
        assert "market" in result
        assert "overnight" in result
        assert "northbound" in result
        assert "portfolio" in result
        assert "alerts" in result
        assert "market_lines" in result
        assert "overnight_lines" in result
        assert "northbound_lines" in result
        assert "pos_lines" in result
        assert "positions_count" in result

    @patch("portfolio.PortfolioManager")
    @patch("data.get_northbound_flow")
    @patch("data.get_quote")
    @patch("monitor.briefing.compute_key_levels")
    def test_briefing_market_lines(self, mock_levels, mock_quote, mock_nb, mock_pm):
        """三大指数行情正确渲染。"""
        from monitor.briefing import compute_briefing

        mock_quote.return_value = MagicMock(price=3500.0, change_pct=0.5)
        mock_pm.return_value.get_positions.return_value = []
        mock_nb.return_value = []
        mock_levels.return_value = {"alerts": []}

        result = compute_briefing()
        assert len(result["market_lines"]) == 3
        assert any("上证指数" in line for line in result["market_lines"])

    @patch("portfolio.PortfolioManager")
    @patch("data.get_northbound_flow")
    @patch("data.get_quote")
    @patch("monitor.briefing.compute_key_levels")
    def test_briefing_northbound_data(self, mock_levels, mock_quote, mock_nb, mock_pm):
        """北向资金数据正确聚合。"""
        from monitor.briefing import compute_briefing

        mock_quote.return_value = MagicMock(price=3500.0, change_pct=0.5)
        mock_pm.return_value.get_positions.return_value = []
        mock_nb.return_value = [
            {
                "date": "2026-07-01",
                "net_buy": 500000000,
                "sh_net": 300000000,
                "sz_net": 200000000,
            },
        ]
        mock_levels.return_value = {"alerts": []}

        result = compute_briefing()
        assert result["northbound"]["net_buy"] == 500000000
        assert len(result["northbound_lines"]) >= 1


class TestRenderBriefing:
    """alert_engine.render_briefing 文本渲染。"""

    def test_render_basic_structure(self):
        """渲染包含各段落标题。"""
        from monitor.alert_engine import render_briefing

        data = {
            "timestamp": "2026-07-09 09:15",
            "market_lines": ["🟢 上证指数: 3500.00 (+0.50%)"],
            "overnight_lines": ["🟢 标普500: 5500.00 (+0.30%)"],
            "northbound_lines": ["🟢 最新北向: +50.0 亿"],
            "pos_lines": [],
            "alerts": [],
            "positions_count": 0,
            "portfolio": {"total_pnl": 0, "total_pnl_pct": 0},
        }
        text = render_briefing(data)
        assert "盘前简报" in text
        assert "市场状态" in text
        assert "隔夜外盘" in text
        assert "北向资金" in text
        assert "持仓概要" in text

    def test_render_no_overnight_skips_section(self):
        """无隔夜外盘数据时不渲染该段。"""
        from monitor.alert_engine import render_briefing

        data = {
            "timestamp": "2026-07-09 09:15",
            "market_lines": ["🟢 上证指数: 3500.00"],
            "overnight_lines": [],
            "northbound_lines": [],
            "pos_lines": [],
            "alerts": [],
            "positions_count": 0,
            "portfolio": {"total_pnl": 0, "total_pnl_pct": 0},
        }
        text = render_briefing(data)
        assert "隔夜外盘" not in text
        assert "北向资金" not in text


class TestVolatilityATR:
    """technical/volatility.py ATR 计算（I9）。"""

    def test_atr_basic(self):
        from technical.volatility import compute_atr

        highs = [10, 11, 12, 11, 10, 13, 14, 12, 11, 10, 12, 13, 11, 10, 12]
        lows = [8, 9, 10, 9, 8, 11, 12, 10, 9, 8, 10, 11, 9, 8, 10]
        closes = [9, 10, 11, 10, 9, 12, 13, 11, 10, 9, 11, 12, 10, 9, 11]
        atr = compute_atr(highs, lows, closes, period=5)
        assert atr > 0

    def test_atr_insufficient_data(self):
        from technical.volatility import compute_atr

        assert compute_atr([10], [8], [9]) == 0
        assert compute_atr([], [], []) == 0

    def test_atr_tolerance_fallback(self):
        """无 highs/lows 时回退到收盘价 2%。"""
        from technical.volatility import atr_tolerance

        tol = atr_tolerance([10, 11, 12, 13, 14], k=0.5)
        assert tol == 14 * 0.02

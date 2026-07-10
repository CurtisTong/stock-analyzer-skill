"""monitor/alert_engine.py 补充测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestRenderScan:
    """render_scan 扫描结果渲染。"""

    def test_empty_results(self):
        from monitor.alert_engine import render_scan
        result = render_scan([])
        assert isinstance(result, str)

    def test_with_results(self):
        from monitor.alert_engine import render_scan
        results = [
            {"code": "sh600519", "name": "茅台", "price": 1800,
             "alerts": [{"message": "突破MA20"}]},
        ]
        result = render_scan(results)
        assert isinstance(result, str)
        assert "茅台" in result or "sh600519" in result


class TestRenderLevels:
    """render_levels 关键点位渲染。"""

    def test_renders_without_error(self):
        from monitor.alert_engine import render_levels
        with patch("monitor.alert_engine._get_pm"), \
             patch("monitor.levels.compute_key_levels", return_value={
                 "code": "sh600519", "name": "茅台", "price": 1800,
                 "levels": {"supports": [1700], "resistances": [1900]},
                 "alerts": [],
             }):
            result = render_levels("sh600519")
            assert isinstance(result, str)


class TestDailyBriefing:
    """daily_briefing 盘前简报。"""

    def test_returns_dict_with_summary(self):
        from monitor.alert_engine import daily_briefing
        with patch("monitor.alert_engine.compute_briefing", return_value={
            "timestamp": "2026-01-01 09:00",
            "market_lines": [], "overnight_lines": [], "northbound_lines": [],
            "pos_lines": [], "alerts": [], "positions_count": 0,
            "portfolio": {"total_pnl": 0, "total_pnl_pct": 0},
        }):
            result = daily_briefing()
            assert "summary" in result
            assert "timestamp" in result

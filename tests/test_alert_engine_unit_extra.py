"""monitor/alert_engine.py 补充测试：main() CLI 入口 + render_scan 更多分支。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from monitor import alert_engine


# ═══════════════════════════════════════════════════════════════
# render_scan - 更多分支
# ═══════════════════════════════════════════════════════════════


class TestRenderScanBranches:
    def test_flat_change_neutral_icon(self):
        """change_pct == 0 -> ⚪ 图标。"""
        results = [{"code": "sh600000", "name": "测试", "price": 10, "change_pct": 0}]
        out = alert_engine.render_scan(results)
        assert "⚪" in out

    def test_positive_change_green_icon(self):
        results = [{"code": "sh600000", "name": "测试", "price": 10, "change_pct": 1.5}]
        out = alert_engine.render_scan(results)
        assert "🟢" in out

    def test_negative_change_red_icon(self):
        results = [{"code": "sh600000", "name": "测试", "price": 10, "change_pct": -1.5}]
        out = alert_engine.render_scan(results)
        assert "🔴" in out

    def test_with_supports(self):
        results = [
            {
                "code": "sh600000",
                "name": "测试",
                "price": 10,
                "change_pct": 1,
                "levels": {"supports": [{"level": 9.5, "source": "前低"}]},
            }
        ]
        out = alert_engine.render_scan(results)
        assert "支撑" in out

    def test_with_resistances(self):
        results = [
            {
                "code": "sh600000",
                "name": "测试",
                "price": 10,
                "change_pct": 1,
                "levels": {"resistances": [{"level": 11, "source": "前高"}]},
            }
        ]
        out = alert_engine.render_scan(results)
        assert "压力" in out

    def test_with_ma_values(self):
        results = [
            {
                "code": "sh600000",
                "name": "测试",
                "price": 10,
                "change_pct": 1,
                "levels": {"ma_values": {"ma5": 9.8, "ma20": 9.5}},
            }
        ]
        out = alert_engine.render_scan(results)
        assert "均线" in out

    def test_with_macd_info(self):
        results = [
            {
                "code": "sh600000",
                "name": "测试",
                "price": 10,
                "change_pct": 1,
                "levels": {
                    "macd": {"dif": 0.1, "dea": 0.05, "bar_trend": "放大"},
                    "macd_signal": "金叉",
                },
            }
        ]
        out = alert_engine.render_scan(results)
        assert "MACD" in out

    def test_with_target_buy_sell(self):
        results = [
            {
                "code": "sh600000",
                "name": "测试",
                "price": 10,
                "change_pct": 1,
                "levels": {"target_buy": 9, "target_sell": 8},
            }
        ]
        out = alert_engine.render_scan(results)
        assert "目标买入" in out
        assert "目标卖出" in out

    def test_with_urgent_alert(self):
        results = [
            {
                "code": "sh600000",
                "name": "测试",
                "price": 10,
                "change_pct": 1,
                "alerts": [{"urgent": True, "message": "止损预警"}],
            }
        ]
        out = alert_engine.render_scan(results)
        assert "🔴" in out
        assert "止损预警" in out

    def test_with_non_urgent_alert(self):
        results = [
            {
                "code": "sh600000",
                "name": "测试",
                "price": 10,
                "change_pct": 1,
                "alerts": [{"urgent": False, "message": "MACD金叉"}],
            }
        ]
        out = alert_engine.render_scan(results)
        assert "🟡" in out

    def test_multiple_results(self):
        results = [
            {"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1},
            {"code": "sh600001", "name": "乙", "price": 20, "change_pct": -2},
            {"code": "sh600002", "name": "丙", "price": 30, "change_pct": 0},
        ]
        out = alert_engine.render_scan(results)
        assert "扫描标的: 3 只" in out

    def test_result_missing_name_uses_code(self):
        results = [{"code": "sh600000", "price": 10, "change_pct": 1}]
        out = alert_engine.render_scan(results)
        assert "sh600000" in out


# ═══════════════════════════════════════════════════════════════
# render_briefing
# ═══════════════════════════════════════════════════════════════


class TestRenderBriefing:
    def test_minimal_data(self):
        data = {
            "timestamp": "2024-01-01 09:00",
            "market_lines": ["上证 3000"],
            "overnight_lines": [],
            "northbound_lines": [],
            "pos_lines": [],
            "alerts": [],
            "positions_count": 0,
            "portfolio": {"total_pnl": 0, "total_pnl_pct": 0},
        }
        out = alert_engine.render_briefing(data)
        assert "盘前简报" in out
        assert "暂无持仓" in out

    def test_with_overnight_and_northbound(self):
        data = {
            "timestamp": "2024-01-01 09:00",
            "market_lines": ["上证 3000"],
            "overnight_lines": ["道指 +1%"],
            "northbound_lines": ["北向 +50亿"],
            "pos_lines": ["sh600000 盈利"],
            "alerts": ["止损预警"],
            "positions_count": 1,
            "portfolio": {"total_pnl": 1000, "total_pnl_pct": 5},
        }
        out = alert_engine.render_briefing(data)
        assert "隔夜外盘" in out
        assert "北向资金" in out
        assert "关键预警" in out

    def test_loss_warning(self):
        data = {
            "timestamp": "2024-01-01 09:00",
            "market_lines": [],
            "overnight_lines": [],
            "northbound_lines": [],
            "pos_lines": ["持仓亏损"],
            "alerts": [],
            "positions_count": 1,
            "portfolio": {"total_pnl": -1000, "total_pnl_pct": -8},
        }
        out = alert_engine.render_briefing(data)
        assert "浮亏较大" in out

    def test_profit_warning(self):
        data = {
            "timestamp": "2024-01-01 09:00",
            "market_lines": [],
            "overnight_lines": [],
            "northbound_lines": [],
            "pos_lines": ["持仓盈利"],
            "alerts": [],
            "positions_count": 1,
            "portfolio": {"total_pnl": 1000, "total_pnl_pct": 15},
        }
        out = alert_engine.render_briefing(data)
        assert "浮盈良好" in out

    def test_normal_portfolio(self):
        data = {
            "timestamp": "2024-01-01 09:00",
            "market_lines": [],
            "overnight_lines": [],
            "northbound_lines": [],
            "pos_lines": ["持仓正常"],
            "alerts": [],
            "positions_count": 1,
            "portfolio": {"total_pnl": 100, "total_pnl_pct": 3},
        }
        out = alert_engine.render_briefing(data)
        assert "状态正常" in out


# ═══════════════════════════════════════════════════════════════
# main() CLI 入口
# ═══════════════════════════════════════════════════════════════


class TestMainCLI:
    def test_no_args_prints_usage_and_exits(self, capsys):
        with patch.object(sys, "argv", ["alert_engine.py"]):
            try:
                alert_engine.main()
                assert False, "应 SystemExit"
            except SystemExit:
                pass
        out = capsys.readouterr().out
        assert "用法" in out

    def test_scan_command_json(self, capsys):
        mock_results = [{"code": "sh600000", "name": "测试", "price": 10, "change_pct": 1}]
        with patch.object(sys, "argv", ["alert_engine.py", "scan", "--json"]):
            with patch("monitor.alert_engine.scan_all", return_value=mock_results):
                alert_engine.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed[0]["code"] == "sh600000"

    def test_scan_command_text(self, capsys):
        mock_results = [{"code": "sh600000", "name": "测试", "price": 10, "change_pct": 1}]
        with patch.object(sys, "argv", ["alert_engine.py", "scan"]):
            with patch("monitor.alert_engine.scan_all", return_value=mock_results):
                alert_engine.main()
        out = capsys.readouterr().out
        assert "关键点位扫描" in out

    def test_levels_command(self, capsys):
        {"code": "sh600000", "name": "测试", "price": 10, "change_pct": 1}
        with patch.object(sys, "argv", ["alert_engine.py", "levels", "600000"]):
            with patch("monitor.alert_engine.render_levels", return_value="点位文本"):
                alert_engine.main()
        out = capsys.readouterr().out
        assert "点位文本" in out

    def test_levels_no_code_exits(self, capsys):
        with patch.object(sys, "argv", ["alert_engine.py", "levels"]):
            try:
                alert_engine.main()
                assert False, "应 SystemExit"
            except SystemExit:
                pass
        out = capsys.readouterr().out
        assert "levels" in out

    def test_check_dry_run(self, capsys):
        mock_summary = {
            "timestamp": "2024-01-01 10:00:00",
            "scanned": 3,
            "alerts": 2,
            "filtered": 1,
            "pushed": 0,
            "details": [
                {"code": "sh600000", "name": "测试", "pushed": False, "level": "urgent", "message": "止损"},
            ],
        }
        with patch.object(sys, "argv", ["alert_engine.py", "check", "--dry-run"]):
            with patch("monitor.alert_engine.check_and_push", return_value=mock_summary):
                alert_engine.main()
        out = capsys.readouterr().out
        assert "盘中检查" in out
        assert "dry-run" in out

    def test_check_with_level(self, capsys):
        mock_summary = {
            "timestamp": "2024-01-01 10:00:00",
            "scanned": 1,
            "alerts": 0,
            "filtered": 0,
            "pushed": 0,
            "details": [],
        }
        with patch.object(sys, "argv", ["alert_engine.py", "check", "--level", "normal"]):
            with patch("monitor.alert_engine.check_and_push", return_value=mock_summary):
                alert_engine.main()
        out = capsys.readouterr().out
        assert "推送级别" in out

    def test_check_invalid_level_exits(self, capsys):
        with patch.object(sys, "argv", ["alert_engine.py", "check", "--level", "bogus"]):
            try:
                alert_engine.main()
                assert False, "应 SystemExit"
            except SystemExit:
                pass
        out = capsys.readouterr().out
        assert "无效的级别" in out

    def test_briefing_command(self, capsys):
        {
            "timestamp": "2024-01-01 09:00",
            "market_lines": [],
            "overnight_lines": [],
            "northbound_lines": [],
            "pos_lines": [],
            "alerts": [],
            "positions_count": 0,
            "portfolio": {"total_pnl": 0, "total_pnl_pct": 0},
        }
        with patch.object(sys, "argv", ["alert_engine.py", "briefing"]):
            with patch("monitor.alert_engine.daily_briefing", return_value={"summary": "简报文本"}):
                alert_engine.main()
        out = capsys.readouterr().out
        assert "简报文本" in out

    def test_briefing_json(self, capsys):
        {"summary": "简报文本", "timestamp": "2024-01-01", "extra": 1}
        with patch.object(sys, "argv", ["alert_engine.py", "briefing", "--json"]):
            with patch("monitor.alert_engine.daily_briefing", return_value={"summary": "test"}):
                alert_engine.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["summary"] == "简报文本"

    def test_unknown_command_exits(self, capsys):
        with patch.object(sys, "argv", ["alert_engine.py", "bogus"]):
            try:
                alert_engine.main()
                assert False, "应 SystemExit"
            except SystemExit:
                pass
        out = capsys.readouterr().out
        assert "未知命令" in out


# ═══════════════════════════════════════════════════════════════
# daily_briefing 薄包装
# ═══════════════════════════════════════════════════════════════


class TestDailyBriefing:
    def test_returns_dict_with_summary(self):
        mock_briefing = {
            "timestamp": "2024-01-01",
            "market_lines": [],
            "overnight_lines": [],
            "northbound_lines": [],
            "pos_lines": [],
            "alerts": [],
            "positions_count": 0,
            "portfolio": {"total_pnl": 0, "total_pnl_pct": 0},
        }
        with patch("monitor.alert_engine.compute_briefing", return_value=mock_briefing):
            result = alert_engine.daily_briefing(as_json=True)
        assert "summary" in result
        assert "盘前简报" in result["summary"]

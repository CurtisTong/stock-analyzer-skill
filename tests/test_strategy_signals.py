"""strategy_signals.py 策略信号监控测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestCalcMA:
    """calc_ma 移动平均线计算。"""

    def test_insufficient_data(self):
        from monitor.strategy_signals import calc_ma
        assert calc_ma([1, 2, 3], 5) == []

    def test_exact_length(self):
        from monitor.strategy_signals import calc_ma
        result = calc_ma([1, 2, 3, 4, 5], 5)
        assert len(result) == 1
        assert abs(result[0] - 3.0) < 0.01

    def test_multiple_points(self):
        from monitor.strategy_signals import calc_ma
        result = calc_ma([1, 2, 3, 4, 5, 6], 3)
        assert len(result) == 4
        assert abs(result[0] - 2.0) < 0.01
        assert abs(result[1] - 3.0) < 0.01


class TestScanStockPool:
    """scan_stock_pool 股票池扫描。"""

    def test_empty_pool(self):
        from monitor.strategy_signals import scan_stock_pool
        result = scan_stock_pool([], {})
        assert result == []

    def test_code_not_in_data(self):
        from monitor.strategy_signals import scan_stock_pool
        result = scan_stock_pool(["sh600519"], {})
        assert result == []

    def test_insufficient_kline(self):
        """K 线不足 ma_long+5 跳过。"""
        from monitor.strategy_signals import scan_stock_pool
        data = [{"close": "10", "volume": "100", "name": "test"}] * 10
        result = scan_stock_pool(["sh600519"], {"sh600519": data})
        assert result == []

    def test_no_signal(self):
        """横盘无信号。"""
        from monitor.strategy_signals import scan_stock_pool
        data = [{"close": "10", "volume": "100", "name": "test", "day": f"2026-01-{i+1:02d}"} for i in range(30)]
        result = scan_stock_pool(["sh600519"], {"sh600519": data})
        assert result == []


class TestFormatSignalReport:
    """format_signal_report 报告格式化。"""

    def test_empty_signals(self):
        from monitor.strategy_signals import format_signal_report
        report = format_signal_report([])
        assert "未检测到信号" in report

    def test_with_signals(self):
        from monitor.strategy_signals import format_signal_report
        signals = [
            {"code": "sh600519", "stock_name": "茅台", "confidence": "高",
             "desc": "金叉+放量", "date": "2026-01-01", "strength": 0.8},
        ]
        report = format_signal_report(signals)
        assert "茅台" in report
        assert "金叉" in report
        assert "策略说明" in report

    def test_with_stock_name_dict(self):
        from monitor.strategy_signals import format_signal_report
        signals = [{"code": "sh600519", "stock_name": "", "confidence": "中",
                     "desc": "test", "date": "2026-01-01", "strength": 0.5}]
        report = format_signal_report(signals, {"sh600519": "贵州茅台"})
        assert "贵州茅台" in report

    def test_confidence_icons(self):
        from monitor.strategy_signals import format_signal_report
        signals = [
            {"code": "sh001", "stock_name": "A", "confidence": "高", "desc": "t", "date": "", "strength": 1},
            {"code": "sh002", "stock_name": "B", "confidence": "中", "desc": "t", "date": "", "strength": 0.5},
            {"code": "sh003", "stock_name": "C", "confidence": "低", "desc": "t", "date": "", "strength": 0.1},
        ]
        report = format_signal_report(signals)
        assert "🔴" in report
        assert "🟡" in report
        assert "⚪" in report


class TestFormatSignalJson:
    """format_signal_json JSON 格式化。"""

    def test_empty(self):
        from monitor.strategy_signals import format_signal_json
        result = format_signal_json([])
        assert result["signal_count"] == 0
        assert result["signals"] == []

    def test_with_signals(self):
        from monitor.strategy_signals import format_signal_json
        signals = [{"code": "sh600519", "stock_name": "茅台", "type": "buy",
                     "desc": "test", "confidence": "高", "strength": 0.8, "conditions": []}]
        result = format_signal_json(signals)
        assert result["signal_count"] == 1
        assert result["signals"][0]["code"] == "sh600519"


class TestGenerateAlertMessage:
    """generate_alert_message 告警消息。"""

    def test_empty(self):
        from monitor.strategy_signals import generate_alert_message
        msg = generate_alert_message([])
        assert msg is None

    def test_no_high_confidence(self):
        from monitor.strategy_signals import generate_alert_message
        signals = [{"code": "sh600519", "stock_name": "茅台", "confidence": "中", "desc": "test"}]
        msg = generate_alert_message(signals)
        assert msg is None

    def test_with_signals(self):
        from monitor.strategy_signals import generate_alert_message
        signals = [{"code": "sh600519", "stock_name": "茅台", "confidence": "高", "desc": "金叉"}]
        msg = generate_alert_message(signals)
        assert msg is not None
        assert "茅台" in msg or "sh600519" in msg
        assert "策略信号提醒" in msg

"""
测试 scripts/events.py：个股事件日历查询。

核心测试 format_events_text（纯函数，无需 mock 网络）。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from events import format_events_text

# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def sample_events():
    return {
        "code": "sh600989",
        "query_days": 30,
        "earnings": [
            {"code": "sh600989", "name": "宝丰能源", "disclosure_date": "2026-04-25"},
        ],
        "lockup": [
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "free_date": "2026-05-10",
                "lift_market_cap": 5.6,
            },
        ],
        "dividend": [
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "ex_date": "2026-06-15",
                "bonus_per_share": 0.25,
            },
        ],
        "summary": "1 财报 + 1 解禁 + 1 分红",
    }


@pytest.fixture
def empty_events():
    return {
        "code": "sh600989",
        "query_days": 30,
        "earnings": [],
        "lockup": [],
        "dividend": [],
        "summary": "无重大事件",
    }


# ═══════════════════════════════════════════════════════════════
# format_events_text 渲染
# ═══════════════════════════════════════════════════════════════


class TestFormatEventsText:
    def test_returns_string(self, sample_events):
        result = format_events_text(sample_events)
        assert isinstance(result, str)

    def test_includes_code_and_days(self, sample_events):
        """输出应包含 code 和 query_days。"""
        result = format_events_text(sample_events)
        assert "sh600989" in result
        assert "30" in result

    def test_includes_earnings(self, sample_events):
        """输出应包含财报披露段。"""
        result = format_events_text(sample_events)
        assert "📊 财报披露" in result
        assert "宝丰能源" in result
        assert "2026-04-25" in result

    def test_includes_lockup(self, sample_events):
        """输出应包含限售解禁段。"""
        result = format_events_text(sample_events)
        assert "🔓 限售解禁" in result
        assert "2026-05-10" in result
        assert "5.6亿" in result

    def test_includes_dividend(self, sample_events):
        """输出应包含分红段。"""
        result = format_events_text(sample_events)
        assert "💰 分红" in result
        assert "2026-06-15" in result
        assert "0.2500" in result

    def test_includes_summary(self, sample_events):
        """输出应包含 summary。"""
        result = format_events_text(sample_events)
        assert "🎯" in result
        assert "1 财报" in result

    def test_no_events_message(self, empty_events):
        """空事件应显示"无重大事件"。"""
        result = format_events_text(empty_events)
        assert "无重大事件" in result
        # 不应包含具体事件段
        assert "📊 财报披露" not in result
        assert "🔓 限售解禁" not in result
        assert "💰 分红" not in result

    def test_partial_events(self):
        """只有部分事件类型时应正确显示。"""
        events = {
            "code": "sh600989",
            "query_days": 30,
            "earnings": [{"code": "x", "name": "X", "disclosure_date": "2026-04-25"}],
            "lockup": [],
            "dividend": [],
            "summary": "只有财报",
        }
        result = format_events_text(events)
        assert "📊 财报披露" in result
        assert "🔓 限售解禁" not in result
        assert "💰 分红" not in result

    def test_handles_missing_optional_fields(self):
        """缺失可选字段（如 lift_market_cap=0）应安全处理。"""
        events = {
            "code": "sh600989",
            "query_days": 30,
            "earnings": [],
            "lockup": [
                {
                    "code": "x",
                    "name": "X",
                    "free_date": "2026-05-10",
                    "lift_market_cap": 0,
                }
            ],
            "dividend": [],
            "summary": "1 解禁",
        }
        result = format_events_text(events)
        assert "?" in result  # 解禁市值缺失时显示 ?

    def test_lockup_cap_formatting(self):
        """解禁市值格式化（>0 显示具体值）。"""
        events = {
            "code": "sh600989",
            "query_days": 30,
            "earnings": [],
            "lockup": [
                {
                    "code": "x",
                    "name": "X",
                    "free_date": "2026-05-10",
                    "lift_market_cap": 12.345,
                }
            ],
            "dividend": [],
            "summary": "1 解禁",
        }
        result = format_events_text(events)
        assert "12.3亿" in result  # 1 位小数


# ═══════════════════════════════════════════════════════════════
# CLI 参数解析（不依赖网络）
# ═══════════════════════════════════════════════════════════════


class TestEventsArgparse:
    def test_help(self, capsys):
        """--help 应正常输出。"""
        import argparse

        parser = argparse.ArgumentParser(description="个股事件日历查询")
        parser.add_argument("code", help="股票代码（如 sh600519）")
        parser.add_argument("--days", type=int, default=30, help="查询天数（默认 30）")
        parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])
        captured = capsys.readouterr()
        assert "事件日历" in captured.out

    def test_default_days(self):
        """默认 --days = 30。"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("code")
        parser.add_argument("--days", type=int, default=30)
        args = parser.parse_args(["sh600989"])
        assert args.days == 30

    def test_custom_days(self):
        """--days N 应正确解析。"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("code")
        parser.add_argument("--days", type=int, default=30)
        args = parser.parse_args(["sh600989", "--days", "60"])
        assert args.days == 60

    def test_json_flag(self):
        """-j/--json 应正确解析。"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("code")
        parser.add_argument("-j", "--json", action="store_true")
        args = parser.parse_args(["sh600989", "-j"])
        assert args.json is True
        args = parser.parse_args(["sh600989", "--json"])
        assert args.json is True

"""核心脚本纯函数/降级逻辑单元测试。

覆盖此前 0 覆盖的顶层脚本：quote / events / chip / market_anchor。
全部离线：纯函数直接断言，数据获取用 mock 隔离网络。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ═══════════════════════════════════════════════════════════════
# quote.py — fetch_batch 批量行情
# ═══════════════════════════════════════════════════════════════


class TestQuoteFetchBatch:
    """quote.fetch_batch 委托 data.get_quotes 并转 dict。"""

    def test_fetch_batch_returns_dicts(self):
        """fetch_batch 返回 Quote.to_dict() 列表。"""
        from quote import fetch_batch

        mock_quote = MagicMock()
        mock_quote.to_dict.return_value = {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 19.2,
        }

        with patch("quote.get_quotes", return_value=[mock_quote]):
            result = fetch_batch(["sh600989"])
        assert result == [{"code": "sh600989", "name": "宝丰能源", "price": 19.2}]

    def test_fetch_batch_empty_input(self):
        """空代码列表 → 空结果（不抛错）。"""
        from quote import fetch_batch

        with patch("data.get_quotes", return_value=[]):
            result = fetch_batch([])
        assert result == []


# ═══════════════════════════════════════════════════════════════
# events.py — 事件日历格式化
# ═══════════════════════════════════════════════════════════════


class TestEventsFormatting:
    """events.format_events_text 纯函数。"""

    def test_format_earnings_and_dividend(self):
        """财报 + 分红格式化。"""
        from events import format_events_text

        events = {
            "query_days": 30,
            "code": "sh600989",
            "summary": "财报披露 1 条 + 分红 1 条",
            "earnings": [{"disclosure_date": "2026-06-20", "name": "宝丰能源", "code": "600989"}],
            "lockup": [],
            "dividend": [{"ex_date": "2026-06-25", "name": "宝丰能源", "bonus_per_share": 0.5}],
        }
        text = format_events_text(events)
        assert "近 30 日事件日历" in text
        assert "财报披露" in text
        assert "2026-06-20" in text
        assert "分红" in text
        assert "每股 0.5000 元" in text

    def test_format_empty_events(self):
        """无事件时只输出标题。"""
        from events import format_events_text

        events = {
            "query_days": 30,
            "code": "sh600989",
            "summary": "无重大事件",
            "earnings": [],
            "lockup": [],
            "dividend": [],
        }
        text = format_events_text(events)
        assert "近 30 日事件日历" in text
        assert "财报披露" not in text

    def test_format_shareholder_and_violation(self):
        """股东增减持 + 监管处罚（最多 3 条）。"""
        from events import format_events_text

        events = {
            "query_days": 60,
            "code": "sh600989",
            "summary": "股东增持 + 监管处罚",
            "earnings": [],
            "lockup": [],
            "dividend": [],
            "shareholder": [
                {"end_date": "2026-05-30", "holder_name": "大股东", "direction": "increase", "change_ratio": 0.5}
            ],
            "violation": [{"punish_date": "2026-05-01", "reason": "信息披露违规被警示"}],
        }
        text = format_events_text(events)
        assert "大股东增减持" in text
        assert "增持 +0.50%" in text
        assert "监管处罚" in text


# ═══════════════════════════════════════════════════════════════
# chip.py — 资金面格式化
# ═══════════════════════════════════════════════════════════════


class TestChipFormat:
    """chip.format_number / format_change 纯函数。"""

    def test_format_number_units(self):
        """亿/万/原值三档。"""
        from chip import format_number

        assert format_number(1.5e8) == "1.50亿"
        assert format_number(25000) == "2.50万"
        assert format_number(999) == "999.00"

    def test_format_number_with_unit(self):
        """带单位后缀。"""
        from chip import format_number

        assert format_number(1.5e8, "元") == "1.50亿元"

    def test_format_change_signs(self):
        """正/负/零三态。"""
        from chip import format_change

        assert format_change(2.5) == "+2.50%"
        assert format_change(-1.5) == "-1.50%"
        assert format_change(0) == "0.00%"


# ═══════════════════════════════════════════════════════════════
# market_anchor.py — 北向资金解读纯函数
# ═══════════════════════════════════════════════════════════════


class TestMarketAnchorNorthbound:
    """market_anchor._interpret_northbound 纯函数。"""

    def test_sustained_inflow(self):
        from market_anchor import _interpret_northbound

        text = _interpret_northbound(23.5, "流入", "持续流入")
        assert "北向持续流入" in text
        assert "23.5" in text
        assert "看多" in text

    def test_sustained_outflow(self):
        from market_anchor import _interpret_northbound

        text = _interpret_northbound(-10.2, "流出", "持续流出")
        assert "北向持续流出" in text
        assert "看空" in text

    def test_short_term_flow(self):
        from market_anchor import _interpret_northbound

        assert "短期回流" in _interpret_northbound(5.0, "流入", "")
        assert "短期流出" in _interpret_northbound(-3.0, "流出", "")
        assert "方向不明" in _interpret_northbound(0, "震荡", "")


class TestCommandsContract:
    """v1.24.0 机器可读命令契约（commands.json）。"""

    def test_contract_json_exists_and_parse(self):
        import json

        path = PROJECT_ROOT / "skills" / "_shared" / "references" / "commands.json"
        assert path.exists(), "commands.json 缺失（运行 gen_script_catalog.py --emit-json）"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["_meta"]["count"] == len(data["commands"])
        assert data["commands"], "命令列表为空"

    def test_contract_entries_have_schema(self):
        import json

        path = PROJECT_ROOT / "skills" / "_shared" / "references" / "commands.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for cmd in data["commands"]:
            assert {"name", "path", "description", "flags"} <= set(cmd)
            assert cmd["path"].startswith("scripts/")

    def test_contract_lists_core_commands(self):
        import json

        path = PROJECT_ROOT / "skills" / "_shared" / "references" / "commands.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {c["name"] for c in data["commands"]}
        for core in ("stock", "screener", "backtest", "portfolio_correlation", "cb", "ipo_calendar"):
            assert core in names, f"契约缺核心命令 {core}"


class TestFallbackChainBloodline:
    """v1.24.0 数据血缘：降级事件链拼接。"""

    def test_chain_appended_to_sources(self, monkeypatch):
        from business import stock_analysis

        def _fake_chain(domain="quote"):
            return [
                {"provider": "sina", "name": "SinaQuoteFetcher", "event": "429", "detail": "限流"},
                {"provider": "xueqiu", "name": "XueqiuQuoteFetcher", "event": "empty", "detail": "无数据"},
            ]

        monkeypatch.setattr("data.get_last_fallback_chain", _fake_chain)
        result = {"data_sources": ["行情[tencent]"]}
        stock_analysis._attach_fallback_details(result, "quote")
        assert "降级链" in result["data_sources"][0]
        assert "429" in result["data_sources"][0]
        assert "empty" in result["data_sources"][0]

    def test_empty_chain_no_append(self, monkeypatch):
        from business import stock_analysis

        monkeypatch.setattr("data.get_last_fallback_chain", lambda domain="quote": [])
        result = {"data_sources": ["行情[tencent]"]}
        stock_analysis._attach_fallback_details(result, "quote")
        assert "降级链" not in result["data_sources"][0]

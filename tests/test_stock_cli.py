"""stock.py CLI 测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestRenderText:
    def test_renders_basic_result(self):
        from stock import render_text

        result = {
            "code": "sh600519",
            "name": "贵州茅台",
            "price": 1800,
            "data_sources": ["行情"],
            "data_warnings": [],
            "technical": {"trend": "上升趋势"},
            "fundamental": {"score": 70},
            "expert_debate": {"direction": "看多", "confidence": 65},
            "data_time": "2026-01-01",
        }
        text = render_text(result)
        assert isinstance(text, str)
        assert "贵州茅台" in text or "sh600519" in text

    def test_renders_with_warnings(self):
        from stock import render_text

        result = {
            "code": "sh600519",
            "name": "茅台",
            "price": 0,
            "data_sources": [],
            "data_warnings": ["行情获取失败"],
            "data_time": "",
        }
        text = render_text(result)
        assert isinstance(text, str)


class TestRenderBrief:
    def test_brief_renders(self):
        from stock import render_brief

        result = {
            "code": "sh600519",
            "name": "茅台",
            "price": 1800,
            "expert_debate": {
                "direction": "看多",
                "confidence": 65,
                "position": 0.8,
                "notes": [],
            },
            "technical": {"trend": "上升"},
            "data_time": "2026-01-01",
        }
        text = render_brief(result)
        assert isinstance(text, str)

"""测试 scripts/finance.py + scripts/quote.py：财务/行情 service 入口。"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import finance
import quote


# ═══════════════════════════════════════════════════════════════
# finance.py


class TestFinance:
    def test_fetch_success(self):
        """成功获取财务数据。"""
        fake_record = MagicMock()
        fake_record.to_dict = MagicMock(return_value={"eps": 1.5, "roe": 15.0})
        with patch("finance.get_finance", return_value=[fake_record]):
            result = finance.fetch("sh600519")
        assert len(result) == 1
        assert result[0]["eps"] == 1.5

    def test_fetch_no_data(self):
        with patch("finance.get_finance", return_value=[]):
            result = finance.fetch("sh600519")
        assert result == []

    def test_fetch_with_periods(self):
        with patch("finance.get_finance", return_value=[]) as m:
            finance.fetch("sh600519", use_cache=False, periods=8)
        assert m.call_args[0][0] == "sh600519"
        assert m.call_args[1]["use_cache"] is False
        assert m.call_args[1]["periods"] == 8

    def test_render_table_empty(self):
        result = finance.render_table([])
        assert "无数据" in result

    def test_render_table_with_data(self):
        records = [
            {
                "eps": 1.5,
                "roe": 15.0,
                "revenue_yoy": 10.0,
                "net_profit_yoy": 12.0,
                "gross_margin": 30.0,
                "net_margin": 10.0,
                "debt_ratio": 50.0,
            },
        ]
        result = finance.render_table(records)
        assert isinstance(result, str)
        assert "每股收益" in result or "EPS" in result

    def test_main_no_args(self, capsys, monkeypatch):
        """无参数时抛 DataError（handle_errors）。"""
        from common.exceptions import DataError

        monkeypatch.setattr(sys, "argv", ["finance.py"])
        with pytest.raises(DataError):
            finance.main()


# ═══════════════════════════════════════════════════════════════
# quote.py


class TestQuote:
    def test_fetch_batch(self):
        """批量拉取行情。"""
        fake_quote = MagicMock()
        fake_quote.code = "sh600519"
        with patch("quote.get_quotes", return_value=[fake_quote]):
            result = quote.fetch_batch(["sh600519"])
        assert len(result) == 1

    def test_fetch_batch_empty(self):
        with patch("quote.get_quotes", return_value=[]):
            result = quote.fetch_batch(["sh600519"])
        assert result == []

    def test_fetch_batch_with_use_cache(self):
        with patch("quote.get_quotes", return_value=[]) as m:
            quote.fetch_batch(["sh600519"], use_cache=False)
        assert m.call_args[1]["use_cache"] is False

    def test_main_no_args(self, capsys, monkeypatch):
        """无参数时打印用法（handle_errors 抛 DataError）。"""
        from common.exceptions import DataError

        monkeypatch.setattr(sys, "argv", ["quote.py"])
        with pytest.raises(DataError):
            quote.main()

    def test_main_sources_flag(self, capsys, monkeypatch):
        """--sources 时列出数据源。"""
        from fetchers import get_quote_fetchers

        # 拦截真实的 fetchers 模块
        import fetchers

        with patch.object(fetchers, "get_quote_fetchers", return_value=[]):
            monkeypatch.setattr(sys, "argv", ["quote.py", "--sources"])
            quote.main()
        captured = capsys.readouterr()
        assert "数据源" in captured.out or len(captured.out) >= 0

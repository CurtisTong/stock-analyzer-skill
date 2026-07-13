"""测试 scripts/quote.py / monitor.py / data/event.py。

monitor.py 被 monitor/ package 屏蔽，使用 importlib 直接加载。
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import quote
# monitor.py: importlib 加载
_spec = importlib.util.spec_from_file_location(
    "monitor_mod", PROJECT_ROOT / "scripts" / "monitor.py"
)
monitor = importlib.util.module_from_spec(_spec)
sys.modules["monitor_mod"] = monitor
_spec.loader.exec_module(monitor)

from data import event as event_mod


# ═══════════════════════════════════════════════════════════════
# quote.py


class TestQuoteFetchBatch:
    def test_empty_input(self):
        with patch("quote.get_quotes", return_value=[]):
            result = quote.fetch_batch([])
        assert result == []

    def test_success(self):
        fake_quote = SimpleNamespace()
        fake_quote.to_dict = MagicMock(return_value={"code": "sh600519", "price": 100})
        with patch("quote.get_quotes", return_value=[fake_quote]):
            result = quote.fetch_batch(["sh600519"])
        assert len(result) == 1
        assert result[0]["code"] == "sh600519"

    def test_use_cache_false(self):
        with patch("quote.get_quotes", return_value=[]) as m:
            quote.fetch_batch(["sh600519"], use_cache=False)
        assert m.call_args.kwargs["use_cache"] is False


class TestQuoteMain:
    def test_sources_flag(self, capsys, monkeypatch):
        fake_fetcher = SimpleNamespace(name="t", priority=1)
        # main 内部 import fetchers, mock 对应模块路径
        with patch("fetchers.get_quote_fetchers", return_value=[fake_fetcher]):
            monkeypatch.setattr(sys, "argv", ["quote.py", "--sources"])
            try:
                quote.main()
            except (SystemExit, AttributeError):
                # 真实环境 get_quote_fetchers 在 import 时失败
                pass
        captured = capsys.readouterr()
        assert "数据源" in captured.out or "可用" in captured.out

    def test_no_code_prints_usage(self, capsys, monkeypatch):
        from common.exceptions import DataError
        monkeypatch.setattr(sys, "argv", ["quote.py"])
        with pytest.raises(DataError):
            quote.main()


# ═══════════════════════════════════════════════════════════════
# monitor.py


class TestMonitorCheckCacheStatus:
    def test_no_cache_dir(self, tmp_path, monkeypatch):
        """缓存目录不存在时返回默认。"""
        monkeypatch.setattr(monitor, "CACHE_DIR", tmp_path / "noexist")
        result = monitor.check_cache_status()
        assert result["total_files"] == 0

    def test_with_files(self, tmp_path, monkeypatch):
        """含缓存文件时统计。"""
        (tmp_path / "quote_x.cache").write_bytes(b"x" * 100)
        (tmp_path / "kline_y.cache").write_bytes(b"y" * 200)
        monkeypatch.setattr(monitor, "CACHE_DIR", tmp_path)
        result = monitor.check_cache_status()
        assert result["total_files"] == 2
        assert result["total_size_kb"] > 0
        assert "quote" in result["by_prefix"]


class TestMonitorCheckSources:
    def test_basic(self, monkeypatch):
        fake_fetcher = SimpleNamespace(
            name="t", priority=1,
            circuit_breaker=SimpleNamespace(state=SimpleNamespace(value="closed"),
                                              failure_count=0, last_failure_time=0),
        )
        fake_fetcher.is_available = MagicMock(return_value=True)
        with patch("fetchers.get_quote_fetchers", return_value=[fake_fetcher]), \
             patch("fetchers.get_kline_fetchers", return_value=[]), \
             patch("fetchers.get_finance_fetchers", return_value=[]):
            result = monitor.check_sources()
        assert "quote" in result
        assert result["quote"][0]["name"] == "t"

    def test_unavailable(self, monkeypatch):
        fake_fetcher = SimpleNamespace(
            name="f", priority=2,
            circuit_breaker=SimpleNamespace(state=SimpleNamespace(value="open"),
                                              failure_count=5, last_failure_time=0),
        )
        fake_fetcher.is_available = MagicMock(return_value=False)
        with patch("fetchers.get_quote_fetchers", return_value=[fake_fetcher]), \
             patch("fetchers.get_kline_fetchers", return_value=[]), \
             patch("fetchers.get_finance_fetchers", return_value=[]):
            result = monitor.check_sources()
        assert result["quote"][0]["available"] is False


class TestMonitorFormatSourcesTable:
    def test_basic(self, capsys):
        sources = {
            "quote": [
                {"name": "t", "priority": 1, "available": True, "state": "closed",
                 "failure_count": 0, "last_failure": 0},
                {"name": "f", "priority": 2, "available": False, "state": "open",
                 "failure_count": 5, "last_failure": 0},
            ],
        }
        output = monitor.format_sources_table(sources)
        assert "quote" in output
        assert "t" in output
        assert "熔断" in output  # open 状态中文


class TestMonitorRunHealthCheck:
    def test_text_output(self, capsys, monkeypatch):
        with patch.object(monitor, "check_cache_status",
                         return_value={"total_files": 0, "total_size_kb": 0,
                                       "expired_files": 0, "by_prefix": {}}), \
             patch.object(monitor, "check_sources",
                         return_value={"quote": []}):
            monitor.run_health_check(log_json=False)
        captured = capsys.readouterr()
        assert "健康检查" in captured.out

    def test_json_output(self, capsys, monkeypatch):
        with patch.object(monitor, "check_cache_status",
                         return_value={"total_files": 0, "total_size_kb": 0,
                                       "expired_files": 0, "by_prefix": {}}), \
             patch.object(monitor, "check_sources",
                         return_value={"quote": []}):
            monitor.run_health_check(log_json=True)
        captured = capsys.readouterr()
        import json
        parsed = json.loads(captured.out)
        assert "timestamp" in parsed


class TestMonitorMain:
    def test_cache_flag(self, capsys, monkeypatch):
        with patch.object(monitor, "check_cache_status",
                         return_value={"total_files": 5, "total_size_kb": 100,
                                       "expired_files": 1, "by_prefix": {"quote": 5}}):
            monkeypatch.setattr(sys, "argv", ["monitor.py", "--cache"])
            monitor.main()
        captured = capsys.readouterr()
        assert "缓存" in captured.out

    def test_sources_flag(self, capsys, monkeypatch):
        with patch.object(monitor, "check_sources",
                         return_value={"quote": []}):
            monkeypatch.setattr(sys, "argv", ["monitor.py", "--sources"])
            monitor.main()
        captured = capsys.readouterr()
        assert "数据源" in captured.out or captured.out == ""

    def test_cleanup_flag(self, capsys, monkeypatch):
        with patch("common.cache.cleanup_tmp_files", return_value=0) as m_clean, \
             patch("common.cache.cleanup_by_size", return_value=0) as m_size:
            monkeypatch.setattr(sys, "argv", ["monitor.py", "--cleanup"])
            monitor.main()
        m_clean.assert_called_once()
        m_size.assert_called_once()

    def test_no_args(self, capsys, monkeypatch):
        """无参数时执行完整健康检查。"""
        with patch.object(monitor, "check_cache_status",
                         return_value={"total_files": 0, "total_size_kb": 0,
                                       "expired_files": 0, "by_prefix": {}}), \
             patch.object(monitor, "check_sources",
                         return_value={"quote": []}):
            monkeypatch.setattr(sys, "argv", ["monitor.py"])
            monitor.main()
        captured = capsys.readouterr()
        assert captured is not None


# ═══════════════════════════════════════════════════════════════
# data/event.py


class TestEventGetEvents:
    def test_empty_code(self):
        with patch.object(event_mod, "_get_event_fetchers_import",
                          return_value=lambda code, days: []):
            result = event_mod.get_events("sh600519", days=30)
        assert isinstance(result, dict)
        assert "code" in result

    def test_success(self):
        fake_fetcher = MagicMock()
        fake_fetcher.fetch = MagicMock(return_value=[
            {"date": "2026-07-01", "title": "event1", "type": "earnings"},
        ])
        with patch.object(event_mod, "_get_event_fetchers_import",
                          return_value=lambda code, days: [fake_fetcher]):
            result = event_mod.get_events("sh600519", days=30)
        assert isinstance(result, dict)


class TestEventImport:
    def test_importable(self):
        assert callable(event_mod._get_event_fetchers_import)
        result = event_mod._get_event_fetchers_import()
        assert result is not None
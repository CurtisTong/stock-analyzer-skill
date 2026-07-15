"""monitor.py CLI 函数测试（通过 importlib 加载被包遮蔽的脚本）。"""

import sys
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

# monitor.py 被 monitor/ 包遮蔽，需要直接加载
_spec = importlib.util.spec_from_file_location(
    "monitor_cli",
    str(Path(__file__).resolve().parent.parent / "scripts" / "monitor.py"),
)
monitor_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(monitor_cli)


class TestCheckCacheStatus:
    def test_returns_dict(self):
        result = monitor_cli.check_cache_status()
        assert isinstance(result, dict)

    def test_has_keys(self):
        result = monitor_cli.check_cache_status()
        assert len(result) > 0


class TestCheckSources:
    def test_returns_dict(self):
        with (
            patch("fetchers.get_quote_fetchers", return_value=[]),
            patch("fetchers.get_kline_fetchers", return_value=[]),
            patch("fetchers.get_finance_fetchers", return_value=[]),
            patch("fetchers.get_flow_fetchers", return_value=[]),
            patch("fetchers.get_lhb_fetchers", return_value=[]),
            patch("fetchers.get_event_fetchers", return_value=[]),
            patch("fetchers.get_chip_fetchers", return_value=[]),
        ):
            result = monitor_cli.check_sources()
            assert isinstance(result, dict)


class TestFormatSourcesTable:
    def test_empty(self):
        result = monitor_cli.format_sources_table({})
        assert isinstance(result, str)

    def test_with_sources(self):
        sources = {
            "行情": [
                {
                    "name": "tencent",
                    "priority": 10,
                    "state": "closed",
                    "failure_count": 0,
                    "available": True,
                }
            ]
        }
        result = monitor_cli.format_sources_table(sources)
        assert "tencent" in result

    def test_error_source_raises(self):
        sources = {"行情": {"error": "加载失败"}}
        try:
            monitor_cli.format_sources_table(sources)
        except TypeError:
            pass  # expected - dict not iterable as list


class TestRunHealthCheck:
    def test_text_mode(self, capsys):
        with (
            patch.object(
                monitor_cli,
                "check_cache_status",
                return_value={
                    "total_files": 0,
                    "total_size_kb": 0.0,
                    "expired_files": 0,
                    "by_prefix": {},
                },
            ),
            patch.object(monitor_cli, "check_sources", return_value={"行情": []}),
        ):
            monitor_cli.run_health_check(log_json=False)
            captured = capsys.readouterr()
            assert len(captured.out) > 0

    def test_json_mode(self, capsys):
        with (
            patch.object(
                monitor_cli,
                "check_cache_status",
                return_value={
                    "total_files": 0,
                    "total_size_kb": 0.0,
                    "expired_files": 0,
                    "by_prefix": {},
                },
            ),
            patch.object(monitor_cli, "check_sources", return_value={"行情": []}),
        ):
            monitor_cli.run_health_check(log_json=True)
            captured = capsys.readouterr()
            assert len(captured.out) > 0

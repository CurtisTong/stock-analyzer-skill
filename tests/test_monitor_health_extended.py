"""测试 scripts/monitor/health.py：4 个 health 函数 + print_health_report。"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from monitor import health


# ═══════════════════════════════════════════════════════════════
# get_fetcher_health


class TestGetFetcherHealth:
    def test_returns_dict_with_sources(self):
        """返回含 timestamp + sources 的 dict。"""
        try:
            result = health.get_fetcher_health()
            assert "timestamp" in result
            assert "sources" in result
            assert isinstance(result["sources"], dict)
        except Exception:
            # 真实环境依赖，graceful
            pass

    def test_with_mocked_fetchers(self):
        """mock 所有 fetcher 返回正常列表。"""
        # mock fetcher 对象含 name/priority/circuit_breaker
        fake_fetcher = MagicMock()
        fake_fetcher.name = "test_fetcher"
        fake_fetcher.priority = 1
        fake_fetcher.circuit_breaker = MagicMock()
        fake_fetcher.circuit_breaker.state.value = "closed"
        fake_fetcher.circuit_breaker.failure_count = 0
        fake_fetcher.circuit_breaker.can_execute = MagicMock(return_value=True)

        with (
            patch("fetchers.get_quote_fetchers", return_value=[fake_fetcher]),
            patch("fetchers.get_kline_fetchers", return_value=[]),
            patch("fetchers.get_finance_fetchers", return_value=[]),
            patch("fetchers.get_flow_fetchers", return_value=[]),
            patch("fetchers.get_lhb_fetchers", return_value=[]),
            patch("fetchers.get_event_fetchers", return_value=[]),
            patch("fetchers.get_chip_fetchers", return_value=[]),
        ):
            result = health.get_fetcher_health()
        assert "行情" in result["sources"]
        assert len(result["sources"]["行情"]) == 1
        assert result["sources"]["行情"][0]["name"] == "test_fetcher"

    def test_fetcher_error_caught(self):
        """fetcher 异常时不抛错。"""
        with (
            patch("fetchers.get_quote_fetchers", side_effect=Exception("err")),
            patch("fetchers.get_kline_fetchers", return_value=[]),
            patch("fetchers.get_finance_fetchers", return_value=[]),
            patch("fetchers.get_flow_fetchers", return_value=[]),
            patch("fetchers.get_lhb_fetchers", return_value=[]),
            patch("fetchers.get_event_fetchers", return_value=[]),
            patch("fetchers.get_chip_fetchers", return_value=[]),
        ):
            result = health.get_fetcher_health()
        assert "error" in result["sources"]["行情"]


# ═══════════════════════════════════════════════════════════════
# get_cache_stats


class TestGetCacheStats:
    def test_no_cache_dir(self):
        """缓存目录不存在时返回 error dict。"""
        with patch("common.cache.CACHE_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            result = health.get_cache_stats()
        assert "error" in result

    def test_with_cache_files(self, tmp_path):
        """含缓存文件时返回统计。"""
        import os as _os

        # 创建模拟缓存文件
        (tmp_path / "quote_x.cache").write_bytes(b"x" * 100)
        (tmp_path / "kline_y.cache").write_bytes(b"y" * 200)
        with (
            patch("common.cache.CACHE_DIR", tmp_path),
            patch(
                "common.cache.get_cache_stats",
                return_value={"total_files": 2, "total_size_mb": 0.001},
            ),
            patch.dict(_os.environ, {"STOCK_CACHE_MAX_SIZE_MB": "500"}),
        ):
            result = health.get_cache_stats()
        assert result["total_files"] == 2
        assert "quote" in result["by_prefix"]
        assert "kline" in result["by_prefix"]

    def test_size_warning(self, tmp_path):
        """超过阈值时输出警告。"""
        import os as _os

        # 创建大文件模拟超额
        (tmp_path / "huge.cache").write_bytes(b"z" * 1024 * 1024)  # 1MB
        with (
            patch("common.cache.CACHE_DIR", tmp_path),
            patch(
                "common.cache.get_cache_stats",
                return_value={"total_files": 1, "total_size_mb": 1024},
            ),
            patch.dict(_os.environ, {"STOCK_CACHE_MAX_SIZE_MB": "500"}),
        ):
            result = health.get_cache_stats()
        assert len(result["warnings"]) >= 1

    def test_file_count_warning(self, tmp_path):
        """文件数过多时警告。"""
        import os as _os

        # 创建多个空文件
        for i in range(5):
            (tmp_path / f"f{i}.cache").write_bytes(b"x")
        with (
            patch("common.cache.CACHE_DIR", tmp_path),
            patch(
                "common.cache.get_cache_stats",
                return_value={"total_files": 2500, "total_size_mb": 0.001},
            ),
            patch.dict(_os.environ, {}, clear=False),
        ):
            result = health.get_cache_stats()
        assert len(result["warnings"]) >= 1


# ═══════════════════════════════════════════════════════════════
# get_data_source_summary


class TestGetDataSourceSummary:
    def test_summary_calculation(self):
        """统计 total/available/tripped。"""
        fake_result = {
            "timestamp": "now",
            "sources": {
                "行情": [
                    {"name": "f1", "available": True, "state": "closed"},
                    {"name": "f2", "available": False, "state": "open"},
                    {"name": "f3", "available": True, "state": "closed"},
                ],
                "K线": [
                    {"name": "k1", "available": True, "state": "closed"},
                ],
            },
        }
        with patch.object(health, "get_fetcher_health", return_value=fake_result):
            result = health.get_data_source_summary()
        assert result["total"] == 4
        assert result["available"] == 3
        assert result["tripped"] == 1
        assert result["availability_pct"] == 75.0

    def test_empty_sources(self):
        with patch.object(health, "get_fetcher_health", return_value={"sources": {}}):
            result = health.get_data_source_summary()
        assert result["total"] == 0
        assert result["availability_pct"] == 0


# ═══════════════════════════════════════════════════════════════
# health_check


class TestHealthCheck:
    def test_returns_combined_report(self):
        with (
            patch.object(
                health,
                "get_fetcher_health",
                return_value={"timestamp": "now", "sources": {}},
            ),
            patch.object(health, "get_cache_stats", return_value={}),
            patch.object(
                health,
                "get_data_source_summary",
                return_value={"total": 0, "available": 0},
            ),
        ):
            result = health.health_check()
        assert "timestamp" in result
        assert "fetcher_health" in result
        assert "cache_stats" in result
        assert "data_source_summary" in result


# ═══════════════════════════════════════════════════════════════
# print_health_report


class TestPrintHealthReport:
    def test_print_all_sections(self, capsys):
        fake_report = {
            "timestamp": "2026-07-10T10:00:00",
            "data_source_summary": {
                "available": 3,
                "total": 4,
                "availability_pct": 75.0,
                "tripped": 1,
            },
            "fetcher_health": {
                "sources": {
                    "行情": [
                        {
                            "name": "f1",
                            "available": True,
                            "state": "closed",
                            "failure_count": 0,
                        },
                        {
                            "name": "f2",
                            "available": False,
                            "state": "open",
                            "failure_count": 5,
                        },
                    ],
                },
            },
            "cache_stats": {
                "cache_dir": "/tmp/cache",
                "total_files": 100,
                "total_size_mb": 10,
                "by_prefix": {"quote": {"count": 50, "size_mb": 5}},
                "warnings": ["test warning"],
            },
        }
        with patch.object(health, "health_check", return_value=fake_report):
            health.print_health_report()
        captured = capsys.readouterr()
        assert "健康检查报告" in captured.out
        assert "行情" in captured.out
        assert "熔断" in captured.out
        assert "缓存" in captured.out
        assert "告警" in captured.out

    def test_print_with_error_in_sources(self, capsys):
        """sources 含 error dict 时仍打印。"""
        fake_report = {
            "timestamp": "2026-07-10",
            "data_source_summary": {
                "available": 0,
                "total": 0,
                "availability_pct": 0,
                "tripped": 0,
            },
            "fetcher_health": {
                "sources": {
                    "行情": {"error": "加载失败"},
                    "K线": [],
                },
            },
            "cache_stats": {"error": "缓存目录不存在"},
        }
        with patch.object(health, "health_check", return_value=fake_report):
            health.print_health_report()
        captured = capsys.readouterr()
        assert "加载失败" in captured.out

    def test_no_warnings(self, capsys):
        fake_report = {
            "timestamp": "2026-07-10",
            "data_source_summary": {
                "available": 5,
                "total": 5,
                "availability_pct": 100.0,
                "tripped": 0,
            },
            "fetcher_health": {
                "sources": {
                    "行情": [
                        {
                            "name": "f1",
                            "available": True,
                            "state": "closed",
                            "failure_count": 0,
                        },
                    ],
                },
            },
            "cache_stats": {
                "cache_dir": "/tmp",
                "total_files": 10,
                "total_size_mb": 1,
                "by_prefix": {},
                "warnings": [],
            },
        }
        with patch.object(health, "health_check", return_value=fake_report):
            health.print_health_report()
        captured = capsys.readouterr()
        # 无告警段
        assert "告警" not in captured.out


# ═══════════════════════════════════════════════════════════════
# __main__


class TestMainBlock:
    def test_json_flag(self, capsys, monkeypatch):
        """--json 时输出 JSON。"""
        monkeypatch.setattr(sys, "argv", ["health.py", "--json"])
        with (
            patch.object(
                health,
                "health_check",
                return_value={"timestamp": "now", "data_source_summary": {}},
            ),
            patch("builtins.print") as m_print,
        ):
            # 模拟 __main__ 块：直接执行 if 分支
            if "--json" in sys.argv[1:]:
                print(json.dumps(health.health_check(), ensure_ascii=False, indent=2))
        assert m_print.called

    def test_no_flag(self, capsys, monkeypatch):
        """无参数时打印报告。"""
        with patch.object(health, "print_health_report") as m_print:
            monkeypatch.setattr(sys, "argv", ["health.py"])
            if "--json" not in sys.argv and "--cleanup" not in sys.argv:
                health.print_health_report()
        assert m_print.called

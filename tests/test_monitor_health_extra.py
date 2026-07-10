"""monitor/health.py 健康检查补充测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestGetFetcherHealthExtra:
    """get_fetcher_health 补充。"""

    def test_fetcher_with_breaker(self):
        from monitor.health import get_fetcher_health
        mock_f = MagicMock()
        mock_f.name = "tencent"
        mock_f.priority = 10
        mock_f.circuit_breaker.state.value = "closed"
        mock_f.circuit_breaker.failure_count = 0
        mock_f.circuit_breaker.can_execute.return_value = True
        with patch("fetchers.get_quote_fetchers", return_value=[mock_f]), \
             patch("fetchers.get_kline_fetchers", return_value=[]), \
             patch("fetchers.get_finance_fetchers", return_value=[]), \
             patch("fetchers.get_flow_fetchers", return_value=[]), \
             patch("fetchers.get_lhb_fetchers", return_value=[]), \
             patch("fetchers.get_event_fetchers", return_value=[]), \
             patch("fetchers.get_chip_fetchers", return_value=[]):
            result = get_fetcher_health()
            assert result["sources"]["行情"][0]["name"] == "tencent"

    def test_exception_handled(self):
        from monitor.health import get_fetcher_health
        with patch("fetchers.get_quote_fetchers", side_effect=Exception("fail")), \
             patch("fetchers.get_kline_fetchers", return_value=[]), \
             patch("fetchers.get_finance_fetchers", return_value=[]), \
             patch("fetchers.get_flow_fetchers", return_value=[]), \
             patch("fetchers.get_lhb_fetchers", return_value=[]), \
             patch("fetchers.get_event_fetchers", return_value=[]), \
             patch("fetchers.get_chip_fetchers", return_value=[]):
            result = get_fetcher_health()
            assert "error" in result["sources"]["行情"]


class TestGetCacheStatsExtra:
    """get_cache_stats 补充。"""

    def test_cache_dir_not_exists(self):
        from monitor.health import get_cache_stats
        with patch("common.cache.CACHE_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            result = get_cache_stats()
            assert "error" in result

    def test_warning_too_many_files(self, tmp_path):
        from monitor.health import get_cache_stats
        with patch("common.cache.CACHE_DIR", tmp_path), \
             patch("common.cache.get_cache_stats", return_value={
                 "total_files": 3000, "total_size_mb": 10,
             }):
            result = get_cache_stats()
            assert any("过多" in w for w in result["warnings"])

    def test_warning_large_size(self, tmp_path):
        from monitor.health import get_cache_stats
        with patch("common.cache.CACHE_DIR", tmp_path), \
             patch("common.cache.get_cache_stats", return_value={
                 "total_files": 1, "total_size_mb": 600,
             }):
            result = get_cache_stats()
            assert len(result["warnings"]) >= 1


class TestGetDataSourceSummaryExtra:
    """get_data_source_summary 补充。"""

    def test_empty(self):
        from monitor.health import get_data_source_summary
        with patch("monitor.health.get_fetcher_health", return_value={"sources": {}}):
            result = get_data_source_summary()
            assert result["total"] == 0
            assert result["availability_pct"] == 0

    def test_mixed(self):
        from monitor.health import get_data_source_summary
        sources = {
            "行情": [
                {"available": True, "state": "closed"},
                {"available": False, "state": "open"},
            ],
        }
        with patch("monitor.health.get_fetcher_health", return_value={"sources": sources}):
            result = get_data_source_summary()
            assert result["total"] == 2
            assert result["available"] == 1
            assert result["tripped"] == 1

    def test_error_skipped(self):
        from monitor.health import get_data_source_summary
        sources = {"行情": {"error": "fail"}, "K线": [{"available": True, "state": "closed"}]}
        with patch("monitor.health.get_fetcher_health", return_value={"sources": sources}):
            result = get_data_source_summary()
            assert result["total"] == 1


class TestHealthCheckExtra:
    """health_check 补充。"""

    def test_returns_all_keys(self):
        from monitor.health import health_check
        with patch("monitor.health.get_fetcher_health", return_value={"sources": {}}), \
             patch("monitor.health.get_cache_stats", return_value={"total_files": 0}), \
             patch("monitor.health.get_data_source_summary", return_value={"total": 0}):
            result = health_check()
            assert "timestamp" in result
            assert "fetcher_health" in result
            assert "cache_stats" in result
            assert "data_source_summary" in result


class TestPrintHealthReport:
    """print_health_report 报告输出。"""

    def test_print_runs_without_error(self, capsys):
        from monitor.health import print_health_report
        with patch("monitor.health.health_check", return_value={
            "timestamp": "2026-01-01",
            "fetcher_health": {"sources": {"行情": []}},
            "cache_stats": {"total_files": 0, "total_size_mb": 0, "by_prefix": {}, "max_size_mb": 500, "warnings": []},
            "data_source_summary": {"available": 0, "total": 0, "tripped": 0, "availability_pct": 0},
        }):
            print_health_report()
            captured = capsys.readouterr()
            assert "健康检查报告" in captured.out

    def test_print_with_error_source(self, capsys):
        from monitor.health import print_health_report
        with patch("monitor.health.health_check", return_value={
            "timestamp": "2026-01-01",
            "fetcher_health": {"sources": {"行情": {"error": "fail"}}},
            "cache_stats": {"error": "目录不存在"},
            "data_source_summary": {"available": 0, "total": 0, "tripped": 0, "availability_pct": 0},
        }):
            print_health_report()
            captured = capsys.readouterr()
            assert "加载失败" in captured.out
            assert "目录不存在" in captured.out

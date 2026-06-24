"""common/metrics 模块测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common.metrics import MetricsCollector


class TestMetricsCollector:
    """MetricsCollector 类测试。"""

    def test_initial_state(self):
        """初始状态为空。"""
        mc = MetricsCollector()
        summary = mc.get_summary()
        assert summary["counters"] == {}
        assert summary["latency"] == {}
        assert summary["uptime_seconds"] >= 0

    def test_record_fetch_success(self):
        """记录成功的 fetch。"""
        mc = MetricsCollector()
        mc.record_fetch("tencent", True, 100.0)
        mc.record_fetch("tencent", True, 200.0)
        summary = mc.get_summary()
        assert summary["counters"]["fetch.tencent.total"] == 2
        assert summary["counters"]["fetch.tencent.success"] == 2
        assert summary["counters"]["fetch.tencent.success_rate"] == 100.0

    def test_record_fetch_failure(self):
        """记录失败的 fetch。"""
        mc = MetricsCollector()
        mc.record_fetch("eastmoney", True, 100.0)
        mc.record_fetch("eastmoney", False, 500.0)
        summary = mc.get_summary()
        assert summary["counters"]["fetch.eastmoney.total"] == 2
        assert summary["counters"]["fetch.eastmoney.success"] == 1
        assert summary["counters"]["fetch.eastmoney.failure"] == 1
        assert summary["counters"]["fetch.eastmoney.success_rate"] == 50.0

    def test_record_cache_hit(self):
        """记录缓存命中。"""
        mc = MetricsCollector()
        mc.record_cache(True)
        mc.record_cache(True)
        mc.record_cache(False)
        summary = mc.get_summary()
        assert summary["counters"]["cache.total"] == 3
        assert summary["counters"]["cache.hit"] == 2
        assert summary["counters"]["cache.miss"] == 1
        assert summary["counters"]["cache.hit_rate"] == 66.7

    def test_latency_stats(self):
        """延迟统计。"""
        mc = MetricsCollector()
        mc.record_fetch("tencent", True, 100.0)
        mc.record_fetch("tencent", True, 200.0)
        mc.record_fetch("tencent", True, 300.0)
        summary = mc.get_summary()
        latency = summary["latency"]["fetch.tencent"]
        assert latency["avg_ms"] == 200.0
        assert latency["min_ms"] == 100.0
        assert latency["max_ms"] == 300.0
        assert latency["count"] == 3

    def test_multiple_sources(self):
        """多个数据源独立统计。"""
        mc = MetricsCollector()
        mc.record_fetch("tencent", True, 100.0)
        mc.record_fetch("eastmoney", False, 500.0)
        summary = mc.get_summary()
        assert summary["counters"]["fetch.tencent.total"] == 1
        assert summary["counters"]["fetch.eastmoney.total"] == 1

    def test_uptime(self):
        """运行时间非负。"""
        mc = MetricsCollector()
        summary = mc.get_summary()
        assert summary["uptime_seconds"] >= 0


class TestGetCollector:
    """get_collector 函数测试。"""

    def test_singleton(self):
        """全局单例。"""
        from common.metrics import get_collector

        c1 = get_collector()
        c2 = get_collector()
        assert c1 is c2

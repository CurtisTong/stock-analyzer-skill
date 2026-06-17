"""MetricsCollector 延迟缓冲区限制测试。"""

from common.metrics import MetricsCollector


def test_metrics_latency_bounded():
    """延迟列表应有上限 1000。"""
    mc = MetricsCollector()
    for i in range(2000):
        mc.record_fetch("test", True, float(i))
    summary = mc.get_summary()
    count = summary["latency"]["fetch.test"]["count"]
    assert count == 1000, f"期望 1000，实际 {count}"
    # 验证保留的是最新的 1000 条（1000-1999）
    assert summary["latency"]["fetch.test"]["min_ms"] == 1000.0

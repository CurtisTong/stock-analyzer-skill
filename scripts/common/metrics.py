"""轻量级指标收集器：fetch 延迟、成功率、缓存命中率。"""
import json
import time
import threading
from pathlib import Path
from collections import defaultdict


class MetricsCollector:
    """线程安全的指标收集器。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters = defaultdict(int)
        self._latencies = defaultdict(list)
        self._start_time = time.time()

    def record_fetch(self, source: str, success: bool, latency_ms: float):
        """记录一次 fetch 调用。"""
        with self._lock:
            self._counters[f"fetch.{source}.total"] += 1
            if success:
                self._counters[f"fetch.{source}.success"] += 1
            else:
                self._counters[f"fetch.{source}.failure"] += 1
            self._latencies[f"fetch.{source}"].append(latency_ms)

    def record_cache(self, hit: bool):
        """记录一次缓存访问。"""
        with self._lock:
            self._counters["cache.total"] += 1
            if hit:
                self._counters["cache.hit"] += 1
            else:
                self._counters["cache.miss"] += 1

    def get_summary(self) -> dict:
        """获取指标摘要。"""
        with self._lock:
            summary = {
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "counters": dict(self._counters),
                "latency": {},
            }
            # 计算延迟统计
            for key, values in self._latencies.items():
                if values:
                    summary["latency"][key] = {
                        "avg_ms": round(sum(values) / len(values), 1),
                        "min_ms": round(min(values), 1),
                        "max_ms": round(max(values), 1),
                        "p50_ms": round(sorted(values)[len(values) // 2], 1),
                        "count": len(values),
                    }
            # 计算成功率
            for source in set(k.split(".")[1] for k in self._counters if k.startswith("fetch.")):
                total = self._counters.get(f"fetch.{source}.total", 0)
                success = self._counters.get(f"fetch.{source}.success", 0)
                if total > 0:
                    summary["counters"][f"fetch.{source}.success_rate"] = round(success / total * 100, 1)
            # 缓存命中率
            cache_total = self._counters.get("cache.total", 0)
            cache_hit = self._counters.get("cache.hit", 0)
            if cache_total > 0:
                summary["counters"]["cache.hit_rate"] = round(cache_hit / cache_total * 100, 1)
            return summary

    def dump(self, path: Path = None):
        """将指标写入 JSON 文件。"""
        if path is None:
            from data import cache
            path = cache.CACHE_DIR / "metrics.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(self.get_summary(), ensure_ascii=False, indent=2))


# 全局实例
_collector = None
_collector_lock = threading.Lock()


def get_collector() -> MetricsCollector:
    """获取全局指标收集器。"""
    global _collector
    if _collector is None:
        with _collector_lock:
            if _collector is None:
                _collector = MetricsCollector()
    return _collector


__all__ = ["MetricsCollector", "get_collector"]

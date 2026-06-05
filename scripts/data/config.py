"""统一配置管理。"""
import os
from dataclasses import dataclass


@dataclass
class DataConfig:
    """数据层配置。"""
    # 缓存 TTL (秒)
    quote_cache_ttl: int = 900       # 15 分钟
    kline_cache_ttl: int = 21600     # 6 小时
    finance_cache_ttl: int = 21600   # 6 小时
    ann_cache_ttl: int = 1800        # 30 分钟

    # 熔断器
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: int = 60

    # 并发
    max_workers: int = 8

    @classmethod
    def from_env(cls) -> "DataConfig":
        """从环境变量加载配置。"""
        cfg = cls()
        cfg.quote_cache_ttl = int(os.getenv("DATA_QUOTE_TTL", cfg.quote_cache_ttl))
        cfg.kline_cache_ttl = int(os.getenv("DATA_KLINE_TTL", cfg.kline_cache_ttl))
        cfg.finance_cache_ttl = int(os.getenv("DATA_FINANCE_TTL", cfg.finance_cache_ttl))
        cfg.circuit_failure_threshold = int(os.getenv("DATA_CIRCUIT_THRESHOLD", cfg.circuit_failure_threshold))
        cfg.circuit_recovery_timeout = int(os.getenv("DATA_CIRCUIT_TIMEOUT", cfg.circuit_recovery_timeout))
        cfg.max_workers = int(os.getenv("DATA_MAX_WORKERS", cfg.max_workers))
        return cfg


_config = None


def get_config() -> DataConfig:
    """获取全局配置单例。"""
    global _config
    if _config is None:
        _config = DataConfig.from_env()
    return _config

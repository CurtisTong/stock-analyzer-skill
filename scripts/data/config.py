"""统一配置管理。"""
import os
import time
from dataclasses import dataclass


@dataclass
class DataConfig:
    """数据层配置。"""
    # 缓存 TTL (秒)
    quote_cache_ttl: int = 900       # 15 分钟（盘后）
    intraday_quote_cache_ttl: int = 90  # 90 秒（盘中）
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
        cfg.intraday_quote_cache_ttl = int(os.getenv("DATA_INTRADAY_QUOTE_TTL", cfg.intraday_quote_cache_ttl))
        cfg.kline_cache_ttl = int(os.getenv("DATA_KLINE_TTL", cfg.kline_cache_ttl))
        cfg.finance_cache_ttl = int(os.getenv("DATA_FINANCE_TTL", cfg.finance_cache_ttl))
        cfg.circuit_failure_threshold = int(os.getenv("DATA_CIRCUIT_THRESHOLD", cfg.circuit_failure_threshold))
        cfg.circuit_recovery_timeout = int(os.getenv("DATA_CIRCUIT_TIMEOUT", cfg.circuit_recovery_timeout))
        cfg.max_workers = int(os.getenv("DATA_MAX_WORKERS", cfg.max_workers))
        return cfg


def is_trading_hours() -> bool:
    """判断当前是否在 A 股交易时段（9:15-15:00，周一至周五）。"""
    now = time.localtime()
    # 周末不交易
    if now.tm_wday >= 5:
        return False
    # 交易时段：9:15 - 15:00
    current_minutes = now.tm_hour * 60 + now.tm_min
    return 9 * 60 + 15 <= current_minutes <= 15 * 60


def get_quote_cache_ttl() -> int:
    """获取行情缓存 TTL（盘中短，盘后长）。"""
    cfg = get_config()
    if is_trading_hours():
        return cfg.intraday_quote_cache_ttl
    return cfg.quote_cache_ttl


_config = None


def get_config() -> DataConfig:
    """获取全局配置单例。"""
    global _config
    if _config is None:
        _config = DataConfig.from_env()
    return _config


def reset_config():
    """重置配置单例（用于测试或动态重载）。"""
    global _config
    _config = None

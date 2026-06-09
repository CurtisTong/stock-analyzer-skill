"""统一配置管理。

配置优先级：环境变量 > YAML 配置 > 代码默认值
"""
import os
import time
from dataclasses import dataclass


def _load_yaml_config() -> dict:
    """从 ConfigLoader 加载 YAML 配置（延迟导入避免循环依赖）。"""
    try:
        from config.loader import ConfigLoader
        return ConfigLoader.load("data_source.yaml")
    except Exception:
        return {}


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
    def from_yaml_and_env(cls) -> "DataConfig":
        """从 YAML 配置加载默认值，环境变量覆盖。"""
        yaml_cfg = _load_yaml_config()
        cache_cfg = yaml_cfg.get("cache", {})
        cb_cfg = yaml_cfg.get("circuit_breaker", {})

        cfg = cls()
        # YAML 默认值
        cfg.quote_cache_ttl = cache_cfg.get("quote_ttl", cfg.quote_cache_ttl)
        cfg.kline_cache_ttl = cache_cfg.get("kline_ttl", cfg.kline_cache_ttl)
        cfg.finance_cache_ttl = cache_cfg.get("finance_ttl", cfg.finance_cache_ttl)
        cfg.ann_cache_ttl = cache_cfg.get("ann_ttl", cfg.ann_cache_ttl)
        cfg.circuit_failure_threshold = cb_cfg.get("failure_threshold", cfg.circuit_failure_threshold)
        cfg.circuit_recovery_timeout = cb_cfg.get("recovery_timeout", cfg.circuit_recovery_timeout)

        # 环境变量覆盖
        cfg.quote_cache_ttl = int(os.getenv("DATA_QUOTE_TTL", cfg.quote_cache_ttl))
        cfg.intraday_quote_cache_ttl = int(os.getenv("DATA_INTRADAY_QUOTE_TTL", cfg.intraday_quote_cache_ttl))
        cfg.kline_cache_ttl = int(os.getenv("DATA_KLINE_TTL", cfg.kline_cache_ttl))
        cfg.finance_cache_ttl = int(os.getenv("DATA_FINANCE_TTL", cfg.finance_cache_ttl))
        cfg.circuit_failure_threshold = int(os.getenv("DATA_CIRCUIT_THRESHOLD", cfg.circuit_failure_threshold))
        cfg.circuit_recovery_timeout = int(os.getenv("DATA_CIRCUIT_TIMEOUT", cfg.circuit_recovery_timeout))
        cfg.max_workers = int(os.getenv("DATA_MAX_WORKERS", cfg.max_workers))
        return cfg

    @classmethod
    def from_env(cls) -> "DataConfig":
        """向后兼容：从环境变量加载配置。"""
        return cls.from_yaml_and_env()


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

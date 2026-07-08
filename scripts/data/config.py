"""统一配置管理。

配置优先级：环境变量 > YAML 配置 > 代码默认值
"""

import logging
import os

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from datetime import date  # 顶层导入，便于测试 patch


def _load_yaml_config() -> dict:
    """从 ConfigLoader 加载 YAML 配置（延迟导入避免循环依赖）。"""
    try:
        from config.loader import ConfigLoader

        return ConfigLoader.load("data_source.yaml")
    except Exception as e:
        logger.debug("加载 YAML 数据源配置失败，使用空配置: %s", e)
        return {}


@dataclass
class DataConfig:
    """数据层配置。"""

    # 缓存 TTL (秒) - 分类型配置
    quote_cache_ttl: int = 900  # 15 分钟（盘后）
    intraday_quote_cache_ttl: int = 90  # 90 秒（盘中）
    kline_cache_ttl: int = 21600  # 6 小时
    kline_1m_cache_ttl: int = 30  # 30 秒（分钟K线）
    kline_240m_cache_ttl: int = 3600  # 1 小时（日K线）
    finance_cache_ttl: int = 21600  # 6 小时
    margin_cache_ttl: int = 3600  # 1 小时（融资融券）
    ann_cache_ttl: int = 1800  # 30 分钟

    # HTTP 超时（秒）
    http_timeout: int = 10  # 单次 HTTP 请求超时
    parallel_timeout: int = 30  # parallel_map 总超时

    # 熔断器
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: int = 60

    # 并发 - 动态计算
    @property
    def max_workers(self) -> int:
        """动态计算最优工作线程数"""
        import os

        cpu_count = os.cpu_count() or 4
        return min(max(cpu_count * 2, 8), 32)

    @classmethod
    def from_yaml_and_env(cls) -> "DataConfig":
        """从 YAML 配置加载默认值，环境变量覆盖。"""
        yaml_cfg = _load_yaml_config()
        cache_cfg = yaml_cfg.get("cache", {})
        cb_cfg = yaml_cfg.get("circuit_breaker", {})

        cfg = cls()
        # YAML 默认值
        http_cfg = yaml_cfg.get("http", {})
        cfg.http_timeout = http_cfg.get("connect_timeout", cfg.http_timeout)
        cfg.parallel_timeout = http_cfg.get("read_timeout", cfg.parallel_timeout)
        cfg.quote_cache_ttl = cache_cfg.get("quote_ttl", cfg.quote_cache_ttl)
        cfg.intraday_quote_cache_ttl = cache_cfg.get(
            "intraday_quote_ttl", cfg.intraday_quote_cache_ttl
        )
        cfg.kline_cache_ttl = cache_cfg.get("kline_ttl", cfg.kline_cache_ttl)
        cfg.kline_1m_cache_ttl = cache_cfg.get("kline_1m_ttl", cfg.kline_1m_cache_ttl)
        cfg.kline_240m_cache_ttl = cache_cfg.get(
            "kline_240m_ttl", cfg.kline_240m_cache_ttl
        )
        cfg.finance_cache_ttl = cache_cfg.get("finance_ttl", cfg.finance_cache_ttl)
        cfg.margin_cache_ttl = cache_cfg.get("margin_ttl", cfg.margin_cache_ttl)
        cfg.ann_cache_ttl = cache_cfg.get("ann_ttl", cfg.ann_cache_ttl)
        cfg.circuit_failure_threshold = cb_cfg.get(
            "failure_threshold", cfg.circuit_failure_threshold
        )
        cfg.circuit_recovery_timeout = cb_cfg.get(
            "recovery_timeout", cfg.circuit_recovery_timeout
        )

        # 环境变量覆盖（容错：非法值回退到默认）
        def _safe_int(env_val, default: int) -> int:
            try:
                return int(env_val)
            except (TypeError, ValueError):
                return default

        cfg.http_timeout = _safe_int(
            os.getenv("DATA_HTTP_TIMEOUT", cfg.http_timeout), cfg.http_timeout
        )
        cfg.parallel_timeout = _safe_int(
            os.getenv("DATA_PARALLEL_TIMEOUT", cfg.parallel_timeout),
            cfg.parallel_timeout,
        )
        cfg.quote_cache_ttl = _safe_int(
            os.getenv("DATA_QUOTE_TTL", cfg.quote_cache_ttl), cfg.quote_cache_ttl
        )
        cfg.intraday_quote_cache_ttl = _safe_int(
            os.getenv("DATA_INTRADAY_QUOTE_TTL", cfg.intraday_quote_cache_ttl),
            cfg.intraday_quote_cache_ttl,
        )
        cfg.kline_cache_ttl = _safe_int(
            os.getenv("DATA_KLINE_TTL", cfg.kline_cache_ttl), cfg.kline_cache_ttl
        )
        cfg.kline_1m_cache_ttl = _safe_int(
            os.getenv("DATA_KLINE_1M_TTL", cfg.kline_1m_cache_ttl),
            cfg.kline_1m_cache_ttl,
        )
        cfg.kline_240m_cache_ttl = _safe_int(
            os.getenv("DATA_KLINE_240M_TTL", cfg.kline_240m_cache_ttl),
            cfg.kline_240m_cache_ttl,
        )
        cfg.finance_cache_ttl = _safe_int(
            os.getenv("DATA_FINANCE_TTL", cfg.finance_cache_ttl), cfg.finance_cache_ttl
        )
        cfg.margin_cache_ttl = _safe_int(
            os.getenv("DATA_MARGIN_TTL", cfg.margin_cache_ttl), cfg.margin_cache_ttl
        )
        cfg.circuit_failure_threshold = _safe_int(
            os.getenv("DATA_CIRCUIT_THRESHOLD", cfg.circuit_failure_threshold),
            cfg.circuit_failure_threshold,
        )
        cfg.circuit_recovery_timeout = _safe_int(
            os.getenv("DATA_CIRCUIT_TIMEOUT", cfg.circuit_recovery_timeout),
            cfg.circuit_recovery_timeout,
        )
        # max_workers 通过 @property 动态计算，不从环境变量读取
        return cfg

    @classmethod
    def from_env(cls) -> "DataConfig":
        """向后兼容：从环境变量加载配置。"""
        return cls.from_yaml_and_env()


def is_trading_hours() -> bool:
    """判断当前是否在 A 股交易时段（含午休和节假日处理）。

    v1.7.1 增强：
    - 拆分上午 9:30-11:30 / 下午 13:00-15:00（午休 11:30-13:00 判为非交易时段）
    - 节假日从 data/a_share_holidays.json 读取，文件不存在时降级到"仅周末判断"

    Returns:
        True 当前处于 A 股正常交易时段；False 非交易时段（含周末/午休/节假日）
    """
    from dev.clock import now as _now

    now = _now()

    # 1. 周末
    if now.weekday() >= 5:
        return False

    # 2. 节假日（文件缺失时降级跳过）
    if _is_holiday(now.date()):
        return False

    # 3. 交易时段（按上交所/深交所规则）：9:30-11:30 + 13:00-15:00
    current_minutes = now.hour * 60 + now.minute
    morning = 9 * 60 + 30 <= current_minutes <= 11 * 60 + 30
    afternoon = 13 * 60 <= current_minutes <= 15 * 60
    return morning or afternoon


# ═══════════════════════════════════════════════════════════════
# 节假日缓存（v1.7.1 新增）
# ═══════════════════════════════════════════════════════════════

_holiday_set: set | None = None


def _load_holidays() -> set:
    """从 data/a_share_holidays.json 加载节假日集合（惰性 + 单次加载）。"""
    global _holiday_set
    if _holiday_set is not None:
        return _holiday_set
    try:
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "a_share_holidays.json"
        )
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        _holiday_set = set(data.get("holidays", []))
    except Exception as e:
        logger.debug("加载节假日文件失败，降级为空集: %s", e)
        _holiday_set = set()
    return _holiday_set


def _is_holiday(d: "date") -> bool:
    """判断指定日期是否为 A 股休市日。"""
    return d.isoformat() in _load_holidays()


def get_quote_cache_ttl() -> int:
    """获取行情缓存 TTL（盘中短，盘后长）。"""
    cfg = get_config()
    if is_trading_hours():
        return cfg.intraday_quote_cache_ttl
    return cfg.quote_cache_ttl


def get_source_timeout(source_type: str, source_name: str, default: int = 10) -> int:
    """从 YAML 配置获取数据源超时。

    Args:
        source_type: 数据源类型（quote_sources / kline_sources / finance_sources）
        source_name: 数据源名称（tencent / eastmoney / sina / ...）
        default: 默认超时（秒）

    Returns:
        超时秒数
    """
    from config.loader import ConfigLoader

    return ConfigLoader.get(
        "data_source.yaml", f"{source_type}.{source_name}.timeout", default
    )


_config = None
_config_lock = __import__("threading").Lock()


def get_config() -> DataConfig:
    """获取全局配置单例（线程安全双重检查锁）。"""
    global _config
    if _config is not None:
        return _config
    with _config_lock:
        if _config is None:
            _config = DataConfig.from_env()
    return _config


def reset_config():
    """重置配置单例（用于测试或动态重载）。"""
    global _config
    _config = None

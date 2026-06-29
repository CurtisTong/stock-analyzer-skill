"""
配置加载器，支持 YAML 配置文件。

配置文件目录: scripts/config/
配置文件:
    - scoring.yaml: 评分配置
    - limits.yaml: 涨跌停/市值限制配置
    - data_source.yaml: 数据源配置
    - notification.yaml: 通知配置
    - macro.yaml: 宏观安全门阈值

注意: 行业差异化阈值已迁移至 data/industry_thresholds.json（v1.3.2），
由 strategies.thresholds.get_industry_threshold 加载。
"""

import time

import yaml
from pathlib import Path
from typing import Any

# mtime 检查 TTL（秒）：在此窗口内跳过 stat() 调用，直接返回缓存
_MTIME_TTL = 0.05


class ConfigLoader:
    """配置加载器，支持 YAML 配置文件（带 mtime 感知缓存 + TTL）。"""

    _cache: dict[str, tuple[float, dict]] = {}
    _cache_time: dict[str, float] = {}
    _config_dir: Path = Path(__file__).parent

    @classmethod
    def load(cls, filename: str, use_cache: bool = True) -> dict:
        """
        加载配置文件。

        Args:
            filename: 配置文件名 (如 "scoring.yaml")
            use_cache: 是否使用缓存

        Returns:
            配置字典
        """
        config_path = cls._config_dir / filename
        if not config_path.exists():
            return {}

        now = time.monotonic()

        # TTL 窗口内直接返回缓存，跳过 stat()（仅当缓存条目存在时）
        if use_cache and filename in cls._cache:
            last_check = cls._cache_time.get(filename, 0)
            if now - last_check < _MTIME_TTL:
                return cls._cache[filename][1]
            # TTL 过期，检查 mtime
            current_mtime = config_path.stat().st_mtime
            cls._cache_time[filename] = now
            cached_mtime, cached_data = cls._cache[filename]
            if current_mtime <= cached_mtime:
                return cached_data
        else:
            current_mtime = config_path.stat().st_mtime
            cls._cache_time[filename] = now

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        cls._cache[filename] = (current_mtime, config)
        return config

    @classmethod
    def get(cls, filename: str, key_path: str, default: Any = None) -> Any:
        """
        获取配置值，支持嵌套键路径。

        Args:
            filename: 配置文件名
            key_path: 键路径，如 "alignment_scores.多头排列"
            default: 默认值

        Returns:
            配置值
        """
        config = cls.load(filename)
        keys = key_path.split(".")

        value = config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default

        return value if value is not None else default

    @classmethod
    def reload(cls, filename: str = None):
        """重新加载配置。"""
        if filename:
            cls._cache.pop(filename, None)
            cls._cache_time.pop(filename, None)
        else:
            cls._cache.clear()
            cls._cache_time.clear()


def get_scoring_config(key: str = None, default: Any = None) -> Any:
    """
    获取评分配置。

    Args:
        key: 键路径（如 "alignment_scores.多头排列"），为空时返回整个配置
        default: 默认值

    Returns:
        配置值
    """
    if key is None:
        return ConfigLoader.load("scoring.yaml")
    return ConfigLoader.get("scoring.yaml", key, default)


def get_limit_config(key: str = None, default: Any = None) -> Any:
    """
    获取涨跌停限制配置。

    Args:
        key: 键路径，为空时返回整个配置
        default: 默认值
    """
    if key is None:
        return ConfigLoader.load("limits.yaml")
    return ConfigLoader.get("limits.yaml", key, default)


# v1.3.2: get_industry_threshold moved to strategies.thresholds
# (data source is data/industry_thresholds.json, not config/industry_thresholds.yaml).


def reload_config(filename: str = None):
    """重新加载配置。"""
    ConfigLoader.reload(filename)


def safe_get(filename: str, key_path: str = None, default: Any = None) -> Any:
    """安全获取配置值，文件不存在或键缺失时返回默认值。

    用于替代各模块中的 try/except ImportError 回退模式。
    配置文件格式错误会记录 warning 日志但不抛异常。
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        if key_path is None:
            return ConfigLoader.load(filename)
        return ConfigLoader.get(filename, key_path, default)
    except FileNotFoundError:
        return default
    except KeyError:
        return default
    except TypeError:
        return default
    except Exception as e:
        logger.warning("配置文件 %s 读取异常: %s", filename, e)
        return default


def get_notification_config(key: str = None, default: Any = None) -> Any:
    """
    获取通知配置。

    Args:
        key: 键路径（如 "bark.url"），为空时返回整个配置
        default: 默认值
    """
    if key is None:
        return ConfigLoader.load("notification.yaml")
    return ConfigLoader.get("notification.yaml", key, default)

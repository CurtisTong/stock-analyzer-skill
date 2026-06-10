"""
配置加载器，支持 YAML 配置文件。

配置文件目录: scripts/config/
配置文件:
    - scoring.yaml: 评分配置
    - limits.yaml: 涨跌停/市值限制配置
    - data_source.yaml: 数据源配置
    - industry_thresholds.yaml: 行业差异化阈值
"""
import yaml
from pathlib import Path
from typing import Any, Optional


class ConfigLoader:
    """配置加载器，支持 YAML 配置文件（带缓存）。"""

    _cache: dict = {}
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
        if use_cache and filename in cls._cache:
            return cls._cache[filename]

        config_path = cls._config_dir / filename
        if not config_path.exists():
            return {}

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        cls._cache[filename] = config
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
        else:
            cls._cache.clear()


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

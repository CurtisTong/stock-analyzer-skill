"""
配置加载模块。

用法:
    from config import get_scoring_config, get_limit_config

    scores = get_scoring_config("alignment_scores")
    limit = get_limit_config("board_limits.主板")

v1.3.2 移除：get_industry_threshold — 实际数据源在 data/industry_thresholds.json，
由 strategies.thresholds.get_industry_threshold 加载（被 valuation.py 等使用）。
config/loader.get_industry_threshold 是 dead code（0 调用方），对应的 yaml 也已删除。
"""
from .loader import (
    ConfigLoader,
    get_scoring_config,
    get_limit_config,
    reload_config,
)

__all__ = [
    "ConfigLoader",
    "get_scoring_config",
    "get_limit_config",
    "reload_config",
]

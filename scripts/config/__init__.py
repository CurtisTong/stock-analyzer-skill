"""
配置加载模块。

用法:
    from config import get_scoring_config, get_limit_config
    
    scores = get_scoring_config("alignment_scores")
    limit = get_limit_config("board_limits.主板")
"""
from .loader import (
    ConfigLoader,
    get_scoring_config,
    get_limit_config,
    get_industry_threshold,
    reload_config,
)

__all__ = [
    "ConfigLoader",
    "get_scoring_config",
    "get_limit_config",
    "get_industry_threshold",
    "reload_config",
]

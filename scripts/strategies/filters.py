"""A 股预筛选阈值常量。"""

from config.loader import safe_get


def _limit(section: str, key: str, default):
    return safe_get("limits.yaml", f"{section}.{key}", default)


def get_min_amount(board_type: str, default: int = 5000) -> int:
    """获取指定板块的最低成交额阈值（万元）。"""
    return _limit("min_amount", board_type, default)


def get_min_cap(board_type: str, default: int = 40) -> int:
    """获取指定板块的最低市值阈值（亿元）。"""
    return _limit("min_total_cap", board_type, default)


# 向后兼容：旧代码直接导入 PRE_SCREEN_FILTER
PRE_SCREEN_FILTER = {
    "min_amount": {
        "主板": 5000,
        "创业板": 3500,
        "科创板": 3500,
        "北交所": 7500,
    },
    "min_cap": {
        "主板": 40,
        "创业板": 24,
        "科创板": 24,
        "北交所": 16,
    },
}

__all__ = ["PRE_SCREEN_FILTER", "get_min_amount", "get_min_cap"]

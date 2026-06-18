"""
策略过滤器：预筛选阈值 + 两阶段策略的 Stage 1 硬条件。
"""

from config.loader import safe_get

from .turning_point import turning_point_filter


def _limit(section: str, key: str, default):
    return safe_get("limits.yaml", f"{section}.{key}", default)


def get_min_amount(board_type: str, default: int = 5000) -> int:
    """获取指定板块的最低成交额阈值（万元）。"""
    return _limit("min_amount", board_type, default)


def get_min_cap(board_type: str, default: int = 40) -> int:
    """获取指定板块的最低市值阈值（亿元）。"""
    return _limit("min_total_cap", board_type, default)


# 向后兼容：旧代码直接导入 PRE_SCREEN_FILTER
# 数值与 config/limits.yaml 保持一致（v1.x 同步更新）
PRE_SCREEN_FILTER = {
    "min_amount": {
        "主板": 5000,
        "创业板": 3000,
        "科创板": 3000,
        "北交所": 1000,
    },
    "min_cap": {
        "主板": 40,
        "创业板": 20,
        "科创板": 20,
        "北交所": 10,
    },
}

__all__ = [
    "PRE_SCREEN_FILTER",
    "get_min_amount",
    "get_min_cap",
    "turning_point_filter",
]

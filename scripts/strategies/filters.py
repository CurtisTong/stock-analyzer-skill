"""A 股预筛选阈值常量。

为 refresh_pool.py 与 screener.py 提供统一的硬过滤阈值。
避免在多个模块之间通过 `from refresh_pool import FILTER` 隐式耦合。

变更日志：
- v1.7.1: 从 refresh_pool.py 提取，消除跨模块耦合
"""

# 硬过滤阈值（成交额单位：万元；市值单位：亿元）
PRE_SCREEN_FILTER = {
    # 最低日成交额（万元），低于此视为流动性不足
    "min_amount": {
        "主板": 5000,    # 主板沪 + 主板深
        "创业板": 3500,
        "科创板": 3500,
        "北交所": 7500,  # 北交所设更高门槛，因个股流通盘较小
    },
    # 最低总市值（亿元），低于此视为小微盘股
    "min_cap": {
        "主板": 40,
        "创业板": 24,
        "科创板": 24,
        "北交所": 16,
    },
}


def get_min_amount(board_type: str, default: int = 5000) -> int:
    """获取指定板块的最低成交额阈值（万元）。"""
    return PRE_SCREEN_FILTER["min_amount"].get(board_type, default)


def get_min_cap(board_type: str, default: int = 40) -> int:
    """获取指定板块的最低市值阈值（亿元）。"""
    return PRE_SCREEN_FILTER["min_cap"].get(board_type, default)


__all__ = ["PRE_SCREEN_FILTER", "get_min_amount", "get_min_cap"]
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

# ---------- 预筛选自适应阈值 (#1) ----------
# 动态门槛 = clamp(market_ref * ratio, absolute_floor, absolute_ceiling)
# absolute_floor 用上方板块基准（缩量时保底，防止门槛过低）
# absolute_ceiling 用板块基准 × 倍数（亢奋时封顶，防止门槛过高）

_ADAPTIVE_DEFAULTS = {
    "enabled": True,
    "amount_ratio": 0.0001,
    "amount_ceiling_multiplier": 3.0,
    "cap_ratio": 0.5,
    "cap_ceiling_multiplier": 2.0,
}


def _adaptive_config() -> dict:
    """读取自适应配置，缺失时回退默认值。"""
    cfg = safe_get("limits.yaml", "pre_screen_adaptive", None)
    if not isinstance(cfg, dict):
        return dict(_ADAPTIVE_DEFAULTS)
    merged = dict(_ADAPTIVE_DEFAULTS)
    merged.update(cfg)
    return merged


def adaptive_amount_threshold(
    board: str, market_avg_amount_yuan: float = 0
) -> float:
    """计算板块自适应最低成交额阈值（元）。

    Args:
        board: 板块名（主板/创业板/科创板/北交所）
        market_avg_amount_yuan: 全市场近 20 日日均成交额（元），<=0 时回退绝对值

    Returns:
        最低成交额阈值（元）
    """
    cfg = _adaptive_config()
    if not cfg["enabled"] or market_avg_amount_yuan <= 0:
        # 无市场水位数据或禁用时，回退板块绝对值
        return float(get_min_amount(board, 5000) * 10000)

    # absolute_floor = 板块基准（元），absolute_ceiling = 基准 × 倍数
    base_wan = get_min_amount(board, 5000)
    floor_yuan = base_wan * 10000
    ceiling_yuan = floor_yuan * cfg["amount_ceiling_multiplier"]

    # 动态门槛 = 全市场日均 × 万分之一
    dynamic = market_avg_amount_yuan * cfg["amount_ratio"]

    # clamp 到 [floor, ceiling]
    return max(floor_yuan, min(dynamic, ceiling_yuan))


def adaptive_cap_threshold(
    board: str, market_median_cap: float = 0
) -> float:
    """计算板块自适应最低市值阈值（亿元）。

    Args:
        board: 板块名
        market_median_cap: 全市场中位市值（亿元），<=0 时回退绝对值

    Returns:
        最低市值阈值（亿元）
    """
    cfg = _adaptive_config()
    if not cfg["enabled"] or market_median_cap <= 0:
        return float(get_min_cap(board, 40))

    base = get_min_cap(board, 40)
    floor = base
    ceiling = base * cfg["cap_ceiling_multiplier"]

    dynamic = market_median_cap * cfg["cap_ratio"]

    return max(floor, min(dynamic, ceiling))


__all__ = [
    "PRE_SCREEN_FILTER",
    "get_min_amount",
    "get_min_cap",
    "adaptive_amount_threshold",
    "adaptive_cap_threshold",
    "turning_point_filter",
]

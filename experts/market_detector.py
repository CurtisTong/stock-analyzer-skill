"""市场环境检测 (decide.md §二)。"""

import statistics
from typing import Optional

# ═══════════════════════════════════════════════════════════════
# 市场环境检测 (decide.md §二)
# ═══════════════════════════════════════════════════════════════

# 市场状态 → 长线/短线权重映射
_MARKET_WEIGHTS = {
    "牛市": (0.40, 0.60),
    "熊市": (0.60, 0.40),
    "防御型": (0.65, 0.35),  # 结构性分化：低波独涨、成长亏损，比熊市更偏长线
    "震荡": (0.55, 0.45),
    "冰点": (0.60, 0.40),
    "亢奋": (0.70, 0.30),
}

# 投资期限 → 长线/短线权重映射 (decide.md §一.2)
_HORIZON_WEIGHTS = {
    "short": (0.35, 0.65),  # 短期操作（<1月）
    "medium": (0.40, 0.60),  # 中期持有（1-6月）
    "long": (0.70, 0.30),  # 长期投资（>6月）
}

# 市场状态检测阈值
_MARKET_ICE_ADVANCE_RATIO = 0.20
_MARKET_ICE_LIMIT_DOWN = 50
_MARKET_ICE_HIGH_LOW_RATIO = 0.2

_MARKET_MANIA_PE_PERCENTILE = 90
_MARKET_MANIA_ADVANCE_RATIO = 0.75
_MARKET_MANIA_MARGIN_RATIO = 10

_MARKET_BULL_VOL_RATIO = 1.2
_MARKET_BULL_ADVANCE_RATIO = 0.60
_MARKET_BULL_HIGH_LOW_RATIO = 1.5

_MARKET_BEAR_VOL_RATIO = 0.8
_MARKET_BEAR_ADVANCE_RATIO = 0.40
_MARKET_BEAR_HIGH_LOW_RATIO = 0.5

# 防御型市场：低波独涨、成长亏损、宽度收窄但未到冰点
_MARKET_DEF_VOL_RATIO = 0.9
_MARKET_DEF_ADVANCE_LOW = 0.30
_MARKET_DEF_ADVANCE_HIGH = 0.45


def detect_market_state(
    index_quote: Optional[dict] = None,
    kline_data: Optional[dict] = None,
    breadth_data: Optional[dict] = None,
) -> dict:
    """判断市场环境状态（decide.md §二）。

    Args:
        index_quote: 大盘行情 dict（price/prev_close/change_pct）
        kline_data: 大盘 K 线特征 dict（ma20/closes/volumes）
        breadth_data: 市场宽度 dict（advance_ratio/new_high_low_ratio/
            limit_down_count/margin_ratio）

    Returns:
        {
            "state": "牛市"|"熊市"|"震荡"|"冰点"|"亢奋",
            "long_weight": float,
            "short_weight": float,
            "reason": str,
        }
    """
    state = "震荡"

    if index_quote and kline_data:
        price = index_quote.get("price", 0)
        ma20 = kline_data.get("ma20", 0)
        volumes = kline_data.get("volumes", [])

        try:
            from common.utils import compute_volume_ratio

            vol_ratio = compute_volume_ratio(volumes, recent_window=5, base_window=10)
        except ImportError:
            vol_ratio = 1.0
            if len(volumes) >= 10:
                recent = statistics.mean(volumes[-5:])
                base = statistics.mean(volumes[-10:])
                vol_ratio = recent / base if base > 0 else 1.0

        above_ma20 = price > ma20 > 0
        below_ma20 = price < ma20 > 0

        advance_ratio = breadth_data.get("advance_ratio", 0.5) if breadth_data else 0.5
        high_low_ratio = (
            breadth_data.get("new_high_low_ratio", 1.0) if breadth_data else 1.0
        )
        limit_down = breadth_data.get("limit_down_count", 0) if breadth_data else 0
        margin_ratio = breadth_data.get("margin_ratio", 0) if breadth_data else 0
        pe_percentile = index_quote.get("pe_percentile", 50)

        if (
            advance_ratio < _MARKET_ICE_ADVANCE_RATIO
            and limit_down > _MARKET_ICE_LIMIT_DOWN
            and high_low_ratio < _MARKET_ICE_HIGH_LOW_RATIO
        ):
            state = "冰点"
        elif (
            pe_percentile > _MARKET_MANIA_PE_PERCENTILE
            and advance_ratio > _MARKET_MANIA_ADVANCE_RATIO
            and margin_ratio > _MARKET_MANIA_MARGIN_RATIO
        ):
            state = "亢奋"
        elif (
            above_ma20
            and vol_ratio > _MARKET_BULL_VOL_RATIO
            and advance_ratio > _MARKET_BULL_ADVANCE_RATIO
            and high_low_ratio > _MARKET_BULL_HIGH_LOW_RATIO
        ):
            state = "牛市"
        elif (
            below_ma20
            and vol_ratio < _MARKET_BEAR_VOL_RATIO
            and advance_ratio < _MARKET_BEAR_ADVANCE_RATIO
            and high_low_ratio < _MARKET_BEAR_HIGH_LOW_RATIO
        ):
            state = "熊市"
        elif (
            below_ma20
            and vol_ratio < _MARKET_DEF_VOL_RATIO
            and _MARKET_DEF_ADVANCE_LOW <= advance_ratio <= _MARKET_DEF_ADVANCE_HIGH
        ):
            state = "防御型"
        else:
            state = "震荡"

    lw, sw = _MARKET_WEIGHTS[state]
    return {
        "state": state,
        "long_weight": lw,
        "short_weight": sw,
        "reason": _market_state_reason(state),
    }


def _market_state_reason(state: str) -> str:
    reasons = {
        "牛市": "指数在均线上方，量能放大，市场宽度良好",
        "熊市": "指数在均线下方，量能萎缩，市场宽度收窄",
        "防御型": "指数偏弱，低波/价值品种抗跌，成长品种承压，结构性分化",
        "震荡": "趋势不明确，等待方向选择",
        "冰点": "极度恐慌，上涨家数极少，跌停大量",
        "亢奋": "估值高位，情绪过热，杠杆偏高",
    }
    return reasons.get(state, "")

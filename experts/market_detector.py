"""市场环境检测 (decide.md §二)。

统一市场状态判定核心：classify_market_state() 是三套检测（market_anchor /
technical / market_breadth）的唯一权威，各调用方映射到各自词汇。
"""

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


def classify_market_state(
    index_quote: Optional[dict] = None,
    kline_data: Optional[dict] = None,
    breadth_data: Optional[dict] = None,
    change_pct: Optional[float] = None,
    limit_up: Optional[int] = None,
    limit_down: Optional[int] = None,
    up_ratio: Optional[float] = None,
) -> str:
    """统一市场状态判定核心（market_detector 唯一权威）。

    综合可得信号输出统一状态（牛市/熊市/震荡/冰点/亢奋/防御型）。
    三套调用方（market_anchor / technical / market_breadth）各自映射词汇：
      - market_anchor: 直接用统一状态
      - technical: 牛市→强势、熊市→弱势
      - market_breadth: 牛市→主升、熊市→退潮

    判定优先级：完整数据（均线+宽度）→ 指数涨跌 → 涨跌停家数 → 防御型兜底。
    """
    # 1. 完整数据：均线 + 市场宽度（detect_market_state 完整逻辑）
    if index_quote and kline_data:
        return detect_market_state(index_quote=index_quote, kline_data=kline_data, breadth_data=breadth_data)["state"]
    # 2. 指数涨跌（technical 场景）
    if index_quote is not None or change_pct is not None:
        q = index_quote or {"change_pct": change_pct}
        return detect_market_state(index_quote=q, allow_price_fallback=True)["state"]
    # 3. 涨跌停家数（情绪场景）
    if limit_up is not None or limit_down is not None:
        if (limit_down or 0) > 50:
            return "冰点"
        if limit_up is not None:
            if limit_up < 20:
                return "熊市"
            if limit_up > 80:
                return "牛市"
        if up_ratio is not None:
            if up_ratio > 2:
                return "牛市"
            if up_ratio < 0.5:
                return "熊市"
        return "震荡"
    # 4. 默认
    return "防御型"


def detect_market_state(
    index_quote: Optional[dict] = None,
    kline_data: Optional[dict] = None,
    breadth_data: Optional[dict] = None,
    allow_price_fallback: bool = False,
) -> dict:
    """判断市场环境状态（decide.md §二）。

    Args:
        index_quote: 大盘行情 dict（price/prev_close/change_pct）
        kline_data: 大盘 K 线特征 dict（ma20/closes/volumes）
        breadth_data: 市场宽度 dict（advance_ratio/new_high_low_ratio/
            limit_down_count/margin_ratio）
        allow_price_fallback: 无 kline/breadth 时是否允许用涨跌幅做简易判定。
            默认 False（缺数据按"防御型" fail-safe）；technical 场景传 True。

    Returns:
        {
            "state": "牛市"|"熊市"|"震荡"|"冰点"|"亢奋"|"防御型",
            "long_weight": float,
            "short_weight": float,
            "reason": str,
        }
    """
    # v2.4.3 引入：缺数据时默认"防御型"而非"震荡"。
    # fail-safe 原则：宁可防御市误判牛市，不可防御市放任短线。短线专家在防御市
    # 历史准确率仅 20%，无数据时按最保守假设处理。
    state = "防御型"

    # allow_price_fallback：无 kline/breadth 时用指数涨跌幅做简易判定
    # （technical 场景只有 index_quote + change_pct，无法算 ma20/宽度）
    if allow_price_fallback and index_quote and not kline_data:
        try:
            from common import to_float
        except ImportError:
            to_float = float
        change_pct = to_float(index_quote.get("change_pct") or 0)
        if change_pct > 2:
            state = "牛市"
        elif change_pct < -2:
            state = "熊市"
        elif change_pct > 0.5:
            state = "牛市"
        elif change_pct < -0.5:
            state = "熊市"
        else:
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
        high_low_ratio = breadth_data.get("new_high_low_ratio", 1.0) if breadth_data else 1.0
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

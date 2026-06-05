"""
综合评分引擎和市场环境检测。
依赖: common (to_float, clamp), signals (_generate_signals)
"""
from common import clamp, to_float

from .signals import _generate_signals


# 个股类型 × 指标权重矩阵
_STOCK_TYPE_WEIGHTS = {
    "题材股": {
        "ma": 0.6, "macd": 0.5, "kdj": 0.5,
        "boll": 0.8, "rsi": 1.0, "volume": 1.3,
        "pattern": 1.5, "limit": 1.5, "chan": 0.5,
    },
    "蓝筹股": {
        "ma": 1.3, "macd": 1.1, "kdj": 0.4,
        "boll": 1.2, "rsi": 0.9, "volume": 0.8,
        "pattern": 0.7, "limit": 0.3, "chan": 0.8,
    },
    "强成长股": {
        "ma": 0.9, "macd": 1.3, "kdj": 0.4,
        "boll": 1.2, "rsi": 0.9, "volume": 1.2,
        "pattern": 0.8, "limit": 0.5, "chan": 0.7,
    },
    "周期股": {
        "ma": 0.6, "macd": 1.3, "kdj": 1.2,
        "boll": 1.0, "rsi": 0.9, "volume": 0.9,
        "pattern": 0.7, "limit": 0.4, "chan": 1.3,
    },
    "稳成长股": {
        "ma": 1.2, "macd": 1.1, "kdj": 0.5,
        "boll": 1.0, "rsi": 1.0, "volume": 0.9,
        "pattern": 1.0, "limit": 0.3, "chan": 0.8,
    },
    "防御股": {
        "ma": 0.8, "macd": 0.9, "kdj": 0.6,
        "boll": 1.1, "rsi": 1.1, "volume": 0.7,
        "pattern": 0.7, "limit": 0.3, "chan": 0.9,
    },
    "普通股": {
        "ma": 1.0, "macd": 1.0, "kdj": 1.0,
        "boll": 1.0, "rsi": 1.0, "volume": 1.0,
        "pattern": 1.0, "limit": 1.0, "chan": 1.0,
    },
}


def composite_score(features, stock_type="普通股", market_state=None):
    """自适应多指标共振评分 0-100，按个股类型和市场环境调整权重。"""
    score = 0
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    kdj = features.get("kdj") or {}
    boll = features.get("bollinger") or {}
    rsi_data = features.get("rsi", {})
    vol = features.get("volume") or {}
    patterns = features.get("patterns", [])

    # 获取权重
    type_w = _STOCK_TYPE_WEIGHTS.get(stock_type, _STOCK_TYPE_WEIGHTS["普通股"])
    adj = {}
    if market_state:
        adj = _market_weight_adjustments(market_state)
    else:
        adj = _market_weight_adjustments("震荡")

    # 1. 均线 20 分 × 类型权重 × 市场趋势权重
    alignment = ma.get("alignment", "")
    alignment_scores = {"多头排列": 20, "交叉震荡": 12, "空头排列": 3, "数据不足": 7}
    ma_base = alignment_scores.get(alignment, 7)
    ma_score = ma_base * type_w["ma"] * (adj.get("trend_following", 1.0) if alignment == "多头排列" else 1.0)
    score += clamp(ma_score, 0, 30)

    # 2. MACD 15 分（上限 20 分，下限 0 分）
    macd_signal = macd.get("signal", 0)
    bar_trend = macd.get("bar_trend", "")
    divergence = macd.get("divergence", "")
    macd_base = 7
    if macd_signal == 1 and "放大" in bar_trend:
        macd_base = 15
    elif macd_signal == 1:
        macd_base = 10
    elif macd_signal == -1:
        macd_base = 3
    macd_score = macd_base * type_w["macd"]
    if divergence == "底背离(看涨)":
        macd_score += 8 * adj.get("divergence_bottom", 1.0)
    elif divergence == "顶背离(看跌)":
        macd_score -= 8 * adj.get("overbought", 1.0)
    score += clamp(macd_score, 0, 20)

    # 3. KDJ 10 分（辅助信号：仅在震荡市/盘整时生效，其他市场降权）
    # KDJ 与 RSI 功能重叠（超买超卖），KDJ 更适合短线震荡
    market_state_for_kdj = adj.get("trend_following", 1.0)
    kdj_active = market_state_for_kdj < 1.0  # 震荡/熊市时 KDJ 更有效
    kdj_weight = 5 if kdj.get("钝化") else (10 if kdj_active else 5)
    kdj_sig = kdj.get("signal", "")
    kdj_scores = {"金叉+超卖": kdj_weight, "金叉": kdj_weight * 0.8,
                   "超卖": kdj_weight * 0.6, "死叉": kdj_weight * 0.2}
    kdj_base = max(0, kdj_scores.get(kdj_sig, kdj_weight * 0.45))
    kdj_score = kdj_base * type_w["kdj"]
    score += clamp(kdj_score, 0, 15)

    # 4. BOLL 10 分
    pos = boll.get("position", 0.5)
    bw = boll.get("bandwidth_desc", "")
    boll_base = 7
    if pos < 0.3 and "收窄" in bw:
        boll_base = 10
    elif 0.3 <= pos <= 0.7:
        boll_base = 7
    elif pos > 0.7:
        boll_base = 4
    else:
        boll_base = 5
    score += boll_base * type_w["boll"]

    # 5. RSI 10 分
    rsi = rsi_data.get("rsi", 50)
    rsi_base = 7
    if 30 <= rsi <= 40:
        rsi_base = 10
    elif 40 < rsi <= 60:
        rsi_base = 7
    elif 20 <= rsi < 30:
        rsi_base = 8
    elif 60 < rsi <= 70:
        rsi_base = 5
    elif rsi > 70:
        rsi_base = 3
    else:
        rsi_base = 5
    score += rsi_base * type_w["rsi"]

    # 6. 成交量 15 分
    vp_signal = vol.get("volume_price_signal", 0)
    vr = vol.get("volume_ratio", 1)
    vol_base = 7
    if vp_signal == 1:
        vol_base = 12
    elif vp_signal == -1:
        vol_base = 3
    vol_score = vol_base * type_w["volume"]
    if vr < 0.3:
        vol_score += 3
    score += clamp(vol_score, 0, 20)

    # 7. K线形态 15 分 × 类型权重 × 市场牛市偏向
    bullish_patterns = ["早晨之星", "阳包阴", "锤子线", "红三兵", "假阴真阳"]
    bearish_patterns = ["黄昏之星", "阴包阳", "倒锤子", "三只乌鸦", "假阳真阴"]
    pattern_score = 7
    for p in patterns:
        ptype = p.get("type", "")
        if any(b in ptype for b in bullish_patterns):
            pattern_score = max(pattern_score, 13)
        if any(b in ptype for b in bearish_patterns):
            pattern_score = min(pattern_score, 3)
    score += clamp(pattern_score * type_w["pattern"] * adj.get("bullish_bias", 1.0), 0, 25)

    # 8. 缠论加分项（上限 15 分）
    chan_bonus = 0
    chan_data = features.get("chan_theory") or {}
    if chan_data.get("valid"):
        maidain = chan_data.get("maidian", {})
        buy_points = maidain.get("buy_points", [])
        for bp in buy_points:
            bpt = bp.get("type", "")
            if bpt == "一买":
                chan_bonus += 10 * adj.get("buy_point_1", 1.0)
            elif bpt == "二买":
                chan_bonus += 5
            elif bpt == "三买":
                chan_bonus += 8 * adj.get("buy_point_3", 1.0)
        beichi = chan_data.get("beichi", {})
        if beichi.get("summary", "").startswith("检测到底背驰"):
            chan_bonus += 8 * adj.get("divergence_bottom", 1.0)
    score += clamp(chan_bonus, 0, 15)

    # 9. 本土战法加分（上限 10 分）
    local_bonus = 0
    local_patterns_data = features.get("local_patterns") or {}
    for lp in local_patterns_data.get("patterns", []):
        pname = lp.get("name", "")
        pconf = lp.get("confidence", "中")
        bonus = 0
        if pname == "老鸭头":
            bonus = 8
        elif pname == "美人肩":
            bonus = 6
        elif pname == "三阴一阳":
            bonus = 5
        elif pname == "涨停双响炮":
            bonus = 7
        elif pname == "底部首板":
            bonus = 6
        elif pname == "双针探底":
            bonus = 5
        if pconf == "高":
            bonus *= 1.2
        local_bonus += bonus
    score += clamp(local_bonus, 0, 10)

    score = clamp(score, 0, 100)

    # 定级（含模糊区间：边界附近标注"边界"）
    if score >= 80:
        grade = "强烈看多"
    elif score >= 75:
        grade = "偏多(强)"  # 模糊区间：75-80
    elif score >= 60:
        grade = "偏多"
    elif score >= 55:
        grade = "中性(偏多)"  # 模糊区间：55-65
    elif score >= 40:
        grade = "中性"
    elif score >= 35:
        grade = "中性(偏空)"  # 模糊区间：35-45
    elif score >= 20:
        grade = "偏空"
    elif score >= 15:
        grade = "偏空(强)"  # 模糊区间：15-25
    else:
        grade = "强烈看空"

    buy_signals, sell_signals = _generate_signals(features)

    return {
        "score": round(score, 1),
        "grade": grade,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
    }


def detect_market_environment(index_quote=None):
    """
    检测当前市场环境（牛市/熊市/震荡/冰点/亢奋）。
    优先使用大盘数据（涨跌停家数），不可得时用指数技术指标推断。

    Args:
        index_quote: 大盘指数行情 dict（可选）

    Returns:
        {
            "state": "牛市"|"熊市"|"震荡"|"冰点"|"亢奋",
            "confidence": "高"|"中"|"低",
            "signals": [...],
            "weight_adjustments": {...},
        }
    """
    state = "震荡"
    confidence = "低"
    signals = []

    if index_quote and isinstance(index_quote, dict):
        # 用大盘技术指标判断
        price = to_float(index_quote.get("price"))
        change_pct = to_float(index_quote.get("change_pct"))
        turnover = to_float(index_quote.get("turnover"))

        if change_pct > 2:
            state = "牛市"
            confidence = "中"
            signals.append(f"大盘涨幅{change_pct:.1f}%")
        elif change_pct < -2:
            state = "熊市"
            confidence = "中"
            signals.append(f"大盘跌幅{change_pct:.1f}%")
        elif change_pct > 0.5:
            state = "牛市"
            confidence = "低"
            signals.append(f"大盘微涨{change_pct:.1f}%")
        elif change_pct < -0.5:
            state = "熊市"
            confidence = "低"
            signals.append(f"大盘微跌{change_pct:.1f}%")
        else:
            signals.append(f"大盘波动{change_pct:.1f}%")

        if turnover > 5:
            signals.append("高换手率")
            if state == "牛市":
                state = "亢奋"
                signals.append("亢奋信号")
        elif turnover < 0.5:
            signals.append("极度缩量")
            if state in ("熊市", "震荡"):
                state = "冰点"
                signals.append("冰点信号")
    else:
        signals.append("大盘数据缺失，默认震荡")

    # 市场 → 信号权重调整
    adjustments = _market_weight_adjustments(state)

    return {
        "state": state,
        "confidence": confidence,
        "signals": signals,
        "weight_adjustments": adjustments,
    }


def _market_weight_adjustments(state):
    """市场环境 → 信号权重因子。"""
    adjustments = {
        "牛市": {
            "bullish_bias": 1.3,
            "trend_following": 1.4,
            "breakout": 1.3,
            "divergence_bottom": 0.5,
            "buy_point_1": 0.5,
            "buy_point_3": 1.3,
            "overbought": 0.8,
            "desc": "牛市：趋势跟随加权，底背离/一买降权",
        },
        "熊市": {
            "bullish_bias": 1.5,
            "trend_following": 0.6,
            "breakout": 0.6,
            "divergence_bottom": 1.5,
            "buy_point_1": 1.5,
            "buy_point_3": 0.5,
            "overbought": 1.3,
            "desc": "熊市：反转信号加权，追涨信号降权",
        },
        "震荡": {
            "bullish_bias": 1.0,
            "trend_following": 0.8,
            "breakout": 0.8,
            "divergence_bottom": 1.2,
            "buy_point_1": 1.1,
            "buy_point_3": 1.2,
            "overbought": 1.0,
            "desc": "震荡：反转+区间交易加权，趋势信号降权",
        },
        "冰点": {
            "bullish_bias": 1.8,
            "trend_following": 0.3,
            "breakout": 0.4,
            "divergence_bottom": 1.8,
            "buy_point_1": 2.0,
            "buy_point_3": 0.3,
            "overbought": 1.5,
            "desc": "冰点：极度超卖反转加权，趋势信号大幅降权",
        },
        "亢奋": {
            "bullish_bias": 0.6,
            "trend_following": 0.5,
            "breakout": 0.5,
            "divergence_bottom": 0.4,
            "buy_point_1": 0.3,
            "buy_point_3": 0.5,
            "overbought": 0.3,
            "desc": "亢奋：全面保守，警惕反转",
        },
    }
    return adjustments.get(state, adjustments["震荡"])

"""
A 股特化分析（涨跌停、连板）。
依赖: common (to_float)
"""

from common import to_float

_LIMIT_RATIOS = {"主板": 9.5, "创业板": 19.5, "科创板": 19.5, "北交所": 29.5}


def limit_analysis(records, board, quote):
    """涨跌停/连板分析。"""
    if len(records) < 10:
        return None

    limit_ratio = _LIMIT_RATIOS.get(board, 9.5)
    limit_up_price = to_float(quote.get("limit_up"))
    limit_down_price = to_float(quote.get("limit_down"))
    last_close = to_float(records[-1].get("close"))
    last_high = to_float(records[-1].get("high"))
    last_low = to_float(records[-1].get("low"))

    result = {
        "board": board,
        "limit_ratio": limit_ratio,
        "limit_up_price": limit_up_price,
        "limit_down_price": limit_down_price,
    }

    # 当前涨跌停状态
    if limit_up_price > 0 and last_close >= limit_up_price * 0.995:
        result["board_status"] = "封涨停"
    elif limit_down_price > 0 and last_low <= limit_down_price * 1.005:
        if last_close > limit_down_price * 1.01:
            result["board_status"] = "翘板(跌停打开)"
        else:
            result["board_status"] = "封跌停"
    elif last_high >= limit_up_price * 0.995 and last_close < limit_up_price * 0.995:
        gap = (limit_up_price - last_close) / limit_up_price * 100
        result["board_status"] = f"炸板(离涨停差{gap:.1f}%)"
    else:
        result["board_status"] = "正常交易"

    # 连板检测
    streak = _count_limit_streak(records, limit_ratio)
    result["limit_streak"] = streak

    if streak > 0:
        if streak == 1:
            result["streak_type"] = "首板"
        elif streak == 2:
            result["streak_type"] = "二板(连板确认)"
        elif streak <= 4:
            result["streak_type"] = f"高位{streak}板"
        else:
            result["streak_type"] = f"妖股({streak}连板)"

        # 连板量能分析
        recent_bars = records[-streak:]
        vols = [to_float(r.get("volume")) for r in recent_bars]
        if len(vols) >= 2 and vols[0] > 0:
            if all(vols[i] < vols[i - 1] for i in range(1, len(vols))):
                result["streak_volume"] = "缩量加速(强-惜售)"
            elif vols[-1] > vols[0] * 1.5:
                result["streak_volume"] = "放量分歧(弱-换手加大)"
            else:
                result["streak_volume"] = "量能稳定(中性)"
    else:
        result["streak_type"] = "无连板"

    # T+1 风险提示
    if streak >= 1 and result.get("board_status") == "封涨停":
        result["t1_risk"] = (
            "T+1隔夜风险：今日追板仓位明日方可卖出，需关注次日溢价和核按钮风险"
        )
    else:
        result["t1_risk"] = None

    return result


def _count_limit_streak(records, limit_ratio):
    """计算当前连板数。"""
    count = 0
    for i in range(len(records) - 1, -1, -1):
        r = records[i]
        close = to_float(r.get("close"))
        prev_close = to_float(records[i - 1].get("close")) if i > 0 else close
        if prev_close <= 0:
            continue
        chg_pct = (close / prev_close - 1) * 100
        if i == len(records) - 1:
            if chg_pct >= limit_ratio * 0.95:
                count = 1
        elif count > 0 and chg_pct >= limit_ratio * 0.95:
            count += 1
        else:
            break
    return count

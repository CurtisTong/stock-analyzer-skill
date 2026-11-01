"""
A 股特化分析（涨跌停、连板）。
依赖: common (to_float)
"""

from common import to_float

# v1.28.0：涨停判定阈值（涨跌幅百分比）。
# 原常量名 _LIMIT_RATIOS 且值已是打折后（主板 9.5），判定处又乘一次 0.95
# → 实际阈值 9.025%（创业板 18.525%），+9.1% 的**非涨停**被计为涨停板，
# 连续 12 天 +9.1% 会被报成"妖股(11 连板)"并触发 +12 分连板加分。
# 现在改为单一阈值口径：涨停比例留 0.2pp 舍入余量（通达信/同花顺惯例）。
_LIMIT_THRESHOLDS = {
    "主板": 9.8,
    "创业板": 19.8,
    "科创板": 19.8,
    "北交所": 29.8,
}
# ST 股涨跌停：主板 ±5%（创业板/科创板 ST 仍为 ±20%，与板块标准一致）
_ST_MAIN_THRESHOLD = 4.8


def _st_threshold(board: str) -> float | None:
    """ST 股的涨停判定阈值；非 ST 或 ST 创业板/科创板返回 None（用板块标准）。"""
    if board in ("创业板", "科创板"):
        return None  # ST 创业板/科创板仍按 ±20%
    return _ST_MAIN_THRESHOLD


def limit_analysis(records, board, quote):
    """涨跌停/连板分析。"""
    if len(records) < 10:
        return None

    limit_ratio = _LIMIT_THRESHOLDS.get(board, 9.8)
    limit_up_price = to_float(quote.get("limit_up"))
    limit_down_price = to_float(quote.get("limit_down"))
    last_close = to_float(records[-1].get("close"))
    last_high = to_float(records[-1].get("high"))
    last_low = to_float(records[-1].get("low"))

    # ST 识别（名称含 ST/*ST）：主板 ST 涨跌幅 ±5%，此前无识别 → ST 主板 +5%
    # 的连板永远计 0 板。
    name = str(quote.get("name", "") or "").upper()
    is_st = "ST" in name
    st_threshold = _st_threshold(board) if is_st else None
    streak_threshold = st_threshold if st_threshold is not None else limit_ratio
    # 封板状态用真实涨跌停价（quote 提供），不受此处阈值影响；
    # 阈值只用于连板计数（无 quote 涨跌停价时的兜底判定）。

    result = {
        "board": board,
        "limit_ratio": limit_ratio,
        "limit_up_price": limit_up_price,
        "limit_down_price": limit_down_price,
        "is_st": is_st,
    }

    # 当前涨跌停状态
    # v1.28.0 修复两处：
    # ① 容差从**比例** 0.5% 改为**绝对** 0.01 元（1 分钱最小变动单位）。
    #    0.5% 比例对茅台级价位意味着 8 元钱的误差——实测 close=1631
    #    （涨停价 1639，差 8 元 / 0.49%）被判"封涨停"，实际未触板。
    # ② quote 的涨跌停价是**今天**的，而 records[-1] 可能是历史 K 线
    #    （数据源不更新 / stale）——二者日期错配时，昨日的板会被判成今日的板。
    #    现在校验 K 线最后一日与行情日的一致性，不一致则不判定封板状态。
    kline_day = str(records[-1].get("day", "") or "")
    quote_day = str(quote.get("day", "") or "")
    same_day = (not kline_day or not quote_day) or (kline_day == quote_day)
    if not same_day:
        result["board_status"] = "正常交易"
        result["kline_stale"] = True
        result["kline_day"] = kline_day
        result["quote_day"] = quote_day
    elif limit_up_price > 0 and last_close >= limit_up_price - 0.01:
        result["board_status"] = "封涨停"
    elif limit_down_price > 0 and last_low <= limit_down_price + 0.01:
        if last_close > limit_down_price + 0.01:
            result["board_status"] = "翘板(跌停打开)"
        else:
            result["board_status"] = "封跌停"
    elif limit_up_price > 0 and last_high >= limit_up_price - 0.01 and last_close < limit_up_price - 0.01:
        gap = (limit_up_price - last_close) / limit_up_price * 100
        result["board_status"] = f"炸板(离涨停差{gap:.1f}%)"
    else:
        result["board_status"] = "正常交易"

    # 连板检测
    streak = _count_limit_streak(records, streak_threshold)
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
        result["t1_risk"] = "T+1隔夜风险：今日追板仓位明日方可卖出，需关注次日溢价和核按钮风险"
    else:
        result["t1_risk"] = None

    return result


def _count_limit_streak(records, limit_ratio):
    """计算当前连板数。

    limit_ratio 是**涨跌幅百分比阈值**（主板 9.8 / 创业板 19.8 / 北交所 29.8，
    ST 主板 4.8）。v1.28.0 修复：原实现又乘一次 0.95 → 主板实际阈值 9.025%，
    +9.1% 的非涨停被计板（连续 12 天 +9.1% 报"妖股 11 连板"）。
    """
    count = 0
    for i in range(len(records) - 1, -1, -1):
        r = records[i]
        close = to_float(r.get("close"))
        prev_close = to_float(records[i - 1].get("close")) if i > 0 else close
        if prev_close <= 0:
            continue
        chg_pct = (close / prev_close - 1) * 100
        if i == len(records) - 1:
            if chg_pct >= limit_ratio:
                count = 1
        elif count > 0 and chg_pct >= limit_ratio:
            count += 1
        else:
            break
    return count

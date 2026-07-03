"""
买卖信号汇总。
无内部依赖。
"""

_LIMIT_UP_RETREAT = 20  # 涨停家数<20 判为退潮
_LIMIT_DOWN_FREEZING = 50  # 跌停>50 判为冰点
_CONTINUOUS_HEIGHT_LOW = 2  # 连板高度<=2 判为接力生态恶化


def _signal_limit_up_down(limit_up, limit_down):
    """涨停家数/跌停家数信号。

    Returns:
        dict: {signal_name: signal_desc} 或空 dict
    """
    signals = {}
    # 退潮期信号（徐翔建议：涨停家数<20家）
    if limit_up < _LIMIT_UP_RETREAT and limit_up > 0:
        signals["退潮"] = f"市场退潮(涨停{limit_up}家<20)"
    # 冰点期信号（养家建议：跌停>50家）
    if limit_down > _LIMIT_DOWN_FREEZING:
        signals["冰点"] = f"市场冰点(跌停{limit_down}家)"
    return signals


def _signal_continuous_height(continuous_height):
    """连板高度信号。

    Returns:
        dict: {signal_name: signal_desc} 或空 dict
    """
    signals = {}
    # 接力生态恶化（赵老哥建议：连板高度<2板）
    if continuous_height <= _CONTINUOUS_HEIGHT_LOW and continuous_height > 0:
        signals["接力恶化"] = f"接力生态恶化(连板{continuous_height}板)"
    return signals


def _signal_advance_decline(up_ratio):
    """涨跌比信号。

    Returns:
        dict: {signal_name: signal_desc} 或空 dict
    """
    signals = {}
    if up_ratio > 2:
        signals["普涨"] = f"市场普涨(涨跌比{up_ratio})"
    return signals


def _generate_signals(features, market_breadth=None):
    """汇总买卖信号。

    Args:
        features: 技术指标特征
        market_breadth: 市场宽度数据（可选）
    """
    buy, sell = [], []
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    kdj = features.get("kdj") or {}
    boll = features.get("bollinger") or {}
    rsi_data = features.get("rsi", {})
    vol = features.get("volume") or {}
    vol_price = vol.get("volume_price", "")
    vol_vp = vol.get("volume_price_signal", 0)
    divergence = macd.get("divergence", "")

    # 趋势判断（用于过滤虚假超卖信号）
    wave = features.get("wave", "")
    ma_alignment = ma.get("alignment", "")
    is_downtrend = (
        "下跌" in wave
        or ma_alignment == "空头排列"
        or (vol_vp == -1 and "出货" in vol_price)
    )

    # 缩量信号（作手新一建议：缩量下跌>放量下跌）
    shrink_signal = vol.get("shrink_signal", 0)
    shrink_desc = vol.get("shrink_desc", "")

    # 市场宽度信号（徐翔、赵老哥、养家建议）
    if market_breadth:
        limit_up = market_breadth.get("limit_up_count", 0)
        limit_down = market_breadth.get("limit_down_count", 0)
        continuous_height = market_breadth.get("continuous_limit_height", 0)
        up_ratio = market_breadth.get("up_ratio", 0)

        # 涨停/跌停信号
        for desc in _signal_limit_up_down(limit_up, limit_down).values():
            sell.append(desc)

        # 连板高度信号
        for desc in _signal_continuous_height(continuous_height).values():
            sell.append(desc)

        # 涨跌比信号
        for desc in _signal_advance_decline(up_ratio).values():
            buy.append(desc)

    # 买入信号
    if macd.get("signal") == 1:
        buy.append("MACD金叉")
    if divergence == "底背离(看涨)":
        buy.append("MACD底背离")
    # KDJ超卖金叉：下跌趋势中降级为"待确认"
    if "金叉" in kdj.get("signal", "") and "超卖" in kdj.get("signal", ""):
        if is_downtrend:
            buy.append("KDJ超卖区金叉(待确认-下跌趋势)")
        else:
            buy.append("KDJ超卖区金叉")
    if boll.get("position", 0.5) < 0.2 and "收窄" in boll.get("bandwidth_desc", ""):
        buy.append("BOLL下轨+收窄(变盘)")
    # RSI超卖：下跌趋势中降级
    if rsi_data.get("rsi", 50) < 35:
        if is_downtrend:
            buy.append(f"RSI超卖({rsi_data.get('rsi')})-下跌趋势待确认")
        else:
            buy.append(f"RSI超卖({rsi_data.get('rsi')})")
    if vol_vp == 1 and "放量上涨" in vol_price:
        buy.append("放量上涨(资金介入)")
    # 连续缩量信号（作手新一建议）
    if shrink_signal == 1 and "连续缩量" in shrink_desc:
        buy.append("连续缩量(抛压减轻)")

    # 趋势警告：当存在出货信号时，超卖信号不可靠
    if is_downtrend and (
        rsi_data.get("rsi", 50) < 35 or "超卖" in kdj.get("signal", "")
    ):
        sell.append("⚠️下跌趋势中超卖信号失效")

    # 缠论买卖点信号
    chan_data = features.get("chan_theory") or {}
    if chan_data.get("valid"):
        maidain = chan_data.get("maidian", {})
        for bp in maidain.get("buy_points", []):
            buy.append(f"缠论{bp['type']}")
        for sp in maidain.get("sell_points", []):
            sell.append(f"缠论{sp['type']}")
        beichi = chan_data.get("beichi", {})
        if beichi.get("summary", "").startswith("检测到底背驰"):
            buy.append("缠论底背驰")
        elif "顶背驰" in beichi.get("summary", ""):
            sell.append("缠论顶背驰")

    # 本土战法信号
    local_patterns = features.get("local_patterns") or {}
    for lp in local_patterns.get("patterns", []):
        if lp["type"] == "看涨":
            buy.append(lp["name"])
        elif lp["type"] == "看跌":
            sell.append(lp["name"])

    # 估值信号（反追涨杀跌核心机制）
    valuation = features.get("valuation") or {}
    pe = valuation.get("pe", 0)
    pb = valuation.get("pb", 0)
    pe_pct = valuation.get("pe_percentile", 50)  # PE 行业相对分位（0-100）
    peg = valuation.get("peg", 0)

    if pe > 0:
        # 估值底信号：PE 行业低位 + PB 低位 → 价值区间
        if pe_pct <= 20 and 0 < pb <= 2:
            buy.append(f"估值底(PE行业{pe_pct:.0f}%分位,PB={pb:.1f})")
        elif pe_pct <= 30:
            buy.append(f"估值偏低(PE行业{pe_pct:.0f}%分位)")
        # 估值顶信号：PE 行业高位 → 高估风险
        if pe_pct >= 80:
            sell.append(f"估值顶(PE行业{pe_pct:.0f}%分位)")
        elif pe_pct >= 65 and peg > 2.5:
            sell.append(f"估值偏高(PE行业{pe_pct:.0f}%分位,PEG={peg:.1f})")

    # 卖出信号
    if macd.get("signal") == -1:
        sell.append("MACD死叉")
    if divergence == "顶背离(看跌)":
        sell.append("MACD顶背离")
    if "死叉" in kdj.get("signal", "") or "超买" in kdj.get("signal", ""):
        sell.append(f"KDJ{kdj.get('signal')}")
    if boll.get("position", 0.5) > 0.8:
        sell.append("BOLL触及上轨")
    if rsi_data.get("rsi", 50) > 70:
        sell.append(f"RSI超买({rsi_data.get('rsi')})")
    if vol_vp == -1 and "出货" in vol_price:
        sell.append("放量下跌(主力出货)")

    return buy, sell

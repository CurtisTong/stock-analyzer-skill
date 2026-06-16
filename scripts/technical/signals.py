"""
买卖信号汇总。
无内部依赖。
"""


def _generate_signals(features):
    """汇总买卖信号。"""
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

    # 买入信号
    if macd.get("signal") == 1:
        buy.append("MACD金叉")
    if divergence == "底背离(看涨)":
        buy.append("MACD底背离")
    if "金叉" in kdj.get("signal", "") and "超卖" in kdj.get("signal", ""):
        buy.append("KDJ超卖区金叉")
    if boll.get("position", 0.5) < 0.2 and "收窄" in boll.get("bandwidth_desc", ""):
        buy.append("BOLL下轨+收窄(变盘)")
    if rsi_data.get("rsi", 50) < 35:
        buy.append(f"RSI超卖({rsi_data.get('rsi')})")
    if vol_vp == 1 and "放量上涨" in vol_price:
        buy.append("放量上涨(资金介入)")

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

"""三类买卖点识别。"""


def chan_maidian(
    merged_bars,
    bi_list,
    zs_list,
    closes,
    beichi=None,
    pullback_pct=0.02,
    highs=None,
    lows=None,
):
    """
    识别缠论三类买卖点。
    一买：离开最后一个中枢后的底背驰结束点
    二买：一买后不创新低的次低点
    三买：突破中枢后，回踩不落入中枢的点

    Args:
        pullback_pct: 回踩容忍度百分比（默认 2%）
        highs: K 线最高价序列（可选，提供时启用 ATR 动态容差）
        lows: K 线最低价序列（可选，同上）

    I9: 回踩容忍度优先基于 ATR 动态计算（半个 ATR），
    未提供 highs/lows 时回退到 pullback_pct 百分比。

    三买/三卖的回踩/反弹判定用**笔口径**：回踩低点 = 离开中枢后最近
    向下笔的 low（分型 bar 的 K 线低点），反弹高点 = 最近向上笔的 high。
    笔 low/high 天然是 K 线极值口径，盘中破位收盘拉回不构成"不落入"；
    highs/lows 参数仅用于 ATR 置信度容差。

    Args:
        beichi: chan_beichi 的返回结果。P2-C4 修复：一买/一卖必须依赖背驰结果，
            无背驰不构成一买/一卖（缠论标准定义）。未提供 beichi 时仅退化为
            "中枢下方+下跌笔结束"的弱信号并标注 confidence=低。
    """
    if not zs_list or not bi_list or len(closes) < 20:
        return {"buy_points": [], "sell_points": [], "summary": "数据不足"}

    last_zs = zs_list[-1]
    last_close = closes[-1]
    # bi 的 start_idx/end_idx 是分型在 merged_bars 中的**列表位置**（fenxing 的 idx），
    # 不是 merged bar 携带的原始 records 索引——两者在发生包含合并后必然不同，
    # 时效窗口必须与分型同一坐标系（原用 merged_bars[-1]["idx"] 导致一买/一卖恒失效）。
    last_idx = len(merged_bars) - 1 if merged_bars else len(closes) - 1

    trend_beichi = (beichi or {}).get("trend_beichi")
    range_beichi = (beichi or {}).get("range_beichi", [])
    # 盘整底背驰也算一买的背驰确认
    has_bottom_beichi = trend_beichi == "底背驰(看涨)" or any("看涨" in rb.get("type", "") for rb in range_beichi)
    has_top_beichi = trend_beichi == "顶背驰(看跌)" or any("看跌" in rb.get("type", "") for rb in range_beichi)
    # 背驰来源标注：趋势背驰（力度对比中枢前后走势）强于盘整背驰（力度对比中枢前后段），
    # 描述里必须写清是哪一种，避免把盘整背驰说成"底背驰"。
    bottom_source = "趋势底背驰" if trend_beichi == "底背驰(看涨)" else ("盘整底背驰" if has_bottom_beichi else "")
    top_source = "趋势顶背驰" if trend_beichi == "顶背驰(看跌)" else ("盘整顶背驰" if has_top_beichi else "")

    buy_points = []
    sell_points = []

    # ── 一买：离开中枢的底背驰段结束 ──
    # P2-C4: 缠论标准要求"离开中枢的下跌走势出现底背驰后的结束点"，无背驰非一买。
    if last_close < last_zs["zd"]:
        down_bis = [b for b in bi_list if b["direction"] == "down"]
        if down_bis:
            last_down = down_bis[-1]
            if last_down["end_idx"] >= last_idx - 5:
                if has_bottom_beichi:
                    buy_points.append(
                        {
                            "type": "一买",
                            "desc": f"离开中枢(ZD={last_zs['zd']})后{bottom_source}结束",
                            "confidence": "中",
                        }
                    )
                elif beichi is None:
                    # 未提供背驰结果，退化为弱信号并降级置信度
                    buy_points.append(
                        {
                            "type": "一买(弱)",
                            "desc": "离开中枢后下跌笔结束（未确认背驰）",
                            "confidence": "低",
                        }
                    )

    # ── 二买：中枢下方 + 近期次低高于前低（不依赖一买） ──
    if last_close < last_zs["zd"]:
        down_bis = [b for b in bi_list if b["direction"] == "down"]
        if len(down_bis) >= 2:
            prev_low = down_bis[-2]["low"]
            curr_low = down_bis[-1]["low"]
            # 次低高于前低 → 下跌力度衰减
            if curr_low > prev_low and last_close > prev_low:
                buy_points.append(
                    {
                        "type": "二买",
                        "desc": f"中枢下方次低({curr_low})高于前低({prev_low})",
                        "confidence": "中",
                    }
                )

    # ── 三买：突破中枢后回踩不入 ──
    # 缠论口径：回踩是"离开中枢后的向下笔"，回踩低点（笔 low）不落入中枢（> ZG）。
    # 笔 low 来自分型 bar 的 K 线低点，天然是 low 口径（盘中破位收盘拉回的分型不成立）。
    above_zs = closes[-1] > last_zs["zg"]
    bi_end = last_zs.get("bi_end", len(bi_list) - 1)
    pullback_bis = [b for b in bi_list[bi_end + 1 :] if b["direction"] == "down"]
    if above_zs and pullback_bis and pullback_bis[-1]["low"] > last_zs["zg"]:
        # I9: 置信度容差优先用 ATR 动态计算（需提供 highs/lows），否则回退百分比
        if highs and lows:
            from technical.volatility import compute_atr

            atr = compute_atr(highs, lows, closes)
            tolerance = atr * 0.5 if atr > 0 else last_zs["zg"] * pullback_pct
        else:
            tolerance = last_zs["zg"] * pullback_pct
        pullback_low = pullback_bis[-1]["low"]
        buy_points.append(
            {
                "type": "三买",
                "desc": f"突破中枢上沿(ZG={last_zs['zg']})后回踩({pullback_low})不落入",
                "confidence": ("高" if last_close > last_zs["zg"] + tolerance else "中"),
            }
        )

    # ── 一卖：离开中枢的顶背驰段结束 ──
    # P2-C4: 同一买，需顶背驰确认
    if last_close > last_zs["zg"]:
        up_bis = [b for b in bi_list if b["direction"] == "up"]
        if up_bis:
            last_up = up_bis[-1]
            if last_up["end_idx"] >= last_idx - 5:
                if has_top_beichi:
                    sell_points.append(
                        {
                            "type": "一卖",
                            "desc": f"离开中枢(ZG={last_zs['zg']})后{top_source}",
                            "confidence": "中",
                        }
                    )
                elif beichi is None:
                    sell_points.append(
                        {
                            "type": "一卖(弱)",
                            "desc": "离开中枢后上涨笔结束（未确认背驰）",
                            "confidence": "低",
                        }
                    )

    # ── 二卖：中枢上方 + 近期次低于前高（不创新高） ──
    if last_close > last_zs["zg"]:
        up_bis = [b for b in bi_list if b["direction"] == "up"]
        if len(up_bis) >= 2:
            prev_high = up_bis[-2]["high"]
            curr_high = up_bis[-1]["high"]
            # 次高低于前高 → 上涨力度衰减
            if curr_high < prev_high and last_close < prev_high:
                sell_points.append(
                    {
                        "type": "二卖",
                        "desc": f"中枢上方次高({curr_high})低于前高({prev_high})",
                        "confidence": "中",
                    }
                )

    # ── 三卖：跌破中枢后反弹不入 ──
    # 缠论口径：反弹是"离开中枢后的向上笔"，反弹高点（笔 high）不落入中枢（< ZD）。
    below_zs = closes[-1] < last_zs["zd"]
    rebound_bis = [b for b in bi_list[bi_end + 1 :] if b["direction"] == "up"]
    if below_zs and rebound_bis and rebound_bis[-1]["high"] < last_zs["zd"]:
        # I9: 置信度容差优先用 ATR 动态计算（需提供 highs/lows），否则回退百分比
        if highs and lows:
            from technical.volatility import compute_atr

            atr = compute_atr(highs, lows, closes)
            tolerance = atr * 0.5 if atr > 0 else last_zs["zd"] * pullback_pct
        else:
            tolerance = last_zs["zd"] * pullback_pct
        rebound_high = rebound_bis[-1]["high"]
        sell_points.append(
            {
                "type": "三卖",
                "desc": f"跌破中枢下沿(ZD={last_zs['zd']})后反弹({rebound_high})不入",
                "confidence": ("高" if last_close < last_zs["zd"] - tolerance else "中"),
            }
        )

    summary_parts = []
    if buy_points:
        summary_parts.append(f"买点: {', '.join(bp['type'] for bp in buy_points)}")
    if sell_points:
        summary_parts.append(f"卖点: {', '.join(sp['type'] for sp in sell_points)}")
    summary = "; ".join(summary_parts) if summary_parts else "当前无明确缠论买卖点"

    return {
        "buy_points": buy_points,
        "sell_points": sell_points,
        "summary": summary,
    }

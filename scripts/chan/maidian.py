"""三类买卖点识别。"""


def chan_maidian(merged_bars, bi_list, zs_list, closes, beichi=None, pullback_pct=0.02):
    """
    识别缠论三类买卖点。
    一买：离开最后一个中枢后的底背驰结束点
    二买：一买后不创新低的次低点
    三买：突破中枢后，回踩不落入中枢的点

    Args:
        pullback_pct: 回踩容忍度（默认 2%，基于 ATR 或百分比判断回踩是否接近中枢边界）

    Args:
        beichi: chan_beichi 的返回结果。P2-C4 修复：一买/一卖必须依赖背驰结果，
            无背驰不构成一买/一卖（缠论标准定义）。未提供 beichi 时仅退化为
            "中枢下方+下跌笔结束"的弱信号并标注 confidence=低。
    """
    if not zs_list or not bi_list or len(closes) < 20:
        return {"buy_points": [], "sell_points": [], "summary": "数据不足"}

    last_zs = zs_list[-1]
    last_close = closes[-1]
    # bi 的 end_idx 基于 merged_bars 的 idx 字段，用 merged_bars 最后一个 idx 作为参考
    last_idx = merged_bars[-1]["idx"] if merged_bars else len(closes) - 1

    trend_beichi = (beichi or {}).get("trend_beichi")
    range_beichi = (beichi or {}).get("range_beichi", [])
    # 盘整底背驰也算一买的背驰确认
    has_bottom_beichi = trend_beichi == "底背驰(看涨)" or any(
        "看涨" in rb.get("type", "") for rb in range_beichi
    )
    has_top_beichi = trend_beichi == "顶背驰(看跌)" or any(
        "看跌" in rb.get("type", "") for rb in range_beichi
    )

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
                            "desc": f"离开中枢(ZD={last_zs['zd']})后底背驰结束",
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
    above_zs = closes[-1] > last_zs["zg"]
    recent_low = min(closes[-5:]) if len(closes) >= 5 else closes[-1]
    if above_zs and recent_low > last_zs["zd"]:
        # 判断是否有回踩动作：近期价格曾接近 ZG（回踩痕迹）
        # 回踩定义为：价格距 ZG 在容差范围内（可略高或略低）
        pullback_tolerance = last_zs["zg"] * pullback_pct
        near_zs = any(
            abs(c - last_zs["zg"]) <= pullback_tolerance for c in closes[-10:]
        )
        if near_zs:
            buy_points.append(
                {
                    "type": "三买",
                    "desc": f"突破中枢上沿(ZG={last_zs['zg']})后回踩不落入",
                    "confidence": "高" if last_close > last_zs["zg"] * 1.02 else "中",
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
                            "desc": f"离开中枢(ZG={last_zs['zg']})后顶背驰",
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
    below_zs = closes[-1] < last_zs["zd"]
    recent_high = max(closes[-5:]) if len(closes) >= 5 else closes[-1]
    if below_zs and recent_high < last_zs["zg"]:
        # 判断是否有反弹动作：近期价格曾接近 ZD（反弹痕迹）
        pullback_tolerance = last_zs["zd"] * pullback_pct
        near_zs = any(
            abs(c - last_zs["zd"]) <= pullback_tolerance for c in closes[-10:]
        )
        if near_zs:
            sell_points.append(
                {
                    "type": "三卖",
                    "desc": f"跌破中枢下沿(ZD={last_zs['zd']})后反弹不入",
                    "confidence": "高" if last_close < last_zs["zd"] * 0.98 else "中",
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

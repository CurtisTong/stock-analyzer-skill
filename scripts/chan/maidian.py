"""三类买卖点识别。"""


def chan_maidian(merged_bars, bi_list, zs_list, closes):
    """
    识别缠论三类买卖点。
    一买：离开最后一个中枢后的底背驰结束点
    二买：一买后不创新低的次低点
    三买：突破中枢后，回踩不落入中枢的点
    """
    if not zs_list or not bi_list or len(closes) < 20:
        return {"buy_points": [], "sell_points": [], "summary": "数据不足"}

    last_zs = zs_list[-1]
    last_close = closes[-1]
    # bi 的 end_idx 基于 merged_bars 的 idx 字段，用 merged_bars 最后一个 idx 作为参考
    last_idx = merged_bars[-1]["idx"] if merged_bars else len(closes) - 1

    buy_points = []
    sell_points = []

    # ── 一买：离开中枢的底背驰段结束 ──
    # 条件：价格在中枢下方 + 下跌笔的结束点 + 出现底背驰
    if last_close < last_zs["zd"]:
        down_bis = [b for b in bi_list if b["direction"] == "down"]
        if down_bis:
            last_down = down_bis[-1]
            # 判断是否为背驰段结尾
            if last_down["end_idx"] >= last_idx - 5:
                buy_points.append(
                    {
                        "type": "一买",
                        "desc": f"离开中枢(ZD={last_zs['zd']})后底背驰结束",
                        "confidence": "中",
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
        # 回踩定义为：价格距 ZG 在 2% 以内（可略高或略低）
        pullback_tolerance = last_zs["zg"] * 0.02
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
    if last_close > last_zs["zg"]:
        up_bis = [b for b in bi_list if b["direction"] == "up"]
        if up_bis:
            last_up = up_bis[-1]
            if last_up["end_idx"] >= last_idx - 5:
                sell_points.append(
                    {
                        "type": "一卖",
                        "desc": f"离开中枢(ZG={last_zs['zg']})后顶背驰",
                        "confidence": "中",
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
        pullback_tolerance = last_zs["zd"] * 0.02
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

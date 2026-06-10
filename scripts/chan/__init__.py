"""
缠中说禅理论（缠论）模块。
包含：K线包含处理 → 分型 → 笔 → 线段 → 中枢 → 买卖点 → 背驰检测。
"""
from .merge import chan_merge_inclusions
from .fenxing import chan_fenxing
from .bi import chan_bi
from .xianduan import chan_xianduan
from .zhongshu import chan_zhongshu
from .macd import _macd_area
from .beichi import chan_beichi
from .maidian import chan_maidian
from common import to_float
from technical.core import _ema_series


def chan_full_analysis(records):
    """一次调用返回完整缠论分析结果。"""
    if len(records) < 30:
        return {"error": "K线数量不足(<30)，缠论分析不可靠", "valid": False}

    # 提取价格数据
    closes = [to_float(r.get("close")) for r in records if to_float(r.get("close")) > 0]

    if len(closes) < 30:
        return {"error": "有效K线不足", "valid": False}

    # 1. 包含处理
    merged = chan_merge_inclusions(records)
    merge_ratio = (len(records) - len(merged)) / len(records) * 100 if records else 0

    # 2. 分型
    fenxing = chan_fenxing(merged)
    top_fx = [f for f in fenxing if f["type"] == "顶"]
    bottom_fx = [f for f in fenxing if f["type"] == "底"]

    # 3. 笔
    bi_list = chan_bi(merged)
    up_bis = [b for b in bi_list if b["direction"] == "up"]
    down_bis = [b for b in bi_list if b["direction"] == "down"]

    # 4. 线段
    xd_list = chan_xianduan(bi_list)

    # 5. 中枢
    zs_list = chan_zhongshu(xd_list)

    # 6. 背驰
    beichi = chan_beichi(bi_list, zs_list, closes)

    # 7. 买卖点
    maidain = chan_maidian(merged, bi_list, zs_list, closes)

    # 8. 当前位置描述
    last_close = closes[-1]
    if zs_list:
        last_zs = zs_list[-1]
        if last_close > last_zs["zg"]:
            position = f"中枢上方({last_zs['zg']}之上)"
        elif last_close < last_zs["zd"]:
            position = f"中枢下方({last_zs['zd']}之下)"
        else:
            position = f"中枢内部(ZG={last_zs['zg']}, ZD={last_zs['zd']})"
    else:
        position = "无中枢，处于原始走势中"

    valid = len(bi_list) >= 3

    return {
        "valid": valid,
        "merged_count": len(merged),
        "original_count": len(records),
        "merge_ratio_pct": round(merge_ratio, 1),
        "fenxing_count": len(fenxing),
        "top_fenxing": len(top_fx),
        "bottom_fenxing": len(bottom_fx),
        "bi_count": len(bi_list),
        "up_bi": len(up_bis),
        "down_bi": len(down_bis),
        "xianduan_count": len(xd_list),
        "zhongshu_list": zs_list,
        "zhongshu_count": len(zs_list),
        "beichi": beichi,
        "maidian": maidain,
        "current_position": position,
    }


__all__ = [
    "chan_merge_inclusions",
    "chan_fenxing",
    "chan_bi",
    "chan_xianduan",
    "chan_zhongshu",
    "_macd_area",
    "_ema_series",
    "chan_beichi",
    "chan_maidian",
    "chan_full_analysis",
]

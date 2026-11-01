"""
缠中说禅理论（缠论）模块。
包含：K线包含处理 → 分型 → 笔 → 线段 → 中枢 → 买卖点 → 背驰检测。

⚠️ 非标准实现声明（2026-11 更新）：
本模块为缠论的简化实现，多处核心算法与缠论标准定义不一致：
- 线段划分已采用特征序列分型判定（chan/xianduan.py，v2.5.0 重构），
  但不区分第一种/第二种情况（缺口二次确认），线段划分偏严格；
- 中枢为笔中枢（chan/zhongshu.py，v2.5.0 起由连续 3 笔重叠构成，
  与 beichi/maidian 的笔级别操作一致），非线段中枢；
- 背驰检测比较同向笔的同色 MACD 柱面积（chan/area.py side 参数）；
- 一买/一卖依赖背驰结果（chan/maidian.py，P2-C4）。
因此输出的买卖点信号可能与标准缠论软件（通达信缠论指标等）结果有差异。
仅供学习参考，不作为交易依据。完整标准实现待后续重构。
"""

from .merge import chan_merge_inclusions
from .fenxing import chan_fenxing
from .bi import chan_bi
from .xianduan import chan_xianduan
from .zhongshu import chan_zhongshu
from .area import (
    _macd_area,
)  # v1.3.2: was chan/macd.py, renamed to avoid clash with technical/macd.py
from .beichi import chan_beichi
from .maidian import chan_maidian
from common import to_float
from technical.core import _ema_series


def chan_full_analysis(records):
    """一次调用返回完整缠论分析结果。"""
    if len(records) < 30:
        return {"error": "K线数量不足(<30)，缠论分析不可靠", "valid": False}

    # 提取价格数据（不过滤零值，保持与 records 索引对齐）
    closes = [to_float(r.get("close")) for r in records]

    if len(closes) < 30:
        return {"error": "有效K线不足", "valid": False}

    # 1. 包含处理
    merged = chan_merge_inclusions(records)
    merge_ratio = (len(records) - len(merged)) / len(records) * 100 if records else 0

    # P2-C3: 构建 merged bar date → closes 索引 映射，供背驰检测将 merged 坐标系
    # 的 bi idx 正确映射到 closes 坐标系（原直接减 _dea_offset 因坐标系不一致会错位）。
    date_to_close_idx = {}
    for i, r in enumerate(records):
        d = r.get("day", "")
        if d and d not in date_to_close_idx:
            date_to_close_idx[d] = i

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

    # 5. 中枢（笔中枢：连续 3 笔重叠区间，与 beichi/maidian 的 bi_list 操作层级一致）
    zs_list = chan_zhongshu(bi_list)

    # 6. 背驰
    beichi = chan_beichi(bi_list, zs_list, closes, date_to_close_idx)

    # 7. 买卖点（传入 highs/lows：启用 ATR 动态回踩容差与 low/high 回踩口径）
    highs = [to_float(r.get("high")) for r in records]
    lows = [to_float(r.get("low")) for r in records]
    maidain = chan_maidian(merged, bi_list, zs_list, closes, beichi, highs=highs, lows=lows)

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

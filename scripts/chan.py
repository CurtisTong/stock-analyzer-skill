#!/usr/bin/env python3
"""
缠中说禅理论（缠论）实现。
包含：K线包含处理 → 分型 → 笔 → 线段 → 中枢 → 买卖点 → 背驰检测。
用于 A 股技术分析，纯算法实现，不依赖外部数据。

此文件为兼容层，实际实现已拆分到 chan/ 模块。
"""
from chan import (
    chan_merge_inclusions,
    chan_fenxing,
    chan_bi,
    chan_xianduan,
    chan_zhongshu,
    _macd_area,
    chan_beichi,
    chan_maidian,
    chan_full_analysis,
)

__all__ = [
    "chan_merge_inclusions",
    "chan_fenxing",
    "chan_bi",
    "chan_xianduan",
    "chan_zhongshu",
    "_macd_area",
    "chan_beichi",
    "chan_maidian",
    "chan_full_analysis",
]


# ── 命令行快速测试 ──
if __name__ == "__main__":
    import sys
    import json
    from common import normalize_quote_code
    from kline import fetch as fetch_kline

    if len(sys.argv) < 2:
        print("用法: python3 chan.py <code>")
        sys.exit(1)

    code = normalize_quote_code(sys.argv[1])
    records = fetch_kline(code, 240, 250)
    result = chan_full_analysis(records)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

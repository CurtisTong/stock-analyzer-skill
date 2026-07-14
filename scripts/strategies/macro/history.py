"""历史宏观数据拉取（为 v2.9 回测准备，v2.8 仅落盘）。

拉取 VIX/TLT/沪深300 历史 N 年日线，对齐日期后落盘 data/macro_history.csv。
v2.9 将构建 HistoricalMacroGate 读取此文件做日期回放回测。

用法:
    python3 -m strategies.macro.history           # 默认拉 10 年
    python3 -m strategies.macro.history --years 5  # 拉 5 年
"""

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

HISTORY_FILE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "macro_history.csv"
)


def fetch_history(years: int = 10) -> str:
    """拉取并落盘历史宏观数据，返回文件路径。

    数据源：
    - VIX (^VIX) 和 TLT：yfinance Ticker.history()
    - 沪深300 (sh000300)：data.get_kline（复用 eastmoney/sina fetcher + 磁盘缓存）

    落盘格式 (CSV)：
    date, vix, tlt, csi300_close, csi300_vol_20d

    Args:
        years: 拉取年数（默认 10）

    Returns:
        落盘文件路径字符串
    """
    import yfinance as yf

    end = datetime.now()
    start = end - timedelta(days=years * 365)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # 美股维度：VIX + TLT
    vix_hist = yf.Ticker("^VIX").history(start=start_str, end=end_str)
    tlt_hist = yf.Ticker("TLT").history(start=start_str, end=end_str)

    vix_map = {}
    for ts, row in vix_hist.iterrows():
        vix_map[ts.strftime("%Y-%m-%d")] = round(float(row["Close"]), 2)

    tlt_map = {}
    for ts, row in tlt_hist.iterrows():
        tlt_map[ts.strftime("%Y-%m-%d")] = round(float(row["Close"]), 2)

    # A 股维度：沪深300 K线
    from data import get_kline

    bars = get_kline("sh000300", scale=240, datalen=years * 252)
    csi300_map = {}
    if bars:
        for b in bars:
            csi300_map[b.day] = float(b.close)

    # 对齐日期（取三源并集，缺失填空）
    all_dates = sorted(set(vix_map) | set(tlt_map) | set(csi300_map))
    window = 20  # 20 日年化波动率窗口

    closes = []
    rows_written = 0
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "vix", "tlt", "csi300_close", "csi300_vol_20d"])

        for date_str in all_dates:
            close = csi300_map.get(date_str)
            if close is not None:
                closes.append(close)

            # 计算 20 日年化波动率（需要至少 21 个收盘价）
            vol_20d = ""
            if len(closes) >= window + 1:
                recent = closes[-(window + 1) :]
                returns = [
                    (recent[i] - recent[i - 1]) / recent[i - 1]
                    for i in range(1, len(recent))
                    if recent[i - 1] > 0
                ]
                if len(returns) >= 2:
                    import statistics

                    daily_std = statistics.stdev(returns)
                    vol_20d = round(daily_std * (252**0.5) * 100, 2)

            vix_val = vix_map.get(date_str, "")
            tlt_val = tlt_map.get(date_str, "")

            # 只写至少有一个指标有值的行
            if vix_val != "" or tlt_val != "" or close is not None:
                writer.writerow([
                    date_str,
                    vix_val,
                    tlt_val,
                    round(close, 2) if close is not None else "",
                    vol_20d,
                ])
                rows_written += 1

    logger.info("历史宏观数据落盘: %s (%d 行)", HISTORY_FILE, rows_written)
    return str(HISTORY_FILE)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="拉取历史宏观数据（VIX/TLT/沪深300）")
    parser.add_argument(
        "--years", type=int, default=10, help="拉取年数（默认 10）"
    )
    args = parser.parse_args()

    path = fetch_history(years=args.years)
    print(f"✅ 历史数据已落盘: {path}")

"""
MA10/MA21 金叉 + 放量突破组合策略

⚠️ 样本量有限（基于 5 只股票回测优化），统计显著性不足，仅供参考。
回测结果：71.4% 胜率，+6.39% 平均收益（样本内），不构成投资建议。
建议：使用前用 --backtest 在更大样本（50+ 股票）上验证。

参数：MA10/MA21 金叉 + 放量 2.5x 突破 + 持仓 5 天 + 止损 -5%

作者：stock-analyzer-skill
版本：1.0.0
"""

import sys
import os

# 添加 scripts 目录到路径
scripts_dir = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from common import to_float


def calc_ma(closes, period):
    """计算简单移动平均线"""
    if len(closes) < period:
        return []
    result = []
    for i in range(period - 1, len(closes)):
        result.append(sum(closes[i - period + 1 : i + 1]) / period)
    return result


def detect_ma_volume_signal(
    records, closes, volumes, ma_short=10, ma_long=21, vol_threshold=2.5
):
    """
    检测 MA 金叉 + 放量突破信号

    Args:
        records: K 线数据列表
        closes: 收盘价序列
        volumes: 成交量序列
        ma_short: 短期均线周期（默认 10）
        ma_long: 长期均线周期（默认 21）
        vol_threshold: 成交量阈值倍数（默认 2.5）

    Returns:
        list: 信号列表
    """
    if len(closes) < ma_long + 5 or len(volumes) < ma_long + 5:
        return []

    ma_short_series = calc_ma(closes, ma_short)
    ma_long_series = calc_ma(closes, ma_long)

    if len(ma_short_series) < 2 or len(ma_long_series) < 2:
        return []

    # 对齐索引
    offset_short = len(closes) - len(ma_short_series)
    offset_long = len(closes) - len(ma_long_series)

    signals = []

    for i in range(1, len(ma_long_series)):
        idx_long = i + offset_long
        # 对齐到同一天：ma_short_series[k] 对应 closes[k + offset_short]，
        # ma_long_series[i] 对应 closes[i + offset_long]，需 k + offset_short == i + offset_long
        idx_short = i + offset_long - offset_short

        if (
            idx_short < 0
            or idx_short >= len(ma_short_series)
            or idx_long >= len(closes)
        ):
            continue

        # 计算信号
        signal = {
            "date": records[idx_long].get("day", ""),
            "idx": idx_long,
            "conditions": [],
            "strength": 0,
        }

        # 条件 1：MA 金叉
        if (
            ma_short_series[idx_short - 1] <= ma_long_series[i - 1]
            and ma_short_series[idx_short] > ma_long_series[i]
        ):
            signal["conditions"].append(f"MA{ma_short}/MA{ma_long}金叉")
            signal["strength"] += 3

        # 条件 2：放量突破
        avg_vol = sum(volumes[max(0, idx_long - 5) : idx_long]) / 5
        vol_ratio = volumes[idx_long] / avg_vol if avg_vol > 0 else 0
        if vol_ratio >= vol_threshold:
            signal["conditions"].append(f"放量{vol_ratio:.1f}x")
            signal["strength"] += 2

        # 条件 3：价格突破前高
        if idx_long >= 5:
            prev_high = max(closes[idx_long - 5 : idx_long])
            if closes[idx_long] > prev_high:
                signal["conditions"].append("突破前高")
                signal["strength"] += 1

        # 至少满足 2 个条件
        if len(signal["conditions"]) >= 2:
            signal["type"] = "买入"
            signal["desc"] = " + ".join(signal["conditions"])

            # 计算置信度
            if signal["strength"] >= 5:
                signal["confidence"] = "高"
            elif signal["strength"] >= 3:
                signal["confidence"] = "中"
            else:
                signal["confidence"] = "低"

            signals.append(signal)

    # ⚠️ 样本内回测警告
    if signals:
        signals[0]["_warning"] = (
            "⚠️ 本策略回测基于 5 只股票样本内优化（71.4%胜率），"
            "未经外样本验证，实盘表现可能显著偏差"
        )

    return signals


def backtest_strategy(
    data, ma_short=10, ma_long=21, vol_threshold=2.5, hold_days=5, stop_loss=-5
):
    """
    回测 MA + 成交量组合策略

    Args:
        data: K 线数据
        ma_short: 短期均线周期
        ma_long: 长期均线周期
        vol_threshold: 成交量阈值
        hold_days: 持有天数
        stop_loss: 止损比例

    Returns:
        list: 交易记录
    """
    closes = [to_float(r.get("close")) for r in data]
    volumes = [to_float(r.get("volume")) for r in data]
    dates = [r.get("day", "") for r in data]

    signals = detect_ma_volume_signal(
        data, closes, volumes, ma_short, ma_long, vol_threshold
    )

    trades = []
    for signal in signals:
        idx = signal["idx"]
        buy_price = closes[idx]
        buy_date = dates[idx]

        if idx + hold_days >= len(closes):
            continue

        sell_price = None
        sell_date = None
        exit_reason = None

        for j in range(1, hold_days + 1):
            if idx + j >= len(closes):
                break
            if (closes[idx + j] - buy_price) / buy_price * 100 <= stop_loss:
                sell_price = buy_price * (1 + stop_loss / 100)
                sell_date = dates[idx + j]
                exit_reason = "止损"
                break
            if j == hold_days:
                sell_price = closes[idx + j]
                sell_date = dates[idx + j]
                exit_reason = "持有到期"

        if sell_price:
            trade_return = (sell_price - buy_price) / buy_price * 100
            trades.append(
                {
                    "buy_date": buy_date,
                    "buy_price": buy_price,
                    "sell_date": sell_date,
                    "sell_price": round(sell_price, 2),
                    "return_pct": round(trade_return, 2),
                    "exit_reason": exit_reason,
                    "signal": signal["desc"],
                    "confidence": signal["confidence"],
                    "strength": signal["strength"],
                }
            )

    return trades


def get_strategy_params():
    """返回策略推荐参数"""
    return {
        "name": "MA_Volume_Combined",
        "version": "1.14.1",
        "description": "MA10/MA21 金叉 + 放量突破组合策略",
        "parameters": {
            "ma_short": 10,
            "ma_long": 21,
            "vol_threshold": 2.5,
            "hold_days": 5,
            "stop_loss": -5,
        },
        "backtest_results": {
            "win_rate": 71.4,
            "avg_return": 6.39,
            "total_return": 44.71,
            "disclosure": (
                "样本内拟合（5 只股票 × 200 个交易日，单股最优参数），"
                "未经外样本验证；5 只平均胜率 59.7%（见 config.json）。"
                "数字仅供参考，不构成投资建议。"
            ),
        },
        "source": "基于宝丰能源等 5 只股票样本内回测",
    }


# 命令行测试
if __name__ == "__main__":
    import sys
    import os

    scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, scripts_dir)

    from common import normalize_quote_code
    from kline import fetch as fetch_kline

    if len(sys.argv) < 2:
        print("用法: python3 ma_volume_strategy.py <code>")
        sys.exit(1)

    code = normalize_quote_code(sys.argv[1])
    records = fetch_kline(code, 240, 250)

    closes = [to_float(r.get("close")) for r in records if to_float(r.get("close")) > 0]
    volumes = [to_float(r.get("volume")) for r in records]

    # 检测信号
    signals = detect_ma_volume_signal(records, closes, volumes)
    print(f"\n检测到 {len(signals)} 个信号:")
    for s in signals[-5:]:  # 显示最近 5 个
        print(f"  {s['date']} | {s['desc']} | 置信度: {s['confidence']}")

    # 回测
    trades = backtest_strategy(records)
    print("\n回测结果:")
    wins = sum(1 for t in trades if t["return_pct"] > 0)
    total = len(trades)
    print(f"  交易次数: {total}")
    print(f"  胜率: {wins/total*100:.1f}%" if total > 0 else "  胜率: N/A")
    print(
        f"  平均收益: {sum(t['return_pct'] for t in trades)/total:.2f}%"
        if total > 0
        else "  平均收益: N/A"
    )

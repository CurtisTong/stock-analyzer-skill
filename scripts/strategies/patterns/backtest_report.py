"""
策略回测报告生成器

生成详细的回测报告，包括：
- 交易统计
- 胜率分析
- 收益分布
- 风险指标
- 可视化图表（ASCII）
"""

import json
import sys
import os
from datetime import datetime

scripts_dir = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from strategies.patterns.ma_volume_strategy import (
    backtest_strategy,
)


def load_kline_data(filepath):
    """加载K线数据"""
    with open(filepath, "r") as f:
        return json.load(f)


def calculate_advanced_stats(trades):
    """计算高级统计指标"""
    if not trades:
        return {}

    returns = [t["return_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    # 基础统计
    total_trades = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total_trades * 100

    # 收益统计
    total_return = sum(returns)
    avg_return = total_return / total_trades
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    # 风险指标
    max_win = max(returns) if returns else 0
    max_loss = min(returns) if returns else 0
    profit_factor = (
        abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float("inf")
    )

    # 连续盈亏
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_wins = 0
    current_losses = 0

    for r in returns:
        if r > 0:
            current_wins += 1
            current_losses = 0
            max_consecutive_wins = max(max_consecutive_wins, current_wins)
        else:
            current_losses += 1
            current_wins = 0
            max_consecutive_losses = max(max_consecutive_losses, current_losses)

    # 夏普比率（简化版）
    if len(returns) > 1:
        import statistics

        std_dev = statistics.stdev(returns)
        sharpe = avg_return / std_dev if std_dev > 0 else 0
    else:
        sharpe = 0

    # 最大回撤
    cumulative = 0
    peak = 0
    max_drawdown = 0
    for r in returns:
        cumulative += r
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 2),
        "total_return": round(total_return, 2),
        "avg_return": round(avg_return, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_win": round(max_win, 2),
        "max_loss": round(max_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_consecutive_wins": max_consecutive_wins,
        "max_consecutive_losses": max_consecutive_losses,
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_drawdown, 2),
    }


def generate_ascii_chart(values, width=50, height=10, title=""):
    """生成 ASCII 图表"""
    if not values:
        return ""

    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val if max_val != min_val else 1

    # 归一化到 0-1
    normalized = [(v - min_val) / val_range for v in values]

    # 创建图表
    chart = []
    if title:
        chart.append(title)
        chart.append("=" * width)

    for row in range(height, -1, -1):
        line = ""
        threshold = row / height
        for n in normalized:
            if n >= threshold:
                line += "█"
            else:
                line += " "
        chart.append(f"{threshold*100:5.0f} |{line}")

    chart.append("      +" + "-" * width)
    chart.append("       " + "".join(str(i % 10) for i in range(width)))

    return "\n".join(chart)


def generate_return_distribution(returns, bins=10):
    """生成收益分布"""
    if not returns:
        return ""

    min_ret = min(returns)
    max_ret = max(returns)
    bin_width = (max_ret - min_ret) / bins if max_ret != min_ret else 1

    distribution = [0] * bins
    for r in returns:
        idx = min(int((r - min_ret) / bin_width), bins - 1)
        distribution[idx] += 1

    max_count = max(distribution)
    chart = []
    chart.append("收益分布:")
    chart.append("-" * 40)

    for i in range(bins):
        lower = min_ret + i * bin_width
        upper = lower + bin_width
        count = distribution[i]
        bar = "█" * int(count / max_count * 20) if max_count > 0 else ""
        chart.append(f"{lower:6.1f}% ~ {upper:6.1f}%: {bar} ({count})")

    return "\n".join(chart)


def generate_trade_timeline(trades, max_trades=20):
    """生成交易时间线"""
    if not trades:
        return ""

    chart = []
    chart.append("交易时间线 (最近 {} 笔):".format(min(len(trades), max_trades)))
    chart.append("-" * 80)
    chart.append(
        f"{'买入日':<12} {'买入价':>8} {'卖出日':<12} {'卖出价':>8} {'收益%':>8} {'结果':<6} {'信号':<20}"
    )
    chart.append("-" * 80)

    for t in trades[-max_trades:]:
        result = "✓" if t["return_pct"] > 0 else "✗"
        signal = t.get("signal", "")[:20]
        chart.append(
            f"{t['buy_date']:<12} {t['buy_price']:>8.2f} {t['sell_date']:<12} {t['sell_price']:>8.2f} {t['return_pct']:>8.2f} {result:<6} {signal:<20}"
        )

    return "\n".join(chart)


def generate_backtest_report(
    data,
    stock_name,
    ma_short=10,
    ma_long=21,
    vol_threshold=2.5,
    hold_days=5,
    stop_loss=-5,
):
    """生成完整回测报告"""
    # 执行回测
    trades = backtest_strategy(
        data, ma_short, ma_long, vol_threshold, hold_days, stop_loss
    )

    if not trades:
        return f"❌ {stock_name}: 未产生交易信号"

    # 计算统计
    stats = calculate_advanced_stats(trades)

    # 生成报告
    report = []
    report.append("=" * 70)
    report.append(f"📊 策略回测报告 - {stock_name}")
    report.append("=" * 70)
    report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    # 策略参数
    report.append("📌 策略参数:")
    report.append(f"  • 均线组合: MA{ma_short}/MA{ma_long}")
    report.append(f"  • 成交量阈值: {vol_threshold}x")
    report.append(f"  • 持有天数: {hold_days}")
    report.append(f"  • 止损比例: {stop_loss}%")
    report.append("")

    # 核心指标
    report.append("📈 核心指标:")
    report.append(f"  • 总交易次数: {stats['total_trades']}")
    report.append(f"  • 胜率: {stats['win_rate']}%")
    report.append(f"  • 平均收益: {stats['avg_return']}%")
    report.append(f"  • 累计收益: {stats['total_return']}%")
    report.append(f"  • 盈亏比: {stats['profit_factor']}")
    report.append(f"  • 夏普比率: {stats['sharpe_ratio']}")
    report.append("")

    # 风险指标
    report.append("⚠️ 风险指标:")
    report.append(f"  • 最大盈利: {stats['max_win']}%")
    report.append(f"  • 最大亏损: {stats['max_loss']}%")
    report.append(f"  • 最大回撤: {stats['max_drawdown']}%")
    report.append(f"  • 最大连胜: {stats['max_consecutive_wins']}")
    report.append(f"  • 最大连亏: {stats['max_consecutive_losses']}")
    report.append("")

    # 收益分布
    returns = [t["return_pct"] for t in trades]
    report.append(generate_return_distribution(returns))
    report.append("")

    # 累计收益曲线
    cumulative = []
    total = 0
    for r in returns:
        total += r
        cumulative.append(total)
    report.append(
        generate_ascii_chart(cumulative, width=50, height=8, title="累计收益曲线 (%)")
    )
    report.append("")

    # 交易时间线
    report.append(generate_trade_timeline(trades))
    report.append("")

    # 总结
    report.append("=" * 70)
    report.append("📝 总结:")
    # P1-15: 强制过拟合警示，避免 71.4% 胜率被误读为实盘可用
    report.append("  ⚠️ 本结果基于样本内回测，未经外样本验证，不构成实盘依据")
    report.append("  ⚠️ 历史业绩不代表未来收益")
    if stats["win_rate"] >= 60:
        report.append("  ✅ 策略表现良好，胜率超过 60%（样本内）")
    elif stats["win_rate"] >= 50:
        report.append("  ⚠️ 策略表现一般，胜率在 50-60% 之间（样本内）")
    else:
        report.append("  ❌ 策略表现较差，胜率低于 50%（样本内）")

    if stats["avg_return"] > 0:
        report.append(f"  ✅ 平均收益为正 ({stats['avg_return']}%, 样本内)")
    else:
        report.append(f"  ❌ 平均收益为负 ({stats['avg_return']}%, 样本内)")

    if stats["profit_factor"] > 1.5:
        report.append(f"  ✅ 盈亏比良好 ({stats['profit_factor']})")
    else:
        report.append(f"  ⚠️ 盈亏比偏低 ({stats['profit_factor']})")

    report.append("=" * 70)

    return "\n".join(report)


def generate_comparison_report(stocks_data, ma_short=10, ma_long=21, vol_threshold=2.5):
    """生成多股票对比报告"""
    report = []
    report.append("=" * 80)
    report.append("📊 多股票策略对比报告")
    report.append("=" * 80)
    report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"策略参数: MA{ma_short}/MA{ma_long} + 放量{vol_threshold}x")
    report.append("")

    all_stats = []

    for stock_name, data in stocks_data.items():
        trades = backtest_strategy(data, ma_short, ma_long, vol_threshold)
        stats = calculate_advanced_stats(trades)
        stats["stock_name"] = stock_name
        all_stats.append(stats)

    # 汇总表
    report.append(
        f"{'股票':<12} {'交易次数':<10} {'胜率%':<10} {'平均收益%':<12} {'累计收益%':<12} {'盈亏比':<10} {'夏普':<8}"
    )
    report.append("-" * 84)

    for stats in all_stats:
        report.append(
            f"{stats['stock_name']:<12} {stats['total_trades']:<10} {stats['win_rate']:<10.1f} {stats['avg_return']:<12.2f} {stats['total_return']:<12.2f} {stats['profit_factor']:<10.2f} {stats['sharpe_ratio']:<8.2f}"
        )

    # 平均值
    avg_win_rate = sum(s["win_rate"] for s in all_stats) / len(all_stats)
    avg_return = sum(s["avg_return"] for s in all_stats) / len(all_stats)
    avg_total = sum(s["total_return"] for s in all_stats) / len(all_stats)
    finite_pfs = [
        s["profit_factor"] for s in all_stats if s["profit_factor"] != float("inf")
    ]
    avg_pf = sum(finite_pfs) / len(finite_pfs) if finite_pfs else float("inf")
    avg_sharpe = sum(s["sharpe_ratio"] for s in all_stats) / len(all_stats)

    report.append("-" * 84)
    report.append(
        f"{'平均':<12} {'':<10} {avg_win_rate:<10.1f} {avg_return:<12.2f} {avg_total:<12.2f} {avg_pf:<10.2f} {avg_sharpe:<8.2f}"
    )

    # 最佳/最差
    best = max(all_stats, key=lambda x: x["avg_return"])
    worst = min(all_stats, key=lambda x: x["avg_return"])

    report.append("")
    report.append("🏆 最佳表现:")
    report.append(
        f"  • {best['stock_name']}: 胜率 {best['win_rate']}%, 平均收益 {best['avg_return']}%"
    )

    report.append("⚠️ 最差表现:")
    report.append(
        f"  • {worst['stock_name']}: 胜率 {worst['win_rate']}%, 平均收益 {worst['avg_return']}%"
    )

    # 结论
    report.append("")
    report.append("=" * 80)
    report.append("📝 结论:")
    # P1-15: 强制过拟合警示
    report.append("  ⚠️ 本结果基于样本内回测，未经外样本验证，不构成实盘依据")
    report.append("  ⚠️ 历史业绩不代表未来收益")
    if avg_win_rate >= 60:
        report.append(f"  ✅ 策略整体表现良好，平均胜率 {avg_win_rate:.1f}%（样本内）")
    else:
        report.append(f"  ⚠️ 策略整体表现一般，平均胜率 {avg_win_rate:.1f}%（样本内）")

    report.append(f"  • 平均收益: {avg_return:.2f}%（样本内）")
    report.append(f"  • 平均累计收益: {avg_total:.2f}%（样本内）")
    report.append("=" * 80)

    return "\n".join(report)


# 命令行测试
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 backtest_report.py <stock_code>              # 单股票报告")
        print("  python3 backtest_report.py --compare                 # 多股票对比")
        sys.exit(1)

    if sys.argv[1] == "--compare":
        # 多股票对比
        stocks = {
            "贵州茅台": "/tmp/kline_600519.json",
            "宁德时代": "/tmp/kline_300750.json",
            "招商银行": "/tmp/kline_600036.json",
            "恒瑞医药": "/tmp/kline_600276.json",
        }

        stocks_data = {}
        for name, path in stocks.items():
            try:
                stocks_data[name] = load_kline_data(path)
            except Exception as e:
                print(f"⚠️ {name}: {e}")

        print(generate_comparison_report(stocks_data))
    else:
        # 单股票
        from kline import fetch as fetch_kline
        from common import normalize_quote_code

        code = normalize_quote_code(sys.argv[1])
        data = fetch_kline(code, 240, 250)
        print(generate_backtest_report(data, code))

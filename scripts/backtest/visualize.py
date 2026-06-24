"""回测结果 ASCII 可视化。

提供终端内的收益曲线、回撤图等文本图表。
"""

from typing import Optional


def render_return_curve(
    returns: list[float],
    width: int = 60,
    height: int = 15,
    title: str = "累计收益曲线",
) -> str:
    """渲染累计收益曲线 ASCII 图。

    Args:
        returns: 各期收益率列表（百分比，如 [1.5, -0.3, 2.1]）
        width: 图表宽度（字符数）
        height: 图表高度（行数）
        title: 图表标题

    Returns:
        ASCII 图表字符串
    """
    if not returns:
        return "(无收益数据)"

    # 计算累计收益
    cumulative = [0.0]
    for r in returns:
        cumulative.append(cumulative[-1] + r)

    min_val = min(cumulative)
    max_val = max(cumulative)
    val_range = max_val - min_val if max_val != min_val else 1

    # 归一化到 [0, height-1]
    def normalize(val):
        return int((val - min_val) / val_range * (height - 1))

    # 构建画布
    canvas = [[" " for _ in range(width)] for _ in range(height)]

    # 填充曲线
    step = max(1, len(cumulative) // width)
    for x in range(min(width, len(cumulative))):
        idx = min(x * step, len(cumulative) - 1)
        y = normalize(cumulative[idx])
        canvas[y][x] = "█"

    # 添加零线
    zero_y = normalize(0)
    if 0 <= zero_y < height:
        for x in range(width):
            if canvas[zero_y][x] == " ":
                canvas[zero_y][x] = "─"

    # 渲染
    lines = [f"  {title}"]
    lines.append("  " + "─" * (width + 2))

    for y in range(height - 1, -1, -1):
        val = min_val + (y / (height - 1)) * val_range if height > 1 else min_val
        label = f"{val:+6.1f}%"
        row = "".join(canvas[y])
        lines.append(f"  {label} │{row}│")

    lines.append("  " + " " * 7 + "└" + "─" * width + "┘")

    # X 轴标签
    if len(returns) > 0:
        x_labels = f"  {'':7}  第1期{'':>{width - 8}}第{len(returns)}期"
        lines.append(x_labels)

    return "\n".join(lines)


def render_drawdown_chart(
    returns: list[float],
    width: int = 60,
    height: int = 8,
) -> str:
    """渲染回撤图 ASCII。

    Args:
        returns: 各期收益率列表（百分比）
        width: 图表宽度
        height: 图表高度

    Returns:
        ASCII 回撤图字符串
    """
    if not returns:
        return "(无收益数据)"

    # 计算回撤序列
    cumulative = [1.0]
    for r in returns:
        cumulative.append(cumulative[-1] * (1 + r / 100))

    peak = cumulative[0]
    drawdowns = []
    for val in cumulative:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        drawdowns.append(dd)

    max_dd = max(drawdowns) if drawdowns else 0

    # 归一化到 [0, height-1]
    def normalize(dd):
        return int(dd / max_dd * (height - 1)) if max_dd > 0 else 0

    # 构建画布
    canvas = [[" " for _ in range(width)] for _ in range(height)]

    step = max(1, len(drawdowns) // width)
    for x in range(min(width, len(drawdowns))):
        idx = min(x * step, len(drawdowns) - 1)
        y = normalize(drawdowns[idx])
        canvas[y][x] = "▓"

    # 渲染
    lines = ["  回撤图"]
    lines.append("  " + "─" * (width + 2))

    for y in range(height - 1, -1, -1):
        dd_val = (y / (height - 1)) * max_dd if height > 1 else 0
        label = f"-{dd_val:5.1f}%"
        row = "".join(canvas[y])
        lines.append(f"  {label} │{row}│")

    lines.append("  " + " " * 7 + "└" + "─" * width + "┘")
    lines.append(f"  最大回撤: {max_dd:.2f}%")

    return "\n".join(lines)


def render_backtest_summary(report: dict) -> str:
    """渲染回测摘要文本。

    Args:
        report: run_backtest 返回的报告 dict

    Returns:
        格式化的回测摘要
    """
    if "error" in report:
        return f"❌ 回测失败: {report['error']}"

    lines = []
    strategy = report.get("strategy", "未知")
    lines.append(f"{'━' * 40}")
    lines.append(f"📊 回测报告: {strategy}")
    lines.append(f"{'━' * 40}")

    # 核心指标
    total_ret = report.get("total_return_pct", 0)
    win_rate = report.get("win_rate_pct", 0)
    sharpe = report.get("sharpe_ratio", 0)
    max_dd = report.get("max_drawdown_pct", 0)

    ret_icon = "🟢" if total_ret >= 0 else "🔴"
    lines.append(f"  {ret_icon} 累计收益: {total_ret:+.2f}%")
    lines.append(f"  📈 胜率: {win_rate:.1f}%")
    lines.append(f"  📉 最大回撤: {max_dd:.2f}%")
    lines.append(f"  ⚖ 夏普比率: {sharpe:.2f}")

    # 补充指标
    calmar = report.get("calmar_ratio", 0)
    pl_ratio = report.get("profit_loss_ratio", 0)
    total_trades = report.get("total_trades", 0)
    lines.append(f"  🎯 卡玛比率: {calmar:.2f}")
    lines.append(f"  💰 盈亏比: {pl_ratio:.2f}")
    lines.append(f"  🔄 总交易: {total_trades} 笔")

    # 收益曲线
    returns = (
        report.get("round_details", [{}])[0].get("returns", [])
        if report.get("round_details")
        else []
    )
    if not returns:
        returns = [report.get("avg_return_pct", 0)] * report.get("rounds", 1)

    lines.append("")
    lines.append(render_return_curve(returns, width=50, height=10))

    lines.append(f"\n{'━' * 40}")
    return "\n".join(lines)

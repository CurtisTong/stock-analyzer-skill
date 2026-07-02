"""
回测统计指标计算：夏普比率、最大回撤、卡玛比率、信息比率等。
"""

from .engine import simulate_strategy


def run_backtest(
    strategy_name: str,
    codes: list,
    top_n: int = 5,
    days: int = 60,
    rounds: int = 5,
    benchmark: str = None,
    weights=None,
):
    """
    运行滚动窗口回测。

    simulate_strategy 内部已做滚动窗口分析，返回每期收益序列。
    本函数只需调用一次，直接使用其返回的各期收益计算统计指标。

    Args:
        strategy_name: 策略名称
        codes: 候选股票代码
        top_n: 每轮买入数量
        days: 回测天数
        rounds: 回测轮数（已弃用，保留兼容性）
        benchmark: 基准指数代码（如 "sh000300" 沪深300），用于信息比率计算
        weights: 可选覆盖权重 dict（透传给 simulate_strategy）。None 时从 STRATEGIES[strategy_name] 读取。

    Returns:
        回测报告 dict
    """
    holding_days = max(1, days // rounds)
    result = simulate_strategy(
        strategy_name,
        codes,
        top_n,
        holding_days=holding_days,
        total_days=days,
        weights=weights,
    )

    if "error" in result:
        return {"error": result["error"]}

    all_returns = result["returns"]
    all_daily_returns = result.get("daily_returns", [])
    total_periods = len(all_returns)

    if total_periods == 0:
        return {"error": "回测失败，无有效数据"}

    benchmark_returns = _fetch_benchmark_returns(benchmark, days) if benchmark else None

    # 累计收益（各期收益连乘）
    total_return = 1.0
    for r in all_returns:
        total_return *= 1 + r / 100
    total_return = (total_return - 1) * 100

    avg_return = sum(all_returns) / len(all_returns)
    max_return = max(all_returns)
    min_return = min(all_returns)
    win_rate = sum(1 for r in all_returns if r > 0) / len(all_returns) * 100

    # 夏普比率（年化，假设无风险利率 3%，一年 252 个交易日）
    # P1-28: 统一用 all_daily_returns 计算；不足时报样本不足而非退化到非独立期收益
    # （原 elif 路径用小样本 stdev + periods_per_year**0.5 年化，非独立样本下数学不成立）。
    annual_risk_free = 0.03
    sharpe = 0
    if len(all_daily_returns) > 1:
        import statistics

        daily_rf = annual_risk_free / 252
        daily_excess = [r - daily_rf for r in all_daily_returns]
        mean_excess = sum(daily_excess) / len(daily_excess)
        std = statistics.stdev(daily_excess)
        sharpe = mean_excess / std * (252**0.5) if std > 0 else 0
    # all_daily_returns 不足时 sharpe 保持 0（样本不足，不退化到非独立期收益路径）

    # 最大回撤
    max_drawdown = 0
    if all_daily_returns:
        cumulative = [1.0]
        for r in all_daily_returns:
            cumulative.append(cumulative[-1] * (1 + r))
        peak = cumulative[0]
        for val in cumulative:
            if val > peak:
                peak = val
            drawdown = (peak - val) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    else:
        cumulative = [1.0]
        for r in all_returns:
            cumulative.append(cumulative[-1] * (1 + r / 100))
        peak = cumulative[0]
        for val in cumulative:
            if val > peak:
                peak = val
            drawdown = (peak - val) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    # 卡玛比率 = 年化收益率 / 最大回撤
    annualized_return = total_return * (252 / days) if days > 0 else 0
    calmar_ratio = (
        round(annualized_return / (max_drawdown * 100), 2) if max_drawdown > 0 else 0
    )

    # 盈亏比 = 平均盈利 / 平均亏损
    winning_trades = [r for r in all_returns if r > 0]
    losing_trades = [r for r in all_returns if r < 0]
    avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = abs(sum(losing_trades) / len(losing_trades)) if losing_trades else 0
    profit_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    total_trades = top_n * total_periods

    # 信息比率
    # P0-12 修复：原实现用 all_daily_returns（多期拼接、不连续）与 benchmark_returns
    # （连续 N 天）按 min_len 前对齐，时间区间错开数周到数月，数值无意义。
    # 改为基于"每期收益 vs 基准同期持有期收益"的超额收益，不依赖日序列时间对齐。
    information_ratio = 0
    if benchmark_returns and len(benchmark_returns) > 1 and len(all_returns) > 1:
        import statistics

        # 基准按 holding_days 切分为各期持有期收益（连乘）
        n_bench_periods = len(benchmark_returns) // max(1, holding_days)
        bench_period_returns = []
        for k in range(n_bench_periods):
            seg = benchmark_returns[k * holding_days : (k + 1) * holding_days]
            cum = 1.0
            for dr in seg:
                cum *= 1 + dr
            bench_period_returns.append((cum - 1) * 100)  # 转百分比

        # 与策略各期收益对齐（取 min 期数），每期都是 holding_days 的持有期收益
        n_periods = min(len(all_returns), len(bench_period_returns))
        if n_periods > 1:
            excess = [
                all_returns[i] - bench_period_returns[i] for i in range(n_periods)
            ]
            mean_excess = sum(excess) / len(excess)
            te = statistics.stdev(excess)
            periods_per_year = 252 / holding_days if holding_days > 0 else 0
            information_ratio = (
                round(mean_excess / te * (periods_per_year**0.5), 2)
                if te > 0
                else 0
            )

    # 换手率估算
    annual_turnover = (252 / holding_days) * top_n if holding_days > 0 else 0

    # 分位置胜率
    round_results = [result]
    win_by_position = _calc_win_by_position(round_results, holding_days)

    return {
        "strategy": strategy_name,
        "rounds": total_periods,
        "total_return_pct": round(total_return, 2),
        "avg_return_pct": round(avg_return, 2),
        "max_return_pct": round(max_return, 2),
        "min_return_pct": round(min_return, 2),
        "win_rate_pct": round(win_rate, 1),
        "sharpe_ratio": round(sharpe, 2),
        "information_ratio": information_ratio,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "calmar_ratio": calmar_ratio,
        "profit_loss_ratio": profit_loss_ratio,
        "total_trades": total_trades,
        "annual_turnover": round(annual_turnover),
        "win_by_position": win_by_position,
        "benchmark": benchmark or "none",
        "round_details": round_results,
    }


def _fetch_benchmark_returns(benchmark_code: str, days: int) -> list:
    """获取基准指数的日收益率序列。"""
    if not benchmark_code:
        return None
    try:
        from data import get_kline
        from common import normalize_quote_code

        bars = get_kline(
            normalize_quote_code(benchmark_code), scale=240, datalen=days + 5
        )
        if not bars or len(bars) < 2:
            return None
        returns = []
        for i in range(1, len(bars)):
            if bars[i - 1].close > 0:
                returns.append((bars[i].close - bars[i - 1].close) / bars[i - 1].close)
        return returns
    except Exception:
        return None


def _calc_win_by_position(round_results: list, holding_days: int) -> dict:
    """计算不同持仓位置的胜率分布。"""
    if not round_results or holding_days <= 0:
        return {}
    thirds = max(1, holding_days // 3)
    positions = {
        "early": {"wins": 0, "total": 0},
        "mid": {"wins": 0, "total": 0},
        "late": {"wins": 0, "total": 0},
    }
    for res in round_results:
        dly = res.get("daily_returns", [])
        for i, r in enumerate(dly):
            pos = "early" if i < thirds else ("mid" if i < 2 * thirds else "late")
            positions[pos]["total"] += 1
            if r > 0:
                positions[pos]["wins"] += 1
    return {
        k: round(v["wins"] / v["total"] * 100, 1) if v["total"] > 0 else 0
        for k, v in positions.items()
    }

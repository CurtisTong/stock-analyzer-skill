"""
回测统计指标计算：夏普比率、最大回撤、卡玛比率、信息比率等。
"""

from datetime import datetime

from .engine import simulate_strategy, SimContext


def run_backtest(
    strategy_name: str,
    codes: list,
    top_n: int = 5,
    days: int = 60,
    rounds: int = 5,
    benchmark=None,
    weights=None,
    atr_stop_multiplier=None,
    trailing_stop_pct=None,
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
        atr_stop_multiplier: ATR 自适应止损倍数（None = 固定 -8% 止损）
        trailing_stop_pct: 移动止盈回撤比例（None = 固定 +20% 止盈）

    Returns:
        回测报告 dict
    """
    holding_days = max(1, days // rounds)
    result = simulate_strategy(
        SimContext(
            strategy_name=strategy_name,
            codes=codes,
            top_n=top_n,
            holding_days=holding_days,
            total_days=days,
            weights=weights,
            atr_stop_multiplier=atr_stop_multiplier,
            trailing_stop_pct=trailing_stop_pct,
        )
    )

    if "error" in result:
        return {"error": result["error"]}

    all_returns = result["returns"]
    all_daily_returns = result.get("daily_returns", [])
    total_periods = len(all_returns)

    if total_periods == 0:
        return {"error": "回测失败，无有效数据"}

    # 多基准：每个基准独立抓日收益并切分为每期持有期收益（连乘）
    benchmark_list = (
        benchmark if isinstance(benchmark, list) else ([benchmark] if benchmark else [])
    )
    benchmark_period_returns_map = {}
    for bm in benchmark_list:
        bm_ret = _fetch_benchmark_returns(bm, days)
        if bm_ret and len(bm_ret) > 1 and len(all_returns) > 1:
            n_bp = len(bm_ret) // max(1, holding_days)
            bp = []
            for k in range(n_bp):
                seg = bm_ret[k * holding_days : (k + 1) * holding_days]
                cum = 1.0
                for dr in seg:
                    cum *= 1 + dr
                bp.append((cum - 1) * 100)
            benchmark_period_returns_map[bm] = bp

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
    max_drawdown = 0.0
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

    # Sortino 比率 = 年化超额收益 / 下行波动率（仅负收益的 stdev）
    sortino_ratio = _calc_sortino(all_daily_returns, annual_risk_free)

    total_trades = top_n * total_periods

    # 信息比率（多基准：基于 benchmark_period_returns_map 循环计算）
    # P0-12 修复：原实现用 all_daily_returns（多期拼接、不连续）与 benchmark_returns
    # （连续 N 天）按 min_len 前对齐，时间区间错开数周到数月，数值无意义。
    # 改为基于"每期收益 vs 基准同期持有期收益"的超额收益，不依赖日序列时间对齐。
    import statistics

    information_ratios = {}
    for bm, bp in benchmark_period_returns_map.items():
        n_periods = min(len(all_returns), len(bp))
        if n_periods > 1:
            excess = [all_returns[i] - bp[i] for i in range(n_periods)]
            mean_excess = sum(excess) / len(excess)
            te = statistics.stdev(excess)
            periods_per_year = 252 / holding_days if holding_days > 0 else 0
            information_ratios[bm] = (
                round(mean_excess / te * (periods_per_year**0.5), 2) if te > 0 else 0
            )
    # 兼容旧字段：取第一个基准（若存在）
    information_ratio = next(iter(information_ratios.values()), 0)

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
        "sortino_ratio": sortino_ratio,
        "information_ratio": information_ratio,
        "information_ratios": information_ratios,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "calmar_ratio": calmar_ratio,
        "profit_loss_ratio": profit_loss_ratio,
        "total_trades": total_trades,
        "annual_turnover": round(annual_turnover),
        "win_by_position": win_by_position,
        "benchmark": (
            benchmark if isinstance(benchmark, list) else (benchmark or "none")
        ),
        "benchmark_returns_pct": {},
        "round_details": round_results,
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data_sources": result.get("data_sources", []),
            "benchmark_source": result.get("benchmark_source"),
            "is_degraded": result.get("is_degraded", False),
        },
    }


def _fetch_benchmark_returns(benchmark_code: str, days: int) -> list | None:
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
    except Exception as e:
        # v1.16.0 P1-2 HIGH: 基准收益计算失败直接影响回测指标——记录
        from common.exceptions import log_silent_fallback

        log_silent_fallback(
            location="backtest.metrics._calc_benchmark_returns",
            exception=e,
            default_value=None,
            fallback_reason="基准收益数据获取/计算失败，回测指标返回 None",
        )
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


def _calc_sortino(daily_returns: list, annual_risk_free: float = 0.03) -> float:
    """计算 Sortino 比率（年化，年化收益 / 下行波动率）。

    与 Sharpe 区别：分母只取负收益的样本标准差（不惩罚上行波动）。
    当样本不足或无下行样本时返回 0（与 Sharpe 在样本不足时的处理一致）。
    """
    if not daily_returns or len(daily_returns) < 2:
        return 0
    import statistics

    daily_rf = annual_risk_free / 252
    excess = [r - daily_rf for r in daily_returns]
    downside = [r for r in excess if r < 0]
    if len(downside) < 2:
        return 0  # 下行样本不足，不强行计算
    downside_std = statistics.stdev(downside)
    if downside_std <= 0:
        return 0
    mean_excess = sum(excess) / len(excess)
    return round(mean_excess / downside_std * (252**0.5), 2)

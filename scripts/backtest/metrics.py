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
    holding_days: int | None = None,
    initial_capital: float = 100000,
    commission: float = 0.00025,
    stamp_tax: float = 0.001,
    slippage: float = 0.001,
    min_commission: float = 5.0,
):
    """
    运行滚动窗口回测。

    simulate_strategy 内部已做滚动窗口分析，返回每期收益序列。
    本函数只需调用一次，直接使用其各期收益计算统计指标。

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
        holding_days: 持有天数。None 时按 days//rounds 推导（历史行为）；
            传入时透传给 simulate_strategy（修复 multi_stock_backtest --holding-days 被忽略）
        initial_capital: 账户初始资金（默认 10 万）。单笔名义金额 = 本金 / top_n，
            决定最低佣金是否触发（本金越小、单笔越少，5 元最低佣金占比越高）
        commission: 佣金费率（默认 0.025%）
        stamp_tax: 印花税率（卖出侧，默认 0.1%）
        slippage: 滑点率（双向，默认 0.1%）
        min_commission: 单笔最低佣金（元，默认 5 元；传 0 可关闭下限）

    Returns:
        回测报告 dict
    """
    holding_days = holding_days or max(1, days // rounds)
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
            initial_capital=initial_capital,
            commission=commission,
            stamp_tax=stamp_tax,
            slippage=slippage,
            min_commission=min_commission,
        )
    )

    if "error" in result:
        return {"error": result["error"]}

    all_returns = result["returns"]
    all_daily_returns = result.get("daily_returns", [])
    total_periods = len(all_returns)

    if total_periods == 0:
        return {"error": "回测失败，无有效数据"}

    # 多基准：每个基准独立抓日收益（带日期），并按**策略期的实际日期区间**切块
    benchmark_list = benchmark if isinstance(benchmark, list) else ([benchmark] if benchmark else [])
    benchmark_period_returns_map = {}
    period_dates = result.get("period_dates") or []
    for bm in benchmark_list:
        fetched = _fetch_benchmark_returns(bm, days)
        if not fetched:
            continue
        bm_dates, bm_ret = fetched
        if len(bm_ret) < 1 or len(all_returns) < 2:
            continue
        if period_dates:
            # 按日期对齐：每期取基准在 [start, start+holding_days] 区间的收益
            bp = _slice_benchmark_by_period(bm_dates, bm_ret, period_dates, holding_days)
        else:
            # 无日期信息（老数据）时退回固定切块
            n_bp = len(bm_ret) // max(1, holding_days)
            bp = []
            for k in range(n_bp):
                seg = bm_ret[k * holding_days : (k + 1) * holding_days]
                cum = 1.0
                for dr in seg:
                    cum *= 1 + dr
                bp.append((cum - 1) * 100)
        if bp:
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
    # 统一用 all_daily_returns 计算；不足时报样本不足而非退化到非独立期收益
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
    # v1.22.1: 年化改为复利（原线性 total_return×(252/days) 低估正收益年化）
    annualized_return = ((1 + total_return / 100) ** (252 / days) - 1) * 100 if days > 0 else 0
    calmar_ratio = round(annualized_return / (max_drawdown * 100), 2) if max_drawdown > 0 else 0

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
    # 修复：原实现用 all_daily_returns（多期拼接、不连续）与 benchmark_returns
    # （连续 N 天）按 min_len 前对齐，时间区间错开数周到数月，数值无意义。
    # 改为基于"每期收益 vs 基准同期持有期收益"的超额收益，不依赖日序列时间对齐。
    import statistics

    information_ratios = {}
    # v1.24.0 超额指标：alpha/beta/excess_sharpe（同口径，每期收益对齐）
    alphas: dict[str, float] = {}
    betas: dict[str, float] = {}
    excess_sharpes: dict[str, float] = {}
    periods_per_year = 252 / holding_days if holding_days > 0 else 0
    annual_risk_free = 0.03  # 与本文件 Sharpe 口径一致
    for bm, bp in benchmark_period_returns_map.items():
        n_periods = min(len(all_returns), len(bp))
        if n_periods > 1:
            # 无风险利率按期折算（期收益口径）
            rf_period = annual_risk_free / periods_per_year if periods_per_year > 0 else 0.0
            excess = [all_returns[i] - bp[i] for i in range(n_periods)]
            mean_excess = sum(excess) / len(excess)
            te = statistics.stdev(excess)
            information_ratios[bm] = round(mean_excess / te * (periods_per_year**0.5), 2) if te > 0 else 0

            # beta = Cov(strategy, benchmark) / Var(benchmark)（期收益口径）
            bm_mean = sum(bp[:n_periods]) / n_periods
            strat_mean = sum(all_returns[:n_periods]) / n_periods
            var_bm = statistics.variance(bp[:n_periods]) if n_periods > 2 else 0
            if var_bm > 0:
                cov = sum((all_returns[i] - strat_mean) * (bp[i] - bm_mean) for i in range(n_periods)) / (n_periods - 1)
                beta = cov / var_bm
                betas[bm] = round(beta, 2)
                # alpha = CAPM 截距：策略超额 - beta × 基准超额（与 Sharpe 的 rf 口径一致）
                alpha_period = (strat_mean - rf_period) - beta * (bm_mean - rf_period)
                alphas[bm] = round(alpha_period * periods_per_year, 2)
            # 超额夏普（excess Sharpe）：策略夏普 - 基准夏普（风险调整口径）
            # 注意与信息比率（IR）区分：IR = 超额收益 / 跟踪误差，衡量"超额稳定性"；
            # 超额夏普是两个夏普之差，衡量"风险调整后相对表现"。二者不可混用。
            if te > 0 and var_bm > 0:
                bm_excess = [bp[i] - rf_period for i in range(n_periods)]
                bm_std = statistics.stdev(bm_excess)
                if bm_std > 0:
                    bm_sharpe = (bm_mean - rf_period) / bm_std * (periods_per_year**0.5)
                    strat_std = statistics.stdev([all_returns[i] - rf_period for i in range(n_periods)])
                    if strat_std > 0:
                        strat_sharpe = (strat_mean - rf_period) / strat_std * (periods_per_year**0.5)
                        excess_sharpes[bm] = round(strat_sharpe - bm_sharpe, 2)
    # 兼容旧字段：取第一个基准（若存在）
    # 样本不足（期数 ≤ 2 → 方差不可估）时输出 None 而非 0：
    # 0 会被误读成"真实的零 beta/零 alpha"，None 才表达"算不出来"。
    information_ratio = next(iter(information_ratios.values()), None)
    alpha_value = next(iter(alphas.values()), None)
    beta_value = next(iter(betas.values()), None)
    excess_sharpe_value = next(iter(excess_sharpes.values()), None)

    # 换手率估算
    annual_turnover = (252 / holding_days) * top_n if holding_days > 0 else 0

    # 分位置胜率
    round_results = [result]
    win_by_position = _calc_win_by_position(round_results, holding_days)

    return {
        "strategy": strategy_name,
        "rounds": total_periods,
        "total_return_pct": round(total_return, 2),
        "annualized_return_pct": round(annualized_return, 2),
        "avg_return_pct": round(avg_return, 2),
        "max_return_pct": round(max_return, 2),
        "min_return_pct": round(min_return, 2),
        "win_rate_pct": round(win_rate, 1),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": sortino_ratio,
        "information_ratio": information_ratio,
        "information_ratios": information_ratios,
        # v1.24.0 超额指标（基准同期期收益对齐口径）
        "alpha": alpha_value,
        "betas": betas,
        "alphas": alphas,
        "beta": beta_value,
        "excess_sharpe": excess_sharpe_value,
        "excess_sharpes": excess_sharpes,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "calmar_ratio": calmar_ratio,
        "profit_loss_ratio": profit_loss_ratio,
        "total_trades": total_trades,
        "annual_turnover": round(annual_turnover),
        "win_by_position": win_by_position,
        "benchmark": (benchmark if isinstance(benchmark, list) else (benchmark or "none")),
        "benchmark_returns_pct": {},
        "round_details": round_results,
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data_sources": result.get("data_sources", []),
            "benchmark_source": result.get("benchmark_source"),
            "is_degraded": result.get("is_degraded", False),
        },
    }


def _fetch_benchmark_returns(benchmark_code: str, days: int) -> tuple[list[str], list[float]] | None:
    """获取基准指数的日收益率序列（带日期）。

    修复（v1.22.1）：原实现只拉 days+5 根且取最旧一段，与策略评估窗口
    （MIN_HISTORY 起）错位约半个持有期，信息比率在错位期上计算。现拉取与
    simulate_strategy 同深（MIN_HISTORY+days+10），并从 bars[MIN_HISTORY]
    起返回——策略第 1 期收益 = returns[MIN_HISTORY..]，两者逐期对齐。

    v1.24.0 复审修复：同时返回日期序列，供基准按**策略期的实际日期区间**
    切块（原先按固定 holding_days 切连续日线，网格一变就与策略错位）。
    """
    if not benchmark_code:
        return None
    try:
        from data import get_kline
        from common import normalize_quote_code
        from .engine import MIN_HISTORY

        bars = get_kline(
            normalize_quote_code(benchmark_code),
            scale=240,
            datalen=MIN_HISTORY + days + 10,
        )
        if not bars or len(bars) < 2:
            return None
        dates: list[str] = []
        returns: list[float] = []
        for i in range(1, len(bars)):
            if bars[i - 1].close > 0:
                dates.append(bars[i].day)
                returns.append((bars[i].close - bars[i - 1].close) / bars[i - 1].close)
        return dates[MIN_HISTORY:], returns[MIN_HISTORY:]
    except Exception as e:
        # v1.16.0 HIGH: 基准收益计算失败直接影响回测指标——记录
        from common.exceptions import log_silent_fallback

        log_silent_fallback(
            location="backtest.metrics._calc_benchmark_returns",
            exception=e,
            default_value=None,
            fallback_reason="基准收益数据获取/计算失败，回测指标返回 None",
        )
        return None


def _slice_benchmark_by_period(
    bm_dates: list[str],
    bm_returns: list[float],
    period_dates: list[dict],
    fallback_holding_days: int,
) -> list[float]:
    """按策略期的**实际日期区间**切基准收益。

    原实现按固定 holding_days 切连续日线块，策略侧却按 date 分组——
    两者只在网格严格对齐时等价。实测策略第 3 期起点 07-31 被拿去与基准
    第 3 块（08-13..08-26）相减，错位约两周。

    Args:
        bm_dates: 基准日收益对应的日期序列
        bm_returns: 基准日收益率序列
        period_dates: 引擎回传的每期信息 [{"start": date, "holding_days": n}, ...]
        fallback_holding_days: 无日期信息时的回退持有期

    Returns:
        与 period_dates 等长的基准期收益列表（%）
    """
    if not bm_dates or not period_dates:
        return []
    date_index = {d: i for i, d in enumerate(bm_dates)}
    out: list[float] = []
    for period in period_dates:
        start = period.get("start")
        hold = period.get("holding_days") or fallback_holding_days
        if not start:
            out.append(0.0)
            continue
        idx = date_index.get(str(start))
        if idx is None:
            # 该期的选股日不在基准序列里（基准数据不足/停牌）——跳过该期，
            # 而不是拿别的期的收益来充数（那会制造错位）
            out.append(0.0)
            continue
        seg = bm_returns[idx : idx + hold]
        if not seg:
            out.append(0.0)
            continue
        cum = 1.0
        for dr in seg:
            cum *= 1 + dr
        out.append((cum - 1) * 100)
    return out


def _calc_win_by_position(round_results: list, holding_days: int) -> dict:
    """计算不同持仓位置的胜率分布。

    修复（v1.22.1）：原实现用扁平拼接的 daily_returns 全局索引分段，仅首个
    持有期的前几日算 early/mid，其余全部归入 late，位置分布失真。现按
    period_daily_returns（每持有期一段）逐段统计，位置索引在每期内重置。
    """
    if not round_results or holding_days <= 0:
        return {}
    thirds = max(1, holding_days // 3)
    positions = {
        "early": {"wins": 0, "total": 0},
        "mid": {"wins": 0, "total": 0},
        "late": {"wins": 0, "total": 0},
    }
    for res in round_results:
        periods = res.get("period_daily_returns")
        if periods:
            # 每持有期一段，位置在期内重置
            for dly in periods:
                for i, r in enumerate(dly):
                    pos = "early" if i < thirds else ("mid" if i < 2 * thirds else "late")
                    positions[pos]["total"] += 1
                    if r > 0:
                        positions[pos]["wins"] += 1
        else:
            # 兼容旧结构：无 period_daily_returns 时退化为扁平拼接（原行为）
            dly = res.get("daily_returns", [])
            for i, r in enumerate(dly):
                pos = "early" if i < thirds else ("mid" if i < 2 * thirds else "late")
                positions[pos]["total"] += 1
                if r > 0:
                    positions[pos]["wins"] += 1
    return {k: round(v["wins"] / v["total"] * 100, 1) if v["total"] > 0 else 0 for k, v in positions.items()}


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


def deflated_sharpe_ratio(
    sharpe_trials: list,
    best_sharpe: float,
    n_obs: int,
) -> float | None:
    """Deflated Sharpe Ratio（Bailey & López de Prado 2014 简化版）。

    参数寻优是在 N 次试验里挑最大夏普——即使全部策略都无效，最大值
    也会"看起来不错"。DSR 回答：在 N 次试验、零假设（无技能）下，
    观测到这个最大夏普的概率有多大。返回 Prob[SR* <= SR_best]，
    低于 0.95 说明"最优夏普"很可能只是选择偏差。

    简化口径：假设收益正态（无偏度/峰度校正）；输入为年化夏普，
    内部换算回单期（日）口径后按 T = n_obs 个交易日计算。

    Args:
        sharpe_trials: 各次试验（含基准）的年化夏普列表
        best_sharpe: 寻优选出的最大年化夏普
        n_obs: 回测窗口交易日数

    Returns:
        DSR ∈ [0, 1]；试验数 < 2、夏普无离散度或样本不足时返回 None
    """
    import math
    from statistics import NormalDist, mean, variance

    trials = [s for s in sharpe_trials if s is not None]
    if len(trials) < 2 or n_obs < 30:
        return None

    var_sr = variance(trials)
    if var_sr <= 0:
        return None

    euler_mascheroni = 0.5772156649
    z = NormalDist().inv_cdf
    n = len(trials)
    expected_max = math.sqrt(var_sr) * (
        (1 - euler_mascheroni) * z(1 - 1 / n) + euler_mascheroni * z(1 - 1 / (n * math.e))
    )

    sqrt252 = 252**0.5
    sr_best_daily = best_sharpe / sqrt252
    sr0_daily = expected_max / sqrt252
    # PSR 分母：sqrt(1 - γ3·SR + ((γ4-1)/4)·SR²)
    # 正态收益下 γ3=0、γ4=3 → sqrt(1 + 0.5·SR²)（PLUS，不是 MINUS）
    # 写成 MINUS 会在高 SR 时把分母钳到 ~0，把 DSR 强行推向 1.0（假阳性"通过"）。
    denom = math.sqrt(max(1e-12, 1 + 0.5 * sr_best_daily**2))
    dsr = NormalDist().cdf((sr_best_daily - sr0_daily) * math.sqrt(n_obs - 1) / denom)
    return round(dsr, 4)

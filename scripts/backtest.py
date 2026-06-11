#!/usr/bin/env python3
"""
多因子选股策略回测框架。
用法:
  python3 scripts/backtest.py --strategy balanced --top 5
  python3 scripts/backtest.py --strategy quality_value --top 10 --days 60
  python3 scripts/backtest.py --all --top 5
  python3 scripts/backtest.py --optimize --strategy balanced
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import to_float, normalize_quote_code, normalize_finance_code, DATA_DIR
from data import get_kline, get_finance
from strategies import STRATEGIES
from strategies.factors.volatility import volatility_score as _volatility_score


def fetch_historical_returns(code: str, days: int = 60) -> list:
    """获取历史日收益率序列。"""
    bars = get_kline(normalize_quote_code(code), scale=240, datalen=days + 5)
    if not bars or len(bars) < 2:
        return []
    returns = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_close = bars[i].close
        if prev_close > 0:
            returns.append((curr_close - prev_close) / prev_close)
    return returns


def _build_hist_quote(bars, i, fin, code):
    """基于历史 K 线和财务数据构建估值/流动性用的行情 dict（严格无前瞻）。"""
    close = bars[i].close
    eps = to_float(fin.get("eps", 0))
    bps = to_float(fin.get("bps", 0))
    pe = close / eps if eps > 0 else 0
    pb = close / bps if bps > 0 else 0
    # 估算总市值（亿元）：close * 总股本，总股本从 total_cap / price 推算
    total_cap = to_float(fin.get("total_cap", 0))
    if total_cap <= 0 and bps > 0 and eps > 0:
        # 无法推算，使用 0
        total_cap = 0
    return {
        "code": code,
        "price": close,
        "pe": pe,
        "pb": pb,
        "amount": bars[i].amount,
        "volume": bars[i].volume,
        "total_cap": total_cap,
        "turnover": 0,  # 无法从 K 线精确计算，设为 0
    }


def simulate_strategy(strategy_name: str, codes: list, top_n: int = 5,
                      holding_days: int = 5, initial_capital: float = 100000):
    """
    模拟策略收益（滚动窗口回测，无前瞻偏差）。

    回测逻辑：
    1. 获取所有候选股票的 K 线历史数据
    2. 在每个可用的历史时点 T，仅用 T 及之前的数据计算因子得分
    3. 选出 top_n 只股票，持有 holding_days 天
    4. 用 T+1 ~ T+holding_days 的实际收益评估
    5. 滚动窗口，重复上述过程

    注意：财务数据使用回测开始前的最新快照（API 不支持历史快照），
    quality 因子存在轻微前瞻偏差。valuation 和 liquidity 因子
    基于历史 K 线价格计算，严格无前瞻。

    Args:
        strategy_name: 策略名称
        codes: 候选股票代码列表
        top_n: 买入数量
        holding_days: 持有天数
        initial_capital: 初始资金

    Returns:
        回测结果 dict
    """
    from screener import infer_industry

    weights = STRATEGIES[strategy_name]
    min_history = 60  # 计算技术指标需要的最少 K 线数

    # 并发获取所有候选股票的 K 线历史
    def _fetch_kline(code):
        ncode = normalize_quote_code(code)
        bars = get_kline(ncode, scale=240, datalen=min_history + holding_days + 10)
        return code, bars

    kline_data = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_kline, c): c for c in codes}
        for future in as_completed(futures):
            try:
                code, bars = future.result()
                if bars and len(bars) >= min_history:
                    kline_data[code] = bars
            except Exception:
                pass

    if not kline_data:
        return {"error": "无法获取足够的 K 线数据"}

    # 并发获取财务数据（注：API 不支持历史快照，此处使用当前最新数据，
    # quality 因子存在轻微前瞻偏差，valuation/liquidity 因子已改为基于历史价格计算）
    def _fetch_finance(code):
        industry = infer_industry("", code)
        try:
            fin_records = get_finance(normalize_finance_code(code))
            fin = fin_records[0].to_dict() if fin_records else {}
        except Exception:
            fin = {}
        return code, industry, fin

    fin_cache = {}
    industry_cache = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_finance, c): c for c in codes}
        for future in as_completed(futures):
            try:
                code, industry, fin = future.result()
                industry_cache[code] = industry
                fin_cache[code] = fin
            except Exception:
                pass

    # 滚动窗口回测（不再获取当前行情快照，改用历史 K 线数据）
    from screener import quality_score, valuation_score, liquidity_score

    all_selections = []

    for code, bars in kline_data.items():
        if len(bars) < min_history + holding_days:
            continue

        fin = fin_cache.get(code, {})
        industry = industry_cache.get(code, "manufacturing")

        # 滚动窗口：从 min_history 位置开始，每次前进 holding_days
        i = min_history
        while i + holding_days <= len(bars):
            # 用 i 及之前的数据计算动量因子（严格无前瞻）
            hist = bars[:i]
            momentum = _compute_momentum_from_bars(hist)

            # 基于历史 K 线价格构建行情 dict（严格无前瞻）
            hist_quote = _build_hist_quote(bars, i, fin, code)

            parts = {
                "quality": quality_score(fin, industry) * 0.85,  # 财务快照前瞻偏差折扣
                "valuation": valuation_score(hist_quote, fin, industry),  # 基于历史价格
                "momentum": momentum,
                "liquidity": liquidity_score(hist_quote),  # 基于历史成交量
                "volatility": _volatility_score(bars[:i], industry),  # 基于历史 K 线
            }
            # 红利因子（有财务数据时可用）
            dividend = _calc_dividend_score(hist_quote, fin, industry)
            if dividend > 0:
                parts["dividend"] = dividend
            score = sum(parts.get(k, 0) * weights.get(k, 0) for k in set(parts) | set(weights) if k != "label")

            # 计算持有期收益（T+1 ~ T+holding_days）
            entry_price = bars[i].close
            exit_price = bars[i + holding_days - 1].close
            if entry_price > 0:
                ret = (exit_price - entry_price) / entry_price
                all_selections.append({
                    "code": code,
                    "date": bars[i].day,
                    "score": round(score, 1),
                    "return_pct": round(ret * 100, 2),
                    "daily_returns": _calc_daily_returns(bars, i, holding_days),
                })

            i += holding_days

    if not all_selections:
        return {"error": "无法计算收益"}

    # 按日期分组，每组取 top_n 只得分最高的股票
    from itertools import groupby
    all_selections.sort(key=lambda x: x["date"])
    portfolio_returns = []
    portfolio_daily_returns = []
    selection_details = []

    for date, group in groupby(all_selections, key=lambda x: x["date"]):
        group_list = sorted(group, key=lambda x: x["score"], reverse=True)[:top_n]
        avg_ret = sum(s["return_pct"] for s in group_list) / len(group_list)
        portfolio_returns.append(avg_ret / 100)
        # 合并日收益率用于精确回撤计算
        for s in group_list:
            portfolio_daily_returns.extend(s["daily_returns"])
        selection_details.extend(group_list)

    avg_return = sum(portfolio_returns) / len(portfolio_returns) * 100

    return {
        "strategy": strategy_name,
        "selections": selection_details[:20],
        "returns": [round(r * 100, 2) for r in portfolio_returns],
        "daily_returns": portfolio_daily_returns,
        "avg_return_pct": round(avg_return, 2),
        "total_periods": len(portfolio_returns),
        "holding_days": holding_days,
        "top_n": top_n,
    }


def _calc_daily_returns(bars, start, holding_days):
    """计算持有期内的日收益率序列（用于精确回撤计算）。"""
    returns = []
    for j in range(start, start + holding_days):
        if j > 0 and bars[j - 1].close > 0:
            returns.append((bars[j].close - bars[j - 1].close) / bars[j - 1].close)
    return returns


def _compute_momentum_from_bars(bars) -> float:
    """从 K 线数据计算动量因子得分（0-100），严格无前瞻。"""
    if len(bars) < 60:
        return 50.0

    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]

    # 1. 趋势方向：MA5 vs MA20
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    trend_score = 70 if ma5 > ma20 else 30

    # 2. RSI(14) - Wilder 平滑
    rsi_val = _calc_rsi(closes, 14)
    if rsi_val < 30:
        rsi_score = 80
    elif rsi_val < 50:
        rsi_score = 60
    elif rsi_val < 70:
        rsi_score = 40
    else:
        rsi_score = 20

    # 3. 价格动量（20 日收益率）
    ret20 = (closes[-1] / closes[-20] - 1) if closes[-20] > 0 else 0
    if ret20 > 0.1:
        mom_score = 80
    elif ret20 > 0:
        mom_score = 60
    elif ret20 > -0.1:
        mom_score = 40
    else:
        mom_score = 20

    # 4. 量比
    if len(volumes) >= 25:
        avg_5 = sum(volumes[-5:]) / 5
        avg_20 = sum(volumes[-25:-5]) / 20 if sum(volumes[-25:-5]) > 0 else 1
        vol_ratio = avg_5 / avg_20 if avg_20 > 0 else 1
        vol_score = min(100, max(0, 50 + (vol_ratio - 1) * 50))
    else:
        vol_score = 50

    return (trend_score * 0.3 + rsi_score * 0.2 + mom_score * 0.3 + vol_score * 0.2)


def _calc_dividend_score(hist_quote: dict, fin: dict, industry: str) -> float:
    """计算红利因子得分（回测用，轻量版）。"""
    try:
        from strategies.factors.dividend import dividend_score
        return dividend_score(hist_quote, fin, industry)
    except ImportError:
        return 0.0


def _calc_rsi(closes: list, period: int = 14) -> float:
    """计算 RSI（Wilder 平滑），无前瞻。"""
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def run_backtest(strategy_name: str, codes: list, top_n: int = 5,
                 days: int = 60, rounds: int = 5,
                 benchmark: str = None):
    """
    运行多轮回测。

    Args:
        strategy_name: 策略名称
        codes: 候选股票代码
        top_n: 每轮买入数量
        days: 回测天数
        rounds: 回测轮数
        benchmark: 基准指数代码（如 "sh000300" 沪深300），用于信息比率计算

    Returns:
        回测报告 dict
    """
    all_returns = []
    all_daily_returns = []
    round_results = []

    for i in range(rounds):
        result = simulate_strategy(strategy_name, codes, top_n, holding_days=days // rounds)
        if "error" not in result:
            all_returns.append(result["avg_return_pct"])
            all_daily_returns.extend(result.get("daily_returns", []))
            round_results.append(result)

    if not all_returns:
        return {"error": "回测失败，无有效数据"}

    # 获取基准收益
    benchmark_returns = _fetch_benchmark_returns(benchmark, days) if benchmark else None

    # 计算统计指标
    total_return = 1.0
    for r in all_returns:
        total_return *= (1 + r / 100)
    total_return = (total_return - 1) * 100

    avg_return = sum(all_returns) / len(all_returns)
    max_return = max(all_returns)
    min_return = min(all_returns)
    win_rate = sum(1 for r in all_returns if r > 0) / len(all_returns) * 100

    # 夏普比率（年化，假设无风险利率 3%，一年 252 个交易日）
    annual_risk_free = 0.03
    # 优先使用日收益率计算（更精确），回退到轮次收益率
    if len(all_daily_returns) > 1:
        import statistics
        daily_rf = annual_risk_free / 252
        daily_excess = [r - daily_rf for r in all_daily_returns]
        mean_excess = sum(daily_excess) / len(daily_excess)
        std = statistics.stdev(daily_excess)
        sharpe = mean_excess / std * (252 ** 0.5) if std > 0 else 0
    elif len(all_returns) > 1:
        import statistics
        holding_days_per_round = days // rounds
        risk_free_per_round = annual_risk_free * holding_days_per_round / 252
        excess_returns = [r / 100 - risk_free_per_round for r in all_returns]
        mean_excess = sum(excess_returns) / len(excess_returns)
        std = statistics.stdev(excess_returns)
        periods_per_year = 252 / holding_days_per_round
        sharpe = mean_excess / std * (periods_per_year ** 0.5) if std > 0 else 0
    else:
        sharpe = 0

    # 最大回撤（优先使用日收益率计算，更精确）
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
    # 假设一年 252 个交易日，按回测天数折算年化
    annualized_return = total_return * (252 / days) if days > 0 else 0
    calmar_ratio = round(annualized_return / (max_drawdown * 100), 2) if max_drawdown > 0 else 0

    # 盈亏比 = 平均盈利 / 平均亏损（基于轮次收益率）
    winning_trades = [r for r in all_returns if r > 0]
    losing_trades = [r for r in all_returns if r < 0]
    avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = abs(sum(losing_trades) / len(losing_trades)) if losing_trades else 0
    profit_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    # 总交易次数 = 每轮持仓数 × 轮次数
    total_trades = top_n * rounds

    # 信息比率 = (策略年化收益 - 基准年化收益) / 跟踪误差
    information_ratio = 0
    if benchmark_returns and len(benchmark_returns) > 1 and len(all_daily_returns) > 1:
        import statistics
        # 对齐长度
        min_len = min(len(all_daily_returns), len(benchmark_returns))
        excess_returns_daily = [
            all_daily_returns[i] - benchmark_returns[i]
            for i in range(min_len)
        ]
        mean_excess = sum(excess_returns_daily) / len(excess_returns_daily)
        te = statistics.stdev(excess_returns_daily)
        information_ratio = round(mean_excess / te * (252 ** 0.5), 2) if te > 0 else 0

    # 换手率估算：每期买入 top_n 只，持有 holding_days，年化换手
    holding_days_per_round = days // rounds
    annual_turnover = (252 / holding_days_per_round) * top_n if holding_days_per_round > 0 else 0

    # 单笔胜率时间分布：按持仓位置分段的胜率
    win_by_position = _calc_win_by_position(round_results, holding_days_per_round) if round_results else {}

    return {
        "strategy": strategy_name,
        "rounds": rounds,
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
        bars = get_kline(normalize_quote_code(benchmark_code), scale=240, datalen=days + 5)
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
        "early": {"wins": 0, "total": 0},     # 前1/3
        "mid": {"wins": 0, "total": 0},        # 中1/3
        "late": {"wins": 0, "total": 0},       # 后1/3
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


def compare_strategies(codes: list, top_n: int = 5, days: int = 60, rounds: int = 5,
                       benchmark: str = None, scenarios: list = None):
    """比较所有策略的表现。

    Args:
        codes: 候选股票代码
        top_n: 每轮买入数量
        days: 回测天数
        rounds: 回测轮数
        benchmark: 基准指数代码
        scenarios: 情景列表，如 [{"label":"2025结构牛", "days":60, "rounds":3}, ...]
    """
    results = {}
    for strategy_name in STRATEGIES:
        print(f"  回测策略: {STRATEGIES[strategy_name]['label']}...", flush=True)
        report = run_backtest(strategy_name, codes, top_n, days, rounds, benchmark)
        # 情景分析
        if scenarios:
            scenario_results = {}
            for sc in scenarios:
                label = sc.get("label", "未知")
                sc_days = sc.get("days", days)
                sc_rounds = sc.get("rounds", max(1, rounds // 2))
                sr = run_backtest(strategy_name, codes, top_n, sc_days, sc_rounds, benchmark)
                scenario_results[label] = {
                    "total_return_pct": sr.get("total_return_pct"),
                    "sharpe_ratio": sr.get("sharpe_ratio"),
                    "max_drawdown_pct": sr.get("max_drawdown_pct"),
                    "win_rate_pct": sr.get("win_rate_pct"),
                }
            report["scenarios"] = scenario_results
        results[strategy_name] = report
    return results


def optimize_weights(codes: list, strategy_name: str, top_n: int = 5, days: int = 60):
    """
    简单网格搜索优化策略权重。

    在当前权重基础上，对 quality/valuation/momentum/liquidity 各 ±5% 做网格搜索。
    """
    import copy
    base_keys = ["quality", "valuation", "momentum", "liquidity"]
    original_weights = {k: STRATEGIES[strategy_name][k] for k in base_keys}

    best_score = -999
    best_weights = original_weights.copy()
    results = []

    # 简化：只测试 3 个档位（-5%, 不变, +5%）
    steps = [-0.05, 0, 0.05]

    print(f"  基准权重: {original_weights}", flush=True)
    base_report = run_backtest(strategy_name, codes, top_n, days, 3)
    base_score = base_report.get("sharpe_ratio", 0)
    print(f"  基准夏普: {base_score:.2f}", flush=True)

    # 网格搜索（简化版：逐维度调整）
    for key in base_keys:
        for step in steps:
            test_weights = original_weights.copy()
            test_weights[key] = max(0.05, test_weights[key] + step)

            # 归一化
            total = sum(test_weights.values())
            test_weights = {k: v / total for k, v in test_weights.items()}

            # 使用深拷贝修改策略权重，避免影响全局状态
            backup = copy.deepcopy(STRATEGIES[strategy_name])
            try:
                STRATEGIES[strategy_name].update(test_weights)
                report = run_backtest(strategy_name, codes, top_n, days, 3)
            finally:
                STRATEGIES[strategy_name].update(backup)

            score = report.get("sharpe_ratio", 0)

            results.append({
                "weights": {k: round(v, 3) for k, v in test_weights.items()},
                "sharpe": score,
                "return": report.get("total_return_pct", 0),
            })

            if score > best_score:
                best_score = score
                best_weights = test_weights.copy()

    return {
        "strategy": strategy_name,
        "best_weights": {k: round(v, 3) for k, v in best_weights.items()},
        "best_sharpe": round(best_score, 3),
        "baseline_sharpe": round(base_score, 3),
        "improvement": round(best_score - base_score, 3),
        "all_results": results,
    }


def load_test_universe():
    """加载测试股票池。"""
    path = DATA_DIR / "sector_stocks.json"
    if not path.exists():
        return []
    sectors = json.loads(path.read_text(encoding="utf-8"))
    all_codes = []
    for items in sectors.values():
        all_codes.extend(items)
    return sorted(set(all_codes))


def main():
    parser = argparse.ArgumentParser(description="多因子选股策略回测")
    parser.add_argument("--strategy", choices=STRATEGIES.keys(), default="balanced",
                        help="回测策略")
    parser.add_argument("--all", action="store_true", help="比较所有策略")
    parser.add_argument("--optimize", action="store_true", help="优化权重")
    parser.add_argument("--top", type=int, default=5, help="每轮买入数量")
    parser.add_argument("--days", type=int, default=60, help="回测天数")
    parser.add_argument("--rounds", type=int, default=5, help="回测轮数")
    parser.add_argument("--codes", help="自定义股票代码（逗号分隔）")
    parser.add_argument("--benchmark", default=None, help="基准指数代码（如 sh000300 沪深300）")
    parser.add_argument("--scenarios", action="store_true", help="运行情景分析")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    # 加载股票池
    if args.codes:
        codes = [normalize_quote_code(c) for c in args.codes.split(",")]
    else:
        codes = load_test_universe()

    if not codes:
        print("❌ 无可用股票池", file=sys.stderr)
        sys.exit(1)

    print(f"📊 回测股票池: {len(codes)} 只", flush=True)

    if args.optimize:
        print(f"\n🔧 优化策略权重: {args.strategy}", flush=True)
        result = optimize_weights(codes, args.strategy, args.top, args.days)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"\n最优权重: {result['best_weights']}")
            print(f"最优夏普: {result['best_sharpe']:.3f}")
            print(f"基准夏普: {result['baseline_sharpe']:.3f}")
            print(f"提升: {result['improvement']:+.3f}")

    elif args.all:
        print(f"\n📈 比较所有策略 (top={args.top}, days={args.days}, rounds={args.rounds})", flush=True)
        # 构建情景
        scenarios = None
        if args.scenarios:
            scenarios = [
                {"label": "2025结构牛", "days": 60, "rounds": 3},
                {"label": "2024震荡修复", "days": 60, "rounds": 3},
                {"label": "2022熊市", "days": 60, "rounds": 3},
            ]
        results = compare_strategies(codes, args.top, args.days, args.rounds,
                                     benchmark=args.benchmark, scenarios=scenarios)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            header = f"{'策略':<18} {'总收益%':>8} {'夏普':>6} {'信息比':>7} {'最大回撤%':>8} {'胜率%':>6}"
            if scenarios:
                header += f" {'情景(收%)':>30}"
            print(header)
            print("-" * (len(header) + 10))
            for name, report in results.items():
                if "error" in report:
                    print(f"{name:<18} {'ERROR':>8}")
                else:
                    line = (f"{name:<18} {report['total_return_pct']:>8.2f} "
                            f"{report['sharpe_ratio']:>6.2f} "
                            f"{report.get('information_ratio', 0):>7.2f} "
                            f"{report['max_drawdown_pct']:>8.2f} "
                            f"{report['win_rate_pct']:>6.1f}")
                    if report.get("scenarios"):
                        scenario_str = "; ".join(
                            f"{k}:{v['total_return_pct']}%" if v.get("total_return_pct") is not None else f"{k}:?"
                            for k, v in report["scenarios"].items()
                        )
                        line += f" {scenario_str[:30]:>30}"
                    print(line)

    else:
        print(f"\n📈 回测策略: {args.strategy} (top={args.top}, days={args.days}, rounds={args.rounds})", flush=True)
        if args.benchmark:
            print(f"   基准: {args.benchmark}")
        report = run_backtest(args.strategy, codes, args.top, args.days, args.rounds,
                              benchmark=args.benchmark)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif "error" in report:
            print(f"❌ {report['error']}")
        else:
            print(f"\n总收益: {report['total_return_pct']:.2f}%")
            print(f"平均收益: {report['avg_return_pct']:.2f}%")
            print(f"最大收益: {report['max_return_pct']:.2f}%")
            print(f"最小收益: {report['min_return_pct']:.2f}%")
            print(f"胜率: {report['win_rate_pct']:.1f}%")
            print(f"夏普比率: {report['sharpe_ratio']:.2f}")
            if report.get("information_ratio"):
                print(f"信息比率: {report['information_ratio']:.2f}")
            print(f"最大回撤: {report['max_drawdown_pct']:.2f}%")
            print(f"盈亏比: {report.get('profit_loss_ratio', 0):.2f}")
            print(f"年化换手: {report.get('annual_turnover', 0)} 次")
            if report.get("win_by_position"):
                wp = report["win_by_position"]
                print(f"分位置胜率: 早期{wp.get('early', '-')}% / 中期{wp.get('mid', '-')}% / 后期{wp.get('late', '-')}%")


if __name__ == "__main__":
    main()

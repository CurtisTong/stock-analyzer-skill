"""
回测核心引擎：策略模拟、因子计算、收益归集。
"""

from concurrent.futures import as_completed
from datetime import datetime, timedelta

from common import (
    to_float,
    normalize_quote_code,
    normalize_finance_code,
    get_shared_executor,
)
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
    total_cap = to_float(fin.get("total_cap", 0))
    if total_cap <= 0 and bps > 0 and eps > 0:
        total_cap = 0
    return {
        "code": code,
        "price": close,
        "pe": pe,
        "pb": pb,
        "amount": bars[i].amount,
        "volume": bars[i].volume,
        "total_cap": total_cap,
        "turnover": 0,
    }


def simulate_strategy(
    strategy_name: str,
    codes: list,
    top_n: int = 5,
    holding_days: int = 5,
    initial_capital: float = 100000,
    total_days: int = 60,
):
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
        total_days: 回测总天数

    Returns:
        回测结果 dict
    """
    from screener import infer_industry

    weights = STRATEGIES[strategy_name]
    min_history = 60

    datalen = min_history + total_days + 10

    def _fetch_kline(code):
        ncode = normalize_quote_code(code)
        bars = get_kline(ncode, scale=240, datalen=datalen)
        return code, bars

    kline_data = {}
    stale_cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    ex = get_shared_executor()
    futures = {ex.submit(_fetch_kline, c): c for c in codes}
    for future in as_completed(futures):
        try:
            code, bars = future.result()
            if bars and len(bars) >= min_history and bars[-1].day >= stale_cutoff:
                kline_data[code] = bars
        except Exception:
            pass

    if not kline_data:
        return {"error": "无法获取足够的 K 线数据"}

    # 并发获取财务数据
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
    ex = get_shared_executor()
    futures = {ex.submit(_fetch_finance, c): c for c in codes}
    for future in as_completed(futures):
        try:
            code, industry, fin = future.result()
            industry_cache[code] = industry
            fin_cache[code] = fin
        except Exception:
            pass

    # 滚动窗口回测
    from screener import quality_score, valuation_score, liquidity_score

    common_start_date = None
    for code, bars in kline_data.items():
        if len(bars) >= min_history:
            start_date = bars[min_history - 1].day
            if common_start_date is None or start_date > common_start_date:
                common_start_date = start_date

    all_selections = []

    for code, bars in kline_data.items():
        if len(bars) < min_history + holding_days:
            continue

        fin = fin_cache.get(code, {})
        industry = industry_cache.get(code, "manufacturing")

        i = min_history
        while i + holding_days <= len(bars):
            if bars[i].day < common_start_date:
                i += holding_days
                continue

            hist = bars[:i]
            momentum = _compute_momentum_from_bars(hist)
            hist_quote = _build_hist_quote(bars, i, fin, code)

            parts = {
                "quality": quality_score(fin, industry) * 0.85,
                "valuation": valuation_score(hist_quote, fin, industry),
                "momentum": momentum,
                "liquidity": liquidity_score(hist_quote),
                "volatility": _volatility_score(bars[:i], industry),
            }
            dividend = _calc_dividend_score(hist_quote, fin, industry)
            if dividend > 0:
                parts["dividend"] = dividend
            score = sum(
                parts.get(k, 0) * weights.get(k, 0)
                for k in set(parts) | set(weights)
                if k != "label"
            )

            entry_price = bars[i].close
            exit_price = bars[i + holding_days - 1].close
            if entry_price > 0:
                ret = (exit_price - entry_price) / entry_price
                all_selections.append(
                    {
                        "code": code,
                        "date": bars[i].day,
                        "score": round(score, 1),
                        "return_pct": round(ret * 100, 2),
                        "daily_returns": _calc_daily_returns(bars, i, holding_days),
                    }
                )

            i += holding_days

    if not all_selections:
        return {"error": "无法计算收益"}

    from itertools import groupby

    all_selections.sort(key=lambda x: x["date"])

    date_groups = {}
    for date, group in groupby(all_selections, key=lambda x: x["date"]):
        date_groups[date] = list(group)

    min_stocks = min(top_n, max(3, len(kline_data) // 10))
    valid_dates = {d for d, items in date_groups.items() if len(items) >= min_stocks}

    portfolio_returns = []
    portfolio_daily_returns = []
    selection_details = []

    for date in sorted(valid_dates):
        group_list = sorted(date_groups[date], key=lambda x: x["score"], reverse=True)[
            :top_n
        ]
        avg_ret = sum(s["return_pct"] for s in group_list) / len(group_list)
        portfolio_returns.append(avg_ret / 100)
        stock_daily_returns = [
            s["daily_returns"] for s in group_list if s["daily_returns"]
        ]
        if stock_daily_returns:
            max_len = max(len(d) for d in stock_daily_returns)
            for day_idx in range(max_len):
                day_returns = [
                    d[day_idx] for d in stock_daily_returns if day_idx < len(d)
                ]
                if day_returns:
                    portfolio_daily_returns.append(sum(day_returns) / len(day_returns))
        selection_details.extend(group_list)

    if not portfolio_returns:
        return {"error": "回测失败，无有效数据"}

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

    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    trend_score = 70 if ma5 > ma20 else 30

    rsi_val = _calc_rsi(closes, 14)
    if rsi_val < 30:
        rsi_score = 80
    elif rsi_val < 50:
        rsi_score = 60
    elif rsi_val < 70:
        rsi_score = 40
    else:
        rsi_score = 20

    ret20 = (closes[-1] / closes[-20] - 1) if closes[-20] > 0 else 0
    if ret20 > 0.1:
        mom_score = 80
    elif ret20 > 0:
        mom_score = 60
    elif ret20 > -0.1:
        mom_score = 40
    else:
        mom_score = 20

    if len(volumes) >= 25:
        avg_5 = sum(volumes[-5:]) / 5
        avg_20 = sum(volumes[-25:-5]) / 20 if sum(volumes[-25:-5]) > 0 else 1
        vol_ratio = avg_5 / avg_20 if avg_20 > 0 else 1
        vol_score = min(100, max(0, 50 + (vol_ratio - 1) * 50))
    else:
        vol_score = 50

    return trend_score * 0.3 + rsi_score * 0.2 + mom_score * 0.3 + vol_score * 0.2


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

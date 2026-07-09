"""
回测核心引擎：策略模拟、因子计算、收益归集。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from common import (
    to_float,
    normalize_quote_code,
    normalize_finance_code,
    parallel_fetch_dict,
)
from data import get_kline, get_finance
from strategies import get_strategy
from strategies.factors.volatility import volatility_score as _volatility_score
from strategies.factors.chip import chip_score_static as _chip_score
from strategies.factors.quality import quality_score
from strategies.factors.valuation import valuation_score
from strategies.factors.liquidity import liquidity_score
from strategies.regime import compute_overlay_weights, RegimeState
from strategies.regime.classifier import _classify_for_backtest
from classifier import infer_industry

logger = logging.getLogger(__name__)


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


# P0-10: A 股财报披露延迟（天）。季报/年报在报告截止日后的法定披露窗口：
#   一季报 4/30、半年报 8/31、三季报 10/31、年报 4/30。
#   取 90 天作为保守上限，确保回测中仅使用已公开披露的财务数据。
_FINANCE_DISCLOSURE_LAG_DAYS = 90


def _visible_fin(fin: dict, trade_day: str) -> dict:
    """P0-10: 返回交易日 trade_day 时已公开披露的财务数据。

    若 fin.report_date + 披露延迟 > trade_day，说明该财报在交易日
    尚未公开，返回空 dict 消除前瞻偏差。否则返回完整 fin。
    """
    report_date = fin.get("report_date", "") if isinstance(fin, dict) else ""
    if not report_date or not trade_day:
        # 无 report_date 或 trade_day 信息，保守返回 fin（维持原行为）
        return fin if isinstance(fin, dict) else {}
    try:
        rd = datetime.strptime(report_date[:10], "%Y-%m-%d")
        td = datetime.strptime(trade_day[:10], "%Y-%m-%d")
        if rd + timedelta(days=_FINANCE_DISCLOSURE_LAG_DAYS) > td:
            return {}  # 财报尚未披露，消除前瞻
    except (ValueError, TypeError):
        pass  # 日期解析失败，保守返回 fin
    return fin if isinstance(fin, dict) else {}


@dataclass
class SimContext:
    """simulate_strategy 的参数封装。"""

    strategy_name: str
    codes: list
    top_n: int = 5
    holding_days: int = 5
    initial_capital: float = 100000
    total_days: int = 60
    commission: float = 0.00025
    stamp_tax: float = 0.001
    slippage: float = 0.001
    weights: dict = None


def simulate_strategy(ctx: SimContext):
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

    P0-10 修复：quality 因子现按 report_date + A 股披露延迟（90 天）
    过滤，仅使用交易日 T 时已公开披露的财务数据，消除前瞻偏差。
    若财务数据尚未披露（report_date + 90 天 > T），quality 因子置 0，
    等效于该因子在回测早期不参与选股。

    Args:
        ctx: 回测上下文（strategy_name, codes, top_n, holding_days,
             initial_capital, total_days, commission, stamp_tax, slippage, weights）

    Returns:
        回测结果 dict
    """
    strategy_name = ctx.strategy_name
    codes = ctx.codes
    top_n = ctx.top_n
    holding_days = ctx.holding_days
    total_days = ctx.total_days
    commission = ctx.commission
    stamp_tax = ctx.stamp_tax
    slippage = ctx.slippage
    weights = ctx.weights

    if weights is None:
        weights = get_strategy(strategy_name)
    min_history = 60

    datalen = min_history + total_days + 10

    # 并行获取 K 线数据
    def _fetch_kline(code):
        ncode = normalize_quote_code(code)
        return get_kline(ncode, scale=240, datalen=datalen)

    kline_data = {}
    stale_cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    raw_kline = parallel_fetch_dict(codes, _fetch_kline, label="backtest:kline")
    for code, bars in raw_kline.items():
        if bars and len(bars) >= min_history and bars[-1].day >= stale_cutoff:
            kline_data[code] = bars

    if not kline_data:
        return {"error": "无法获取足够的 K 线数据"}

    # 并行获取财务数据
    fin_cache = {}
    industry_cache = {}

    def _fetch_finance(code):
        industry = infer_industry("", code)
        try:
            fin_records = get_finance(normalize_finance_code(code))
            fin = fin_records[0].to_dict() if fin_records else {}
        except Exception as e:
            logger.warning("获取财务数据失败 %s: %s", code, e)
            fin = {}
        return industry, fin

    fin_results = parallel_fetch_dict(codes, _fetch_finance, label="backtest:finance")
    for code, (industry, fin) in fin_results.items():
        industry_cache[code] = industry
        fin_cache[code] = fin

    # 滚动窗口回测
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

        fin_raw = fin_cache.get(code, {})
        industry = industry_cache.get(code, "manufacturing")

        i = min_history
        while i + holding_days <= len(bars):
            if bars[i].day < common_start_date:
                i += holding_days
                continue

            # 跳过涨跌停和停牌日
            if _is_limit_or_suspended(bars, i, code):
                i += 1
                continue

            hist = bars[:i]
            momentum = _compute_momentum_from_bars(hist)
            # P0-10: 仅使用交易日已披露的财务数据，消除前瞻偏差
            fin = _visible_fin(fin_raw, bars[i].day)
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

            # 筹码因子（股东户数变化率，静态评分，零网络开销）
            # P1-13 修复：原调用 chip_score_dynamic(hist_quote, fin, industry) 签名错误
            # （chip_score_dynamic 只收 code），TypeError 被 except 吞掉致 chip 因子永远为 0。
            # 改用 chip_score_static(code)，回测中避免网络请求。
            try:
                chip = _chip_score(code)
                if chip > 0:
                    parts["chip"] = chip
            except Exception as e:
                logger.debug("chip 因子计算失败: %s", e)

            # 事件因子（解禁/分红/增减持/违规）
            # 注意：event_score 涉及网络请求，回测中禁用以避免超时
            # 如需启用，请确保事件数据已预加载到缓存

            # 策略权重应用 market regime overlay（Sprint 3 收口）
            regime = _classify_for_backtest(bars[:i]) if i >= 60 else RegimeState.RANGE
            effective_weights = compute_overlay_weights(weights, regime)

            score = sum(
                parts.get(k, 0) * effective_weights.get(k, 0)
                for k in set(parts) | set(effective_weights)
                if k not in ("label", "two_stage")
            )

            # 止损止盈逻辑：-8% 止损，+20% 止盈
            ret, actual_days, exit_reason = _calc_return_with_stop_loss(
                bars, i, holding_days, stop_loss=-0.08, take_profit=0.20
            )
            # 扣除交易成本：佣金(双向) + 印花税(卖出) + 滑点(双向)
            total_cost = commission * 2 + stamp_tax + slippage * 2
            ret -= total_cost
            all_selections.append(
                {
                    "code": code,
                    "date": bars[i].day,
                    "score": round(score, 1),
                    "return_pct": round(ret * 100, 2),
                    "daily_returns": _calc_daily_returns(bars, i, actual_days),
                    "exit_reason": exit_reason,
                    "holding_days": actual_days,
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

    pool_size = len(kline_data)
    # 股票池太小时，降低入选门槛（pool=1 时 min_stocks=1）
    min_stocks = min(top_n, max(1, pool_size, pool_size // 10 * 3))
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
    """计算持有期内的日收益率序列（用于精确回撤计算）。

    P1-26 修复：持仓从 bars[start].close 起算，第 1 天收益应为 bars[start+1]
    相对 bars[start] 的变化。原实现从 j=start 起算（含信号日日内波动），
    与 entry_price=bars[start].close 错位一天，导致回撤/夏普基准偏移。
    """
    returns = []
    for j in range(start + 1, start + 1 + holding_days):
        if j < len(bars) and j > 0 and bars[j - 1].close > 0:
            returns.append((bars[j].close - bars[j - 1].close) / bars[j - 1].close)
    return returns

def _calc_return_with_stop_loss(
    bars, start, holding_days, stop_loss=-0.08, take_profit=0.20
):
    """计算带止损止盈的持有期收益。

    Args:
        bars: K 线数据
        start: 起始索引
        holding_days: 持有天数
        stop_loss: 止损阈值（默认 -8%）
        take_profit: 止盈阈值（默认 +20%）

    Returns:
        (return_pct, exit_day, exit_reason)
    """
    entry_price = bars[start].close
    if entry_price <= 0:
        return 0.0, holding_days, "invalid"

    # P1-27: 止损/止盈用日内 low/high 判断是否触及（而非收盘价），
    # 触及后按阈值价成交（保守估计，避免收盘价回升导致乐观偏差）。
    # day=0 为信号日次日（持仓第 1 天），与 entry_price=bars[start].close 对齐。
    for day in range(1, holding_days + 1):
        idx = start + day
        if idx >= len(bars):
            break
        bar = bars[idx]
        # 日内触及止损（最低价跌破止损线）→ 按止损价成交
        stop_price = entry_price * (1 + stop_loss)
        take_price = entry_price * (1 + take_profit)
        if bar.low <= stop_price:
            return stop_loss, day, "stop_loss"
        if bar.high >= take_price:
            return take_profit, day, "take_profit"

    # 未触发止损止盈，持有到期，用末日收盘价
    exit_idx = min(start + holding_days, len(bars) - 1)
    exit_price = bars[exit_idx].close
    ret = (exit_price - entry_price) / entry_price
    return ret, holding_days, "normal"


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


def _is_limit_or_suspended(bars, idx, code=""):
    """检查指定日期是否涨跌停或停牌。

    涨跌停判断：当日涨跌幅接近 ±10%（普通股）或 ±20%（创业板/科创板）。
    停牌判断：成交量为 0。

    Args:
        bars: K 线数据
        idx: 当前索引
        code: 股票代码（如 sz300001/sh688001），用于判断 20cm 涨跌幅板。
            KlineBar 无 code 字段，须由调用方传入。

    Returns:
        True 表示应跳过该日
    """
    if idx <= 0 or idx >= len(bars):
        return False

    bar = bars[idx]
    prev = bars[idx - 1]
    prev_close = prev.close if hasattr(prev, "close") else prev.get("close", 0)
    bar_close = bar.close if hasattr(bar, "close") else bar.get("close", 0)
    volume = bar.volume if hasattr(bar, "volume") else bar.get("volume", 0)

    # 停牌：成交量为 0 且价格无变化（真正的停牌）
    if volume <= 0 and bar_close == prev_close:
        return True

    # 涨跌停：涨跌幅接近 ±10% 或 ±20%
    if prev_close > 0 and bar_close > 0:
        change_pct = (bar_close - prev_close) / prev_close
        # 创业板/科创板 20% 涨跌幅
        limit = 0.195 if code.startswith(("sz300", "sz301", "sh688")) else 0.095
        if abs(change_pct) >= limit:
            return True

    return False

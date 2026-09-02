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
from strategies.factors.momentum import momentum_score
from technical.pipeline import compute_indicators
from strategies.regime import compute_overlay_weights, RegimeState
from strategies.regime.classifier import classify_regime
from strategies.regime.detector import compute_signals_from_bars
from config.loader import safe_get
from classifier import infer_industry

logger = logging.getLogger(__name__)

# 因子计算所需的最小历史 K 线根数（回测评估起点）。
# metrics._fetch_benchmark_returns 依赖此常量对齐基准与策略评估窗口。
MIN_HISTORY = 60


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


# A 股财报披露延迟（天）。季报/年报在报告截止日后的法定披露窗口：
#   一季报 4/30、半年报 8/31、三季报 10/31、年报 4/30。
#   取 90 天作为保守上限，确保回测中仅使用已公开披露的财务数据。
_FINANCE_DISCLOSURE_LAG_DAYS = 90


def _visible_fin(fin: dict, trade_day: str) -> dict:
    """返回交易日 trade_day 时已公开披露的财务数据。

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
    weights: dict | None = None
    # v1.21.1 盈亏比修复：ATR 自适应止损 + 移动止盈。
    # 均为 None 时保持原固定阈值行为（-8% 止损 / +20% 止盈），不改变既有回测结果。
    atr_stop_multiplier: float | None = None  # 止损价 = 入场价 - k×ATR
    trailing_stop_pct: float | None = None  # 移动止盈：最高价回撤 X% 卖出
    # walk-forward 窗口（修复：原实现窗口边界从未传给引擎，OOS 数据被 IS 见过）。
    # eval_start: 收益评估起点（bars 索引，0=全部）；window_end: 模拟终点（None=全部）。
    # 因子计算始终用 bars[:i] 全历史（无前瞻），仅评估区间受窗口限制。
    eval_start: int = 0
    eval_end: int | None = None


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

    修复：quality 因子现按 report_date + A 股披露延迟（90 天）
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
    atr_stop_multiplier = ctx.atr_stop_multiplier
    trailing_stop_pct = ctx.trailing_stop_pct

    if weights is None:
        weights = get_strategy(strategy_name)
    min_history = MIN_HISTORY

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
        source = None
        is_degraded = False
        try:
            # 解构 (records, meta) tuple
            fin_records, _meta = get_finance(normalize_finance_code(code))
            fin = fin_records[0].to_dict() if fin_records else {}
            if _meta is not None:
                source = getattr(_meta, "source", None)
                is_degraded = getattr(_meta, "is_degraded", False)
        except Exception as e:
            logger.warning("获取财务数据失败 %s: %s", code, e)
            fin = {}
        return industry, fin, source, is_degraded

    finance_sources = set()
    finance_degraded = False
    fin_results = parallel_fetch_dict(codes, _fetch_finance, label="backtest:finance")
    for code, payload in fin_results.items():
        # 兼容旧签名（无 source/is_degraded）
        if len(payload) == 2:
            industry, fin = payload
        else:
            industry, fin, src, deg = payload
            if src:
                finance_sources.add(src)
            finance_degraded = finance_degraded or deg
        industry_cache[code] = industry
        fin_cache[code] = fin

    # 指数级 regime 判定数据源（复用 kline_data，缺失时拉取一次）
    index_bars = _fetch_index_bars_for_backtest(kline_data)

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
        # eval_end 上限 = len(bars)（datalen 不足时窗口截断，不越界）
        eval_end = min(ctx.eval_end, len(bars)) if ctx.eval_end is not None else len(bars)
        while i + holding_days <= eval_end:
            if bars[i].day < common_start_date:
                i += holding_days
                continue

            # 跳过涨跌停和停牌日
            if _is_limit_or_suspended(bars, i, code):
                i += 1
                continue

            # 仅使用交易日已披露的财务数据，消除前瞻偏差
            fin = _visible_fin(fin_raw, bars[i].day)
            hist_quote = _build_hist_quote(bars, i, fin, code)

            # 评分同源化：与 screener 的 compute_all_factors 同一套因子
            # （原 quality ×0.85 系数仅回测存在；momentum 用自研分桶而非 momentum_score）
            features = compute_indicators(bars[:i])

            # 两阶段策略（turning_point）：Stage 1 硬条件过滤，与实盘 screener 同源。
            # 修复：原回测引擎未实现 two_stage，turning_point 回测只是 balanced 变权，
            # 与实盘"先硬过滤再打分"口径不一致。财务未披露（fin 为空）时跳过过滤——
            # 保守不误杀（无法确认基本面）；flow_data=[] 避免资金流网络请求。
            # 用策略注册表标记而非 weights（optimize_weights 传入的自定义 weights
            # 不含 two_stage 键，会导致过滤静默失效）。
            if get_strategy(strategy_name).get("two_stage") and fin:
                from strategies.filters.turning_point import turning_point_filter

                pass_, _reason = turning_point_filter(hist_quote, fin, features, flow_data=[])
                if not pass_:
                    i += holding_days
                    continue

            parts = {
                "quality": quality_score(fin, industry),
                "valuation": valuation_score(hist_quote, fin, industry),
                "momentum": momentum_score(features, hist_quote),
                "liquidity": liquidity_score(hist_quote),
                "volatility": _volatility_score(bars[:i], industry),
            }
            dividend = _calc_dividend_score(hist_quote, fin, industry)
            if dividend > 0:
                parts["dividend"] = dividend

            # 筹码因子（股东户数变化率，静态评分，零网络开销）
            # 修复：原调用 chip_score_dynamic(hist_quote, fin, industry) 签名错误
            # （chip_score_dynamic 只收 code），TypeError 被 except 吞掉致 chip 因子永远为 0。
            # 改用 chip_score_static(code)，回测中避免网络请求。
            # v1.22.1 修复：传 trade_day 做披露时点过滤，消除 chip 因子前瞻偏差
            # （原实现用当前股东户数数据评分历史所有时点）。
            try:
                chip = _chip_score(code, trade_day=bars[i].day)
                if chip > 0:
                    parts["chip"] = chip
            except Exception as e:
                logger.debug("chip 因子计算失败: %s", e)

            # 事件因子（解禁/分红/增减持/违规）
            # 注意：event_score 涉及网络请求，回测中禁用以避免超时
            # 如需启用，请确保事件数据已预加载到缓存

            # 策略权重应用 market regime overlay
            # 修复：v2.8 的指数级 regime 判定（_fetch_index_bars_for_backtest /
            # _classify_regime_from_index）此前无调用方，主路径仍用个股 bars 误判
            # regime。现改为指数 bars + current_day 截断（严格无前瞻）。
            if i >= 60:
                regime, extreme_drop = _classify_regime_from_index(index_bars, bars[i].day)
            else:
                regime, extreme_drop = RegimeState.RANGE, False
            effective_weights = compute_overlay_weights(weights, regime, extreme_drop=extreme_drop)

            score = sum(
                parts.get(k, 0) * effective_weights.get(k, 0)
                for k in set(parts) | set(effective_weights)
                if k not in ("label", "two_stage")
            )

            # 止损止盈逻辑：默认 -8% 止损 / +20% 止盈；
            # v1.21.1 起支持 ATR 自适应止损（atr_stop_multiplier）与
            # 移动止盈（trailing_stop_pct），见 _calc_return_with_stop_loss
            ret, actual_days, exit_reason = _calc_return_with_stop_loss(
                bars,
                i,
                holding_days,
                stop_loss=-0.08,
                take_profit=0.20,
                atr_multiplier=atr_stop_multiplier,
                trailing_pct=trailing_stop_pct,
            )
            # 扣除交易成本：佣金(双向) + 印花税(卖出) + 滑点(双向)
            total_cost = commission * 2 + stamp_tax + slippage * 2
            ret -= total_cost
            if i < ctx.eval_start:
                i += holding_days
                continue  # walk-forward：评估区间外的轮次不计入结果
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
    # v1.22.1: 每期日收益分段（供分位置胜率按持有期统计，而非全局拼接）
    portfolio_period_daily_returns = []
    selection_details = []

    for date in sorted(valid_dates):
        group_list = sorted(date_groups[date], key=lambda x: x["score"], reverse=True)[:top_n]
        avg_ret = sum(s["return_pct"] for s in group_list) / len(group_list)
        portfolio_returns.append(avg_ret / 100)
        stock_daily_returns = [s["daily_returns"] for s in group_list if s["daily_returns"]]
        if stock_daily_returns:
            max_len = max(len(d) for d in stock_daily_returns)
            period_daily = []
            for day_idx in range(max_len):
                day_returns = [d[day_idx] for d in stock_daily_returns if day_idx < len(d)]
                if day_returns:
                    period_daily.append(sum(day_returns) / len(day_returns))
            portfolio_daily_returns.extend(period_daily)
            portfolio_period_daily_returns.append(period_daily)
        selection_details.extend(group_list)

    if not portfolio_returns:
        return {"error": "回测失败，无有效数据"}

    avg_return = sum(portfolio_returns) / len(portfolio_returns) * 100

    return {
        "strategy": strategy_name,
        "selections": selection_details[:20],
        "returns": [round(r * 100, 2) for r in portfolio_returns],
        "daily_returns": portfolio_daily_returns,
        "period_daily_returns": portfolio_period_daily_returns,
        "avg_return_pct": round(avg_return, 2),
        "total_periods": len(portfolio_returns),
        "holding_days": holding_days,
        "top_n": top_n,
        "data_sources": (sorted(finance_sources) if finance_sources else ["K线(多源聚合)"]),
        "is_degraded": finance_degraded,
    }


def _calc_daily_returns(bars, start, holding_days):
    """计算持有期内的日收益率序列（用于精确回撤计算）。

    修复：持仓从 bars[start].close 起算，第 1 天收益应为 bars[start+1]
    相对 bars[start] 的变化。原实现从 j=start 起算（含信号日日内波动），
    与 entry_price=bars[start].close 错位一天，导致回撤/夏普基准偏移。
    """
    returns = []
    for j in range(start + 1, start + 1 + holding_days):
        if j < len(bars) and j > 0 and bars[j - 1].close > 0:
            returns.append((bars[j].close - bars[j - 1].close) / bars[j - 1].close)
    return returns


def _calc_atr(bars, period: int = 14) -> float:
    """计算给定 K 线段的平均真实波幅（ATR）。

    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    ATR = 最近 period 根 TR 的简单平均。

    Args:
        bars: K 线列表（需含 high/low/close 字段）
        period: ATR 周期（默认 14）

    Returns:
        ATR 值；数据不足时返回 0（调用方回退到固定止损）
    """
    if not bars or len(bars) < period + 1:
        return 0.0
    trs = []
    for j in range(len(bars) - period, len(bars)):
        bar = bars[j]
        prev_close = bars[j - 1].close if j > 0 else bar.open
        if prev_close <= 0:
            continue
        tr = max(
            bar.high - bar.low,
            abs(bar.high - prev_close),
            abs(bar.low - prev_close),
        )
        trs.append(tr)
    if not trs:
        return 0.0
    return sum(trs) / len(trs)


def _calc_return_with_stop_loss(
    bars,
    start,
    holding_days,
    stop_loss=-0.08,
    take_profit=0.20,
    atr_multiplier=None,
    trailing_pct=None,
):
    """计算带止损止盈的持有期收益。

    三种模式（v1.21.1 起）：
    1. 默认（atr_multiplier=None 且 trailing_pct=None）：固定阈值，
       stop_loss=-8% / take_profit=+20%，行为与历史版本完全一致。
    2. ATR 止损（atr_multiplier=k）：止损价 = 入场价 - k×ATR(14)，
       波动率归一，高波动股不再被固定 -8% 频繁截断。
    3. 移动止盈（trailing_pct=x）：持仓期间最高价回撤超过 x% 即卖出，
       让盈利单跑出趋势，替代固定 +20% 止盈。

    Args:
        bars: K 线数据
        start: 起始索引
        holding_days: 持有天数
        stop_loss: 固定止损阈值（默认 -8%）
        take_profit: 固定止盈阈值（默认 +20%）
        atr_multiplier: ATR 止损倍数（None = 固定止损）
        trailing_pct: 移动止盈回撤比例（None = 固定止盈）

    Returns:
        (return_pct, exit_day, exit_reason)
    """
    entry_price = bars[start].close
    if entry_price <= 0:
        return 0.0, holding_days, "invalid"

    # ATR 止损：用 start 之前（不含当日）的 K 线计算，严格无前瞻
    if atr_multiplier is not None:
        atr = _calc_atr(bars[:start], period=14)
        if atr > 0:
            stop_price = entry_price - atr_multiplier * atr
        else:
            stop_price = entry_price * (1 + stop_loss)  # ATR 不可用回退固定
    else:
        stop_price = entry_price * (1 + stop_loss)

    # 止损/止盈用日内 low/high 判断是否触及（而非收盘价），
    # 触及后按阈值价成交（保守估计，避免收盘价回升导致乐观偏差）。
    # day=0 为信号日次日（持仓第 1 天），与 entry_price=bars[start].close 对齐。
    # 移动止盈例外：用收盘价触发（methodology 止损铁律"收盘确认"），
    # 避免当日冲高后回落立即触发（日内 high 与 low 的顺序不可知）。
    trailing_peak = entry_price
    for day in range(1, holding_days + 1):
        idx = start + day
        if idx >= len(bars):
            break
        bar = bars[idx]
        # 移动止盈：更新最高价（收盘确认），回撤超过 trailing_pct 即卖出
        if trailing_pct is not None:
            if bar.high > trailing_peak:
                trailing_peak = bar.high
            if trailing_peak > entry_price:
                trail_stop = trailing_peak * (1 - trailing_pct)
                if bar.close <= trail_stop:
                    # 按移动止盈价成交（保守估计）
                    ret = (trail_stop - entry_price) / entry_price
                    return ret, day, "take_profit"
        # 日内触及止损（最低价跌破止损线）→ 按止损价成交。
        # v1.22.1 修复：ATR 模式下返回实际止损价收益（stop_price-entry）/entry。
        # ATR 止损价可宽于固定 -8%，原实现恒返回 stop_loss（-8%）会系统性
        # 少报亏损、高估回测收益。固定模式（atr_multiplier=None）保持返回
        # stop_loss 原值，不改变既有回测结果。
        if bar.low <= stop_price:
            if atr_multiplier is not None:
                return (stop_price - entry_price) / entry_price, day, "stop_loss"
            return stop_loss, day, "stop_loss"
        # 固定止盈（仅非移动止盈模式）
        if trailing_pct is None:
            take_price = entry_price * (1 + take_profit)
            if bar.high >= take_price:
                return take_profit, day, "take_profit"

    # 未触发止损止盈，持有到期，用末日收盘价
    exit_idx = min(start + holding_days, len(bars) - 1)
    exit_price = bars[exit_idx].close
    ret = (exit_price - entry_price) / entry_price
    return ret, holding_days, "normal"


def _calc_rsi(closes: list, period: int = 14) -> float:
    """计算 RSI（Wilder 平滑），无前瞻。保留为公共工具（测试引用）。"""
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


def _calc_dividend_score(hist_quote: dict, fin: dict, industry: str) -> float:
    """计算红利因子得分（回测用，轻量版）。"""
    try:
        from strategies.factors.dividend import dividend_score

        return dividend_score(hist_quote, fin, industry)
    except ImportError:
        return 0.0


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


# ════════════════════════════════════════
# v2.8: 指数级 regime 判定（修复回测用个股 bars 误判的 P0 bug）
# ════════════════════════════════════════


def _fetch_index_bars_for_backtest(kline_data: dict):
    """为回测获取 sh000300 指数 K 线。

    优先使用调用方已有的 kline_data["sh000300"]（避免重复网络拉取），
    缺失时调用 get_kline 拉取，失败返回空列表。

    Args:
        kline_data: 模拟上下文中已有的 K 线字典 {code: [KlineBar]}

    Returns:
        指数 K 线列表（最近的 bar 在末尾），失败时返回 []
    """
    if not isinstance(kline_data, dict):
        return []

    existing = kline_data.get("sh000300")
    if existing:
        return existing

    try:
        # v2.8: 拉取 80 根 K 线（gate 80 阈值，与 _classify_regime_from_index 对齐）。
        # v1.22.1 修复：walk-forward 旧窗口的 current_day 早于最近 80 根时，
        # 截断后 < 80 根导致 regime 恒为 RANGE_LOW_VOL。现按最深个股 K 线序列
        # 同深拉取，覆盖整个回测窗口（gate 仍为 80）。
        max_depth = max((len(b) for b in kline_data.values()), default=80)
        return get_kline("sh000300", scale=240, datalen=max(80, max_depth))
    except Exception as e:
        logger.debug("backtest 拉取 sh000300 失败: %s", e)
        return []


def _classify_regime_from_index(index_bars, current_day: str):
    """v2.8: 用沪深 300 指数 bars 判定市场状态（严格无前瞻）。

    与原 _classify_for_backtest 的关键差异：
      1. 数据源：指数 bars（屏蔽个股异动对 regime 的污染）
      2. 截断：current_day 之前（含）的 bars 才参与计算，杜绝未来函数
      3. Gate：< 80 根时降级 RANGE_LOW_VOL（数据不足以判定）

    Args:
        index_bars: 指数 K 线列表（最近的 bar 在末尾）
        current_day: 回测当前交易日（YYYY-MM-DD）；只用此日期及之前的 bars

    Returns:
        (regime, extreme_drop) 二元组：
          - regime: RegimeState 枚举值
          - extreme_drop: bool，是否触发极端跌幅降动量
    """
    if not index_bars:
        return RegimeState.RANGE_LOW_VOL, False

    # 无前瞻：只用 current_day 之前的 bars
    truncated = [b for b in index_bars if getattr(b, "day", "") <= current_day]
    if len(truncated) < 80:
        return RegimeState.RANGE_LOW_VOL, False

    # 计算 4 类信号
    signals = compute_signals_from_bars(truncated)
    regime = classify_regime(signals)

    # 检测 extreme_drop：近 N 个交易日内是否有任意单日跌幅 < 阈值
    threshold = safe_get("regime.yaml", "thresholds.extreme_drop_threshold", -0.05)
    window = safe_get("regime.yaml", "thresholds.extreme_drop_window", 10)
    extreme_drop = _has_extreme_drop(truncated, window, threshold)

    return regime, extreme_drop


def _has_extreme_drop(bars, window: int, threshold: float) -> bool:
    """检测近 window 个交易日内是否有任意单日跌幅 < threshold。"""
    if not bars or len(bars) < 2:
        return False

    recent = list(bars[-window:]) if len(bars) > window else list(bars)
    for i in range(1, len(recent)):
        prev_close = to_float(recent[i - 1].close)
        curr_close = to_float(recent[i].close)
        if prev_close > 0 and curr_close > 0:
            change_pct = (curr_close - prev_close) / prev_close
            if change_pct < threshold:
                return True
    return False

"""
动量派评分函数（利弗莫尔 + 理查德·丹尼斯）。

人设：趋势跟踪 + 关键转折点突破 + 海龟法则（系统化止损/加仓）。
核心逻辑：
- 技术面权重最高（40%）：MA 多头排列 + 关键转折点突破 + 量价配合
- 情绪/资金（25%）：板块共振 + 量能放大
- 风险（20%）：流动性 + ATR + 距止损空间
- 基本面（10%）：仅作排除性（亏损股/ST/造假）
- 估值（5%）：动量派不重估值，看势不看法

仓位建议规则（海龟法则）：
- 单笔风险 ≤ 账户 2%
- 同时持仓不超过 3-4 个标的
- 单一板块暴露 ≤ 25%
"""

from typing import Dict

from ._utils import _safe_float


def _ma(values, n: int) -> float:
    """简单移动平均（无值时返回 0）。"""
    if not values or len(values) < n:
        return 0.0
    return sum(values[-n:]) / n


def score(stock_data: dict) -> Dict[str, float]:
    """动量派专属评分：趋势强度 + 关键转折点 + 量价配合。

    Args:
        stock_data: 包含 quote / finance / kline_data / market_features。

    Returns:
        {基本面, 估值, 技术面, 情绪/资金, 风险} 五维分值（0-100）。
    """
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline = stock_data.get("kline_features") or {}
    market = stock_data.get("market_features") or {}
    kline_data = stock_data.get("kline_data") or {}

    # P2-04: ST 股票硬 veto -- 动量派不追 ST/退市风险股
    stock_name = quote.get("name", "") or ""
    from data.pool import is_st

    if is_st(stock_name):
        return {
            "基本面": 10,
            "估值": 10,
            "技术面": 20,
            "情绪/资金": 10,
            "风险": 10,
        }

    closes = kline_data.get("closes") or []
    volumes = kline_data.get("volumes") or []
    highs = kline_data.get("highs") or []

    # ── 基本面：仅作排除性（亏损股=陷阱）──
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    profit_yoy = _safe_float(fin.get("PARENTNETPROFITTZ") or fin.get("net_profit_yoy"))
    revenue_yoy = _safe_float(fin.get("TOTALOPERATEREVETZ") or fin.get("revenue_yoy"))

    # 动量派不在乎具体基本面，但排除"亏损股+造假+退市"
    if roe < 0 or profit_yoy < -30:
        fundamental = 10  # 价值陷阱信号
    elif revenue_yoy > 0 and roe > 0:
        fundamental = 70  # 不拖后腿
    else:
        fundamental = 50  # 默认中性（动量派不深究）

    # ── 估值：仅作背景，动量派不看估值 ──
    pe = _safe_float(quote.get("pe"))
    if pe > 0 and pe <= 80:
        valuation = 55  # 不极端即可
    elif pe > 80:
        valuation = 35  # 估值极贵，趋势末端风险高
    elif pe < 0:
        valuation = 30  # 亏损
    else:
        valuation = 50  # 数据缺失

    # ── 技术面：趋势强度 + 关键转折点 + 量价（动量派核心）──
    tech_score = 50  # 默认

    if len(closes) >= 120:
        ma20 = _ma(closes, 20)
        ma60 = _ma(closes, 60)
        ma120 = _ma(closes, 120)
        price = closes[-1]

        # 多头排列：MA20 > MA60 > MA120 且价格 > MA20
        if price > ma20 > ma60 > ma120:
            tech_score = 100
        elif price > ma20 > ma60:
            tech_score = 80
        elif price > ma20:
            tech_score = 60
        elif price < ma20 < ma60 < ma120:
            tech_score = 0
        elif price < ma20 < ma60:
            tech_score = 20
        else:
            tech_score = 40

    # 关键转折点加分：突破 60 日高点
    if len(closes) >= 60 and highs:
        high_60 = max(highs[-60:])
        if closes[-1] >= high_60 * 0.98:
            tech_score = min(100, tech_score + 15)  # 突破关键转折点加分

    # 量价确认：突破日量能 ≥ 5 日均量 × 2
    if len(volumes) >= 5:
        vol_ma5 = _ma(volumes, 5)
        if vol_ma5 > 0 and volumes[-1] >= vol_ma5 * 2.0:
            tech_score = min(100, tech_score + 10)  # 放量确认加分

    # 辅助：kline_features 趋势补充（数据不足时用）
    trend_kf = kline.get("trend", 0)
    if trend_kf > 0 and tech_score < 70:
        tech_score = min(100, tech_score + 5)

    # ── 情绪/资金：板块共振 + 量能 + 涨停家数 ──
    sentiment = 50
    limit_up = market.get("limit_up_count", 0) or 0
    sector_limit_up = market.get("sector_limit_up_count", 0) or 0
    advance_ratio = market.get("advance_ratio")

    # 板块共振加分（同板块 ≥3 家涨停）
    if sector_limit_up >= 5:
        sentiment += 25
    elif sector_limit_up >= 3:
        sentiment += 15
    elif sector_limit_up >= 1:
        sentiment += 5
    else:
        sentiment -= 10  # 孤立突破扣分

    # 量能配合
    if len(volumes) >= 20:
        vol_ma20 = _ma(volumes, 20)
        if vol_ma20 > 0 and volumes[-1] >= vol_ma20 * 1.5:
            sentiment += 15  # 量能放大
        elif vol_ma20 > 0 and volumes[-1] < vol_ma20 * 0.5:
            sentiment -= 15  # 缩量

    # 大盘情绪（仅作辅助）
    if limit_up > 80:
        sentiment += 10  # 普涨环境加分
    elif limit_up < 15:
        sentiment -= 15  # 冰点环境扣分

    if advance_ratio is not None:
        if advance_ratio > 0.6:
            sentiment += 5
        elif advance_ratio < 0.3:
            sentiment -= 10

    sentiment = max(0, min(100, sentiment))

    # ── 风险：流动性 + ATR + 距止损空间 ──
    risk_score = 50

    # 流动性（成交额，单位：元，与 Quote.amount 一致）
    amount = _safe_float(quote.get("amount"))
    # 转换为亿元：10 亿、5 亿、2 亿为流动性阈值
    amount_yi = amount / 1e8 if amount > 0 else 0

    if amount_yi >= 10:
        risk_score += 25  # 流动性充裕
    elif amount_yi >= 5:
        risk_score += 15
    elif amount_yi >= 2:
        risk_score += 5
    elif amount_yi > 0:
        risk_score -= 30  # 流动性不足，无法止损
    else:
        risk_score -= 20  # 数据缺失

    # ATR 波动性（动量派偏好波动适中）
    atr_pct = 0.0
    if (
        len(closes) >= 14
        and len(highs) >= 14
        and len(kline_data.get("lows") or []) >= 14
    ):
        lows = kline_data.get("lows") or []
        trs = []
        for i in range(-14, 0):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]) if i - 1 >= -len(closes) else 0,
                abs(lows[i] - closes[i - 1]) if i - 1 >= -len(closes) else 0,
            )
            trs.append(tr)
        if trs and closes[-1] > 0:
            atr = sum(trs) / len(trs)
            atr_pct = atr / closes[-1] * 100

    if 2.0 <= atr_pct <= 6.0:
        risk_score += 15  # 波动适中
    elif atr_pct > 8.0:
        risk_score -= 15  # 波动过大，止损易触发
    elif atr_pct > 0 and atr_pct < 1.5:
        risk_score -= 5  # 波动过小，趋势空间有限

    # 距 MA20 的偏离度（过远=超买风险）
    if len(closes) >= 20 and closes[-1] > 0:
        ma20 = _ma(closes, 20)
        if ma20 > 0:
            deviation = (closes[-1] - ma20) / ma20 * 100
            if deviation > 15:
                risk_score -= 15  # 超买
            elif deviation < -15:
                risk_score -= 20  # 远离均线，下跌趋势中

    risk_score = max(0, min(100, risk_score))

    return {
        "基本面": fundamental,
        "估值": valuation,
        "技术面": tech_score,
        "情绪/资金": sentiment,
        "风险": risk_score,
    }


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """动量派评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["momentum_trader"]
    return generic_score_with_reasoning(profile, score, stock_data)

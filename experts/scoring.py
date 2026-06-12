"""
专家评分引擎。

v1.3.2 引入通用启发式；v2.0.0 新增每位专家专属评分函数。

提供两套评分路径：
- score_expert(): 通用启发式（fallback，所有专家共用同一套简单规则）
- score_expert_precise(): 专家专属评分（精确复现 experts/*.md §九 评分矩阵）

通用路径供兼容和降级使用；精确路径是 debate 模式的推荐评分方式，
输出可作为 LLM 推理的量化基线参考。

Args:
    profile: ExpertProfile 实例
    dim_scores: Dict[dimension_name, 0..100]，缺维度视为 50 (中性)

Returns:
    0-100 之间的浮点分
"""
import statistics
from typing import Callable, Dict, List, Optional
from . import ExpertProfile, direction_from_score


# ═══════════════════════════════════════════════════════════════
# 基础工具函数
# ═══════════════════════════════════════════════════════════════

def score_from_dimensions(profile: ExpertProfile, dim_scores: Dict[str, float]) -> float:
    """根据维度分和权重计算专家总分（0-100）。

    Args:
        profile: 专家人设（含 5 维度权重）
        dim_scores: 维度分 dict。缺维度视为 50（中性）。

    Returns:
        0-100 之间的总分
    """
    total = 0.0
    for dim, weight in profile.weights.items():
        score = dim_scores.get(dim, 50.0)
        score = max(0.0, min(100.0, float(score)))
        total += score * (weight / 100.0)
    return max(0.0, min(100.0, total))


def dimension_breakdown(profile: ExpertProfile, dim_scores: Dict[str, float]) -> Dict[str, float]:
    """返回每个维度的加权贡献（用于在 debate 报告中显示）。

    与 score_from_dimensions 一致，对输入分值做 0-100 钳制。
    """
    breakdown = {}
    for dim, weight in profile.weights.items():
        score = dim_scores.get(dim, 50.0)
        score = max(0.0, min(100.0, float(score)))
        breakdown[dim] = round(score * (weight / 100.0), 2)
    return breakdown


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════
# 通用启发式评分（v1.3.2，所有专家共用，作为 fallback）
# ═══════════════════════════════════════════════════════════════

def _score_fundamentals(fin: dict) -> float:
    """基本面维度：ROE + 净利增速 + 营收增速 + 毛利率。"""
    if not fin:
        return 50.0
    roe = float(fin.get("roe") or fin.get("ROEJQ") or 0)
    profit_yoy = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0)
    revenue_yoy = float(fin.get("revenue_yoy") or fin.get("TOTALOPERATEREVETZ") or 0)
    gross_margin = float(fin.get("gross_margin") or fin.get("XSMLL") or 0)
    debt = float(fin.get("debt_ratio") or fin.get("ZCFZL") or 0)

    score = 0
    score += min(100, roe * 5)
    score += min(100, max(0, profit_yoy + 50))
    score += min(100, max(0, revenue_yoy + 50))
    score += min(100, gross_margin * 2)
    score += min(100, max(0, 100 - debt))
    return round(score / 5, 1)


def _score_valuation(quote: dict, fin: dict) -> float:
    """估值维度：PE + PEG。"""
    if not quote:
        return 50.0
    pe = float(quote.get("pe") or 0)
    pb = float(quote.get("pb") or 0)
    growth = float(fin.get("net_profit_yoy") or fin.get("PARENTNETPROFITTZ") or 0) if fin else 0

    if pe <= 0 and pb <= 0:
        return 50.0

    score = 0
    if pe > 0:
        if pe <= 15:
            score += 60
        elif pe <= 25:
            score += 45
        elif pe <= 40:
            score += 25
        else:
            score += 10
    if pb > 0 and pb <= 2:
        score += 20
    elif pb > 0 and pb <= 5:
        score += 10
    if pe > 0 and growth > 0:
        peg = pe / growth
        if peg <= 1.0:
            score += 20
        elif peg <= 2.0:
            score += 10
    return min(100, max(0, score))


def _score_technical(kline_features: dict) -> float:
    """技术面维度：趋势 + RSI + MACD。"""
    if not kline_features:
        return 50.0
    score = 50
    trend = kline_features.get("trend", 0)
    if trend > 0:
        score += 20
    elif trend < 0:
        score -= 20

    rsi = kline_features.get("rsi", 50)
    if 30 <= rsi <= 70:
        score += 5
    elif rsi > 80:
        score -= 15
    elif rsi < 20:
        score -= 5

    macd = kline_features.get("macd_signal", 0)
    if macd > 0:
        score += 10
    elif macd < 0:
        score -= 10

    return max(0, min(100, score))


def _score_sentiment(market_features: dict) -> float:
    """情绪/题材维度：基于市场行情（上涨家数比+涨停家数+炸板率+两融余额占比）。"""
    if not market_features:
        return 50.0
    score = 50

    advance_ratio = market_features.get("advance_ratio", None)
    if advance_ratio is not None:
        if advance_ratio > 0.6:
            score += 15
        elif advance_ratio > 0.4:
            score += 5
        elif advance_ratio < 0.3:
            score -= 15
        elif advance_ratio < 0.2:
            score -= 25

    nh_nl_ratio = market_features.get("nh_nl_ratio", None)
    if nh_nl_ratio is not None:
        if nh_nl_ratio > 1.5:
            score += 10
        elif nh_nl_ratio < 0.5:
            score -= 10
        elif nh_nl_ratio < 0.2:
            score -= 20

    limit_up_count = market_features.get("limit_up_count", 0)
    if limit_up_count > 80:
        score += 15
    elif limit_up_count > 50:
        score += 10
    elif limit_up_count > 30:
        score += 5
    elif limit_up_count < 15:
        score -= 15

    limit_down_count = market_features.get("limit_down_count", 0)
    if limit_down_count > 50:
        score -= 25
    elif limit_down_count > 20:
        score -= 10

    margin_ratio = market_features.get("margin_ratio", None)
    if margin_ratio is not None:
        if margin_ratio > 0.10:
            score -= 15
        elif margin_ratio < 0.04:
            score -= 5

    return max(0, min(100, score))


def score_expert(
    profile: ExpertProfile,
    stock_data: dict,
) -> dict:
    """通用启发式评分（v1.3.2 fallback）。

    所有专家共用同一套简单规则，不区分专家风格。
    精确评分请使用 score_expert_precise()。
    """
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    dim_scores: Dict[str, float] = {}
    for dim in profile.weights:
        if dim in ("基本面", "fundamentals"):
            dim_scores[dim] = _score_fundamentals(fin)
        elif dim in ("估值", "valuation"):
            dim_scores[dim] = _score_valuation(quote, fin)
        elif dim in ("技术面", "technical"):
            dim_scores[dim] = _score_technical(kline_features)
        elif dim in ("情绪", "情绪/题材", "情绪/反身性", "sentiment"):
            dim_scores[dim] = _score_sentiment(market_features)
        elif dim in ("安全边际", "margin_of_safety", "margin"):
            margin = (_score_valuation(quote, fin) * 0.5 +
                      _score_fundamentals(fin) * 0.5)
            dim_scores[dim] = round(margin, 1)
        elif dim in ("风险", "risk"):
            risk = (
                _score_fundamentals(fin) * 0.4 +
                _score_valuation(quote, fin) * 0.3 +
                (100 - float(fin.get("debt_ratio") or fin.get("ZCFZL") or 50)) * 0.3
            )
            dim_scores[dim] = round(max(0, min(100, risk)), 1)
        else:
            dim_scores[dim] = 50.0

    total = score_from_dimensions(profile, dim_scores)
    return {
        "score": round(total, 1),
        "direction": direction_from_score(total),
        "breakdown": dimension_breakdown(profile, dim_scores),
        "dim_scores": dim_scores,
    }


# ═══════════════════════════════════════════════════════════════
# v2.0.0: 专家专属评分函数
# 精确复现 experts/*.md §九 评分矩阵中的阈值规则
# ═══════════════════════════════════════════════════════════════

# ------ 巴菲特 ------
# 维度：基本面(42%) + 估值(28%) + 技术面(5%) + 情绪(5%) + 安全边际(20%)

def _score_buffett(stock_data: dict) -> Dict[str, float]:
    """巴菲特专属评分：ROE 阶梯 + PE 阶梯 + 负债率/FCF 安全边际。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline = stock_data.get("kline_features") or {}

    # 基本面：ROE 阶梯
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    if roe >= 20:
        base = 100
    elif roe >= 15:
        base = 75
    elif roe >= 10:
        base = 40
    else:
        base = 0

    # 估值：PE 阶梯 + 历史分位调整
    pe = _safe_float(quote.get("pe"))
    if pe <= 0:
        val = 50.0
    elif pe <= 15:
        val = 100
    elif pe <= 25:
        val = 60
    elif pe <= 40:
        val = 25
    else:
        val = 0
    # PE 历史分位调整（近5年）
    pe_percentile = _safe_float(quote.get("pe_percentile"), -1)
    if 0 <= pe_percentile < 20:
        val = _clamp(val + 15)
    elif pe_percentile > 80:
        val = _clamp(val - 20)

    # 技术面：简单趋势
    trend = kline.get("trend", 0)
    tech = 60 if trend > 0 else (40 if trend == 0 else 20)

    # 情绪：简单情绪
    market = stock_data.get("market_features") or {}
    adv = market.get("advance_ratio")
    if adv is not None:
        sent = 70 if adv > 0.5 else (50 if adv > 0.3 else 20)
    else:
        sent = 50

    # 安全边际：负债率 + FCF
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"))
    eps = _safe_float(fin.get("EPSJB") or fin.get("eps"))
    ocf = _safe_float(fin.get("MGJYXJJE") or fin.get("ocf_per_share"))
    fcf_ratio = ocf / max(abs(eps), 0.01) if eps > 0 else 0
    if debt < 30 and fcf_ratio > 0.8:
        margin = 100
    elif debt < 50:
        margin = 60
    else:
        margin = 0

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "安全边际": margin}


# ------ 彼得·林奇 ------
# 维度：基本面(35%) + 估值(28%) + 技术面(15%) + 情绪(10%) + 风险(12%)

def _score_lynch(stock_data: dict) -> Dict[str, float]:
    """林奇专属评分：净利增速阶梯 + PEG 阶梯 + 负债率风险。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline = stock_data.get("kline_features") or {}

    # 基本面：净利增速阶梯
    profit_growth = _safe_float(fin.get("PARENTNETPROFITTZ") or fin.get("net_profit_yoy"))
    if profit_growth >= 25:
        base = 100
    elif profit_growth >= 20:
        base = 80
    elif profit_growth >= 15:
        base = 50
    else:
        base = 20

    # 估值：PEG 阶梯
    pe = _safe_float(quote.get("pe"))
    if pe > 0 and profit_growth > 0:
        peg = pe / profit_growth
        if peg <= 0.5:
            val = 100
        elif peg <= 1.0:
            val = 80
        elif peg <= 1.5:
            val = 50
        elif peg <= 2.0:
            val = 30
        else:
            val = 0
    else:
        val = 30

    # 技术面：趋势
    trend = kline.get("trend", 0)
    if trend > 0:
        tech = 80
    elif trend == 0:
        tech = 50
    else:
        tech = 20

    # 情绪：内部人交易 / 机构态度
    market = stock_data.get("market_features") or {}
    insider = market.get("insider_net_buy")
    inst_holding = market.get("institutional_holding")
    if insider is not None and insider > 0:
        sent = 100
    elif inst_holding is not None:
        sent = 60 if inst_holding < 0.6 else 0
    else:
        sent = 50

    # 风险：负债率
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"))
    if debt < 60:
        risk = 100
    elif debt < 100:
        risk = 60
    else:
        risk = 0

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "风险": risk}


# ------ 索罗斯 ------
# 维度：基本面(15%) + 估值(10%) + 技术面(25%) + 情绪/反身性(30%) + 风险(20%)

def _score_soros(stock_data: dict) -> Dict[str, float]:
    """索罗斯专属评分：趋势强度 + 反身性（逆向情绪）+ 流动性风险。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline = stock_data.get("kline_features") or {}
    market = stock_data.get("market_features") or {}

    # 基本面：仅作背景
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    profit_growth = _safe_float(fin.get("PARENTNETPROFITTZ") or fin.get("net_profit_yoy"))
    base = 60 if roe >= 15 else 30
    if profit_growth > 20:
        base = max(base, 60)

    # 估值：PE 分位
    pe = _safe_float(quote.get("pe"))
    if pe > 0 and pe < 25:
        val = 80
    elif pe > 60:
        val = 0
    else:
        val = 50

    # 技术面：趋势强度 + 量能
    kline_data = stock_data.get("kline_data") or {}
    closes = kline_data.get("closes") or []
    volumes = kline_data.get("volumes") or []
    if len(closes) >= 10:
        recent = closes[-10:]
        up_count = sum(1 for i in range(len(recent) - 1) if recent[i] < recent[i + 1])
        if up_count >= 9:
            tech = 100
        elif up_count <= 1:
            tech = 0
        else:
            tech = 40
    else:
        trend = kline.get("trend", 0)
        tech = 80 if trend > 0 else (40 if trend == 0 else 10)

    # 情绪/反身性：逆向——极度悲观=机会，高度一致看多=风险
    limit_up = market.get("limit_up_count", 0)
    adv = market.get("advance_ratio")
    if limit_up > 80 or (adv is not None and adv > 0.7):
        sent = 40  # 亢奋，一致性过高
    elif limit_up > 40 or (adv is not None and adv > 0.4):
        sent = 60
    else:
        sent = 100  # 冰点，反向机会

    # 风险：流动性 + 政策
    total_amount = market.get("total_amount", 0)
    limit_down = market.get("limit_down_count", 0)
    if total_amount > 0 and total_amount < 5000:
        risk = 20  # 流动性枯竭
    elif limit_down > 50:
        risk = 10
    elif limit_down > 20:
        risk = 40
    else:
        risk = 80

    return {"基本面": base, "估值": val, "技术面": tech, "情绪/反身性": sent, "风险": risk}


# ------ 段永平 ------
# 维度：基本面(38%) + 估值(22%) + 技术面(5%) + 情绪(5%) + 安全边际(30%)

def _score_duan_yongping(stock_data: dict) -> Dict[str, float]:
    """段永平专属评分：护城河(ROE) + PE 机会成本 + FCF 安全边际。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}

    # 基本面：商业模式/护城河（ROE 代理）
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    if roe >= 20:
        base = 100
    elif roe >= 15:
        base = 60
    else:
        base = 20

    # 估值：PE vs 无风险利率倒数
    pe = _safe_float(quote.get("pe"))
    pe_threshold = 33  # 1/0.03
    if pe <= 0:
        val = 30
    elif pe < pe_threshold * 0.75:
        val = 100
    elif pe < pe_threshold:
        val = 70
    elif pe < pe_threshold * 1.2:
        val = 40
    else:
        val = 0

    # 技术面：价格 vs 内在价值（简化为 PE 分位代理）
    if pe > 0 and pe < 20:
        tech = 100
    elif pe > 0 and pe < 35:
        tech = 50
    else:
        tech = 20

    # 情绪：市场恐慌程度
    market = stock_data.get("market_features") or {}
    adv = market.get("advance_ratio")
    if adv is not None and adv < 0.3:
        sent = 100  # 恐慌，"敢为天下后"
    elif adv is not None and adv > 0.6:
        sent = 0  # 追涨
    else:
        sent = 50

    # 安全边际：FCF + 管理层
    eps = _safe_float(fin.get("EPSJB") or fin.get("eps"))
    ocf = _safe_float(fin.get("MGJYXJJE") or fin.get("ocf_per_share"))
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"))
    if eps > 0 and ocf > eps * 0.8 and debt < 50:
        margin = 100
    elif eps > 0 and ocf > 0:
        margin = 50
    else:
        margin = 0

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "安全边际": margin}


# ------ 徐翔 ------
# 维度：基本面(5%) + 估值(5%) + 技术面(30%) + 情绪/题材(50%) + 风险(10%)

def _score_xu_xiang(stock_data: dict) -> Dict[str, float]:
    """徐翔专属评分：涨停基因 + 板块联动封单 + 流通市值。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    market = stock_data.get("market_features") or {}
    kline_data = stock_data.get("kline_data") or {}

    # 基本面：仅排雷
    eps = _safe_float(fin.get("EPSJB") or fin.get("eps"))
    base = 60 if eps > 0 else 0

    # 估值：流通市值
    circ_cap = _safe_float(quote.get("circulating_cap"))
    if 30 <= circ_cap <= 150:
        val = 100
    elif 150 < circ_cap <= 300:
        val = 60
    elif circ_cap > 500 or circ_cap < 30:
        val = 0
    else:
        val = 50

    # 技术面：涨停板基因
    limit_up_30d = market.get("limit_up_30d_count", 0)
    if limit_up_30d is None or limit_up_30d == 0:
        # 从 K 线数据估算
        closes = kline_data.get("closes") or []
        if len(closes) >= 2:
            limit_up_30d = sum(
                1 for i in range(1, len(closes))
                if closes[i - 1] > 0 and (closes[i] / closes[i - 1] - 1) >= 0.085
            )
    if limit_up_30d >= 2:
        tech = 100
    elif limit_up_30d >= 1:
        tech = 50
    else:
        tech = 0

    # 情绪/题材：板块联动 + 封单强度
    sector_limits = market.get("sector_limit_up_count", 0)
    seal_ratio = market.get("seal_to_circ_ratio", 0)
    if sector_limits >= 3 and seal_ratio > 0.01:
        sent = 100
    elif sector_limits >= 2:
        sent = 60
    elif sector_limits >= 1:
        sent = 20
    else:
        sent = 10

    # 风险：大盘趋势 + 炸板率 + 监管
    idx_above_ma20 = market.get("index_above_ma20", True)
    limit_up_total = market.get("limit_up_count", 0)
    if idx_above_ma20 and limit_up_total > 50:
        risk = 100
    elif not idx_above_ma20 or limit_up_total < 20:
        risk = 20
    else:
        risk = 60

    return {"基本面": base, "估值": val, "技术面": tech, "情绪/题材": sent, "风险": risk}


# ------ 赵老哥 ------
# 维度：基本面(10%) + 估值(8%) + 技术面(35%) + 情绪/题材(35%) + 风险(12%)

def _score_zhao_laoge(stock_data: dict) -> Dict[str, float]:
    """赵老哥专属评分：均线排列 + 题材生命周期 + 流通市值。"""
    quote = stock_data.get("quote") or {}
    kline = stock_data.get("kline_features") or {}
    kline_data = stock_data.get("kline_data") or {}
    market = stock_data.get("market_features") or {}

    # 基本面：题材容量（简化）
    base = 50

    # 估值：流通市值
    circ_cap = _safe_float(quote.get("circulating_cap"))
    if 50 <= circ_cap <= 300:
        val = 100
    elif 30 <= circ_cap <= 500:
        val = 60
    elif circ_cap > 1000:
        val = 20
    else:
        val = 50

    # 技术面：均线系统
    closes = kline_data.get("closes") or []
    if len(closes) >= 20:
        ma5 = statistics.mean(closes[-5:])
        ma10 = statistics.mean(closes[-10:])
        ma20 = statistics.mean(closes[-20:])
        if ma5 > ma10 > ma20:
            tech = 100
        elif ma5 < ma10 < ma20:
            tech = 0
        else:
            tech = 70
    else:
        trend = kline.get("trend", 0)
        tech = 80 if trend > 0 else (40 if trend == 0 else 10)

    # 情绪/题材：量价配合
    volumes = kline_data.get("volumes") or []
    if len(closes) >= 10 and len(volumes) >= 10:
        recent_vol = statistics.mean(volumes[-5:])
        prev_vol = statistics.mean(volumes[-10:-5])
        if recent_vol > prev_vol * 1.2 and closes[-1] > statistics.mean(closes[-5:-1]):
            sent = 100
        elif recent_vol < prev_vol * 0.8:
            sent = 60
        else:
            sent = 40
    else:
        sent = 50

    # 风险：龙头地位 + 20日均线
    if len(closes) >= 20:
        ma20 = statistics.mean(closes[-20:])
        if closes[-1] < ma20:
            risk = 0  # 跌破20日线
        else:
            risk = 100
    else:
        risk = 60

    return {"基本面": base, "估值": val, "技术面": tech, "情绪/题材": sent, "风险": risk}


# ------ 炒股养家 ------
# 维度：基本面(5%) + 估值(5%) + 技术面(15%) + 情绪(65%) + 风险(10%)

def _score_chaogu_yangjia(stock_data: dict) -> Dict[str, float]:
    """养家专属评分：情绪周期阶段（冰点/主升/震荡/退潮）为绝对核心。"""
    quote = stock_data.get("quote") or {}
    market = stock_data.get("market_features") or {}

    # 基本面：仅题材
    base = 50

    # 估值：流通市值
    circ_cap = _safe_float(quote.get("circulating_cap"))
    val = 100 if 0 < circ_cap < 200 else 50

    # 技术面：市场温度计
    limit_up = market.get("limit_up_count", 0)
    if limit_up > 80:
        tech = 100
    elif limit_up >= 40:
        tech = 50
    else:
        tech = 0

    # 情绪：情绪周期阶段（核心维度）
    limit_down = market.get("limit_down_count", 0)
    break_rate = market.get("break_rate", 0)
    adv = market.get("advance_ratio")
    if limit_down > 50 and break_rate > 0.6:
        sent = 100  # 冰点转折
    elif limit_up > 80 and break_rate < 0.2:
        sent = 80  # 主升初期
    elif 40 <= limit_up <= 60:
        sent = 50  # 震荡
    elif limit_up < 20 or limit_down > 30:
        sent = 0  # 退潮
    else:
        sent = 40

    # 风险：跌停家数
    if limit_down < 10:
        risk = 100
    elif limit_down <= 30:
        risk = 30
    else:
        risk = 0

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "风险": risk}


# ------ 作手新一 ------
# 维度：基本面(8%) + 估值(5%) + 技术面(40%) + 情绪(35%) + 风险(12%)

def _score_zuoshou_xinyi(stock_data: dict) -> Dict[str, float]:
    """作手新一专属评分：缩量回调 + K线反转形态 + 强势股基因。"""
    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    market = stock_data.get("market_features") or {}
    kline_data = stock_data.get("kline_data") or {}

    # 基本面：强势股基因
    limit_up_30d = market.get("limit_up_30d_count", 0)
    if limit_up_30d >= 4:
        base = 100
    elif limit_up_30d >= 1:
        base = 60
    else:
        base = 0

    # 估值：流通市值 + 回调深度
    circ_cap = _safe_float(quote.get("circulating_cap"))
    pullback = _safe_float(market.get("pullback_pct"), -1)
    if 30 <= circ_cap <= 200:
        val = 100
    elif 10 <= circ_cap <= 300:
        val = 50
    else:
        val = 0
    if pullback > 62:
        val = _clamp(val * 0.3)

    # 技术面：K线反转形态 + 缩量程度
    closes = kline_data.get("closes") or []
    volumes = kline_data.get("volumes") or []
    if len(closes) >= 10 and len(volumes) >= 10:
        peak_vol = max(volumes[-10:]) if volumes else 1
        recent_vol = statistics.mean(volumes[-3:]) if len(volumes) >= 3 else 1
        vol_ratio = recent_vol / peak_vol if peak_vol > 0 else 1

        last3 = closes[-3:]
        # 锤子线：下跌后下影线长、实体小、收在高点附近（简化：收阳且高于前低）
        is_hammer = (len(last3) == 3 and
                     last3[-2] < last3[-3] and
                     last3[-1] > last3[-2])
        # 吞没形态：阳包阴（收阳且实体覆盖前一根阴线）
        is_engulfing = (len(last3) == 3 and
                        last3[-1] > last3[-2] and
                        last3[-2] < last3[-3] and
                        last3[-1] > last3[-3])

        if vol_ratio <= 0.5 and (is_hammer or is_engulfing):
            tech = 100
        elif vol_ratio <= 0.5:
            tech = 60
        else:
            tech = 20
    else:
        tech = 40

    # 情绪：调整阶段
    if len(closes) >= 10:
        peak_idx = closes.index(max(closes))
        adjust_days = len(closes) - peak_idx - 1
        if 3 <= adjust_days <= 7:
            sent = 100
        elif adjust_days < 3:
            sent = 40
        else:
            sent = 30
    else:
        sent = 50

    # 风险：止损距离
    support = _safe_float(market.get("support_price"))
    price = _safe_float(quote.get("price"))
    if support > 0 and price > 0:
        stop_loss_pct = (price - support) / price * 100
        if stop_loss_pct < 3:
            risk = 100
        elif stop_loss_pct < 8:
            risk = 60
        else:
            risk = 20
    else:
        risk = 60

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "风险": risk}


# ═══════════════════════════════════════════════════════════════
# 专家评分函数注册表
# ═══════════════════════════════════════════════════════════════

_EXPERT_SCORING_FUNCTIONS: Dict[str, Callable[[dict], Dict[str, float]]] = {
    "buffett": _score_buffett,
    "lynch": _score_lynch,
    "soros": _score_soros,
    "duan_yongping": _score_duan_yongping,
    "xu_xiang": _score_xu_xiang,
    "zhao_laoge": _score_zhao_laoge,
    "chaogu_yangjia": _score_chaogu_yangjia,
    "zuoshou_xinyi": _score_zuoshou_xinyi,
}


def score_expert_precise(
    profile: ExpertProfile,
    stock_data: dict,
) -> dict:
    """专家专属评分（v2.0.0）。

    精确复现 experts/*.md §九 评分矩阵中的阈值规则，
    每位专家有独立的评分函数。输出可作为 debate 模式的量化基线参考。

    Args:
        profile: 专家人设
        stock_data: 股票数据，支持以下字段：
            - quote: 行情 dict
                - pe: 市盈率（倍）
                - pb: 市净率（倍）
                - circulating_cap: 流通市值（**亿元**），各专家阈值基于此单位
                - price: 当前股价（元）
                - pe_percentile: PE 近5年历史分位（0-100）
            - finance: 财务 dict
                - ROEJQ/roe: ROE（%）
                - PARENTNETPROFITTZ/net_profit_yoy: 净利润同比增速（%）
                - ZCFZL/debt_ratio: 资产负债率（%）
                - EPSJB/eps: 每股收益（元）
                - MGJYXJJE/ocf_per_share: 每股经营现金流（元）
            - kline_features: 技术指标 dict（trend/rsi/macd_signal）
            - kline_data: K线原始数据 dict
                - closes: 收盘价列表（按时间正序）
                - volumes: 成交量列表
            - market_features: 市场特征 dict
                - limit_up_count/limit_down_count: 涨停/跌停家数
                - advance_ratio: 上涨家数比（0-1）
                - break_rate: 炸板率（0-1）
                - limit_up_30d_count: 近30日涨停次数
                - sector_limit_up_count: 同板块涨停家数

    Returns:
        {
            "score": 0-100 总分,
            "direction": 方向标签,
            "breakdown": {dim: weighted_contribution, ...},
            "dim_scores": {dim: raw_0_100, ...},
            "method": "precise",
        }
    """
    scoring_fn = _EXPERT_SCORING_FUNCTIONS.get(profile.name)
    if scoring_fn is None:
        # 回退到通用启发式
        result = score_expert(profile, stock_data)
        result["method"] = "fallback"
        return result

    dim_scores = scoring_fn(stock_data)

    # 确保所有权重维度都有评分
    for dim in profile.weights:
        if dim not in dim_scores:
            dim_scores[dim] = 50.0

    total = score_from_dimensions(profile, dim_scores)
    return {
        "score": round(total, 1),
        "direction": direction_from_score(total),
        "breakdown": dimension_breakdown(profile, dim_scores),
        "dim_scores": dim_scores,
        "method": "precise",
    }


# ═══════════════════════════════════════════════════════════════
# 信心指数计算（含校准因子）
# ═══════════════════════════════════════════════════════════════

def compute_confidence_index(
    expert_scores: List[float],
    composite_score: float,
    calibration_factor: float = 0.0,
) -> float:
    """计算信心指数（decide.md §六.3）。

    Args:
        expert_scores: 8 位专家的评分列表
        composite_score: 调整后综合分
        calibration_factor: 校准因子，范围 [-1, 1]，默认 0（无校准数据）

    Returns:
        0-100 信心指数
    """
    if not expert_scores:
        return 50.0

    mean = statistics.mean(expert_scores)
    if mean > 0:
        cv = statistics.stdev(expert_scores) / mean if len(expert_scores) > 1 else 0
    else:
        cv = 1.0

    consistency = max(0.0, min(100.0, 100 - cv * 150))
    cal_adjustment = calibration_factor * 10  # 归一化后 ×10，校准贡献不超过 ±10 分

    confidence = consistency * 0.35 + composite_score * 0.55 + cal_adjustment * 0.1
    return max(0.0, min(100.0, round(confidence, 1)))


__all__ = [
    "score_from_dimensions",
    "dimension_breakdown",
    "score_expert",
    "score_expert_precise",
    "compute_confidence_index",
]

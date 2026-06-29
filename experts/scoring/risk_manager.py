"""
风险管理评分函数 v2.1.2。

v2.1.0：骨架实现
v2.1.1：明确 TODO 标注
v2.1.2：实现"周期位置 + 风险预算 + 二阶思维"完整版

人设：二阶思维 + 周期位置 + 风险预算。
核心逻辑：
- 风险维度权重最高（30%）：高杠杆 + 高估值 = 高风险
- 周期位置：pe_percentile >80% 视为周期顶部
- 二阶思维：情绪极端（>80 或 <20）= 警示信号
- 估值/情绪权重低（风险管理专注"风险"而非"机会"）
"""

from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """风险管理专属评分。

    维度：风险（最高权重）+ 估值倒数（PE 越高越警示）+ 情绪倒数。
    """
    from ._utils import _score_fundamentals, _score_technical, _score_sentiment

    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    # ── 基本面：低权重（风险管理专注风险，基本面只作辅助）──
    fund = _score_fundamentals(fin)

    # ── 估值：作为"风险预警"——PE 越高风险越大 ──
    _safe_float(quote.get("pe"))
    pe_pct = _safe_float(quote.get("pe_percentile"), 50)

    # PE 行业分位 >80% = 周期顶部警示
    if pe_pct >= 90:
        risk_valuation = 10  # 极端高估
    elif pe_pct >= 80:
        risk_valuation = 25
    elif pe_pct >= 60:
        risk_valuation = 45
    elif pe_pct >= 40:
        risk_valuation = 60
    elif pe_pct >= 20:
        risk_valuation = 75
    else:
        risk_valuation = 85  # 低估=风险低

    # ── 技术：作为"风险预警"——跌破均线 = 技术风险 ──
    risk_tech = _score_technical(kline_features)

    # ── 情绪：极端情绪 = 警示信号（二阶思维）──
    sentiment_raw = _score_sentiment(market_features)
    # 情绪温度 80+ 或 20- = 反向（过热/过冷都是警示）
    if sentiment_raw >= 80:
        risk_sentiment = 30  # 极端贪婪 = 警示
    elif sentiment_raw >= 65:
        risk_sentiment = 50
    elif sentiment_raw >= 35:
        risk_sentiment = 60
    elif sentiment_raw >= 20:
        risk_sentiment = 45  # 恐慌也是机会但短期风险高
    else:
        risk_sentiment = 30  # 极端恐慌

    # ── 风险（核心维度）：负债 + 估值 + 杠杆 ──
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"), 50)
    # 高负债 + 高估值 = 双重风险
    if debt >= 70 and pe_pct >= 70:
        core_risk = 10  # 双重高风险
    elif debt >= 70 or pe_pct >= 80:
        core_risk = 25
    elif debt >= 50 or pe_pct >= 60:
        core_risk = 45
    elif debt < 30 and pe_pct < 40:
        core_risk = 90  # 低负债 + 低估值 = 低风险
    else:
        core_risk = 65

    return {
        "基本面": fund,
        "估值": risk_valuation,
        "技术面": risk_tech,
        "情绪": risk_sentiment,
        "风险": core_risk,
    }


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """风险管理评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["risk_manager"]
    return generic_score_with_reasoning(profile, score, stock_data)

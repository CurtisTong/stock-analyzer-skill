"""
巴菲特专属评分函数。

维度：基本面(42%) + 估值(28%) + 技术面(5%) + 情绪(5%) + 安全边际(20%)
精确复现 experts/buffett.md §九 评分矩阵中的阈值规则。
"""

from typing import Dict

from ._utils import _safe_float, _get_clamp


def score(stock_data: dict) -> Dict[str, float]:
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
    if 0 <= pe_percentile < 20 and val >= 25:
        val = _get_clamp()(val + 15)
    elif pe_percentile > 80:
        val = _get_clamp()(val - 20)

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

    return {
        "基本面": base,
        "估值": val,
        "技术面": tech,
        "情绪": sent,
        "安全边际": margin,
    }


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """巴菲特评分（含推理链）。

    内部调用 score() 获取维度数值（单一事实来源），仅附加推理文本。

    Returns:
        {
            "scores": {"基本面": float, "估值": float, ...},
            "reasoning": ["推理1", "推理2", ...],
            "dimensions": {
                "基本面": {"score": float, "weight": float, "reason": str},
                ...
            }
        }
    """
    scores = score(stock_data)

    quote = stock_data.get("quote") or {}
    fin = stock_data.get("finance") or {}
    kline = stock_data.get("kline_features") or {}
    market = stock_data.get("market_features") or {}

    reasoning = []
    dimensions = {}

    # ── 基本面：ROE 阶梯 ──
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    if roe >= 20:
        reason = f"✅ ROE 优秀：{roe:.1f}% ≥ 20% 阈值"
    elif roe >= 15:
        reason = f"✅ ROE 良好：{roe:.1f}% ≥ 15% 阈值"
    elif roe >= 10:
        reason = f"⚠️ ROE 一般：{roe:.1f}% 在 10-15% 区间"
    else:
        reason = f"❌ ROE 较差：{roe:.1f}% < 10% 阈值"
    reasoning.append(reason)
    dimensions["基本面"] = {"score": scores["基本面"], "weight": 0.42, "reason": reason}

    # ── 估值：PE 阶梯 + 历史分位调整 ──
    pe = _safe_float(quote.get("pe"))
    pe_percentile = _safe_float(quote.get("pe_percentile"), -1)

    if pe <= 0:
        val_reason = f"⚠️ PE 无效或为负：{pe}"
    elif pe <= 15:
        val_reason = f"✅ PE 低估：{pe:.1f} ≤ 15 阈值"
    elif pe <= 25:
        val_reason = f"⚠️ PE 合理：{pe:.1f} 在 15-25 区间"
    elif pe <= 40:
        val_reason = f"⚠️ PE 偏高：{pe:.1f} 在 25-40 区间"
    else:
        val_reason = f"❌ PE 高估：{pe:.1f} > 40 阈值"

    if 0 <= pe_percentile < 20 and scores["估值"] >= 40:
        val_reason += f"（历史分位 {pe_percentile:.0f}%，低估加分 +15）"
    elif pe_percentile > 80:
        val_reason += f"（历史分位 {pe_percentile:.0f}%，高估扣分 -20）"

    reasoning.append(val_reason)
    dimensions["估值"] = {"score": scores["估值"], "weight": 0.28, "reason": val_reason}

    # ── 技术面：简单趋势 ──
    trend = kline.get("trend", 0)
    if trend > 0:
        tech_reason = "✅ 趋势向上"
    elif trend == 0:
        tech_reason = "⚠️ 趋势横盘"
    else:
        tech_reason = "❌ 趋势向下"
    reasoning.append(tech_reason)
    dimensions["技术面"] = {
        "score": scores["技术面"],
        "weight": 0.05,
        "reason": tech_reason,
    }

    # ── 情绪：市场情绪 ──
    adv = market.get("advance_ratio")
    if adv is not None:
        if adv > 0.5:
            sent_reason = f"✅ 市场情绪偏多：上涨家数比例 {adv:.1%}"
        elif adv > 0.3:
            sent_reason = f"⚠️ 市场情绪中性：上涨家数比例 {adv:.1%}"
        else:
            sent_reason = f"❌ 市场情绪偏空：上涨家数比例 {adv:.1%}"
    else:
        sent_reason = "⚠️ 市场情绪数据缺失，取中性值"
    reasoning.append(sent_reason)
    dimensions["情绪"] = {
        "score": scores["情绪"],
        "weight": 0.05,
        "reason": sent_reason,
    }

    # ── 安全边际：负债率 + FCF ──
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"))
    eps = _safe_float(fin.get("EPSJB") or fin.get("eps"))
    ocf = _safe_float(fin.get("MGJYXJJE") or fin.get("ocf_per_share"))
    fcf_ratio = ocf / max(abs(eps), 0.01) if eps > 0 else 0

    if debt < 30 and fcf_ratio > 0.8:
        margin_reason = (
            f"✅ 安全边际充足：负债率 {debt:.1f}% < 30%，FCF/EPS {fcf_ratio:.1%} > 80%"
        )
    elif debt < 50:
        margin_reason = f"⚠️ 安全边际一般：负债率 {debt:.1f}% < 50%"
    else:
        margin_reason = f"❌ 安全边际不足：负债率 {debt:.1f}% ≥ 50%"
    reasoning.append(margin_reason)
    dimensions["安全边际"] = {
        "score": scores["安全边际"],
        "weight": 0.20,
        "reason": margin_reason,
    }

    return {
        "scores": scores,
        "reasoning": reasoning,
        "dimensions": dimensions,
    }


def format_reasoning(result: dict) -> str:
    """格式化推理链输出。"""
    scores = result["scores"]
    reasoning = result["reasoning"]
    dimensions = result["dimensions"]

    # 计算加权总分
    weights = {
        "基本面": 0.42,
        "估值": 0.28,
        "技术面": 0.05,
        "情绪": 0.05,
        "安全边际": 0.20,
    }
    total = sum(scores.get(dim, 0) * w for dim, w in weights.items())

    lines = [
        "📊 巴菲特评分详情",
        "",
        f"总分：{total:.0f}/100",
        "",
        "## 评分明细",
        "",
        "| 维度 | 权重 | 得分 | 推理过程 |",
        "|------|------|------|----------|",
    ]

    for dim in ["基本面", "估值", "技术面", "情绪", "安全边际"]:
        if dim in dimensions:
            d = dimensions[dim]
            lines.append(
                f"| {dim} | {d['weight']:.0%} | {d['score']:.0f} | {d['reason']} |"
            )

    lines.append("")
    lines.append("## 关键判断")
    lines.append("")

    for r in reasoning:
        lines.append(f"- {r}")

    return "\n".join(lines)

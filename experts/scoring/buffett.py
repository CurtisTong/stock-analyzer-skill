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

    return {"基本面": base, "估值": val, "技术面": tech, "情绪": sent, "安全边际": margin}

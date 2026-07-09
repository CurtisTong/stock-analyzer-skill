"""
段永平专属评分函数。

维度：基本面(38%) + 估值(22%) + 技术面(5%) + 情绪(5%) + 安全边际(30%)
精确复现 experts/duan_yongping.md §九 评分矩阵中的阈值规则。

# 已知近似：技术面维度 persona 定义为"股价 vs 内在价值"（<70%->100，≈->50，>130%->0），
# 代码用绝对 PE（<20->100，<35->50，else 20）近似，因 DCF 内在价值计算需完整财报预测，
# 超出当前数据可得范围。PE 作为估值的粗略代理，方向一致但非内在价值折扣。
"""

from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
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

    return {
        "基本面": base,
        "估值": val,
        "技术面": tech,
        "情绪": sent,
        "安全边际": margin,
    }


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """段永平评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["duan_yongping"]
    return generic_score_with_reasoning(profile, score, stock_data)

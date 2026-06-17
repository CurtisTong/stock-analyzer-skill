"""
机构派评分函数 v2.1.2。

v2.1.0：骨架实现
v2.1.1：明确 TODO 标注
v2.1.2：实现"长期主义 + 深度尽调代理"完整版

人设：深度尽调 + 长期持有 + 集中持仓。
核心逻辑：
- 基本面权重最高（50%）：ROE + 现金流质量 + 营收可持续性
- 估值次之：低 PE + PEG < 1（成长可消化估值）
- 安全边际：高 FCF/股 + 低负债率
- 技术/情绪降权（机构不在乎短期波动）
"""

from typing import Dict

from ._utils import _safe_float


def score(stock_data: dict) -> Dict[str, float]:
    """机构派专属评分。

    维度：基本面（深度尽调）+ 估值（PEG 视角）+ 安全边际（FCF）。
    """
    pass  # 通用评分函数未使用，各维度自行计算
    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    # ── 基本面：深度尽调（ROE + 净利增速 + 毛利率）──
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    profit_yoy = _safe_float(fin.get("PARENTNETPROFITTZ") or fin.get("net_profit_yoy"))
    gross_margin = _safe_float(fin.get("XSMLL") or fin.get("gross_margin"))

    # ROE 是机构最看重的指标
    if roe >= 25:
        institution_fundamental = 100
    elif roe >= 20:
        institution_fundamental = 90
    elif roe >= 15:
        institution_fundamental = 70
    elif roe >= 10:
        institution_fundamental = 45
    else:
        institution_fundamental = 15  # 不达机构门槛

    # 净利增速调整（高 ROE + 持续高增速 = 真龙头）
    if profit_yoy >= 20 and roe >= 15:
        institution_fundamental = min(100, institution_fundamental + 10)
    elif profit_yoy < 0 and roe >= 15:
        institution_fundamental = max(0, institution_fundamental - 15)  # 增收不增利警示

    # 毛利率调整（高毛利 = 商业模式优秀）
    if gross_margin >= 50:
        institution_fundamental = min(100, institution_fundamental + 5)

    # ── 估值：PEG 视角（机构偏好 PEG<1）──
    pe = _safe_float(quote.get("pe"))
    if pe > 0 and profit_yoy > 0:
        peg = pe / profit_yoy
        if peg < 0.5:
            institution_valuation = 95  # 严重低估
        elif peg < 1.0:
            institution_valuation = 80  # 合理
        elif peg < 1.5:
            institution_valuation = 60
        elif peg < 2.5:
            institution_valuation = 35
        else:
            institution_valuation = 15
    else:
        # 亏损股机构一般不投
        institution_valuation = 25

    # ── 技术/情绪：机构不在乎短期波动，给予中性 ──
    institution_tech = 50  # 中性
    institution_sentiment = 50  # 中性

    # ── 安全边际：FCF/股 + 低负债 ──
    fcf_per_share = _safe_float(fin.get("MGJYXJJE") or fin.get("ocf_per_share"))
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"), 50)

    if fcf_per_share > 0 and debt < 30:
        margin_of_safety = 90
    elif fcf_per_share > 0 and debt < 50:
        margin_of_safety = 70
    elif fcf_per_share > 0:
        margin_of_safety = 50
    elif debt < 30:
        margin_of_safety = 40  # 低杠杆但现金流弱
    else:
        margin_of_safety = 15  # 高杠杆 + 弱现金流

    return {
        "基本面": institution_fundamental,
        "估值": institution_valuation,
        "技术面": institution_tech,
        "情绪": institution_sentiment,
        "安全边际": margin_of_safety,
    }

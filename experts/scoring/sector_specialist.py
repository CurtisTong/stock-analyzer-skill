"""
行业专家评分函数 v2.4.0。

v2.1.0：骨架实现
v2.1.2：实现"行业 PE 分位 + 行业景气 + 竞争格局代理"完整版
v2.4.0：兑现人设承诺——按 5 大行业类差异化阈值

行业分类映射（从 quote.industry 或 infer_industry 获取）：
- 消费（白酒/食品/家电/医药消费）：品牌溢价允许高 PE，ROE 阈值更宽容
- 科技（半导体/软件/AI/新能源）：营收增速权重更高，PE 分位宽容
- 医药（生物/化学药/器械）：研发投入容忍亏损，PE 分位低分不惩罚
- 周期（钢铁/煤炭/化工/银行）：营收增速看波动方向而非绝对值，ROE 天然高
- 金融（银行/保险/券商）：杠杆业务 ROE 阈值更低，负债率不惩罚
- 其他：默认阈值（原逻辑不变）
"""

from typing import Dict

from ._utils import _safe_float

# 行业关键词 → 行业分类映射
_SECTOR_KEYWORDS = {
    "消费": ["白酒", "食品", "家电", "饮料", "调味品", "乳制品", "服装", "零售", "化妆品", "免税"],
    "科技": ["半导体", "芯片", "软件", "AI", "计算机", "通信", "电子", "新能源", "光伏", "锂电", "互联网"],
    "医药": ["生物", "化学药", "器械", "中药", "疫苗", "创新药", "医药"],
    "周期": ["钢铁", "煤炭", "化工", "有色", "建材", "水泥", "造纸", "航运", "石油"],
    "金融": ["银行", "保险", "券商", "信托", "多元金融"],
}

# 行业差异化阈值配置
_SECTOR_THRESHOLDS = {
    "消费": {"roe_min_high": 15, "roe_min_mid": 10, "pe_pct_low": 40, "pe_pct_high": 85, "rev_weight": 0.3},
    "科技": {"roe_min_high": 10, "roe_min_mid": 5,  "pe_pct_low": 50, "pe_pct_high": 90, "rev_weight": 0.5},
    "医药": {"roe_min_high": 10, "roe_min_mid": 5,  "pe_pct_low": 30, "pe_pct_high": 85, "rev_weight": 0.3},
    "周期": {"roe_min_high": 12, "roe_min_mid": 6,  "pe_pct_low": 30, "pe_pct_high": 70, "rev_weight": 0.2},
    "金融": {"roe_min_high": 10, "roe_min_mid": 5,  "pe_pct_low": 30, "pe_pct_high": 75, "rev_weight": 0.2},
    "default": {"roe_min_high": 20, "roe_min_mid": 10, "pe_pct_low": 20, "pe_pct_high": 80, "rev_weight": 0.3},
}


def _classify_sector(industry: str) -> str:
    """将行业名映射到 5 大行业类。"""
    if not industry:
        return "default"
    industry_lower = industry.lower()
    for sector, keywords in _SECTOR_KEYWORDS.items():
        if any(kw.lower() in industry_lower for kw in keywords):
            return sector
    return "default"


def score(stock_data: dict) -> Dict[str, float]:
    """行业专家专属评分（v2.4.0 行业差异化阈值）。

    维度：基本面（行业景气）+ 估值（行业 PE 分位）+ 风险（竞争格局）。
    不同行业使用不同的 ROE/PE 分位/增速阈值，体现行业特征差异。
    """
    from ._utils import _score_technical, _score_sentiment

    fin = stock_data.get("finance") or {}
    quote = stock_data.get("quote") or {}
    kline_features = stock_data.get("kline_features") or {}
    market_features = stock_data.get("market_features") or {}

    # 获取行业分类
    industry = quote.get("industry", "") or stock_data.get("industry", "")
    sector_class = _classify_sector(industry)
    thresholds = _SECTOR_THRESHOLDS.get(sector_class, _SECTOR_THRESHOLDS["default"])

    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    rev_yoy = _safe_float(fin.get("TOTALOPERATEREVETZ") or fin.get("revenue_yoy"))
    rev_weight = thresholds["rev_weight"]

    # ── 基本面：行业景气（行业差异化 ROE + 营收增速权重）──
    if roe >= thresholds["roe_min_high"]:
        roe_score = 80
    elif roe >= thresholds["roe_min_mid"]:
        roe_score = 55
    else:
        roe_score = 25

    if rev_yoy >= 20:
        rev_score = 95
    elif rev_yoy >= 10:
        rev_score = 70
    elif rev_yoy >= 0:
        rev_score = 45
    else:
        rev_score = 15

    sector_prosperity = round(roe_score * (1 - rev_weight) + rev_score * rev_weight, 1)

    # ── 估值：行业 PE 分位（行业差异化阈值）──
    pe = _safe_float(quote.get("pe"))
    pe_pct = _safe_float(quote.get("pe_percentile"), 50)
    pe_pct_low = thresholds["pe_pct_low"]
    pe_pct_high = thresholds["pe_pct_high"]

    if 0 <= pe_pct <= pe_pct_low:
        sector_valuation = 90
    elif pe_pct_low < pe_pct <= pe_pct_low + 20:
        sector_valuation = 70
    elif pe_pct_low + 20 < pe_pct <= pe_pct_high:
        sector_valuation = 55
    elif pe_pct_high < pe_pct <= pe_pct_high + 10:
        sector_valuation = 35
    else:
        sector_valuation = 20 if pe > 100 else 30

    # ── 技术面：行业趋势 ──
    sector_tech = _score_technical(kline_features)

    # ── 情绪：行业情绪 ──
    sector_sentiment = max(0.0, min(100.0, _score_sentiment(market_features)))

    # ── 风险：竞争格局（金融行业不惩罚高负债）──
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"), 50)
    if sector_class == "金融":
        competitive_moat = 75 if roe >= 10 else 45
    elif debt < 30 and roe >= thresholds["roe_min_high"]:
        competitive_moat = 90
    elif debt < 50 and roe >= thresholds["roe_min_mid"]:
        competitive_moat = 65
    elif debt > 70:
        competitive_moat = 20
    else:
        competitive_moat = 45

    return {
        "基本面": sector_prosperity,
        "估值": sector_valuation,
        "技术面": sector_tech,
        "情绪": sector_sentiment,
        "风险": competitive_moat,
    }


def score_with_reasoning(stock_data: dict) -> Dict[str, object]:
    """行业专家评分（含推理链）。

    v2.2.0 起统一使用 generic_score_with_reasoning 模板。
    """
    from experts.registry import EXPERT_REGISTRY
    from ._utils import generic_score_with_reasoning

    profile = EXPERT_REGISTRY["sector_specialist"]
    return generic_score_with_reasoning(profile, score, stock_data)

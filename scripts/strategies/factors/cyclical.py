"""周期因子评分：多因子周期位置评估矩阵（v2.5.0 Phase 3）。

三维度周期位置评估，取代单一指标判定：
- 价格维度：主要产品价格在历史分位数中的位置
- 供给维度：行业产能投放 vs 需求增速剪刀差
- 成本维度：主要原料价格走势 + 公司成本曲线相对位置

触发规则：3 维度中 ≥2 个指向高位区域 -> 触发"周期顶部"标签。
返回 0-100 分（越高=周期位置越安全/越偏底部）。

数据源：
- macro_indicators.fetch_coal/polyethylene/rebar 等（fixture-only）
- industry_thresholds.json 周期行业阈值
- 财务数据的多期 ROE 趋势（如有）
"""

import logging

from common import to_float, clamp
from strategies.thresholds import get_industry_threshold

logger = logging.getLogger(__name__)


# 周期类行业集合（industry_thresholds.json 中有周期性标注的行业）
_CYCLICAL_INDUSTRIES = {
    "周期",
    "能源",
    "钢铁",
    "基础化工",
    "有色金属",
    "农林牧渔",
    "建筑材料",
}

# 行业 -> 主要原料映射（用于成本维度）
_INDUSTRY_RAW_MATERIAL = {
    "钢铁": "rebar",
    "基础化工": "polyethylene",
    "能源": "coal",
    "有色金属": "copper",
    "周期": "rebar",  # 默认用螺纹钢
}

# 原料 -> fetcher 函数名映射（延迟导入避免循环依赖）
_RAW_MATERIAL_FETCHERS = {
    "coal": "fetch_coal",
    "polyethylene": "fetch_polyethylene",
    "polypropylene": "fetch_polypropylene",
    "rebar": "fetch_rebar",
    "copper": "fetch_copper",
    "aluminum": "fetch_aluminum",
}


def _is_cyclical(industry: str) -> bool:
    """判断是否为周期类行业。"""
    return industry in _CYCLICAL_INDUSTRIES


def _fetch_raw_material_price(material_key: str):
    """延迟导入 macro_indicators 获取原料价格。"""
    fetcher_name = _RAW_MATERIAL_FETCHERS.get(material_key)
    if not fetcher_name:
        return None
    try:
        from scripts import macro_indicators

        fetcher = getattr(macro_indicators, fetcher_name, None)
        if fetcher:
            return fetcher()
    except Exception as e:
        logger.debug("获取原料价格失败 (%s): %s", material_key, e)
    return None


# ═══════════════════════════════════════════════════════════════
# 三维度评估
# ═══════════════════════════════════════════════════════════════


def _price_dimension(fin: dict, quote: dict, industry: str) -> dict:
    """价格维度：PE/PB 分位 + 利润增速是否处于异常高位。

    返回 {"position": "high"/"mid"/"low", "evaluable": bool, "detail": str}
    """
    pe = to_float(quote.get("pe"))
    pb = to_float(quote.get("pb"))
    profit_growth = to_float(fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ")))

    pe_expensive = get_industry_threshold(industry, "pe_expensive", 40)
    pe_undervalued = get_industry_threshold(industry, "pe_undervalued", 15)
    pb_expensive = get_industry_threshold(industry, "pb_expensive", 3.5)
    cycle_peak_growth = get_industry_threshold(industry, "cycle_peak_profit_growth", 50)

    if pe <= 0 and pb <= 0:
        return {"position": "mid", "evaluable": False, "detail": "PE/PB数据缺失"}

    high_signals = 0
    low_signals = 0
    details = []

    if pe > 0:
        if pe >= pe_expensive:
            high_signals += 1
            details.append(f"PE={pe:.1f}>={pe_expensive}")
        elif pe <= pe_undervalued:
            low_signals += 1
            details.append(f"PE={pe:.1f}<={pe_undervalued}")

    if pb > 0 and pb_expensive > 0:
        if pb >= pb_expensive:
            high_signals += 1
            details.append(f"PB={pb:.1f}>={pb_expensive}")

    # 利润增速异常高位 -> 周期顶部信号
    if profit_growth > 0 and cycle_peak_growth > 0:
        if profit_growth >= cycle_peak_growth:
            high_signals += 1
            details.append(f"增速{profit_growth:.0f}%>={cycle_peak_growth}%(疑似顶部)")

    if high_signals >= 2:
        return {"position": "high", "evaluable": True, "detail": "; ".join(details)}
    if low_signals >= 1:
        return {"position": "low", "evaluable": True, "detail": "; ".join(details)}
    return {
        "position": "mid",
        "evaluable": True,
        "detail": "; ".join(details) or "估值中性",
    }


def _supply_dimension(fin: dict, industry: str) -> dict:
    """供给维度：产能投放 vs 需求增速剪刀差。

    当前数据层无产能数据，用 ROE 趋势作为代理：
    - ROE 持续上升 + 高位 -> 供给可能正在扩张（周期顶部前兆）
    - ROE 持续下降 -> 供给收缩（周期底部前兆）
    """
    roe_trend = fin.get("roe_trend", [])
    if len(roe_trend) < 3:
        return {"position": "mid", "evaluable": False, "detail": "ROE趋势数据不足"}

    # 计算趋势方向
    diffs = [roe_trend[i] - roe_trend[i - 1] for i in range(1, len(roe_trend))]
    rise_count = sum(1 for d in diffs if d > 0)
    decline_count = sum(1 for d in diffs if d < 0)

    # 当前 ROE 水平
    current_roe = roe_trend[-1] if roe_trend else 0
    roe_excellent = get_industry_threshold(industry, "roe_excellent", 15)

    # ROE 高位 + 持续上升 -> 供给扩张，疑似顶部
    if current_roe >= roe_excellent and rise_count >= len(diffs) * 0.6:
        return {
            "position": "high",
            "evaluable": True,
            "detail": f"ROE={current_roe:.1f}%高位+持续上升(供给扩张)",
        }
    # ROE 低位 + 持续下降 -> 供给收缩，疑似底部
    if current_roe < roe_excellent * 0.6 and decline_count >= len(diffs) * 0.6:
        return {
            "position": "low",
            "evaluable": True,
            "detail": f"ROE={current_roe:.1f}%低位+持续下降(供给收缩)",
        }
    return {"position": "mid", "evaluable": True, "detail": "ROE趋势中性"}


def _cost_dimension(industry: str) -> dict:
    """成本维度：主要原料价格走势。

    使用 macro_indicators 获取原料价格（fixture-only）。
    无历史序列时无法判断分位，返回中性。
    """
    material_key = _INDUSTRY_RAW_MATERIAL.get(industry)
    if not material_key:
        return {"position": "mid", "evaluable": False, "detail": "无原料映射"}

    price_data = _fetch_raw_material_price(material_key)
    if price_data is None:
        return {
            "position": "mid",
            "evaluable": False,
            "detail": f"{material_key}价格缺失",
        }

    # fixture-only 模式下无历史序列，无法判断分位
    # 但价格存在即说明数据可用，返回中性（Phase 3 后续可扩展历史序列）
    return {
        "position": "mid",
        "evaluable": True,
        "detail": f"{material_key}={price_data.get('value', 'N/A')}(无历史分位)",
    }


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════


def cyclical_score(fin: dict, quote: dict, features: dict, industry: str) -> float:
    """周期因子评分（三维度周期位置矩阵）。

    Args:
        fin: 财务数据 dict
        quote: 行情数据 dict（含 pe/pb）
        features: K线特征 dict（未使用，保持接口一致）
        industry: 行业类型

    Returns:
        0-100 分。越高=周期位置越安全（偏底部），越低=周期顶部风险高。
        非周期行业返回 50（中性，不影响评分）。
    """
    if not _is_cyclical(industry):
        return 50.0

    # 三维度评估
    price_dim = _price_dimension(fin, quote, industry)
    supply_dim = _supply_dimension(fin, industry)
    cost_dim = _cost_dimension(industry)

    # 统计高位信号数（仅可评估维度）
    evaluable_dims = [d for d in [price_dim, supply_dim, cost_dim] if d["evaluable"]]
    if not evaluable_dims:
        return 50.0  # 全部不可评估，返回中性

    high_count = sum(1 for d in evaluable_dims if d["position"] == "high")
    low_count = sum(1 for d in evaluable_dims if d["position"] == "low")

    # 触发规则：≥2 个维度指向高位 -> 周期顶部
    if high_count >= 2:
        # 周期顶部：低分（高风险）
        base_score = 20.0
    elif high_count == 1 and low_count == 0:
        # 1 个高位信号：中等偏 caution
        base_score = 40.0
    elif low_count >= 2:
        # ≥2 个低位信号：周期底部（机会）
        base_score = 85.0
    elif low_count == 1:
        # 1 个低位信号：中等偏乐观
        base_score = 65.0
    else:
        # 全部中性
        base_score = 50.0

    # 可评估维度越多，置信度越高，分数可更偏离中性
    confidence_adj = (len(evaluable_dims) - 1) * 3  # 1维+0, 2维+3, 3维+6
    if base_score < 50:
        base_score = max(10, base_score - confidence_adj)
    elif base_score > 50:
        base_score = min(95, base_score + confidence_adj)

    return clamp(base_score)


def get_cycle_position(fin: dict, quote: dict, industry: str) -> str:
    """获取周期位置标签（供 veto_evaluator 和 DCF 情景使用）。

    Returns:
        "high"（周期顶部）/ "mid"（中性）/ "low"（周期底部）/ "unknown"
    """
    if not _is_cyclical(industry):
        return "unknown"

    price_dim = _price_dimension(fin, quote, industry)
    supply_dim = _supply_dimension(fin, industry)
    cost_dim = _cost_dimension(industry)

    evaluable_dims = [d for d in [price_dim, supply_dim, cost_dim] if d["evaluable"]]
    if not evaluable_dims:
        return "unknown"

    high_count = sum(1 for d in evaluable_dims if d["position"] == "high")
    low_count = sum(1 for d in evaluable_dims if d["position"] == "low")

    if high_count >= 2:
        return "high"
    if low_count >= 2:
        return "low"
    return "mid"

"""
红利因子评分：股息率、分红连续性、分红率稳定性。
2026年 A 股市场红利因子有效性显著提升（保险/养老金增量资金偏好）。
支持行业差异化阈值。
"""

from common import to_float, clamp


def dividend_score(quote: dict, fin: dict = None, industry: str = "默认") -> float:
    """红利因子评分（0-100）。

    三个维度：
    - 股息率（60分）：最新股息率越高越好
    - 分红连续性（24分）：连续分红年限，连续不分红扣分
    - 分红率稳定性（16分）：分红率在合理区间且稳定

    Args:
        quote: 行情 dict（需含 price/pe/total_cap/pb）
        fin: 财务 dict（需含 eps/dps 或 dividend 相关字段）
        industry: 行业名称

    Returns:
        0-100 红利因子得分
    """
    price = to_float(quote.get("price", 0))

    # ---- 1. 股息率评分（60分）----
    # 方式A：直接股息率（有DPS时）
    eps_dps_bonus = to_float(
        fin.get("dps") or fin.get("MGJXFH") or fin.get("每股现金分红") or 0
    )
    pe = to_float(quote.get("pe", 0))

    dividend_yield = 0.0
    if price > 0 and eps_dps_bonus > 0:
        dividend_yield = eps_dps_bonus / price * 100
    elif price > 0 and pe > 0:
        # PE 倒数作为股息率近似（保守：假设30%分红率）
        dividend_yield = (1 / pe) * 0.3 * 100

    yield_score = _score_dividend_yield(dividend_yield, industry)

    # ---- 2. 分红连续性评分（24分）----
    # 检查分红记录：从 fin 中获取历史分红信息
    dividend_years = _count_dividend_years(fin)
    continuity_score = _score_continuity(dividend_years)

    # ---- 3. 分红率稳定性评分（16分）----
    # 分红率 = 每股分红 / EPS，合理区间 20%-70%
    payout_ratio = _calc_payout_ratio(fin)
    stability_score = _score_stability(payout_ratio, dividend_years)

    total = yield_score + continuity_score + stability_score
    return clamp(total)


def _score_dividend_yield(yield_pct: float, industry: str) -> float:
    """股息率评分（60分满分）。"""
    from strategies.thresholds import get_industry_threshold

    excellent = get_industry_threshold(industry, "dividend_yield_excellent", 3)
    good = get_industry_threshold(industry, "dividend_yield_good", 1.5)
    fair = get_industry_threshold(industry, "dividend_yield_fair", 0.8)

    if yield_pct >= excellent:
        return 60.0
    elif yield_pct >= good:
        ratio = (yield_pct - good) / (excellent - good) if excellent > good else 0
        return 30.0 + ratio * 30.0
    elif yield_pct >= fair:
        ratio = (yield_pct - fair) / (good - fair) if good > fair else 0
        return 10.0 + ratio * 20.0
    elif yield_pct > 0:
        ratio = yield_pct / fair if fair > 0 else 0
        return ratio * 10.0
    else:
        return 0.0


def _count_dividend_years(fin: dict) -> int:
    """估算连续分红年数。返回 0-10。只使用实际分红数据。"""
    if not fin:
        return 0

    dividend_records = fin.get("dividend_records", None)
    if dividend_records and isinstance(dividend_records, list):
        return min(len(dividend_records), 10)

    # 无完整记录时不假设连续性，返回 0 避免误导连续性评分
    return 0


def _score_continuity(years: int) -> float:
    """分红连续性评分（24分满分）。"""
    if years >= 10:
        return 24.0
    elif years >= 5:
        return 18.0 + (years - 5) * 1.2  # 18-24
    elif years >= 3:
        return 10.0 + (years - 3) * 4.0  # 10-18
    elif years >= 1:
        return 5.0 + years * 5.0  # 5-10
    else:
        return -12.0  # 连续不分红扣分


def _calc_payout_ratio(fin: dict) -> float:
    """计算分红率 = 每股分红 / EPS (0-1)。"""
    if not fin:
        return 0
    eps = to_float(fin.get("eps", fin.get("EPSJB", 0)))
    dps = to_float(fin.get("dps", fin.get("MGJXFH", 0)))
    if eps > 0 and dps > 0:
        return min(dps / eps, 1.0)
    return 0


def _score_stability(payout_ratio: float, years: int) -> float:
    """分红率稳定性评分（16分满分）。

    合理分红率区间 20%-70%：
    - 过高（>80%）：不可持续
    - 过低（<15%）：分红意愿弱
    - 连续多年稳定在 30%-60%：最优
    """
    if years < 1:
        return 0.0

    if payout_ratio <= 0:
        return 0.0

    if 0.3 <= payout_ratio <= 0.6:
        return 16.0  # 最优区间
    elif 0.2 <= payout_ratio < 0.3:
        return 12.0
    elif 0.6 < payout_ratio <= 0.8:
        return 10.0
    elif 0.1 <= payout_ratio < 0.2:
        return 6.0
    elif payout_ratio > 0.8:
        return 4.0  # 过高不可持续
    else:
        return 2.0

"""
流动性因子评分：成交额、总市值、换手率（板块差异化）。
"""
from common import to_float, clamp, board_type


def liquidity_score(quote: dict) -> float:
    """流动性因子评分（板块差异化）。满分 100。"""
    amount = to_float(quote.get("amount"))  # 成交额（万元）
    cap = to_float(quote.get("total_cap"))  # 总市值（亿元）
    turnover = to_float(quote.get("turnover"))
    bd = board_type(quote.get("code", ""))

    # 板块差异化满分阈值
    # 主板：成交额 5 亿满分，市值 150 亿满分
    # 创业板/科创板：成交额 2 亿满分，市值 60 亿满分
    # 北交所：成交额 0.5 亿满分，市值 20 亿满分
    amount_max = {"主板": 50000, "创业板": 20000, "科创板": 20000, "北交所": 5000}.get(bd, 50000)
    cap_max = {"主板": 150, "创业板": 60, "科创板": 60, "北交所": 20}.get(bd, 150)

    score = 0
    score += clamp(amount / amount_max * 42)
    score += clamp(cap / cap_max * 28)
    if 0.5 <= turnover <= 8:
        score += 24
    elif 8 < turnover <= 15:
        score += 14
    else:
        score += 6
    return clamp(score)

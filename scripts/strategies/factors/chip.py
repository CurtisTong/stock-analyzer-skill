"""
筹码因子评分：股东户数变化率（Phase 1 静态）+ 融资融券趋势（Phase 2 动态）。

2026 新增：将 chip.py 的资金面数据纳入多因子选股管道。
Phase 1 仅用缓存数据（零网络开销），Phase 2 融合实时融资融券趋势。
"""

import logging
from common import clamp

logger = logging.getLogger(__name__)


def chip_score_static(code: str) -> float:
    """Phase 1 静态评分：仅用缓存数据（股东户数变化率）。满分 100。

    从 data/chip 缓存读取，零网络开销，适用于 5000 只初筛。

    评分维度：
    - 股东户数变化率（100分）：筹码集中度趋势

    Args:
        code: 股票代码（如 sh600989）

    Returns:
        0-100 筹码因子得分
    """
    holders = _get_cached_holders(code)
    if not holders or len(holders) < 2:
        return 50  # 无数据给中性分

    change = holders[0].holder_num_change
    return _score_concentration(change)


def chip_score_dynamic(code: str) -> float:
    """Phase 2 动态评分：融合融资融券趋势 + 机构持仓变化 + 北向资金。需网络请求。

    Args:
        code: 股票代码（如 sh600989）

    Returns:
        0-100 筹码因子得分
    """
    base = chip_score_static(code)

    # 融资净买入趋势（近5日）
    margin_score = _score_margin_trend(code)
    base += margin_score

    # 机构持仓变化（十大流通）
    inst_score = _score_institution_change(code)
    base += inst_score

    # 北向资金净买入（2026 新增）
    northbound_score = _score_northbound_flow(code)
    base += northbound_score

    return clamp(base)


def chip_details(code: str) -> dict:
    """筹码详情（展示用）。返回 holders/margin 汇总。"""
    holders = _get_cached_holders(code)
    margin = _get_margin_data(code, days=5)

    result = {
        "holder_count": holders[0].holder_num if holders else None,
        "holder_change": holders[0].holder_num_change if holders else None,
        "concentration": holders[0].concentration if holders else None,
        "margin_net_5d": None,
        "margin_trend": None,
    }

    if margin and len(margin) >= 3:
        net_5d = sum(m.rzjme for m in margin[:5])
        result["margin_net_5d"] = net_5d
        if all(m.rzjme > 0 for m in margin[:5]):
            result["margin_trend"] = "连续净买入"
        elif all(m.rzjme < 0 for m in margin[:5]):
            result["margin_trend"] = "连续净卖出"
        elif net_5d > 0:
            result["margin_trend"] = "偏多"
        elif net_5d < 0:
            result["margin_trend"] = "偏空"
        else:
            result["margin_trend"] = "中性"

    return result


# ---------- 内部工具函数 ----------


def _get_cached_holders(code: str) -> list:
    """从缓存获取股东户数数据（不触发网络请求）。"""
    try:
        from data.chip import get_holders

        return get_holders(code, periods=4)
    except Exception as e:
        logger.debug("get_holders 失败 %s: %s", code, e)
        return []


def _get_margin_data(code: str, days: int = 5) -> list:
    """获取融资融券数据。"""
    try:
        from data.chip import get_margin

        return get_margin(code, days=days)
    except Exception as e:
        logger.debug("get_margin 失败 %s: %s", code, e)
        return []


def _get_top_holders(code: str) -> list:
    """获取十大流通股东数据。"""
    try:
        from data.chip import get_top_holders

        return get_top_holders(code)
    except Exception as e:
        logger.debug("get_top_holders 失败 %s: %s", code, e)
        return []


def _score_concentration(change_pct: float) -> float:
    """股东户数变化率评分（100分满分）。

    负值 = 集中（主力吸筹），正值 = 分散（主力出货）。
    """
    if change_pct < -15:
        return 80.0  # 大幅集中（主力吸筹）
    elif change_pct < -10:
        return 70.0
    elif change_pct < -5:
        return 60.0  # 集中
    elif change_pct < -2:
        return 52.0
    elif change_pct < 2:
        return 50.0  # 正常
    elif change_pct < 5:
        return 45.0
    elif change_pct < 10:
        return 35.0  # 分散
    elif change_pct < 15:
        return 28.0
    else:
        return 20.0  # 大幅分散（主力出货）


def _score_margin_trend(code: str) -> float:
    """融资净买入趋势评分（±15分）。"""
    margin = _get_margin_data(code, days=5)
    if not margin or len(margin) < 3:
        return 0

    rzjme_5d = sum(m.rzjme for m in margin[:5])
    positive_count = sum(1 for m in margin[:5] if m.rzjme > 0)

    if positive_count >= 4:
        return 15  # 连续净买入
    elif rzjme_5d > 0:
        return 8  # 偏多
    elif positive_count <= 1:
        return -15  # 连续净卖出
    elif rzjme_5d < 0:
        return -8  # 偏空
    return 0


def _score_institution_change(code: str) -> float:
    """机构持仓变化评分（±10分）。"""
    top = _get_top_holders(code)
    if not top:
        return 0

    inst_up = sum(1 for t in top if t.is_institution and t.change_type == "增持")
    inst_down = sum(1 for t in top if t.is_institution and t.change_type == "减持")

    return (inst_up - inst_down) * 8


def _score_northbound_flow(code: str) -> float:
    """北向资金净买入评分（±12分）。

    连续 5 日/20 日净买入作为加分信号。
    北向资金是 A 股最重要的"聪明钱"信号之一。
    """
    try:
        from data.flow import get_northbound_flow

        flow = get_northbound_flow(code, days=20)
    except Exception as e:
        logger.debug("get_northbound_flow 失败 %s: %s", code, e)
        return 0

    if not flow or len(flow) < 3:
        return 0

    sum(f.get("net_buy", 0) for f in flow[:5])
    net_20d = sum(f.get("net_buy", 0) for f in flow[:20])
    pos_5d = sum(1 for f in flow[:5] if f.get("net_buy", 0) > 0)

    score = 0.0

    # 连续 5 日净买入
    if pos_5d >= 5:
        score += 8.0
    elif pos_5d >= 4:
        score += 5.0
    elif pos_5d <= 0:
        score -= 5.0

    # 20 日累计净买入
    if net_20d > 0:
        score += 4.0
    elif net_20d < 0:
        score -= 3.0

    return clamp(score, -12, 12)

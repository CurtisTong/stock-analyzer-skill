"""
筹码因子评分：股东户数变化率（Phase 1 静态）+ 融资融券趋势（Phase 2 动态）。

2026 新增：将 chip.py 的资金面数据纳入多因子选股管道。
Phase 1 仅用缓存数据（零网络开销），Phase 2 融合实时融资融券趋势。

v2.x (#5) 筹码稳定性增强：
- 多期平滑：用最近 4 期变化率中位数代替单期值，减小单期扰动
- 滞后衰减：最新一期 end_date 距今超过 60 交易日时，信号线性衰减至 0.5×
- 交叉验证：户均持股(avg_amount) 变化方向与股东户数变化交叉验证
"""

import logging
import statistics
from datetime import datetime
from common import clamp, to_float

logger = logging.getLogger(__name__)

# (#5) 滞后衰减参数
_STALE_THRESHOLD_TRADING_DAYS = 60   # 超过此交易日数开始衰减
_STALE_MAX_DECAY_DAYS = 120           # 衰减至 0.5× 的天数
_STALE_FLOOR = 0.5                    # 衰减下限
_TRADING_DAYS_PER_CALENDAR = 0.68     # 日历日 -> 交易日近似系数（252/365）


def chip_score_static(code: str) -> float:
    """Phase 1 静态评分：仅用缓存数据（股东户数变化率）。满分 100。

    从 data/chip 缓存读取，零网络开销，适用于 5000 只初筛。

    v2.x (#5) 评分维度：
    - 股东户数变化率（多期平滑，100分）：筹码集中度趋势
    - 滞后衰减：数据陈旧时信号打折
    - 户均持股交叉验证：户数↓+户均↑ -> 强吸筹信号加分

    Args:
        code: 股票代码（如 sh600989）

    Returns:
        0-100 筹码因子得分
    """
    holders = _get_cached_holders(code)
    if not holders or len(holders) < 2:
        return 50  # 无数据给中性分

    # (#5) 多期平滑：取最近 4 期变化率中位数
    recent = holders[:4]
    changes = [
        to_float(h.holder_num_change) for h in recent if to_float(h.holder_num_change) != 0
    ]
    if not changes:
        return 50  # 无有效变化率
    smoothed_change = statistics.median(changes)

    # (#5) 滞后衰减：最新一期 end_date 距今的交易日数
    decay = _compute_staleness_decay(holders[0].end_date)

    # 基础评分
    base_score = _score_concentration(smoothed_change)

    # (#5) 户均持股交叉验证：户数↓ + 户均↑ -> 强吸筹，额外加分
    cross_bonus = _cross_verify_holders(holders)

    # 衰减只作用于变化信号（base_score - 50），中性基准 50 不衰减
    signal = (base_score - 50) * decay
    final = 50 + signal + cross_bonus * decay

    return clamp(final)


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

    # 北向资金净买入（2026 新增）-- 复用模块级缓存
    northbound_score = _score_northbound_flow(code)
    base += northbound_score

    return clamp(base)


# (#11) 北向资金模块级缓存：全市场级别数据，所有股票共享同一份
# 避免每只股票重复请求北向资金数据（从 O(N) 降到 O(1)）
_NORTHBOUND_CACHE: dict = {}
_NORTHBOUND_CACHE_TS: float = 0.0
_NORTHBOUND_CACHE_TTL: int = 300  # 5 分钟


def _get_northbound_flow_cached(code: str, days: int = 20) -> list:
    """(#11) 获取北向资金数据（带模块级缓存）。

    北向资金是市场级别数据，所有股票共享同一份缓存。
    """
    import time

    global _NORTHBOUND_CACHE, _NORTHBOUND_CACHE_TS

    # 缓存有效期内直接返回（北向资金按 code 过滤，但市场级数据共享）
    cache_key = f"{code}:{days}"
    now = time.time()
    if (
        cache_key in _NORTHBOUND_CACHE
        and (now - _NORTHBOUND_CACHE_TS) < _NORTHBOUND_CACHE_TTL
    ):
        return _NORTHBOUND_CACHE[cache_key]

    # 获取数据
    try:
        from data.flow import get_northbound_flow

        flow = get_northbound_flow(code, days=days)
    except Exception as e:
        logger.debug("get_northbound_flow 失败 %s: %s", code, e)
        flow = []

    _NORTHBOUND_CACHE[cache_key] = flow
    _NORTHBOUND_CACHE_TS = now
    return flow


def chip_score_dynamic_batch(codes: list) -> dict:
    """(#11) 批量动态评分：用 parallel_fetch_dict 并发获取 margin/top_holders。

    将 Phase 2 的 N×3 串行网络请求改为并行，大幅缩短运行时间。
    northbound 使用模块级缓存（O(1) 请求）。

    Args:
        codes: 股票代码列表

    Returns:
        {code: score} dict
    """
    if not codes:
        return {}

    from common import parallel_fetch_dict

    # 并行获取 margin 和 top_holders
    margin_data = parallel_fetch_dict(
        codes, lambda c: _get_margin_data(c, days=5), label="margin"
    )
    top_holders_data = parallel_fetch_dict(
        codes, lambda c: _get_top_holders(c), label="top_holders"
    )

    results = {}
    for code in codes:
        base = chip_score_static(code)

        # 用预取的 margin 数据评分
        margin = margin_data.get(code, [])
        base += _score_margin_trend_from_data(margin)

        # 用预取的 top_holders 数据评分
        top = top_holders_data.get(code, [])
        base += _score_institution_change_from_data(top)

        # 北向资金（模块级缓存）
        base += _score_northbound_flow(code)

        results[code] = clamp(base)

    return results


def _score_margin_trend_from_data(margin: list) -> float:
    """从预取的 margin 数据评分（避免重复网络请求）。"""
    if not margin or len(margin) < 3:
        return 0

    rzjme_5d = sum(m.rzjme for m in margin[:5])
    positive_count = sum(1 for m in margin[:5] if m.rzjme > 0)

    if positive_count >= 4:
        return 15
    elif rzjme_5d > 0:
        return 8
    elif positive_count <= 1:
        return -15
    elif rzjme_5d < 0:
        return -8
    return 0


def _score_institution_change_from_data(top: list) -> float:
    """从预取的 top_holders 数据评分。"""
    if not top:
        return 0

    inst_up = sum(1 for t in top if t.is_institution and t.change_type == "增持")
    inst_down = sum(1 for t in top if t.is_institution and t.change_type == "减持")

    return max(-10, min(10, (inst_up - inst_down) * 8))


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


def _compute_staleness_decay(end_date_str: str) -> float:
    """(#5) 计算数据滞后衰减系数。

    最新一期报告截止日距今超过 60 交易日时，信号线性衰减至 0.5×（120 交易日时）。

    Args:
        end_date_str: 报告截止日期（YYYY-MM-DD）

    Returns:
        衰减系数 [0.5, 1.0]，无法解析时返回 1.0（不衰减）
    """
    if not end_date_str:
        return 1.0  # 无日期信息时不衰减（容错）
    try:
        end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return 1.0

    calendar_days = (datetime.now() - end_date).days
    if calendar_days <= 0:
        return 1.0  # 未来日期不衰减

    # 日历日 -> 交易日近似
    trading_days = calendar_days * _TRADING_DAYS_PER_CALENDAR
    if trading_days <= _STALE_THRESHOLD_TRADING_DAYS:
        return 1.0  # 60 交易日内不衰减

    # 线性衰减：60 -> 120 交易日，从 1.0 衰减到 0.5
    excess = trading_days - _STALE_THRESHOLD_TRADING_DAYS
    decay_range = _STALE_MAX_DECAY_DAYS - _STALE_THRESHOLD_TRADING_DAYS  # 60
    decay = 1.0 - (excess / decay_range) * (1.0 - _STALE_FLOOR)
    return max(_STALE_FLOOR, decay)


def _cross_verify_holders(holders: list) -> float:
    """(#5) 户均持股交叉验证：户数↓ + 户均↑ -> 强吸筹信号。

    当股东户数减少（主力吸筹）且户均持股增加（筹码集中）时，
    两个信号同向确认，额外加分。

    Args:
        holders: 最近 2 期+的 HolderData 列表（holders[0] 最新）

    Returns:
        交叉验证加分 [0, +8]
    """
    if len(holders) < 2:
        return 0.0
    latest = holders[0]
    prev = holders[1]

    # 户数减少（change < 0）+ 户均持股增加 -> 强吸筹
    latest_change = to_float(latest.holder_num_change)
    latest_avg = to_float(latest.avg_amount)
    prev_avg = to_float(prev.avg_amount)
    holder_decreasing = latest_change < 0
    avg_increasing = latest_avg > 0 and prev_avg > 0 and latest_avg > prev_avg

    if holder_decreasing and avg_increasing:
        # 双信号确认，加分幅度与变化率相关
        intensity = min(abs(latest_change) / 15, 1.0)
        return 8.0 * intensity

    # 户数增加 + 户均持股减少 -> 主力出货，不额外扣分（已在基础评分中体现）
    return 0.0


def _score_concentration(change_pct: float) -> float:
    """股东户数变化率评分（100分满分）。

    负值 = 集中（主力吸筹），正值 = 分散（主力出货）。

    v2.x (#5): 接收平滑后的变化率（中位数），减小单期扰动。
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

    # P2-H4: 限制在 ±10，避免机构全增持时 +80 远超注释声称的 ±10
    return max(-10, min(10, (inst_up - inst_down) * 8))


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

    # flow 按日期升序排列（旧->新），取最后 5 根为"近 5 日"
    recent_5d = flow[-5:]
    net_5d = sum(f.get("net_buy", 0) for f in recent_5d)
    net_20d = sum(f.get("net_buy", 0) for f in flow[-20:])
    pos_5d = sum(1 for f in recent_5d if f.get("net_buy", 0) > 0)

    score = 0.0

    # 连续 5 日净买入
    if pos_5d >= 5:
        score += 8.0
    elif pos_5d >= 4:
        score += 5.0
    elif pos_5d <= 0:
        score -= 5.0

    # 5 日累计净买入
    if net_5d > 0:
        score += 3.0
    elif net_5d < 0:
        score -= 2.0

    # 20 日累计净买入
    if net_20d > 0:
        score += 4.0
    elif net_20d < 0:
        score -= 3.0

    return clamp(score, -15, 15)

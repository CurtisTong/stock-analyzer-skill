"""事件因子评分：财报披露、限售解禁、分红、增减持、违规的风险/机会评估。

将 events.py 的事件数据纳入多因子选股管道。
事件因子作为风险修正维度，解禁前降权、分红前加分、违规降权。
"""

from common import clamp
from datetime import datetime, timedelta


def event_score(code: str) -> float:
    """事件因子评分。满分 100（中性 50）。

    维度：
    - 限售解禁（-20~0）：解禁前 30 日降权
    - 分红事件（0~+10）：高股息分红加分
    - 财报披露（-5~+5）：财报前观望，财报后加分
    - 大股东增减持（-15~+15）：增持加分，减持降权
    - 监管处罚（-30~0）：违规/立案调查降权

    Args:
        code: 股票代码（如 sh600519）

    Returns:
        0-100 事件因子得分（50=中性）
    """
    try:
        from events import fetch_events

        events = fetch_events(code, days=60)
    except Exception:
        return 50  # 无数据给中性分

    score = 50.0  # 基准分

    # 1. 限售解禁（-20~0）
    lockup = events.get("lockup", [])
    if lockup:
        today = datetime.now().strftime("%Y-%m-%d")
        for item in lockup:
            free_date = item.get("free_date", "")
            if not free_date:
                continue
            days_until = _days_between(today, free_date)
            if 0 <= days_until <= 30:
                # 解禁前 30 日降权
                cap = item.get("lift_market_cap", 0)
                if cap > 50:
                    score -= 20  # 大额解禁
                elif cap > 20:
                    score -= 12
                else:
                    score -= 5
                break  # 只看最近一次解禁

    # 2. 分红事件（0~+10）
    dividend = events.get("dividend", [])
    if dividend:
        today = datetime.now().strftime("%Y-%m-%d")
        for item in dividend:
            ex_date = item.get("ex_date", "")
            if not ex_date:
                continue
            days_until = _days_between(today, ex_date)
            if 0 <= days_until <= 30:
                bonus = item.get("bonus_per_share", 0)
                if bonus > 1.0:
                    score += 10  # 高分红
                elif bonus > 0.3:
                    score += 5
                break

    # 3. 财报披露（-5~+5）
    earnings = events.get("earnings", [])
    if earnings:
        today = datetime.now().strftime("%Y-%m-%d")
        for item in earnings:
            disc_date = item.get("disclosure_date", "")
            if not disc_date:
                continue
            days_until = _days_between(today, disc_date)
            if 0 <= days_until <= 7:
                score -= 3  # 财报前观望
                break
            elif -7 <= days_until < 0:
                score += 3  # 财报刚披露
                break

    # 4. 大股东增减持（-15~+15）
    shareholder = events.get("shareholder", [])
    if shareholder:
        today = datetime.now().strftime("%Y-%m-%d")
        recent_changes = [
            item
            for item in shareholder
            if _days_between(today, item.get("end_date", "")) >= -90
        ]
        if recent_changes:
            total_ratio = sum(item.get("change_ratio", 0) for item in recent_changes)
            if total_ratio > 1.0:
                score += 15  # 大比例增持
            elif total_ratio > 0.3:
                score += 8
            elif total_ratio < -1.0:
                score -= 15  # 大比例减持
            elif total_ratio < -0.3:
                score -= 8

    # 5. 监管处罚（-30~0）
    violation = events.get("violation", [])
    if violation:
        today = datetime.now().strftime("%Y-%m-%d")
        recent_violations = [
            item
            for item in violation
            if _days_between(today, item.get("punish_date", "")) >= -180
        ]
        if recent_violations:
            # 严重程度按内容关键词判断
            for item in recent_violations:
                content = item.get("content", "") + item.get("reason", "")
                if "立案" in content or "调查" in content:
                    score -= 30  # 立案调查，重大风险
                elif "处罚" in content or "罚款" in content:
                    score -= 15  # 行政处罚
                elif "警示" in content or "关注" in content:
                    score -= 5  # 轻微警示
                break  # 只看最近一次

    return clamp(score)


def _days_between(date1_str: str, date2_str: str) -> int:
    """计算两个日期字符串之间的天数。"""
    try:
        d1 = datetime.strptime(date1_str[:10], "%Y-%m-%d")
        d2 = datetime.strptime(date2_str[:10], "%Y-%m-%d")
        return (d2 - d1).days
    except (ValueError, TypeError):
        return 999  # 无法解析时返回大数

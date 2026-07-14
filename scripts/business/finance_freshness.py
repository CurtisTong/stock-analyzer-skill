"""(#2) 财务数据时效性判定。

根据 A 股财报披露惯例（Q1 4/30、中报 8/31、三季报 10/31、年报次年 4/30），
判定 fin.report_date 是否已过期（应已披露更新一期但缓存未更新）。

判定逻辑：
  today > expected_deadline + grace_days 且 fin.report_date < expected_report_end
  -> is_stale = True

过期时，调用方应将硬过滤条件降级为软警告（data_freshness=stale），
避免基于过时数据做出错误的过滤决策。
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from config.loader import safe_get

logger = logging.getLogger(__name__)


def _parse_date(month_day_str: str, year: int) -> date:
    """将 MM-DD 字符串解析为指定年份的 date。"""
    month, day = month_day_str.split("-")
    return date(year, int(month), int(day))

# A 股报告期惯例：(report_end_month, report_end_day, deadline_month, deadline_day)
# 按报告期结束日降序排列（最近的在前）
_PERIODS = [
    ("09-30", "10-31"),   # Q3 三季报
    ("06-30", "08-31"),   # 半年报
    ("03-31", "04-30"),   # Q1 一季报
    ("12-31", "04-30"),   # 年报（次年 4/30）
]


def _load_disclosure_config() -> dict:
    """加载披露截止日配置。"""
    config = safe_get("disclosure.yaml", "ashare_disclosure", None)
    if not isinstance(config, dict):
        # 回退硬编码默认
        return {
            "periods": {
                "Q1": {"report_end": "03-31", "deadline": "04-30"},
                "half_year": {"report_end": "06-30", "deadline": "08-31"},
                "Q3": {"report_end": "09-31", "deadline": "10-31"},
                "full_year": {"report_end": "12-31", "deadline": "04-30"},
            },
            "grace_days": 7,
            "stale_action": "downgrade",
        }
    return config


def _expected_latest_period(today: date) -> tuple:
    """根据当前日期反推应已披露的最近报告期。

    返回:
        (report_end_str, deadline_date) - 报告期结束日字符串和截止日期
        (None, None) - 无法判定
    """
    cfg = _load_disclosure_config()
    periods_cfg = cfg.get("periods", {})

    # 构建当年和上一年的所有报告期候选，按报告期结束日降序
    candidates = []
    for year_offset in (0, -1):
        year = today.year + year_offset
        for pname, pinfo in periods_cfg.items():
            report_end_str = pinfo.get("report_end", "")
            deadline_str = pinfo.get("deadline", "")
            if not report_end_str or not deadline_str:
                continue

            re_month, re_day = report_end_str.split("-")
            report_end_date = date(year, int(re_month), int(re_day))

            dl_month, dl_day = deadline_str.split("-")
            if pname == "full_year":
                # 年报截止日是次年 4/30
                deadline_date = date(year + 1, int(dl_month), int(dl_day))
            else:
                deadline_date = date(year, int(dl_month), int(dl_day))

            candidates.append((report_end_str, report_end_date, deadline_date))

    # 按报告期结束日降序，找第一个 deadline <= today 的（即应已披露）
    candidates.sort(key=lambda x: x[1], reverse=True)
    for report_end_str, report_end_date, deadline_date in candidates:
        if deadline_date <= today:
            return (report_end_str, deadline_date)

    return (None, None)


def check_finance_freshness(fin: dict, today: date = None) -> tuple:
    """判定财务数据是否过期。

    Args:
        fin: 财务 dict（需含 report_date 字段，格式 YYYY-MM-DD）
        today: 当前日期（测试可注入），默认 date.today()

    Returns:
        (is_stale, warning_msg) - is_stale=True 表示数据已过期需降级
    """
    if today is None:
        today = date.today()

    report_date_str = fin.get("report_date", "") if isinstance(fin, dict) else ""
    if not report_date_str:
        # 无 report_date 时不判定（容错，避免误报）
        return (False, "")

    try:
        report_date = datetime.strptime(report_date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return (False, "")

    expected_end_str, expected_deadline = _expected_latest_period(today)
    if expected_end_str is None or expected_deadline is None:
        return (False, "")

    cfg = _load_disclosure_config()
    grace_days = cfg.get("grace_days", 7)

    # 判定：当前日期已过截止日+宽限期，且 report_date 早于应披露的报告期结束日
    effective_deadline = expected_deadline + timedelta(days=grace_days)
    expected_end_date = _parse_date(expected_end_str, today.year)
    if today > effective_deadline and report_date < expected_end_date:
        return (
            True,
            f"财报数据过期(report_date={report_date_str}, 应已披露至 {expected_end_str})",
        )

    return (False, "")

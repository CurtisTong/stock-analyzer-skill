"""(#2) 财务数据时效性判定。

根据 A 股财报披露惯例（Q1 4/30、中报 8/31、三季报 10/31、年报次年 4/30），
判定 fin.report_date 是否已过期（应已披露更新一期但缓存未更新）。

判定逻辑：
  today > expected_deadline + grace_days 且 fin.report_date < expected_report_end
  -> is_stale = True

过期时，调用方应将硬过滤条件降级为软警告（data_freshness=stale），
避免基于过时数据做出错误的过滤决策。

WP6 (2026-07-21): 按股票代码前缀反推板块，使用 board_overrides 配置覆盖默认 deadline。
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


def _board_for_code(code: str) -> str:
    """根据股票代码前缀反推板块。

    已知前缀（顺序敏感：科创板 SH68 必须先于主板 SH6，
    因为 SH688xxx 字符串上 startswith("SH6") 也为 True）：
    - SH68/SH69: 科创板（688xxx / 689xxx）
    - SH60: 沪市主板（60xxxx）
    - SZ30: 创业板（300xxx）
    - SZ00: 深市主板（000xxx）
    - BJ83/BJ43: 北交所
    - 未知: "default"（回退默认 periods）

    注：A 股实际规则：
    - 沪市主板: 600xxx, 601xxx, 603xxx, 605xxx
    - 沪市科创板: 688xxx, 689xxx
    - 深市主板: 000xxx, 001xxx, 002xxx, 003xxx
    - 深市创业板: 300xxx, 301xxx
    - 北交所: 8xxxxx, 4xxxxx
    """
    if not code:
        return "default"
    code = code.upper()
    # ⚠ 顺序：科创板 SH68 必须在主板 SH6 之前
    if code.startswith(("SH68", "SH69")):
        return "SH8"
    if code.startswith("SH6"):
        return "SH6"
    if code.startswith("SZ3"):
        return "SZ3"
    if code.startswith("SZ0"):
        return "SZ0"
    if code.startswith(("BJ8", "BJ4")):
        return "BJ8"
    return "default"


# A 股报告期惯例：(report_end_month, report_end_day, deadline_month, deadline_day)
# 按报告期结束日降序排列（最近的在前）
_PERIODS = [
    ("09-30", "10-31"),  # Q3 三季报
    ("06-30", "08-31"),  # 半年报
    ("03-31", "04-30"),  # Q1 一季报
    ("12-31", "04-30"),  # 年报（次年 4/30）
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
                "Q3": {"report_end": "09-30", "deadline": "10-31"},
                "full_year": {"report_end": "12-31", "deadline": "04-30"},
            },
            "grace_days": 7,
            "stale_action": "downgrade",
            "board_overrides": {},
        }
    # 兜底 board_overrides 字段（兼容性）
    if "board_overrides" not in config:
        config["board_overrides"] = {}
    return config


def _periods_for_board(board: str, base_periods: dict) -> dict:
    """根据板块覆盖 base_periods。

    WP6: 从 board_overrides 中取 board 的覆盖项，与 base_periods 合并。
    未配置覆盖项时返回原 base_periods。
    """
    cfg = _load_disclosure_config()
    overrides = cfg.get("board_overrides", {}).get(board, {})
    if not overrides:
        return base_periods
    # 深合并：覆盖项中的字段覆盖 base_periods 对应 pname
    merged = dict(base_periods)
    for pname, override in overrides.items():
        if pname in merged and isinstance(override, dict):
            merged[pname] = {**merged[pname], **override}
    return merged


def _expected_latest_period(today: date, code: str = "") -> tuple:
    """根据当前日期反推应已披露的最近报告期。

    WP6: code 参数用于按板块差异化 deadline（通过 board_overrides）。

    返回:
        (report_end_str, deadline_date) - 报告期结束日字符串和截止日期
        (None, None) - 无法判定
    """
    cfg = _load_disclosure_config()
    base_periods = cfg.get("periods", {})
    if code:
        board = _board_for_code(code)
        periods_cfg = _periods_for_board(board, base_periods)
    else:
        periods_cfg = base_periods

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

    # WP6 bugfix: 找 deadline <= today 且 report_end 最大的（即最新应披露期）。
    # 返回值加 expected_end_date（带年份），避免 check_finance_freshness
    # 用 today.year 错把去年 Q3 当今年 Q3（2024-09-30 vs 2025-09-30）。
    eligible = [(e, r, d) for e, r, d in candidates if d <= today]
    if not eligible:
        return (None, None, None)
    # 按 report_end 降序，第一个就是"最新已到期"
    eligible.sort(key=lambda x: x[1], reverse=True)
    report_end_str, report_end_date, deadline_date = eligible[0]
    return (report_end_str, deadline_date, report_end_date)


def check_finance_freshness(fin: dict, today: date = None, code: str = "") -> tuple:
    """判定财务数据是否过期。

    Args:
        fin: 财务 dict（需含 report_date 字段，格式 YYYY-MM-DD）
        today: 当前日期（测试可注入），默认 date.today()
        code: 股票代码（WP6 新增），用于按板块差异化 deadline

    Returns:
        (is_stale, warning_msg) - is_stale=True 表示数据已过期需降级
    """
    if today is None:
        today = date.today()

    # WP6: 从 fin 推断 code（若未显式传入）
    if not code and isinstance(fin, dict):
        code = fin.get("code", "")

    report_date_str = fin.get("report_date", "") if isinstance(fin, dict) else ""
    if not report_date_str:
        # 无 report_date 时不判定（容错，避免误报）
        return (False, "")

    try:
        report_date = datetime.strptime(report_date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return (False, "")

    expected_end_str, expected_deadline, expected_end_date = _expected_latest_period(
        today, code
    )
    if expected_end_str is None or expected_deadline is None:
        return (False, "")

    cfg = _load_disclosure_config()
    grace_days = cfg.get("grace_days", 7)

    # 判定：当前日期已过截止日+宽限期，且 report_date 早于应披露的报告期结束日
    effective_deadline = expected_deadline + timedelta(days=grace_days)
    if today > effective_deadline and report_date < expected_end_date:
        board_hint = f" (board={_board_for_code(code)})" if code else ""
        return (
            True,
            f"财报数据过期{board_hint}(report_date={report_date_str}, "
            f"应已披露至 {expected_end_str})",
        )

    return (False, "")

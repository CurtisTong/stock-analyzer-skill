"""东方财富事件日历数据源（财报披露、解禁、分红）。"""
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher, http_get, to_float

# 财报披露日历 API
EARNINGS_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=SECURITY_CODE&sortTypes=1&pageSize=50&pageNumber=1&reportName=RPT_PUBLIC_OP_NEWDATE&columns=SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,OP_DATE,OP_CHANGE,PREPLAN_DATE&filter=(OP_DATE>='{start_date}')(OP_DATE<='{end_date}')"

# 限售解禁日历 API
LOCKUP_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=FREE_DATE&sortTypes=1&pageSize=50&pageNumber=1&reportName=RPT_LIFT_STAGE&columns=SECURITY_CODE,SECURITY_NAME_ABBR,FREE_DATE,LIFT_NUM,LIFT_MARKET_CAP,NEW_PRICE&filter=(FREE_DATE>='{start_date}')(FREE_DATE<='{end_date}')"

# 分红日历 API
DIVIDEND_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=EX_DIVIDEND_DATE&sortTypes=1&pageSize=50&pageNumber=1&reportName=RPT_SHAREBONUS_DET&columns=SECURITY_CODE,SECURITY_NAME_ABBR,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,PLAN_NOTICE_DATE,REG_DATE&filter=(EX_DIVIDEND_DATE>='{start_date}')(EX_DIVIDEND_DATE<='{end_date}')"


class EarningsCalendarFetcher(BaseFetcher):
    """财报披露日历数据源。"""

    def __init__(self):
        super().__init__("earnings_calendar", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取财报披露日历。code 为空时返回近期全部。"""
        days = kwargs.get("days", 30)
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        start_date = datetime.now().strftime("%Y-%m-%d")

        url = EARNINGS_URL.format(start_date=start_date, end_date=end_date)
        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not data or data.get("success") is not True:
            return None

        result_data = data.get("result", {}).get("data", [])
        if not result_data:
            return None

        items = []
        for r in result_data:
            item = {
                "code": r.get("SECURITY_CODE", ""),
                "name": r.get("SECURITY_NAME_ABBR", ""),
                "report_date": r.get("REPORT_DATE", "")[:10],
                "disclosure_date": r.get("OP_DATE", "")[:10],
                "change": r.get("OP_CHANGE", ""),
            }
            if code and item["code"] != code.lstrip("shszSHSZbjBJ"):
                continue
            items.append(item)

        return {"type": "earnings", "items": items}


class LockupCalendarFetcher(BaseFetcher):
    """限售解禁日历数据源。"""

    def __init__(self):
        super().__init__("lockup_calendar", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取限售解禁日历。"""
        days = kwargs.get("days", 30)
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        start_date = datetime.now().strftime("%Y-%m-%d")

        url = LOCKUP_URL.format(start_date=start_date, end_date=end_date)
        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not data or data.get("success") is not True:
            return None

        result_data = data.get("result", {}).get("data", [])
        if not result_data:
            return None

        items = []
        for r in result_data:
            item = {
                "code": r.get("SECURITY_CODE", ""),
                "name": r.get("SECURITY_NAME_ABBR", ""),
                "free_date": r.get("FREE_DATE", "")[:10],
                "lift_num": to_float(r.get("LIFT_NUM", 0)),
                "lift_market_cap": to_float(r.get("LIFT_MARKET_CAP", 0)),
                "price": to_float(r.get("NEW_PRICE", 0)),
            }
            if code and item["code"] != code.lstrip("shszSHSZbjBJ"):
                continue
            items.append(item)

        return {"type": "lockup", "items": items}


class DividendCalendarFetcher(BaseFetcher):
    """分红日历数据源。"""

    def __init__(self):
        super().__init__("dividend_calendar", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取分红日历。"""
        days = kwargs.get("days", 30)
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        start_date = datetime.now().strftime("%Y-%m-%d")

        url = DIVIDEND_URL.format(start_date=start_date, end_date=end_date)
        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not data or data.get("success") is not True:
            return None

        result_data = data.get("result", {}).get("data", [])
        if not result_data:
            return None

        items = []
        for r in result_data:
            item = {
                "code": r.get("SECURITY_CODE", ""),
                "name": r.get("SECURITY_NAME_ABBR", ""),
                "ex_date": r.get("EX_DIVIDEND_DATE", "")[:10],
                "bonus_per_share": to_float(r.get("PRETAX_BONUS_RMB", 0)),
                "notice_date": r.get("PLAN_NOTICE_DATE", "")[:10],
                "record_date": r.get("REG_DATE", "")[:10],
            }
            if code and item["code"] != code.lstrip("shszSHSZbjBJ"):
                continue
            items.append(item)

        return {"type": "dividend", "items": items}


__all__ = ["EarningsCalendarFetcher", "LockupCalendarFetcher", "DividendCalendarFetcher"]

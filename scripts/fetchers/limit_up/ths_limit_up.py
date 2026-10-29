"""同花顺涨停揭秘数据源（涨停池 + 涨停原因归因）。

接口：data.10jqka.com.cn/dataapi/limit_up/limit_up_pool（2026-10 实测
无 cookie 可访问，单请求全市场，注意控制调用频率防封）。

与东财 push2ex 涨停池（data/zt_pool.py，lbc/fund/zbc）互补：本源提供
涨停原因（reason_type）、板型（limit_up_type）、封板成功率、回封标记、
开板次数等题材归因与封板质量字段。

返回时间戳为秒级 epoch，转 HH:MM 展示。
"""

import json

from common import BaseFetcher, http_get, to_float, strip_prefix
from common.exceptions import (
    NetworkError,
    RateLimitError,
    HTTPStatusError,
    ParseError,
)

# 涨停揭秘池（page 由分页循环注入；limit=100 单页覆盖绝大多数交易日）。
# field 列表为接口准入参数（缺失时返回非 JSON），2026-10 实测值。
LIMIT_UP_POOL_URL = (
    "https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool"
    "?page={page}&limit=100&filter=HS,GEM2STAR&order_field=330324&order_type=0&date={date}"
    "&field=199112,10,9001,330323,330324,330325,9002,330329,133971,133970,1968584,3475914,9003,9004"
)

MAX_PAGES = 5


def _ts_to_hhmm(ts) -> str:
    """秒级时间戳 → HH:MM（固定北京时间 Asia/Shanghai，避免 CI 时区差异）；无效值返回空串。"""
    try:
        from datetime import datetime, timezone, timedelta

        cst = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(int(ts), tz=cst).strftime("%H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


class LimitUpReasonFetcher(BaseFetcher):
    """涨停原因归因数据源（同花顺涨停揭秘）。"""

    def __init__(self):
        # provider 显式声明为 ths：按 name 推断会得到 "limit"，
        # 与 data_source.yaml 的 limit_up_sources.ths 键不匹配导致配置失效
        super().__init__("limit_up_reason", priority=5, provider="ths")

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取当日（或指定交易日）涨停池与涨停原因。

        Args:
            code: 股票代码；非空时只返回该股记录（无记录返回 None）
            date: 交易日 YYYYMMDD（默认今天；非交易日返回 None）
        """
        from datetime import timedelta

        from dev.clock import market_now

        date = kwargs.get("date", "") or market_now().strftime("%Y%m%d")

        items = []
        truncated = False
        total_pages = 1
        page = 1
        while page <= total_pages and page <= MAX_PAGES:
            url = LIMIT_UP_POOL_URL.format(page=page, date=date)
            try:
                raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
            except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
                raise
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                break
            if not isinstance(data, dict) or data.get("status_code") != 0:
                break
            payload = data.get("data", {}) or {}
            info = payload.get("info", []) or []
            if page == 1:
                total = payload.get("page", {}).get("total", 0) or 0
                total_pages = max(1, -(-total // 100))  # ceil div
            if not info:
                break
            items.extend(info)
            page += 1
        truncated = total_pages > MAX_PAGES

        if not items:
            return None

        records = []
        for r in items:
            records.append(
                {
                    "code": r.get("code", ""),
                    "name": r.get("name", ""),
                    "change_pct": to_float(r.get("change_rate", 0)),
                    "turnover_rate": to_float(r.get("turnover_rate", 0)),
                    # 涨停原因/题材归因（如 "机器人+数据中心温控"）
                    "reason_type": r.get("reason_type", ""),
                    # 板型：换手板/一字板/T字板/秒板
                    "limit_up_type": r.get("limit_up_type", ""),
                    "high_days": r.get("high_days", ""),  # 首板 / N天N板
                    "open_num": int(to_float(r.get("open_num", 0))),  # 开板次数
                    # 回封：接口可能回 "0"/"1" 字符串，bool("0") is True 会全部误标回封
                    "is_again_limit": int(to_float(r.get("is_again_limit"), 0)) == 1,
                    "limit_up_suc_rate": to_float(r.get("limit_up_suc_rate", 0)),
                    "first_time": _ts_to_hhmm(r.get("first_limit_up_time")),
                    "last_time": _ts_to_hhmm(r.get("last_limit_up_time")),
                    "order_amount": to_float(r.get("order_amount", 0)),  # 封单额（元）
                    "currency_value": to_float(r.get("currency_value", 0)),  # 流通市值
                }
            )

        if code:
            plain = strip_prefix(code)
            records = [r for r in records if r["code"] == plain]
            if not records:
                return None

        return {"type": "limit_up_reason", "date": date, "items": records, "truncated": truncated}


__all__ = ["LimitUpReasonFetcher"]

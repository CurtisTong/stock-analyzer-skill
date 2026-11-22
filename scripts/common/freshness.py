"""数据新鲜度断言：任何 fallback 值必须携带原始报文时间戳。

社区依据（原文，非摘要）：
- dbt freshness: ``warn_after`` / ``error_after`` + ``loaded_at_field``，先有原始
  时间戳才谈得上分级告警：https://docs.getdbt.com/reference/resource-configs/freshness
- Google SRE Workbook ch13: freshness SLO 形如 "The oldest data is no older than Y"；
  过期数据若未显式标注会污染下游：https://sre.google/workbook/data-processing/
- RFC 9111 §4.2.4: 仅在断连或显式允许时才可 serve stale：
  https://httpwg.org/specs/rfc9111.html#rfc.section.4.2.4

规则：缺原始时间戳、时间戳无法解析、时间在未来、或年龄超过阈值 → 抛 StaleDataError。
禁止用 ``as_of = datetime.now()`` 给 fallback 值冒充行情时间。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
BEIJING = ZoneInfo("Asia/Shanghai")

# 未来时间超过 5 分钟视为时钟错误或伪造，直接拒绝
_FUTURE_SKEW_SECONDS = 300


class StaleDataError(ValueError):
    """数据缺原始时间戳，或其年龄超过允许阈值。"""


def _utcnow() -> datetime:
    """当前 UTC 时间；测试可 monkeypatch 本函数以固定时钟。"""
    return datetime.now(timezone.utc)


def parse_quote_time(raw: str | datetime, *, source_tz=ET) -> datetime:
    """把原始报价时间解析成带时区的 UTC datetime。

    支持 CBOE ``2026-11-20T16:15:01``（美东本地 naive）、腾讯
    ``2026-09-11 09:30:00``（美东本地 naive）、以及带 offset 的 ISO。
    naive 时间按 ``source_tz`` 定位（默认美东），绝不按本机时区猜。

    Raises:
        StaleDataError: 时间戳缺失、为空或无法解析。
    """
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.strip().replace(" ", "T"))
        except ValueError as e:
            raise StaleDataError(f"原始报价时间无法解析: {raw!r}") from e
    else:
        raise StaleDataError(f"缺少原始报价时间戳: {raw!r}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=source_tz)
    return dt.astimezone(timezone.utc)


def data_age_seconds(raw: str | datetime, *, source_tz=ET, now: datetime | None = None) -> float:
    """返回数据年龄（秒）；原始时间戳缺失或非法时抛 StaleDataError。"""
    quote_utc = parse_quote_time(raw, source_tz=source_tz)
    ref = now if now is not None else _utcnow()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return (ref - quote_utc).total_seconds()


def assert_fresh(
    raw: str | datetime,
    *,
    max_age: timedelta | float,
    source_tz=ET,
    now: datetime | None = None,
    label: str = "data",
) -> datetime:
    """校验新鲜度并返回带时区的 UTC 报价时间。

    Args:
        raw: 原始报文里的报价时间（不是抓取时间、不是报文生成时间）。
        max_age: 允许的最大年龄，timedelta 或秒数。
        source_tz: naive 时间戳所属时区（默认美东）。
        now: 可注入的当前时间（带时区），便于 hermetic 测试。
        label: 报错中的字段标识。

    Raises:
        StaleDataError: 缺时间戳 / 解析失败 / 未来时间 / 超过 max_age。
    """
    limit = max_age.total_seconds() if isinstance(max_age, timedelta) else float(max_age)
    quote_utc = parse_quote_time(raw, source_tz=source_tz)
    ref = now if now is not None else _utcnow()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    age = (ref - quote_utc).total_seconds()

    if age < -_FUTURE_SKEW_SECONDS:
        raise StaleDataError(f"{label}: 报价时间在未来 {-age:.0f}s，拒绝（时钟错误或伪造）")
    if age > limit:
        raise StaleDataError(
            f"{label}: 数据年龄 {age / 3600:.1f}h 超过阈值 {limit / 3600:.1f}h "
            f"(quote_utc={quote_utc.isoformat()})"
        )
    return quote_utc

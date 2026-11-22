"""数据完整性信封（P0-4a）。

三层边界（只在本模块收口，其它层只声明意图）：

- L1 事实层：``DataFetcherManager`` 的 per-code 降级链（``data.get_last_fallback_chain``）
  与缓存标志；本模块只读这些事实，不新增网络探测。
- L2 业务层：只声明"哪些数据域是必需的"（``required``）和"域缺失时哪些字段不可信"
  （``field_map``），不自己拼文案。
- L3 输出层：``envelope()`` 产出 ``data_quality`` 顶层键，``render_header()`` 出
  Markdown 首行，``conclusions_allowed()`` 让入口降结论强度。

用户口径（P0-4 硬约束，勿改）：

1. **缺失一律 None，禁止 0 占位**：``price: 0`` / ``roe: 0.0`` 会被下游脚本与 LLM
   当成真实值，比"没有这个字段"危险得多。域缺失时本模块把该域字段置 None，
   并把路径记进 ``degraded_fields``。
2. **status != ok 时同时降结论强度**：``conclusions_allowed`` 为 False，入口必须
   去掉仓位建议与"可以买/加仓"类结论，只保留事实与待确认项。提示是给人看的，
   结论强度是给模型看的——后者优先级更高。
3. Markdown 首行固定在**任何标题与结论之前**；JSON 顶层键名固定 ``data_quality``。
4. ``degraded_fields`` 与 ``data_quality`` 的关系（保留一版兼容）：老脚本在
   ``data_quality.degraded_fields`` 里直接放字段名列表；本模块沿用同一位置、
   同一含义（不可信字段路径），并新增 ``missing``（整个数据域缺失）与
   ``degraded``（域在但走了降级源）。

用法（入口脚本）::

    from common import data_quality as dq

    result = dq.envelope(
        result,
        required=("quote", "kline", "finance"),
        field_map={"quote": ("price",), "kline": ("kline",), "finance": ("finance",)},
        conclusion_keys=("advice", "position_advice", "score"),
        code=args.code,
    )
    print(dq.render_header(result["data_quality"]))   # Markdown 首行，先于标题
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
from common.exceptions.silent_fallback import log_silent_fallback

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUSES = (STATUS_OK, STATUS_DEGRADED, STATUS_PARTIAL, STATUS_FAILED)

# critical 域缺一个就要降结论强度；cosmetic 域只进 JSON
CRITICAL_DOMAINS = frozenset({"quote", "kline", "finance"})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _winner_provider(domain: str, code: str | None) -> str | None:
    """本域最近一次成功供数的 provider；不可得返回 None（不臆测）。"""
    try:
        from data import get_last_success_provider

        return get_last_success_provider(domain, code=code)
    except Exception:
        return None


def _chain_providers(domain: str, code: str | None) -> list[str]:
    """只读消费现有降级链，拿"试过哪些源"。取不到就当没有（不臆测）。"""
    try:
        from data import get_last_fallback_chain

        chain = get_last_fallback_chain(domain, code=code) or []
    except Exception as exc:
        log_silent_fallback("data_quality._chain_providers", exc)
        return []
    providers: list[str] = []
    for event in chain:
        provider = event.get("provider") or event.get("name") or ""
        if provider and provider not in providers:
            providers.append(provider)
    return providers


def _present(payload: Mapping[str, Any], domain: str, field_map: Mapping[str, Sequence[str]]) -> bool:
    """域是否"有值"：映射字段里至少一个非 None（0 也算有值，缺值才置 None）。"""
    keys = field_map.get(domain)
    if not keys:
        return payload.get(domain) is not None if domain in payload else True
    return any(payload.get(key) is not None for key in keys)


def envelope(
    payload: MutableMapping[str, Any] | Mapping[str, Any],
    *,
    required: Sequence[str] = (),
    field_map: Mapping[str, Sequence[str]] | None = None,
    conclusion_keys: Sequence[str] = (),
    code: str | None = None,
    checked_at: str | None = None,
    events: Mapping[str, Sequence[str]] | None = None,
    failed: Sequence[str] = (),
    degraded: Sequence[str] = (),
    row_stats: Mapping[str, tuple[int, int]] | None = None,
) -> dict:
    """给结果加 ``data_quality``，并把不可信字段置 None。

    Args:
        payload: 入口产出的结果 dict（原地不修改，返回浅拷贝 + 覆盖字段）。
        required: 必需的数据域，如 ("quote", "kline", "finance")。
        field_map: {域: (该域不可信时置 None 的字段名, ...)}。
        conclusion_keys: 降级时置 None 的结论类字段（仓位建议、评分等）。
        code: 指定标的时按标的取降级链，避免串标的。
        checked_at: 覆盖检查时间（测试用）。
        events: 预先采好的降级事件 {域: [provider, ...]}；不传则读 manager。
        failed: 入口已判定的失败域（如 ``result["data_failed"]``），优先于字段探测。
        degraded: 入口已判定"域有值但不可信"的降级域（如部分标的价格 <=0），
            与降级链发现的降级域合并，不重复。
        row_stats: {域: (缺失行数, 总行数)}——有行级事实时，missing/degraded 会带上
            missing_rows/total_rows，首行按"缺 N/M 只"渲染（域级计数对使用者没有意义）。

    Returns:
        新 dict：payload + ``data_quality``。
    """
    field_map = field_map or {}
    data: dict[str, Any] = dict(payload)
    missing: list[str] = []
    degraded: list[str] = [domain for domain in degraded if domain in required]
    # P1-7：顶层行情若标记为最小源（THS K 线端点），即使有价也判 quote 域降级，
    # 并把 0 占位估值字段置 None；下游 scoring 不再把 0 当真实估值。
    if data.get("is_minimal") and "quote" in required and "quote" not in failed:
        if "quote" not in degraded:
            degraded.append("quote")
        data = neutralize_minimal_quotes([data])[0]
    degraded_fields: list[str] = []
    sources: dict[str, list[str]] = {}
    winners: dict[str, str] = {}

    for domain in required:
        providers = list(events.get(domain, ())) if events and domain in events else _chain_providers(domain, code)
        if providers:
            sources[domain] = providers
        winner = _winner_provider(domain, code)
        if winner:
            winners[domain] = winner
        if domain in failed or not _present(data, domain, field_map):
            missing.append(domain)
            # 显式传了 degraded 但该域实际整域缺失：只算 missing，不能两个列表都出现
            if domain in degraded:
                degraded.remove(domain)
            for key in field_map.get(domain, ()):
                if data.get(key) is not None:
                    data[key] = None
                if key not in degraded_fields:
                    degraded_fields.append(key)
        elif providers or domain in degraded:
            if domain not in degraded:
                degraded.append(domain)
            for key in field_map.get(domain, ()):
                if key not in degraded_fields:
                    degraded_fields.append(key)

    if required and len(missing) == len(required):
        status = STATUS_FAILED
    elif missing:
        status = STATUS_PARTIAL
    elif degraded:
        status = STATUS_DEGRADED
    else:
        status = STATUS_OK

    # 结论强度：critical 域不全为 ok 就不许给仓位建议/买入结论
    critical_ok = not any(domain in CRITICAL_DOMAINS for domain in missing + degraded)
    allowed = status == STATUS_OK and critical_ok
    if not allowed:
        for key in conclusion_keys:
            if data.get(key) is not None:
                data[key] = None
                path = f"conclusion.{key}"
                if path not in degraded_fields:
                    degraded_fields.append(path)

    # 老口径兼容：不认识的 data_quality.degraded_fields 合并保留
    legacy = (payload.get("data_quality") or {}).get("degraded_fields") if isinstance(payload, Mapping) else None
    if legacy:
        for item in legacy:
            if item not in degraded_fields:
                degraded_fields.append(item)

    stats = dict(row_stats or {})

    def _entry(domain: str) -> dict:
        missing_rows, total_rows = stats.get(domain, (0, 0))
        item: dict[str, Any] = {"domain": domain}
        if total_rows:
            item["missing_rows"] = int(missing_rows)
            item["total_rows"] = int(total_rows)
        return item

    data["data_quality"] = {
        "status": status,
        "required": list(required),
        "missing": [_entry(d) for d in missing],
        "degraded": [_entry(d) for d in degraded],
        "missing_domains": list(missing),
        "degraded_domains": list(degraded),
        "row_counts": {
            d: {"missing_rows": int(m), "total_rows": int(t)} for d, (m, t) in stats.items() if t
        },
        "degraded_fields": degraded_fields,
        "sources": sources,
        "winners": winners,
        "conclusions_allowed": allowed,
        "checked_at": checked_at or _now(),
    }
    return data


def usable_price(value: Any) -> bool:
    """价格是否可用：None / 非数字 / <=0 都算"没有报价"（0 是占位，不是行情）。"""
    if value is None:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


# P1-7 (2026-11-21 review §3.1 #7)：最小数据源（THS K 线端点）用 0 占位的估值字段。
# 这些 0 不是“真实估值”，透传到 scoring 会污染价值因子。
_MINIMAL_VALUATION_FIELDS = ("pe", "pb", "total_cap", "circulating_cap", "turnover")


def _is_minimal_quote(row: Any) -> bool:
    return isinstance(row, Mapping) and bool(row.get("is_minimal", False))


def _is_zero_placeholder(value: Any) -> bool:
    """估值字段是否为 0 占位（None/0/'0'/''），非零值原样保留。"""
    if value is None or value == "":
        return True
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def neutralize_minimal_quotes(rows: Iterable[Any]) -> list:
    """返回行副本：is_minimal 行的 0 占位估值字段置 None（P1-7）。

    不修改入参对象，避免污染调用方持有的 Quote.to_dict() 结果。
    """
    out: list[Any] = []
    for row in rows:
        if not _is_minimal_quote(row):
            out.append(row)
            continue
        clone = dict(row)
        for key in _MINIMAL_VALUATION_FIELDS:
            if key in clone and _is_zero_placeholder(clone[key]):
                clone[key] = None
        out.append(clone)
    return out


def quote_flags(rows: Iterable[Any], price_key: str = "price") -> tuple[tuple[str, ...], tuple[str, ...]]:
    """按 rows 的价格缺失比例给出 (failed, degraded)，供 envelope() 使用。

    全部缺价 = quote 域 failed；部分缺价 = degraded；空 rows 不算缺（筛不出票
    不等于数据缺失）。多个入口（screener / quote / kline）共用同一口径。
    P1-7：最小数据源即使有价也必须计入 degraded（非实时 + 估值字段缺失）。
    """
    dict_rows = [row for row in rows if isinstance(row, Mapping)]
    if not dict_rows:
        return (), ()
    bad = [row for row in dict_rows if not usable_price(row.get(price_key))]
    if len(bad) == len(dict_rows):
        return ("quote",), ()
    if bad or any(_is_minimal_quote(row) for row in dict_rows):
        return (), ("quote",)
    return (), ()


def envelope_rows(
    rows: Iterable[Any],
    *,
    price_key: str = "price",
    extra: Mapping[str, Any] | None = None,
    checked_at: str | None = None,
) -> dict:
    """把 rows 包成 {rows, data_quality}，行情域按 quote_flags() 判级。"""
    # P1-7：先把最小源的 0 占位估值置 None，再判级/输出，避免下游误用。
    row_list = neutralize_minimal_quotes(rows)
    failed, degraded = quote_flags(row_list, price_key=price_key)
    dict_rows = [row for row in row_list if isinstance(row, Mapping)]
    bad = sum(1 for row in dict_rows if not usable_price(row.get(price_key)))
    payload: dict[str, Any] = dict(extra or {})
    payload["rows"] = row_list
    return envelope(
        payload,
        required=("quote",),
        field_map={"quote": ()},
        failed=failed,
        degraded=degraded,
        row_stats={"quote": (bad, len(dict_rows))} if dict_rows else None,
        checked_at=checked_at,
    )


def render_header(data_quality: Mapping[str, Any] | None) -> str:
    """Markdown 报告首行（任何标题与结论之前）。"""
    raw = dict(data_quality or {})
    if not raw or not raw.get("status"):
        # 未采集 ≠ ok：没跑过信封就不能暗示数据完整（也不许出现 "ok" 字样）
        return "> 数据完整性：未采集（本次没有产生 data_quality，结论不可用于判断数据完整性）"
    dq = raw
    status = dq.get("status")
    required = list(dq.get("required") or [])
    missing = list(dq.get("missing") or [])
    degraded = list(dq.get("degraded") or [])
    total = len(required)
    ok_count = total - len(missing)

    def _rows_of(entries: list) -> tuple[int, int]:
        """汇总行级事实：(缺失行数, 总行数)；没有行级事实返回 (0, 0)。"""
        miss = sum(int(e.get("missing_rows", 0)) for e in entries if isinstance(e, Mapping))
        tot = sum(int(e.get("total_rows", 0)) for e in entries if isinstance(e, Mapping))
        return miss, tot

    miss_rows, total_rows = _rows_of(missing)
    deg_rows, deg_total = _rows_of(degraded)
    row_counts = dq.get("row_counts") or {}
    if row_counts:
        total_rows = sum(int(v.get("total_rows", 0)) for v in row_counts.values())
        miss_rows = sum(int(v.get("missing_rows", 0)) for v in row_counts.values())
    checked = dq.get("checked_at") or _now()
    sources = dq.get("sources") or {}

    if status == STATUS_OK and not missing and not degraded:
        winners = dq.get("winners") or {}
        src = " / ".join(dict.fromkeys(winners.values())) or " / ".join(
            dict.fromkeys(p for providers in sources.values() for p in providers)
        )
        count = f"{total_rows - miss_rows}/{total_rows} 只报价" if total_rows else f"{total}/{total}"
        if not src:
            return f"> 数据完整性：{STATUS_OK} {count} · 数据源 未记录 · {checked}"
        return f"> 数据完整性：{STATUS_OK} {count} · 数据源 {src} · {checked}"

    bits: list[str] = []
    for item in missing:
        domain = item.get("domain") if isinstance(item, Mapping) else str(item)
        if isinstance(item, Mapping) and item.get("total_rows"):
            bits.append(f"{domain}（缺失 {item['total_rows']} 只）")
        else:
            bits.append(f"{domain}（缺失）")
    for item in degraded:
        if isinstance(item, Mapping):
            domain = item.get("domain", "")
            providers = sources.get(domain) or []
            suffix = f"{' → '.join(providers)}" if providers else "降级源"
            if item.get("total_rows"):
                bits.append(f"{domain}（{suffix}，缺 {item.get('missing_rows', 0)} 只）")
            else:
                bits.append(f"{domain}（{suffix}）")
        else:
            domain = str(item)
            providers = sources.get(domain) or []
            bits.append(f"{domain}（{' → '.join(providers) if providers else '降级源'}）")
    detail = "、".join(bits) if bits else "见 degraded_fields"
    allowed = dq.get("conclusions_allowed")
    tail = "结论仅供参考" if allowed is False else ""
    if total_rows:
        head_count = f"{total_rows - miss_rows}/{total_rows} 只报价"
    elif deg_total:
        head_count = f"{deg_total - deg_rows}/{deg_total} 只报价"
    else:
        head_count = f"{ok_count}/{total}"
    head = f"> ⚠️ 数据完整性：{status} {head_count} · {detail}"
    return f"{head} · {tail}" if tail else head


def conclusions_allowed(data_quality: Mapping[str, Any] | None) -> bool:
    """入口据此决定是否输出仓位建议/买入类结论（默认 False，宁可保守）。"""
    return bool((data_quality or {}).get("conclusions_allowed", False))


def null_paths(payload: MutableMapping[str, Any], paths: Iterable[str]) -> list[str]:
    """把 a.b.c 形式的路径置 None，返回真正改动的路径（缺失字段禁 0 占位）。"""
    changed: list[str] = []
    for path in paths:
        node: Any = payload
        parts = path.split(".")
        for part in parts[:-1]:
            if not isinstance(node, MutableMapping) or part not in node:
                node = None
                break
            node = node[part]
        last = parts[-1]
        if isinstance(node, MutableMapping) and node.get(last) is not None:
            node[last] = None
            changed.append(path)
    return changed

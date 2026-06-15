"""
业务分发模块。

根据 action 调用对应的 PortfolioManager 方法。
"""
from typing import Any, Optional

from .utils import _err, _ok, _parse_float, _parse_int, _to_bool_str_list

# action 白名单
ALLOWED_ACTIONS = {
    "add_position", "reduce_position", "remove_position",
    "update_position", "tag_position", "untag_position",
    "add_watch", "remove_watch", "update_watch",
}

POSITION_UPDATE_FIELDS = {"cost", "quantity", "name", "buy_date", "tags"}
POSITION_REQUIRED = {"add_position": ("code", "cost", "quantity")}


def dispatch(pm, body: dict) -> dict:
    """根据 body['action'] 调用对应 manager 方法。

    Args:
        pm: PortfolioManager 实例
        body: 请求体

    Returns:
        响应 dict（不含 ok/code/error 字段）
    """
    if not isinstance(body, dict):
        return _err("invalid_body", 400, "request body must be a JSON object")

    action = body.get("action")
    if not action:
        return _err("missing_action", 400, "'action' field is required")
    if action not in ALLOWED_ACTIONS:
        return _err("unknown_action", 400,
                    f"action must be one of {sorted(ALLOWED_ACTIONS)}")

    code = body.get("code")
    if not code or not isinstance(code, str):
        return _err("missing_code", 400, "'code' is required (e.g. sh600989)")

    try:
        if action == "add_position":
            return _do_add_position(pm, body, code)
        if action == "reduce_position":
            return _do_reduce_position(pm, body, code)
        if action == "remove_position":
            return _do_remove_position(pm, code)
        if action == "update_position":
            return _do_update_position(pm, body, code)
        if action == "tag_position":
            return _do_tag_position(pm, body, code, untag=False)
        if action == "untag_position":
            return _do_tag_position(pm, body, code, untag=True)
        if action == "add_watch":
            return _do_add_watch(pm, body, code)
        if action == "remove_watch":
            return _do_remove_watch(pm, code)
        if action == "update_watch":
            return _do_update_watch(pm, body, code)
    except ValueError as e:
        return _err("validation_error", 400, str(e))
    except Exception as e:
        return _err("internal_error", 500, f"{type(e).__name__}: {e}")

    return _err("unknown_action", 400, "unreachable")


def _do_add_position(pm, body: dict, code: str) -> dict:
    """处理 add_position 动作。"""
    cost = _parse_float(body.get("cost"))
    if cost is None:
        return _err("invalid_cost", 400, "'cost' must be a number")
    if cost < 0:
        return _err("invalid_cost", 400, "'cost' must be >= 0")
    qty = _parse_int(body.get("quantity"))
    if qty is None:
        return _err("invalid_quantity", 400, "'quantity' must be an integer")
    if qty <= 0:
        return _err("invalid_quantity", 400, "'quantity' must be > 0")

    name = body.get("name", "") or ""
    buy_date = body.get("buy_date", "") or ""
    tags = _to_bool_str_list(body.get("tags")) or []

    result = pm.add_position(code, name, cost, qty,
                             buy_date=buy_date, tags=tags)
    return _ok(result)


def _do_reduce_position(pm, body: dict, code: str) -> dict:
    """处理 reduce_position 动作。"""
    qty = _parse_int(body.get("quantity"))
    if qty is None:
        return _err("invalid_quantity", 400, "'quantity' must be an integer")
    if qty <= 0:
        return _err("invalid_quantity", 400, "'quantity' must be > 0")

    result = pm.reduce_position(code, qty)
    return _ok(result, warn=["position_removed"] if result is None else None)


def _do_remove_position(pm, code: str) -> dict:
    """处理 remove_position 动作。"""
    removed = pm.remove_position(code)
    return _ok(removed)


def _do_update_position(pm, body: dict, code: str) -> dict:
    """处理 update_position 动作。"""
    extra = {}
    for k, v in body.items():
        if k in ("action", "code"):
            continue
        if k in POSITION_UPDATE_FIELDS:
            extra[k] = v

    if not extra:
        return _err("no_update_fields", 400,
                    f"at least one of {sorted(POSITION_UPDATE_FIELDS)} is required")

    if "cost" in extra:
        c = _parse_float(extra["cost"])
        if c is None:
            return _err("invalid_cost", 400, "'cost' must be a number")
        extra["cost"] = c
    if "quantity" in extra:
        q = _parse_int(extra["quantity"])
        if q is None:
            return _err("invalid_quantity", 400, "'quantity' must be an integer")
        extra["quantity"] = q
    if "tags" in extra:
        tags = _to_bool_str_list(extra["tags"])
        if tags is None:
            return _err("invalid_tags", 400, "'tags' must be list or comma-separated string")
        extra["tags"] = tags

    result = pm.update_position(code, **extra)
    warn = ["update_position_replaces_tags"] if "tags" in extra else None
    return _ok(result, warn=warn)


def _do_tag_position(pm, body: dict, code: str, untag: bool) -> dict:
    """处理 tag_position / untag_position 动作。"""
    tags = _to_bool_str_list(body.get("tags"))
    if not tags:
        verb = "untag" if untag else "tag"
        return _err("missing_tags", 400, f"'{verb}_position' requires non-empty 'tags'")
    method = pm.untag_position if untag else pm.tag_position
    result = method(code, *tags)
    return _ok(result)


def _do_add_watch(pm, body: dict, code: str) -> dict:
    """处理 add_watch 动作。"""
    name = body.get("name", "") or ""

    target_buy_raw = body.get("target_buy")
    target_sell_raw = body.get("target_sell")
    target_buy = 0
    target_sell = 0
    if target_buy_raw is not None:
        if isinstance(target_buy_raw, bool) or not isinstance(target_buy_raw, (int, float)):
            return _err("invalid_target_buy", 400, "'target_buy' must be a number (omit or null to skip)")
        if target_buy_raw == 0:
            return _err("invalid_target_buy", 400,
                        "'target_buy=0' is ignored by PortfolioManager; omit the field to leave unchanged")
        if target_buy_raw < 0:
            return _err("invalid_target_buy", 400, "'target_buy' must be > 0")
        target_buy = float(target_buy_raw)
    if target_sell_raw is not None:
        if isinstance(target_sell_raw, bool) or not isinstance(target_sell_raw, (int, float)):
            return _err("invalid_target_sell", 400, "'target_sell' must be a number (omit or null to skip)")
        if target_sell_raw == 0:
            return _err("invalid_target_sell", 400,
                        "'target_sell=0' is ignored by PortfolioManager; omit the field to leave unchanged")
        if target_sell_raw < 0:
            return _err("invalid_target_sell", 400, "'target_sell' must be > 0")
        target_sell = float(target_sell_raw)

    result = pm.add_watch(code, name=name,
                          target_buy=target_buy, target_sell=target_sell)
    return _ok(result)


def _do_remove_watch(pm, code: str) -> dict:
    """处理 remove_watch 动作。"""
    removed = pm.remove_watch(code)
    return _ok(removed)


def _do_update_watch(pm, body: dict, code: str) -> dict:
    """处理 update_watch 动作。"""
    extra = {}
    for k in ("name", "target_buy", "target_sell"):
        if k in body:
            extra[k] = body[k]
    if not extra:
        return _err("no_update_fields", 400,
                    "at least one of name/target_buy/target_sell is required")
    if "target_buy" in extra:
        if extra["target_buy"] == 0:
            return _err("invalid_target_buy", 400,
                        "'target_buy=0' is ignored by PortfolioManager; omit to leave unchanged")
        extra["target_buy"] = _parse_float(extra["target_buy"]) or 0
    if "target_sell" in extra:
        if extra["target_sell"] == 0:
            return _err("invalid_target_sell", 400,
                        "'target_sell=0' is ignored by PortfolioManager; omit to leave unchanged")
        extra["target_sell"] = _parse_float(extra["target_sell"]) or 0

    existing = pm.get_watch(code)
    if existing is None:
        return _ok(None)
    name = extra.get("name", "") or ""
    tb = extra.get("target_buy", 0)
    ts = extra.get("target_sell", 0)
    result = pm.add_watch(code, name=name or existing.get("name", ""),
                          target_buy=tb or 0, target_sell=ts or 0)
    return _ok(result)

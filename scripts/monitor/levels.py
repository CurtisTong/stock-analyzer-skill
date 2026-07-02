"""关键点位计算。

从 alert_engine.py 拆分，计算单只股票的支撑/阻力、均线、MACD、目标价、涨跌停等关键点位。
"""

from typing import Optional

from common import to_float, board_type, board_exact_limit_pct
from monitor.data_fetch import _fetch_technical_data
from monitor.rules import _check_alerts


def compute_key_levels(
    code: str, position: Optional[dict] = None, watch: Optional[dict] = None
) -> dict:
    """计算单只股票的关键点位集合。

    Args:
        code: 股票代码
        position: 持仓信息（可选）
        watch: 自选信息（可选）

    Returns:
        {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 18.50,
            "levels": {
                "supports": [...],
                "resistances": [...],
                "target_buy": 12.00,
                "target_sell": 15.00,
                "macd_signal": "金叉",
                "ma_break": "突破MA20",
            },
            "alerts": [...]  # 当前触发的预警
        }
    """
    data = _fetch_technical_data(code)
    result = {
        "code": code,
        "name": data.get("quote", {}).get("name", ""),
        "price": 0,
        "change_pct": 0,
        "levels": {},
        "alerts": [],
        "position": position,
        "watch": watch,
        "error": data.get("error"),
    }

    if data.get("error") or not data.get("quote"):
        return result

    price = to_float(data["quote"].get("price", 0))
    result["price"] = price
    result["change_pct"] = to_float(data["quote"].get("change_pct", 0))

    if price <= 0:
        result["error"] = "价格无效"
        return result

    levels = {}

    # ── 支撑/阻力位 ──
    sr = data.get("sr", {})
    levels["supports"] = sr.get("supports", [])
    levels["resistances"] = sr.get("resistances", [])
    levels["nearest_support"] = sr.get("nearest_support")
    levels["nearest_resistance"] = sr.get("nearest_resistance")

    # ── 均线 ──
    ma = data.get("ma", {})
    levels["ma_values"] = {}
    for p in [5, 10, 20, 60]:
        v = ma.get(f"ma{p}")
        if v is not None:
            levels["ma_values"][f"MA{p}"] = v
    levels["ma_alignment"] = ma.get("alignment", "")

    # 均线突破检测
    ma_breaks = []
    for p in [20, 60]:
        v = ma.get(f"ma{p}")
        if v is not None:
            # 从下方突破
            if price >= v and price < v * 1.02:
                ma_breaks.append(f"突破MA{p}({v})")
            # 跌破
            elif price <= v and price > v * 0.98:
                ma_breaks.append(f"跌破MA{p}({v})")
    levels["ma_breaks"] = ma_breaks

    # ── MACD ──
    macd = data.get("macd", {})
    if macd:
        levels["macd"] = {
            "dif": macd.get("dif"),
            "dea": macd.get("dea"),
            "bar": macd.get("macd_bar"),
            "signal": macd.get("signal_desc", "无"),
            "bar_trend": macd.get("bar_trend", ""),
        }
        if macd.get("signal") == 1:
            levels["macd_signal"] = "金叉"
        elif macd.get("signal") == -1:
            levels["macd_signal"] = "死叉"
        else:
            levels["macd_signal"] = ""

    # ── 目标买入/卖出价（来自自选） ──
    if watch:
        tb = to_float(watch.get("target_buy", 0))
        ts = to_float(watch.get("target_sell", 0))
        if tb > 0:
            levels["target_buy"] = tb
        if ts > 0:
            levels["target_sell"] = ts

    # ── 涨跌停附近 ──
    prev_close = to_float(data["quote"].get("prev_close", 0))
    if prev_close > 0:
        bd = board_type(code)
        exact_pct = board_exact_limit_pct(bd)
        limit_up = round(prev_close * (1 + exact_pct / 100), 2)
        limit_down = round(prev_close * (1 - exact_pct / 100), 2)
        levels["limit_up"] = limit_up
        levels["limit_down"] = limit_down
        dist_up = (limit_up - price) / price * 100
        dist_down = (price - limit_down) / price * 100
        if dist_up < 1 and dist_up >= 0:
            levels["near_limit_up"] = True
        if dist_down < 1 and dist_down >= 0:
            levels["near_limit_down"] = True

    result["levels"] = levels

    # ── 生成预警 ──
    alerts = _check_alerts(price, levels, position, watch)
    result["alerts"] = alerts

    return result

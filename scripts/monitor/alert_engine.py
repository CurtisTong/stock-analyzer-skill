"""
策略信号引擎：计算持仓+自选股的关键点位，盘中触及即推送。

用法:
  python3 scripts/monitor/alert_engine.py scan               # 扫描全部，输出关键点位
  python3 scripts/monitor/alert_engine.py scan --json        # JSON 输出
  python3 scripts/monitor/alert_engine.py levels sh600989    # 单股关键点位
  python3 scripts/monitor/alert_engine.py check              # 盘中检查，触发推送
  python3 scripts/monitor/alert_engine.py check --dry-run    # 只输出不推送
"""

import json
import logging
import sys
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 添加 scripts 目录到 path

from common import normalize_quote_code, to_float, board_type, board_limit_pct
from data import get_quotes
from data.helpers import fetch_quote_dict_or_none, fetch_kline_dicts, fetch_quote_dict
from technical.moving_average import ma_system
from technical.macd import macd_full
from technical.trend import support_resistance

# 模块级缓存（惰性初始化）
_nm = None
_pm = None


def _get_nm():
    """获取 NotificationManager 单例。"""
    global _nm
    if _nm is None:
        from monitor import NotificationManager

        _nm = NotificationManager()
    return _nm


def _get_pm():
    """获取 PortfolioManager 单例。"""
    global _pm
    if _pm is None:
        from portfolio import PortfolioManager

        _pm = PortfolioManager()
    return _pm


def _reset_cache():
    """重置缓存（用于测试）。"""
    global _nm, _pm
    _nm = None
    _pm = None


# 从配置加载止损/止盈阈值
try:
    from config.loader import ConfigLoader

    _STOP_LOSS_PCT = ConfigLoader.get("limits.yaml", "stop_loss_pct", -8)
    _TAKE_PROFIT_PCT = ConfigLoader.get("limits.yaml", "take_profit_pct", 20)
except Exception as e:
    logger.debug("加载止损/止盈配置失败，使用默认值: %s", e)
    _STOP_LOSS_PCT = -8
    _TAKE_PROFIT_PCT = 20


# ═══════════════════════════════════════════════════════════════
# 预警分级配置
# ═══════════════════════════════════════════════════════════════

# 预警类型配置（扁平化：每种类型包含级别、推送类型等全部元数据）
ALERT_LEVELS = {
    "stop_loss": {"level": "urgent", "push_type": "risk"},
    "target_buy": {"level": "urgent", "push_type": "price"},
    "target_sell": {"level": "urgent", "push_type": "price"},
    "near_limit": {"level": "urgent", "push_type": "risk"},
    "support_touch": {"level": "important", "push_type": "break"},
    "resistance_touch": {"level": "important", "push_type": "price"},
    "macd_golden": {"level": "important", "push_type": "technical"},
    "macd_dead": {"level": "important", "push_type": "technical"},
    "ma_break": {"level": "important", "push_type": "technical"},
    "take_profit": {"level": "important", "push_type": "portfolio"},
    "support_touch_weak": {"level": "normal", "push_type": "break"},
}

# 级别元数据（名称、通知、声音）
_LEVEL_META = {
    "urgent": {"name": "紧急", "notify": True, "sound": True},
    "important": {"name": "重要", "notify": True, "sound": False},
    "normal": {"name": "普通", "notify": False, "sound": False},
}


def get_alert_level(alert_type: str, urgent: bool = False) -> str:
    """获取预警级别。

    Args:
        alert_type: 预警类型
        urgent: 是否标记为紧急

    Returns:
        "urgent" / "important" / "normal"
    """
    if urgent:
        return "urgent"
    return ALERT_LEVELS.get(alert_type, {}).get("level", "normal")


def _fetch_technical_data(code: str, datalen: int = 120) -> dict:
    """获取单只股票的技术分析数据。

    Returns:
        {"quote": {...}, "kline": [...], "ma": {...}, "macd": {...}, "sr": {...}}
    """
    result = {"code": code, "quote": None, "error": None}

    # 实时行情
    try:
        result["quote"] = fetch_quote_dict_or_none(code)
    except Exception as e:
        result["error"] = f"行情获取失败: {e}"
        return result

    # K 线
    try:
        records = fetch_kline_dicts(code, scale=240, datalen=datalen)
    except Exception as e:
        result["error"] = f"K线获取失败: {e}"
        return result

    if not records or len(records) < 20:
        result["error"] = "K线数据不足"
        return result

    closes = [r["close"] for r in records]
    highs = [r["high"] for r in records]
    lows = [r["low"] for r in records]

    # 均线系统
    result["ma"] = ma_system(closes)

    # MACD
    result["macd"] = macd_full(closes)

    # 支撑/阻力位
    result["sr"] = support_resistance(closes, highs, lows, result["ma"])

    return result


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
        limit_pct = board_limit_pct(bd)
        limit_up = round(prev_close * (1 + limit_pct / 100), 2)
        limit_down = round(prev_close * (1 - limit_pct / 100), 2)
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


def _check_alerts(
    price: float,
    levels: dict,
    position: Optional[dict] = None,
    watch: Optional[dict] = None,
) -> list:
    """检查当前价格是否触发预警条件。"""
    alerts = []

    # 支撑位触及（强/弱分级）
    for s in levels.get("supports", []):
        lv = s.get("level", 0)
        if lv > 0 and price <= lv * 1.01:
            strength = s.get("strength", "中")
            alert_type = "support_touch" if strength == "强" else "support_touch_weak"
            alerts.append(
                {
                    "type": alert_type,
                    "level": lv,
                    "source": s.get("source", ""),
                    "message": f"触及{strength}支撑位 {lv}（{s.get('source', '')}）",
                    "urgent": strength == "强",
                }
            )

    # 压力位触及
    for r in levels.get("resistances", []):
        lv = r.get("level", 0)
        if lv > 0 and price >= lv * 0.99:
            alerts.append(
                {
                    "type": "resistance_touch",
                    "level": lv,
                    "source": r.get("source", ""),
                    "message": f"触及压力位 {lv}（{r.get('source', '')}）",
                    "urgent": False,
                }
            )

    # 目标买入价
    tb = levels.get("target_buy", 0)
    if tb > 0 and price <= tb:
        alerts.append(
            {
                "type": "target_buy",
                "level": tb,
                "message": f"到达目标买入价 {tb}",
                "urgent": True,
            }
        )

    # 目标卖出价
    ts = levels.get("target_sell", 0)
    if ts > 0 and price >= ts:
        alerts.append(
            {
                "type": "target_sell",
                "level": ts,
                "message": f"到达目标卖出价 {ts}",
                "urgent": True,
            }
        )

    # MACD 金叉/死叉
    macd_sig = levels.get("macd_signal", "")
    if macd_sig == "金叉":
        alerts.append(
            {
                "type": "macd_golden",
                "message": "MACD 金叉",
                "urgent": False,
            }
        )
    elif macd_sig == "死叉":
        alerts.append(
            {
                "type": "macd_dead",
                "message": "MACD 死叉",
                "urgent": False,
            }
        )

    # 均线突破
    for mb in levels.get("ma_breaks", []):
        alerts.append(
            {
                "type": "ma_break",
                "message": mb,
                "urgent": False,
            }
        )

    # 涨跌停附近
    if levels.get("near_limit_up"):
        alerts.append(
            {
                "type": "near_limit",
                "message": f"距涨停 <1%（涨停价 {levels.get('limit_up')}）",
                "urgent": True,
            }
        )
    if levels.get("near_limit_down"):
        alerts.append(
            {
                "type": "near_limit",
                "message": f"距跌停 <1%（跌停价 {levels.get('limit_down')}）",
                "urgent": True,
            }
        )

    # 持仓盈亏预警
    if position:
        cost = to_float(position.get("cost", 0))
        if cost > 0:
            pnl_pct = (price - cost) / cost * 100
            if pnl_pct <= _STOP_LOSS_PCT:
                alerts.append(
                    {
                        "type": "stop_loss",
                        "message": f"持仓亏损 {pnl_pct:.1f}%，触及止损线",
                        "urgent": True,
                    }
                )
            elif pnl_pct >= _TAKE_PROFIT_PCT:
                alerts.append(
                    {
                        "type": "take_profit",
                        "message": f"持仓盈利 {pnl_pct:.1f}%，可考虑止盈",
                        "urgent": False,
                    }
                )

    return alerts


def scan_all() -> list:
    """扫描持仓+自选股，返回关键点位集合。"""
    pm = _get_pm()
    positions = pm.get_positions()
    watchlist = pm.get_watchlist()

    # 批量预获取行情（减少串行 HTTP 请求）
    all_codes = [p.get("code", "") for p in positions if p.get("code")]
    pos_codes = set(all_codes)
    for w in watchlist:
        code = w.get("code", "")
        if code and code not in pos_codes:
            all_codes.append(code)

    if all_codes:
        try:
            get_quotes(all_codes, use_cache=True)
        except Exception as e:
            logger.debug("批量预获取行情失败，将逐股获取: %s", e)

    results = []

    # 持仓
    for pos in positions:
        code = pos.get("code", "")
        if not code:
            continue
        r = compute_key_levels(code, position=pos)
        results.append(r)

    # 自选（去重）
    for w in watchlist:
        code = w.get("code", "")
        if not code or code in pos_codes:
            continue
        r = compute_key_levels(code, watch=w)
        results.append(r)

    return results


def check_and_push(dry_run: bool = False, level: str = "important") -> dict:
    """盘中检查：扫描全部标的，触发预警则推送。

    Args:
        dry_run: 只输出不推送
        level: 推送级别阈值（"urgent"/"important"/"normal"）

    Returns:
        {"scanned": int, "alerts": int, "pushed": int, "details": [...]}
    """
    results = scan_all()
    nm = _get_nm() if not dry_run else None

    # 级别阈值：只推送 >= level 的预警
    level_order = {"normal": 0, "important": 1, "urgent": 2}
    min_level = level_order.get(level, 1)

    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scanned": len(results),
        "alerts": 0,
        "filtered": 0,
        "pushed": 0,
        "level": level,
        "details": [],
    }

    for r in results:
        code = r["code"]
        name = r.get("name", code)
        price = r.get("price", 0)
        alerts = r.get("alerts", [])

        if not alerts:
            continue

        summary["alerts"] += len(alerts)

        for alert in alerts:
            alert_type = alert.get("type", "unknown")
            message = alert.get("message", "")
            urgent = alert.get("urgent", False)

            # 计算预警级别
            alert_level = get_alert_level(alert_type, urgent)
            alert_level_value = level_order.get(alert_level, 0)

            # 过滤低级别预警
            if alert_level_value < min_level:
                summary["filtered"] += 1
                continue

            # 构造推送内容
            level_icon = {"urgent": "🔴", "important": "🟡", "normal": "🟢"}.get(
                alert_level, "⚪"
            )
            body = f"{level_icon} [{_LEVEL_META[alert_level]['name']}]"
            body += f"\n现价 {price}"
            if r.get("change_pct"):
                body += f"（{r['change_pct']:+.2f}%）"
            body += f"\n{message}"

            # 持仓信息
            if r.get("position"):
                pos = r["position"]
                cost = to_float(pos.get("cost", 0))
                qty = to_float(pos.get("quantity", 0))
                if cost > 0 and qty > 0:
                    pnl = (price - cost) * qty
                    pnl_pct = (price - cost) / cost * 100
                    body += f"\n持仓 {int(qty)} 股 | 盈亏 {pnl:+,.0f}({pnl_pct:+.1f}%)"

            detail = {
                "code": code,
                "name": name,
                "type": alert_type,
                "level": alert_level,
                "message": message,
                "price": price,
                "pushed": False,
            }

            if not dry_run and nm:
                push_type = ALERT_LEVELS.get(alert_type, {}).get("push_type", "price")
                result = nm.send_alert(
                    alert_type=push_type,
                    stock_name=name,
                    stock_code=code,
                    message=body,
                    urgent=urgent,
                )
                detail["pushed"] = result.get("sent", 0) > 0
                if detail["pushed"]:
                    summary["pushed"] += 1

            summary["details"].append(detail)

    return summary


def render_scan(results: list) -> str:
    """渲染扫描结果为可读文本。"""
    lines = []
    lines.append(f"📊 关键点位扫描 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"扫描标的: {len(results)} 只")
    lines.append("")

    for r in results:
        code = r["code"]
        name = r.get("name", code)
        price = r.get("price", 0)
        change = r.get("change_pct", 0)
        error = r.get("error")

        if error:
            lines.append(f"❌ {name}({code}): {error}")
            continue

        icon = "🔴" if change < 0 else "🟢" if change > 0 else "⚪"
        lines.append(f"{icon} {name}({code}) | 现价 {price} | {change:+.2f}%")

        levels = r.get("levels", {})

        # 支撑位
        supports = levels.get("supports", [])
        if supports:
            items = [f"{s['level']}({s.get('source', '')})" for s in supports[:3]]
            lines.append(f"  支撑: {' / '.join(items)}")

        # 压力位
        resistances = levels.get("resistances", [])
        if resistances:
            items = [f"{r['level']}({r.get('source', '')})" for r in resistances[:3]]
            lines.append(f"  压力: {' / '.join(items)}")

        # 均线
        ma_vals = levels.get("ma_values", {})
        if ma_vals:
            items = [f"{k}={v}" for k, v in ma_vals.items()]
            lines.append(f"  均线: {' | '.join(items)}")

        # MACD
        macd_info = levels.get("macd", {})
        if macd_info:
            sig = levels.get("macd_signal", "")
            bar = macd_info.get("bar_trend", "")
            lines.append(
                f"  MACD: DIF={macd_info.get('dif')} DEA={macd_info.get('dea')} | {sig or bar}"
            )

        # 目标价
        if levels.get("target_buy"):
            lines.append(f"  目标买入: {levels['target_buy']}")
        if levels.get("target_sell"):
            lines.append(f"  目标卖出: {levels['target_sell']}")

        # 预警
        alerts = r.get("alerts", [])
        if alerts:
            for a in alerts:
                urgent_mark = "🔴" if a.get("urgent") else "🟡"
                lines.append(f"  {urgent_mark} 预警: {a['message']}")

        lines.append("")

    return "\n".join(lines)


def render_levels(code: str) -> str:
    """渲染单股关键点位。"""
    pm = PortfolioManager()
    pos = pm.get_position(code)
    watch = pm.get_watch(code)
    r = compute_key_levels(code, position=pos, watch=watch)
    return render_scan([r])


def daily_briefing(as_json: bool = False) -> dict:
    """盘前简报：市场状态 + 持仓概要 + 关键价位。

    组合 market quick + portfolio health + alert levels，
    输出一份结构化晨报，适合每日 9:15 自动运行。

    Returns:
        {"market": {...}, "portfolio": {...}, "alerts": [...], "summary": str}
    """
    from data import get_quote
    from portfolio import PortfolioManager

    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "market": {},
        "portfolio": {},
        "alerts": [],
        "summary": "",
    }

    # 1. 市场状态（三大指数）
    indices = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
    }
    market_lines = []
    for code, name in indices.items():
        try:
            q = get_quote(code)
            if q:
                price = q.price if hasattr(q, "price") else 0
                change = q.change_pct if hasattr(q, "change_pct") else 0
                icon = "🟢" if change >= 0 else "🔴"
                market_lines.append(f"{icon} {name}: {price:.2f} ({change:+.2f}%)")
                result["market"][code] = {
                    "name": name,
                    "price": price,
                    "change_pct": change,
                }
        except Exception as e:
            market_lines.append(f"⚪ {name}: 获取失败 ({e})")

    # 2. 持仓概要
    pm = PortfolioManager()
    positions = pm.get_positions()
    pos_lines = []
    total_cost = 0
    total_value = 0
    for pos in positions:
        code = pos.get("code", "")
        name = pos.get("name", code)
        cost = to_float(pos.get("cost", 0))
        qty = to_float(pos.get("quantity", 0))
        if not code or cost <= 0 or qty <= 0:
            continue
        try:
            q = get_quote(code)
            price = (q.price if hasattr(q, "price") else 0) if q else 0
        except Exception:
            price = 0
        pos_cost = cost * qty
        pos_value = price * qty
        pnl_pct = (price - cost) / cost * 100 if cost > 0 else 0
        icon = "🟢" if pnl_pct >= 0 else "🔴"
        total_cost += pos_cost
        total_value += pos_value
        pos_lines.append(
            f"  {icon} {name}({code}): {price:.2f} 成本{cost:.2f} {pnl_pct:+.1f}%"
        )

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    result["portfolio"] = {
        "count": len(positions),
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
    }

    # 3. 关键价位（仅持仓）
    alert_lines = []
    for pos in positions:
        code = pos.get("code", "")
        if not code:
            continue
        try:
            r = compute_key_levels(code, position=pos)
            alerts = r.get("alerts", [])
            if alerts:
                name = pos.get("name", code)
                for a in alerts[:2]:  # 每只最多取 2 个最重要的
                    alert_lines.append(f"  ⚠️ {name}: {a.get('message', '')}")
        except Exception:
            pass

    result["alerts"] = alert_lines

    # 4. 组装输出
    lines = [
        f"📊 盘前简报 | {result['timestamp']}",
        "",
        "━━ 市场状态 ━━",
    ]
    lines.extend(market_lines)

    lines.append("")
    lines.append(f"━━ 持仓概要（{len(positions)} 只）━━")
    if pos_lines:
        lines.extend(pos_lines)
        pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
        lines.append(f"  {pnl_icon} 总盈亏: {total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)")
    else:
        lines.append("  （暂无持仓）")

    if alert_lines:
        lines.append("")
        lines.append("━━ 关键预警 ━━")
        lines.extend(alert_lines)

    lines.append("")
    lines.append("━━ 建议 ━━")
    if not positions:
        lines.append("  📌 无持仓，可运行 /screener 选股")
    elif total_pnl_pct < -5:
        lines.append("  ⚠️ 组合浮亏较大，关注止损位")
    elif total_pnl_pct > 10:
        lines.append("  📈 组合浮盈良好，注意止盈纪律")
    else:
        lines.append("  ✅ 组合状态正常，保持纪律")

    result["summary"] = "\n".join(lines)
    return result


def main():
    args = sys.argv[1:]
    if not args:
        print("用法:")
        print("  alert_engine.py scan [--json]                  # 扫描全部标的")
        print("  alert_engine.py levels <code>                  # 单股关键点位")
        print("  alert_engine.py check [--dry-run] [--level L]  # 盘中检查+推送")
        print("  alert_engine.py briefing [--json]              # 盘前简报")
        print("")
        print("推送级别 (--level):")
        print("  urgent    - 只推送紧急预警（止损、涨跌停附近）")
        print("  important - 推送重要+紧急预警（默认）")
        print("  normal    - 推送所有预警")
        sys.exit(1)

    cmd = args[0]

    if cmd == "scan":
        results = scan_all()
        if "--json" in args:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(render_scan(results))

    elif cmd == "levels":
        if len(args) < 2:
            print("用法: alert_engine.py levels <code>")
            sys.exit(1)
        code = normalize_quote_code(args[1])
        print(render_levels(code))

    elif cmd == "check":
        dry_run = "--dry-run" in args

        # 解析 --level 参数
        level = "important"  # 默认推送重要+紧急
        if "--level" in args:
            level_idx = args.index("--level")
            if level_idx + 1 < len(args):
                level = args[level_idx + 1]
                if level not in _LEVEL_META:
                    print(f"无效的级别: {level}，可选: {', '.join(_LEVEL_META.keys())}")
                    sys.exit(1)

        summary = check_and_push(dry_run=dry_run, level=level)
        if "--json" in args:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            mode = "（dry-run）" if dry_run else ""
            level_name = _LEVEL_META.get(level, {}).get("name", level)
            print(f"📡 盘中检查{mode} | {summary['timestamp']}")
            print(f"推送级别: {level_name}")
            print(
                f"扫描: {summary['scanned']} | 预警: {summary['alerts']} | 过滤: {summary.get('filtered', 0)} | 推送: {summary['pushed']}"
            )
            for d in summary.get("details", []):
                status = "✅" if d.get("pushed") else "⏭️"
                level_icon = {"urgent": "🔴", "important": "🟡", "normal": "🟢"}.get(
                    d.get("level", ""), "⚪"
                )
                print(
                    f"  {status} {level_icon} {d['name']}({d['code']}): {d['message']}"
                )

    elif cmd == "briefing":
        result = daily_briefing(as_json="--json" in args)
        if "--json" in args:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["summary"])

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

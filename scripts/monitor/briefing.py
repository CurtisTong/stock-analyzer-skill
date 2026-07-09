"""盘前简报数据计算。

从 alert_engine.py 拆分，负责组装市场状态、持仓概要、关键预警的结构化数据。
文本渲染由 alert_engine.render_briefing 完成。
"""

import logging
from datetime import datetime

from common import to_float
from monitor.levels import compute_key_levels

logger = logging.getLogger(__name__)


def compute_briefing() -> dict:
    """盘前简报：市场状态 + 隔夜外盘 + 北向资金 + 持仓概要 + 关键价位（结构化数据）。

    组合 market quick + overnight US + northbound flow + portfolio health + alert levels，
    输出结构化晨报数据，适合每日 9:15 自动运行。

    Returns:
        {
            "timestamp": str,
            "market": {code: {name, price, change_pct}},
            "overnight": {code: {name, price, change_pct}},  # 隔夜美股指数
            "northbound": {net_buy, sh_net, sz_net, days},   # 北向资金近 5 日
            "portfolio": {count, total_cost, total_value, total_pnl, total_pnl_pct},
            "alerts": [str],          # 预警文本行
            "market_lines": [str],    # 市场状态文本行（供渲染用）
            "overnight_lines": [str], # 隔夜外盘文本行（供渲染用）
            "northbound_lines": [str],# 北向资金文本行（供渲染用）
            "pos_lines": [str],       # 持仓明细文本行（供渲染用）
            "positions_count": int,   # 持仓数量（供渲染用）
        }
    """
    from data import get_quote, get_northbound_flow
    from portfolio import PortfolioManager

    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "market": {},
        "overnight": {},
        "northbound": {},
        "portfolio": {},
        "alerts": [],
        "market_lines": [],
        "overnight_lines": [],
        "northbound_lines": [],
        "pos_lines": [],
        "positions_count": 0,
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

    result["market_lines"] = market_lines

    # 1b. 隔夜外盘（美股三大指数 + VIX）
    overnight_indices = {
        "us:^gspc": "标普500",
        "us:^ixic": "纳斯达克",
        "us:^dji": "道琼斯",
        "us:^vix": "VIX恐慌指数",
    }
    overnight_lines = []
    for code, name in overnight_indices.items():
        try:
            q = get_quote(code)
            if q:
                price = q.price if hasattr(q, "price") else 0
                change = q.change_pct if hasattr(q, "change_pct") else 0
                # VIX 涨为恐慌（🔴），跌为平静（🟢）；指数涨跌正常显示
                if code == "us:^vix":
                    icon = "🔴" if change >= 0 else "🟢"
                    overnight_lines.append(f"{icon} {name}: {price:.2f}")
                else:
                    icon = "🟢" if change >= 0 else "🔴"
                    overnight_lines.append(f"{icon} {name}: {price:.2f} ({change:+.2f}%)")
                result["overnight"][code] = {
                    "name": name,
                    "price": price,
                    "change_pct": change,
                }
        except Exception as e:
            logger.debug("隔夜外盘 %s 失败: %s", code, e)

    result["overnight_lines"] = overnight_lines

    # 1c. 北向资金（近 5 日净买入）
    northbound_lines = []
    try:
        nb_data = get_northbound_flow("", days=5)
        if nb_data:
            latest = nb_data[-1]
            net = latest.get("net_buy", 0)
            icon = "🟢" if net >= 0 else "🔴"
            northbound_lines.append(
                f"{icon} 最新北向: {net / 1e4:+.1f} 亿"
            )
            # 5 日累计
            total_5d = sum(d.get("net_buy", 0) for d in nb_data) / 1e4
            northbound_lines.append(f"  5日累计: {total_5d:+.1f} 亿")
            result["northbound"] = {
                "net_buy": net,
                "sh_net": latest.get("sh_net", 0),
                "sz_net": latest.get("sz_net", 0),
                "days": nb_data,
            }
    except Exception as e:
        logger.debug("北向资金获取失败: %s", e)

    result["northbound_lines"] = northbound_lines

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
        except Exception as e:
            logger.debug("获取行情失败 %s: %s", code, e)
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
    result["pos_lines"] = pos_lines
    # 有效持仓数（pos_lines 已过滤掉 code/cost/qty 无效的仓位）
    result["positions_count"] = len(pos_lines)

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
        except Exception as e:
            logger.debug("compute_key_levels 失败 %s: %s", code, e)

    result["alerts"] = alert_lines

    return result

"""预警分级配置与预警检查规则。

从 alert_engine.py 拆分，包含预警级别常量、级别查询函数、预警触发检查。
"""

import logging

import yaml

from common import to_float

logger = logging.getLogger(__name__)

# 从配置加载止损/止盈阈值
try:
    from config.loader import ConfigLoader

    _raw_stop_loss = ConfigLoader.get("limits.yaml", "stop_loss_pct", 8)
    _STOP_LOSS_PCT = -abs(_raw_stop_loss)  # 确保为负数
    _raw_take_profit = ConfigLoader.get("limits.yaml", "take_profit_pct", 20)
    _TAKE_PROFIT_PCT = abs(_raw_take_profit)  # 确保为正数
except (FileNotFoundError, yaml.YAMLError) as e:
    logger.warning("加载止损/止盈配置失败，使用默认值: %s", e)
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
    # v2.4.0 新增：组合/市场级预警
    "risk_change": {"level": "important", "push_type": "portfolio"},
    "underperform_days": {"level": "normal", "push_type": "portfolio"},
    "concentration": {"level": "important", "push_type": "portfolio"},
    "index_change": {"level": "important", "push_type": "market"},
    "sector_moved": {"level": "normal", "push_type": "market"},
    "northbound_flow": {"level": "urgent", "push_type": "market"},
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


def _check_alerts(
    price: float,
    levels: dict,
    position: dict = None,
    watch: dict = None,
) -> list:
    """检查当前价格是否触发预警条件。"""
    alerts = []

    # 支撑位触及（强/弱分级）：价格运行到支撑位 ±1% 区间才报警，
    # 避免一字跌停/连续阴跌时反复误报
    for s in levels.get("supports", []):
        lv = s.get("level", 0)
        if lv > 0 and lv * 0.99 <= price <= lv * 1.01:
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

    # 压力位触及（与支撑位对称：加上界，避免价格远超压力位后持续误报）
    for r in levels.get("resistances", []):
        lv = r.get("level", 0)
        if lv > 0 and lv * 0.99 <= price <= lv * 1.01:
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

    # 目标卖出价（止损价：价格跌破此价应卖出）
    ts = levels.get("target_sell", 0)
    if ts > 0 and price <= ts:
        dist_pct = (price - ts) / ts * 100
        alerts.append(
            {
                "type": "target_sell",
                "level": ts,
                "message": f"已跌破目标卖出/止损价 {ts}（偏离 {dist_pct:+.1f}%）",
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


# ═══════════════════════════════════════════════════════════════
# 组合/市场级预警（v2.4.0 新增，对应 notification.yaml 中 6 项未实现规则）
# ═══════════════════════════════════════════════════════════════


# notification.yaml 配置加载
def _load_notification_config() -> dict:
    """加载 notification.yaml 中未实现的预警阈值。"""
    try:
        from config.loader import ConfigLoader

        notif = ConfigLoader.load("notification.yaml") or {}
        rules = notif.get("notification_rules", {}) or {}
        return {
            "underperform_days": rules.get("underperform_days", 2),
            "index_change_threshold": rules.get("index_change", 2.0),
            "northbound_threshold_yi": rules.get("northbound_flow", 50),
        }
    except Exception:
        return {
            "underperform_days": 2,
            "index_change_threshold": 2.0,
            "northbound_threshold_yi": 50,
        }


def check_portfolio_alerts(
    positions: list,
    quotes: dict,
    benchmark_change_pct: float = None,
    northbound_net_yi: float = None,
    sector_changes: dict = None,
    prev_risk_state: str = None,
    current_risk_state: str = None,
) -> list:
    """检查组合/市场级预警。

    Args:
        positions: 持仓列表 [{code, name, cost, quantity, tags}]
        quotes: {code: {price, change_pct, ...}}
        benchmark_change_pct: 沪深300 当日涨跌幅（%）
        northbound_net_yi: 北向资金净流入/出（亿元）
        sector_changes: 持仓板块涨跌幅 {sector: change_pct}
        prev_risk_state / current_risk_state: 风险状态切换（GREEN/YELLOW/RED）

    Returns:
        预警列表
    """
    if not positions:
        return []
    cfg = _load_notification_config()
    alerts = []

    # 1. 风险状态变更（GREEN→RED 时紧急预警）
    if prev_risk_state and current_risk_state:
        risk_order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
        p = risk_order.get(prev_risk_state, 0)
        c = risk_order.get(current_risk_state, 0)
        if c > p:
            alerts.append(
                {
                    "type": "risk_change",
                    "message": f"风险状态升级：{prev_risk_state} → {current_risk_state}",
                    "urgent": current_risk_state == "RED",
                }
            )

    # 2. 连续跑输基准
    # 当前为单次快照模式：组合当日加权收益 vs 基准收益的差值超过阈值时触发。
    # underperform_days 阈值含义：跑输基准的百分点差值（非天数），
    # 默认 2 表示跑输基准 2 个百分点时触发预警。
    if benchmark_change_pct is not None and positions:
        total_value = sum(
            quotes.get(p["code"], {}).get("price", p.get("cost", 0))
            * p.get("quantity", 0)
            for p in positions
        )
        if total_value > 0:
            weighted_pnl_pct = (
                sum(
                    (
                        quotes.get(p["code"], {}).get("price", p.get("cost", 0))
                        / p.get("cost", 1)
                        - 1
                    )
                    * 100
                    * (quotes.get(p["code"], {}).get("price", 0) * p.get("quantity", 0))
                    for p in positions
                )
                / total_value
            )
            diff = weighted_pnl_pct - benchmark_change_pct
            if diff < -cfg["underperform_days"]:
                alerts.append(
                    {
                        "type": "underperform_days",
                        "message": f"组合跑输沪深300 {abs(diff):.1f}个百分点（基准{benchmark_change_pct:.1f}% vs 组合{weighted_pnl_pct:.1f}%）",
                        "urgent": False,
                    }
                )

    # 3. 持仓集中度超标
    if positions:
        total = sum(
            quotes.get(p["code"], {}).get("price", 0) * p.get("quantity", 0)
            for p in positions
        )
        if total > 0:
            single_max = 0.20  # 单标的上限
            top3 = 0.50  # 前 3 持仓上限
            # 计算单标的权重
            sorted_by_value = sorted(
                [
                    (
                        p,
                        quotes.get(p["code"], {}).get("price", 0)
                        * p.get("quantity", 0),
                    )
                    for p in positions
                ],
                key=lambda x: x[1],
                reverse=True,
            )
            top1 = sorted_by_value[0][1] / total if sorted_by_value else 0
            top3_pct = (
                sum(v for _, v in sorted_by_value[:3]) / total
                if len(sorted_by_value) >= 3
                else sum(v for _, v in sorted_by_value) / total
            )
            if top1 > single_max:
                alerts.append(
                    {
                        "type": "concentration",
                        "message": f"单一标的集中度 {top1*100:.1f}% 超标（>20%）",
                        "urgent": True,
                    }
                )
            elif top3_pct > top3:
                alerts.append(
                    {
                        "type": "concentration",
                        "message": f"前3大持仓 {top3_pct*100:.1f}% 超标（>50%）",
                        "urgent": False,
                    }
                )

    # 4. 大盘涨跌幅超阈值
    if (
        benchmark_change_pct is not None
        and abs(benchmark_change_pct) >= cfg["index_change_threshold"]
    ):
        alerts.append(
            {
                "type": "index_change",
                "message": f"沪深300 {benchmark_change_pct:+.1f}%（阈值 ±{cfg['index_change_threshold']}%）",
                "urgent": abs(benchmark_change_pct)
                >= cfg["index_change_threshold"] * 1.5,
            }
        )

    # 5. 持仓板块异动
    if sector_changes and positions:
        for p in positions:
            tags = p.get("tags", [])
            if tags:
                sector = tags[0]
                sector_chg = sector_changes.get(sector)
                if sector_chg is not None and abs(sector_chg) >= 3.0:
                    alerts.append(
                        {
                            "type": "sector_moved",
                            "message": f"持仓板块 {sector} 涨跌幅 {sector_chg:+.1f}%",
                            "urgent": False,
                        }
                    )
                    break  # 只触发一次

    # 6. 北向资金大幅净流入/出
    if (
        northbound_net_yi is not None
        and abs(northbound_net_yi) >= cfg["northbound_threshold_yi"]
    ):
        direction = "流入" if northbound_net_yi > 0 else "流出"
        alerts.append(
            {
                "type": "northbound_flow",
                "message": f"北向资金 {direction} {abs(northbound_net_yi):.0f}亿元（阈值 {cfg['northbound_threshold_yi']}亿）",
                "urgent": abs(northbound_net_yi)
                >= cfg["northbound_threshold_yi"] * 1.5,
            }
        )

    return alerts

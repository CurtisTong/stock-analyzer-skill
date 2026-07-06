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

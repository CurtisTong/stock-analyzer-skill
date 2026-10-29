"""组合保护机制三件套（v1.24.0，Freqtrade Protections 的 A 股化）。

- 回撤熔断（MaxDrawdown）：组合清仓利润曲线峰谷回撤超阈值 → 停止加仓
- 连亏熔断（StoplossGuard）：连续 N 笔亏损 → 冷却期停手
- 冷却期（CooldownPeriod）：同票清仓后 N 个自然日内不再入场

数据来自 TradeLog（清仓记录）+ 当前持仓估值（回撤口径近似）。
纯函数可单独测试；check_protections 聚合输出供 /portfolio 渲染。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

# 默认阈值（Freqtrade 经验值 A 股化）
DEFAULT_DRAWDOWN_PCT = 15.0  # 累计利润曲线回撤 15% 熔断
DEFAULT_CONSECUTIVE_LOSSES = 3  # 连亏 3 笔熔断
DEFAULT_COOLDOWN_DAYS = 10  # 同票清仓后 10 个自然日冷却


def check_max_drawdown(
    equity_points: list[float],
    threshold_pct: float = DEFAULT_DRAWDOWN_PCT,
) -> Optional[dict]:
    """回撤熔断：从权益序列峰谷计算当前回撤。

    Args:
        equity_points: 权益/利润序列（时间顺序）
        threshold_pct: 熔断阈值（%）

    Returns:
        {"triggered": bool, "drawdown_pct": float, "message": str}
    """
    if len(equity_points) < 2:
        return None
    peak = equity_points[0]
    max_dd = 0.0
    for v in equity_points:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd
    triggered = max_dd >= threshold_pct
    return {
        "triggered": triggered,
        "drawdown_pct": round(max_dd, 2),
        "message": (
            f"累计利润回撤 {max_dd:.1f}% ≥ 阈值 {threshold_pct}%"
            if triggered
            else f"累计利润回撤 {max_dd:.1f}%（未触发，阈值 {threshold_pct}%）"
        ),
    }


def check_consecutive_losses(
    trades: list[dict],
    n: int = DEFAULT_CONSECUTIVE_LOSSES,
) -> Optional[dict]:
    """连亏熔断：最近连续亏损笔数（按时间序，最新在末尾）。"""
    if not trades:
        return None
    recent = 0
    for t in reversed(trades):
        if t.get("profit_pct", 0) < 0:
            recent += 1
        else:
            break
    triggered = recent >= n
    return {
        "triggered": triggered,
        "consecutive_losses": recent,
        "message": (
            f"连续 {recent} 笔亏损 ≥ 熔断阈值 {n} 笔，进入冷却"
            if triggered
            else f"最近连续亏损 {recent} 笔（阈值 {n}）"
        ),
    }


def check_cooldown(
    trades: list[dict],
    code: str,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
    today: Optional[str] = None,
) -> Optional[dict]:
    """冷却期：该股最近清仓后是否仍在冷却窗口内。"""
    today = today or datetime.now().strftime("%Y-%m-%d")
    for t in reversed(trades):
        if t.get("code") != code:
            continue
        sell_date = t.get("sell_date", "")[:10]
        if not sell_date:
            return None
        try:
            days_since = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(sell_date, "%Y-%m-%d")).days
        except ValueError:
            return None
        remaining = cooldown_days - days_since
        return {
            "triggered": remaining > 0,
            "days_left": max(remaining, 0),
            "message": (
                f"{code} 冷却期还有 {remaining} 天（{sell_date} 清仓后 {cooldown_days} 天）"
                if remaining > 0
                else f"{code} 已过冷却期（{sell_date} 清仓，{days_since} 天前）"
            ),
        }
    return None


def check_protections(
    trades: list[dict],
    position_pnl_pct: Optional[float] = None,
    cooldown_codes: Optional[list[str]] = None,
) -> dict:
    """聚合三件套检查（供 portfolio health 渲染）。

    Args:
        trades: TradeLog records 列表（时间序）
        position_pnl_pct: 当前持仓整体盈亏%（并入回撤视角，简单口径）
        cooldown_codes: 需要检查冷却期的代码列表（如持仓/自选）

    Returns:
        {"drawdown": ..., "losses": ..., "cooldowns": {...},
         "all_clear": bool, "summary": str}
    """
    result: dict = {}

    # 回撤：累计清仓利润序列（无持仓 pnl 时）
    equity = []
    acc = 0.0
    for t in trades:
        acc += t.get("profit", 0.0)
        equity.append(acc)
    dd = check_max_drawdown(equity) if equity else None
    result["drawdown"] = dd

    # 连亏
    losses = check_consecutive_losses(trades) if trades else None
    result["losses"] = losses

    # 冷却期
    cooldowns = {}
    if cooldown_codes:
        for code in cooldown_codes:
            c = check_cooldown(trades, code)
            if c and c["triggered"]:
                cooldowns[code] = c
    result["cooldowns"] = cooldowns

    triggered = [k for k, v in result.items() if isinstance(v, dict) and v.get("triggered")]
    if cooldowns:
        triggered.append("cooldowns")
    result["all_clear"] = not triggered
    if triggered:
        result["summary"] = "保护触发: " + "、".join(triggered) + "（建议暂停加仓并复核仓位）"
    else:
        result["summary"] = "保护机制全部正常"
    return result


__all__ = [
    "check_max_drawdown",
    "check_consecutive_losses",
    "check_cooldown",
    "check_protections",
    "DEFAULT_DRAWDOWN_PCT",
    "DEFAULT_CONSECUTIVE_LOSSES",
    "DEFAULT_COOLDOWN_DAYS",
]

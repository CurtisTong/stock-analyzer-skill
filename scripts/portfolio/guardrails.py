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


def _sort_trades_newest_first(trades: list[dict]) -> list[dict]:
    """按卖出日期排序，最新在前。

    TradeLog.query() 返回的是降序（最新在前，trade_log.py:196），而
    本模块原实现用 reversed() 假设升序——同一批交易在两种顺序下结论相反
    （连亏计数 2 vs 0、冷却期取到最老的一笔）。这里统一按日期降序，
    不依赖调用方的顺序约定。
    """
    return sorted(trades, key=lambda t: t.get("sell_date", "") or "", reverse=True)


def check_max_drawdown(
    equity_points: list[float],
    threshold_pct: float = DEFAULT_DRAWDOWN_PCT,
) -> Optional[dict]:
    """回撤熔断：从权益序列峰谷计算当前回撤。

    Args:
        equity_points: 权益序列（时间顺序，绝对金额口径）
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
        # 分母为峰值权益。峰值 <= 0（亏损账户，权益为负）时不能用 peak 做分母，
        # 否则回撤恒为 0——"账户越亏越不会熔断"，方向完全反了。
        # 负权益段改用绝对值口径衡量权益的进一步恶化。
        if peak > 0:
            dd = (peak - v) / peak * 100
        elif peak < 0:
            dd = (peak - v) / abs(peak) * 100
        else:
            dd = 0.0
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
    for t in _sort_trades_newest_first(trades):
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
    for t in _sort_trades_newest_first(trades):
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
    initial_capital: Optional[float] = None,
) -> dict:
    """聚合三件套检查（供 portfolio health 渲染）。

    Args:
        trades: TradeLog records 列表（顺序不限，内部按 sell_date 排序）
        position_pnl_pct: 当前持仓整体盈亏%（并入回撤视角，简单口径）
        cooldown_codes: 需要检查冷却期的代码列表（如持仓/自选）
        initial_capital: 账户初始资金（回撤按权益口径计算时需要；
            缺省时退化为累计利润口径）

    Returns:
        {"drawdown": ..., "losses": ..., "cooldowns": {...},
         "all_clear": bool, "summary": str}
    """
    result: dict = {}

    # 回撤：权益曲线（初始资金 + 累计清仓利润 + 当前持仓浮动盈亏）。
    # 原实现直接累加"利润"当权益，峰值 <= 0（亏损账户）时回撤恒为 0，
    # 账户越亏越不会熔断——方向完全反了。有初始资金时用权益口径。
    equity = []
    acc = 0.0
    for t in sorted(trades, key=lambda x: x.get("sell_date", "") or ""):
        acc += t.get("profit", 0.0)
        equity.append((initial_capital + acc) if initial_capital else acc)
    # 当前持仓的浮动盈亏是权益的最新状态——不并入的话，持仓浮亏时回撤看不到亏损
    if position_pnl_pct is not None:
        if initial_capital:
            equity.append(initial_capital + acc + initial_capital * position_pnl_pct / 100.0)
        else:
            # 无初始资金时无法把百分比折算成金额，用累计利润的比例近似
            equity.append(acc * (1 + position_pnl_pct / 100.0))
    dd = check_max_drawdown(equity) if equity else None
    result["drawdown"] = dd
    if position_pnl_pct is not None:
        result["position_pnl_pct"] = round(position_pnl_pct, 2)

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

    # 持久化熔断状态（v1.25 复审修复）：原实现是纯函数，熔断"是否处于熔断中"
    # 完全依赖当前交易内容——追加一笔盈利交易连亏计数归零，熔断自动解除，
    # 没有任何冷却锁定；进程重启后更是一片空白。
    #
    # 本函数只**读**状态（检查语义，不产生写副作用）；写入由
    # sync_breakers() 显式调用，避免"检查即落盘"的隐式行为。
    state = load_state()
    active = _active_breakers(state)
    if active:
        result["active_breakers"] = active
        result["breaker"] = {
            "triggered": True,
            "message": "；".join(b["message"] for b in active),
        }

    triggered = [k for k, v in result.items() if isinstance(v, dict) and v.get("triggered")]
    if cooldowns:
        triggered.append("cooldowns")
    result["all_clear"] = not triggered
    if triggered:
        result["summary"] = "保护触发: " + "、".join(triggered) + "（建议暂停加仓并复核仓位）"
    else:
        result["summary"] = "保护机制全部正常"
    return result


# ═══════════════════════════════════════════════════════════════
# 熔断状态持久化（v1.25 复审修复）
# ═══════════════════════════════════════════════════════════════

STATE_FILE = "guardrails_state.json"

# 熔断冷却期（自然日）：触发后在此期间内禁止加仓
DEFAULT_BREAKER_COOLDOWN_DAYS = 10


def _state_path():
    from portfolio._file_utils import data_dir

    return data_dir() / STATE_FILE


def load_state() -> dict:
    """读取保护机制状态（不存在或损坏时返回空状态）。"""
    import json

    path = _state_path()
    if not path.exists():
        return {"breakers": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"breakers": []}
    if not isinstance(data, dict):
        return {"breakers": []}
    data.setdefault("breakers", [])
    return data


def save_state(state: dict) -> None:
    """写入保护机制状态（原子写 + 文件锁）。"""
    from portfolio._file_utils import atomic_write

    atomic_write(_state_path(), state)


def record_breaker(kind: str, message: str, cooldown_days: int = DEFAULT_BREAKER_COOLDOWN_DAYS) -> dict:
    """记录一次熔断（带冷却期），返回状态条目。

    熔断在冷却期到期前持续生效——不因后续盈利交易而自动解除。

    Args:
        kind: 熔断类型（drawdown / losses / manual）
        message: 展示文案
        cooldown_days: 冷却天数（默认 10）

    Returns:
        写入的状态条目
    """
    from datetime import datetime

    state = load_state()
    now = datetime.now()
    entry = {
        "kind": kind,
        "message": message,
        "triggered_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "until": (now + timedelta(days=cooldown_days)).strftime("%Y-%m-%d"),
        "cooldown_days": cooldown_days,
    }
    breakers = [b for b in state.get("breakers", []) if b.get("kind") != kind]
    breakers.append(entry)
    state["breakers"] = breakers
    save_state(state)
    return entry


def clear_breakers(kind: str | None = None) -> int:
    """清除熔断状态（kind=None 清除全部），返回清除条数。"""
    state = load_state()
    before = len(state.get("breakers", []))
    if kind:
        state["breakers"] = [b for b in state.get("breakers", []) if b.get("kind") != kind]
    else:
        state["breakers"] = []
    save_state(state)
    return before - len(state["breakers"])


def _active_breakers(state: dict, today: str | None = None) -> list[dict]:
    """返回仍在冷却期内的熔断条目（已过期的自动清理）。"""
    from datetime import datetime

    today = today or datetime.now().strftime("%Y-%m-%d")
    active = []
    expired = []
    for b in state.get("breakers", []):
        until = b.get("until", "")
        if until and until < today:
            expired.append(b)
        else:
            active.append(b)
    if expired:
        # 顺手清理过期条目
        state["breakers"] = active
        try:
            save_state(state)
        except OSError:
            pass
    return active


def sync_breakers(
    trades: list[dict],
    initial_capital: Optional[float] = None,
    cooldown_days: int = DEFAULT_BREAKER_COOLDOWN_DAYS,
) -> list[dict]:
    """根据交易记录同步熔断状态（显式写入）。

    check_protections 是纯读检查；熔断状态的落盘由本函数显式触发，
    避免"检查即写盘"的隐式副作用（会污染数据文件、让检查不可重入）。

    Args:
        trades: 交易记录
        initial_capital: 账户初始资金（回撤按权益口径）
        cooldown_days: 熔断冷却天数

    Returns:
        当前生效的熔断条目列表
    """
    if not trades:
        return []
    equity = []
    acc = 0.0
    for t in sorted(trades, key=lambda x: x.get("sell_date", "") or ""):
        acc += t.get("profit", 0.0)
        equity.append((initial_capital + acc) if initial_capital else acc)
    dd = check_max_drawdown(equity) if equity else None
    losses = check_consecutive_losses(trades)

    for kind, check in (("drawdown", dd), ("losses", losses)):
        if check and check.get("triggered"):
            try:
                record_breaker(kind, check.get("message", kind), cooldown_days)
            except OSError:
                pass
    return _active_breakers(load_state())


def is_trading_allowed(code: str, cooldown_codes: list[str] | None = None) -> tuple[bool, str]:
    """硬阻止接口：是否允许对该股加仓。

    与"提示型"的 check_protections 互补——本函数给出可直接用于
    拒绝加仓的结论（True = 允许，False = 阻止 + 原因）。

    Args:
        code: 待加仓的股票代码
        cooldown_codes: 需要检查冷却期的代码列表（如当前持仓/自选）

    Returns:
        (allowed, reason)
    """
    state = load_state()
    active = _active_breakers(state)
    if active:
        return False, "；".join(b["message"] for b in active)

    if cooldown_codes:
        try:
            from portfolio.trade_log import TradeLog

            trades = TradeLog().query()
        except Exception:
            trades = []
        if trades:
            c = check_cooldown(trades, code)
            if c and c.get("triggered"):
                return False, c.get("message", f"{code} 在冷却期内")
    return True, ""


__all__ = [
    "check_max_drawdown",
    "check_consecutive_losses",
    "check_cooldown",
    "check_protections",
    "load_state",
    "save_state",
    "record_breaker",
    "clear_breakers",
    "sync_breakers",
    "is_trading_allowed",
    "DEFAULT_DRAWDOWN_PCT",
    "DEFAULT_CONSECUTIVE_LOSSES",
    "DEFAULT_COOLDOWN_DAYS",
    "DEFAULT_BREAKER_COOLDOWN_DAYS",
]

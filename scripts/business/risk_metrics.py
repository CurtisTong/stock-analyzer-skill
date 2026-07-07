"""组合风险量化指标。

扩展 risk_warning.py（仅宏观提示），加入：
- VaR（Value at Risk）：历史模拟法
- CVaR（Conditional VaR）：尾部风险
- 最大回撤
- 收益波动率
- 行业相关性矩阵提示

v2.4.0 新增。
"""

import math
import statistics
from typing import Dict, List, Optional


def historical_var(returns: List[float], confidence: float = 0.95) -> float:
    """历史模拟法 VaR。

    Args:
        returns: 日收益率序列（小数，例如 -0.02 表示 -2%）
        confidence: 置信度（默认 0.95）

    Returns:
        VaR 值（正数表示亏损幅度，例如 0.05 表示一天最多可能亏 5%）

    Example:
        var = historical_var([-0.05, 0.02, -0.01, 0.03, ...])
        # var ≈ 0.05 (一天最多亏 5%)
    """
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    idx = int((1 - confidence) * len(sorted_r))
    idx = max(0, min(idx, len(sorted_r) - 1))
    return abs(sorted_r[idx])


def conditional_var(returns: List[float], confidence: float = 0.95) -> float:
    """CVaR（条件 VaR / Expected Shortfall）：亏损超过 VaR 时的平均亏损。

    比 VaR 更严格——它考虑了尾部极端损失的平均水平。
    """
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    cutoff = int((1 - confidence) * len(sorted_r))
    cutoff = max(1, cutoff)
    tail = sorted_r[:cutoff]
    return abs(sum(tail) / len(tail))


def max_drawdown(prices: List[float]) -> Dict[str, float]:
    """最大回撤（peak-to-trough）。

    Args:
        prices: 价格序列（递增列表）

    Returns:
        {"max_dd_pct": -0.15, "peak_idx": 100, "trough_idx": 150, "recovery_idx": 180}
    """
    if len(prices) < 2:
        return {"max_dd_pct": 0.0, "peak_idx": 0, "trough_idx": 0, "recovery_idx": 0}

    peak = prices[0]
    peak_idx = 0
    max_dd = 0.0
    trough_idx = 0
    recovery_idx = 0

    for i, p in enumerate(prices):
        if p > peak:
            peak = p
            peak_idx = i
        dd = (p - peak) / peak if peak > 0 else 0
        if dd < max_dd:
            max_dd = dd
            trough_idx = i
            recovery_idx = i  # 默认未恢复

    # 寻找 trough 后的价格回到 peak 的位置
    for j in range(trough_idx + 1, len(prices)):
        if prices[j] >= peak:
            recovery_idx = j
            break

    return {
        "max_dd_pct": round(max_dd, 4),
        "peak_idx": peak_idx,
        "trough_idx": trough_idx,
        "recovery_idx": recovery_idx if recovery_idx > trough_idx else None,
    }


def volatility(returns: List[float]) -> float:
    """收益波动率（年化）。

    Args:
        returns: 日收益率序列（小数）

    Returns:
        年化波动率（例如 0.25 = 25%）
    """
    if len(returns) < 2:
        return 0.0
    return statistics.stdev(returns) * math.sqrt(252)


def sharpe(returns: List[float], risk_free: float = 0.03) -> float:
    """夏普比率。

    Args:
        returns: 日收益率序列
        risk_free: 无风险年化利率（默认 3%）

    Returns:
        夏普比率（> 1 为优秀，< 0 为亏损）
    """
    if len(returns) < 2:
        return 0.0
    avg = statistics.mean(returns) * 252  # 年化收益
    vol = volatility(returns)
    if vol == 0:
        return 0.0
    return round((avg - risk_free) / vol, 2)


def position_var_summary(
    positions: List[Dict],
    quotes: Optional[Dict[str, float]] = None,
    confidence: float = 0.95,
) -> dict:
    """组合层级 VaR 摘要（基于个股 VaR 加权聚合的近似）。

    Args:
        positions: [{code, name, cost, quantity, weight, vol?}, ...]
        quotes: {code: current_price} 估值
        confidence: 置信度

    Returns:
        {"var_pct": 0.03, "cvar_pct": 0.05, "worst_scenarios": [...]}
    """
    if not positions:
        return {"var_pct": 0.0, "cvar_pct": 0.0, "worst_scenarios": []}

    total_var = 0.0
    total_cvar = 0.0
    worst = []

    for p in positions:
        code = p.get("code", "")
        weight = p.get("weight", 0.0)
        vol = p.get("vol", 0.20)  # 默认 20% 年化波动
        # 单股 VaR ≈ z × σ × sqrt(1/252)
        z_score = 1.65 if confidence == 0.95 else 2.33  # 95% / 99%
        daily_vol = vol / math.sqrt(252)
        var_1d = z_score * daily_vol
        cvar_1d = var_1d * 1.2  # CVaR 约为 VaR 的 1.2 倍（经验值）
        total_var += weight * var_1d
        total_cvar += weight * cvar_1d
        if weight > 0.05:
            worst.append(
                {
                    "code": code,
                    "name": p.get("name", ""),
                    "weight": round(weight, 3),
                    "var_1d_pct": round(var_1d * 100, 2),
                }
            )

    worst.sort(key=lambda x: x["var_1d_pct"], reverse=True)

    return {
        "var_pct": round(total_var * 100, 2),
        "cvar_pct": round(total_cvar * 100, 2),
        "worst_scenarios": worst[:5],
    }

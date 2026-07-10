#!/usr/bin/env python3
"""
个股 beta 系数计算（v2.6.0 新增）。

基于历史 60 日 K 线 vs 基准指数的 OLS 协方差，手写实现（**不引入 numpy/pandas**），
与 business/risk_metrics.py 和 strategies/factors/registry.py:445-455 风格一致。

公式（标准 CAPM beta）：
    beta = Cov(r_s, r_i) / Var(r_i)
         = sum((r_s - mean_s) * (r_i - mean_i)) / sum((r_i - mean_i)^2)

    alpha = mean(r_s) - beta * mean(r_i)         # 日度
    alpha_annual = alpha * 252                    # 年化
    r_squared = 1 - sum((r_s - r_pred)^2) / sum((r_s - mean_s)^2)

基准指数动态选择（按个股流通市值）：
    > 500 亿   → sh000300 (沪深 300)
    > 100 亿   → sh000905 (中证 500)
    否则       → sh000852 (中证 1000)

复用：
- data.get_kline()        60 日日 K 线（1h TTL 缓存）
- data.get_quotes()       个股流通市值
- statistics.mean/stdev   手写 OLS

用法:
  from industry_beta import compute_beta, select_index_by_size
  beta = compute_beta("sh600519")  # 自动选基准
  beta = compute_beta("sh600519", index_code="sh000300", window=60)
"""

import sys
import logging
import statistics
from pathlib import Path

logger = logging.getLogger(__name__)

# 确保 scripts/ 在 import 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import get_kline, get_quotes  # noqa: E402 多源数据层

# ═══════════════════════════════════════════════════════════════
# 动态基准指数选择（按流通市值）
# ═══════════════════════════════════════════════════════════════

SIZE_THRESHOLD_LARGE = 500.0  # > 500 亿 → 沪深 300
SIZE_THRESHOLD_MID = 100.0  # > 100 亿 → 中证 500；否则中证 1000


def select_index_by_size(stock_code: str) -> str:
    """按流通市值动态选基准指数。

    阈值（流通市值，单位亿元）：
    - > 500   → sh000300 (沪深 300，覆盖大盘蓝筹)
    - 100-500 → sh000905 (中证 500，覆盖中盘)
    - <= 100  → sh000852 (中证 1000，覆盖小盘)

    Returns:
        str: 指数代码（默认 sh000300 当市值数据缺失时）

    Args:
        stock_code: 个股代码（sh600519）

    Note:
        流通市值从 get_quotes() 实时拉取（无缓存依赖）；失败 fallback 到 sh000300。
    """
    try:
        quotes = get_quotes([stock_code], use_cache=True)
        if quotes:
            q = quotes[0]
            if q and q.has_basic_data():
                total_cap = getattr(q, "total_cap", 0) or 0
                if total_cap > SIZE_THRESHOLD_LARGE:
                    return "sh000300"
                if total_cap > SIZE_THRESHOLD_MID:
                    return "sh000905"
                return "sh000852"
    except Exception as e:
        logger.debug("select_index_by_size 拉市值失败: %s", e)
    # fallback: 沪深 300
    return "sh000300"


# ═══════════════════════════════════════════════════════════════
# 收益率序列计算
# ═══════════════════════════════════════════════════════════════


def _daily_returns(closes: list) -> list:
    """日收益率序列：r_t = (close_t / close_{t-1}) - 1。

    输入长度 N → 输出 N-1 个收益率。
    """
    if not closes or len(closes) < 2:
        return []
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append(closes[i] / closes[i - 1] - 1)
    return returns


# ═══════════════════════════════════════════════════════════════
# OLS beta 计算（手写）
# ═══════════════════════════════════════════════════════════════


def _ols_beta(r_stock: list, r_index: list) -> dict | None:
    """手写 OLS beta 系数计算。

    Returns:
        dict: {beta, alpha, alpha_annual, r_squared, volatility_pct}
        任一字段缺失返回 None。
    """
    n = min(len(r_stock), len(r_index))
    if n < 10:  # 至少 10 个观测值
        return None

    r_s = r_stock[:n]
    r_i = r_index[:n]

    mean_s = statistics.mean(r_s)
    mean_i = statistics.mean(r_i)

    # Cov(r_s, r_i)
    cov_si = sum((r_s[k] - mean_s) * (r_i[k] - mean_i) for k in range(n))
    # Var(r_i)
    var_i = sum((r_i[k] - mean_i) ** 2 for k in range(n))

    if var_i == 0:
        return None  # 指数无波动，beta 无定义

    beta = cov_si / var_i
    alpha = mean_s - beta * mean_i
    alpha_annual = alpha * 252  # 年化

    # R² = 1 - SS_res / SS_tot
    # SS_res = sum((r_s - r_pred)^2)，r_pred = alpha + beta * r_i
    ss_res = sum((r_s[k] - (alpha + beta * r_i[k])) ** 2 for k in range(n))
    ss_tot = sum((r_s[k] - mean_s) ** 2 for k in range(n))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # 个股年化波动率（daily_std * sqrt(252) * 100）
    if n >= 2:
        daily_std = statistics.stdev(r_s)
        volatility_pct = daily_std * (252**0.5) * 100
    else:
        volatility_pct = None

    return {
        "beta": round(beta, 4),
        "alpha": round(alpha, 6),
        "alpha_annual": round(alpha_annual, 4),
        "r_squared": round(r_squared, 4),
        "volatility_pct": round(volatility_pct, 2) if volatility_pct else None,
        "n_observations": n,
    }


def _interpret_beta(beta: float | None) -> str:
    """beta 解读。"""
    if beta is None:
        return "数据不足"
    if beta < 0:
        return "负 beta：与市场反向（避险/反向 ETF 特征）"
    if beta < 0.5:
        return "超防御型：弹性远小于市场（公用事业/必需消费）"
    if beta < 0.8:
        return "防御型：弹性小于市场"
    if beta < 1.2:
        return "同步型：与市场同向同幅"
    if beta < 1.5:
        return "成长型：弹性大于市场"
    return "高弹性：弹性远大于市场（周期/小盘/科技）"


# ═══════════════════════════════════════════════════════════════
# 顶层入口
# ═══════════════════════════════════════════════════════════════


def compute_beta(
    stock_code: str,
    index_code: str | None = None,
    window: int = 60,
) -> dict | None:
    """计算个股 vs 基准指数的 beta（手写 OLS）。

    Args:
        stock_code: 个股代码（如 sh600519）
        index_code: 基准指数代码（None → 按市值动态选）
        window: K 线窗口（默认 60 日）

    Returns:
        dict:
          {
            "stock_code": "sh600519",
            "index_code": "sh000300",
            "window": 60,
            "beta": 0.85,
            "alpha": 0.0003,
            "alpha_annual": 0.0756,    # 7.56% 年化超额
            "r_squared": 0.65,
            "volatility_pct": 24.5,
            "n_observations": 59,
            "interpretation": "防御型：弹性小于市场",
            "data_quality": {"degraded_fields": [...]}
          }
        数据不足 / K 线缺失 → 返回 None 或部分字段为 None。
    """
    # 动态选基准
    if index_code is None:
        index_code = select_index_by_size(stock_code)

    degraded = []
    try:
        # 拉日 K 线（缓存命中后秒回）
        stock_klines = get_kline(stock_code, scale=240, datalen=window)
        index_klines = get_kline(index_code, scale=240, datalen=window)

        if not stock_klines:
            degraded.append("industry_beta.stock_kline")
        if not index_klines:
            degraded.append("industry_beta.index_kline")
        if not stock_klines or not index_klines:
            return {
                "stock_code": stock_code,
                "index_code": index_code,
                "window": window,
                "beta": None,
                "alpha": None,
                "alpha_annual": None,
                "r_squared": None,
                "volatility_pct": None,
                "n_observations": 0,
                "interpretation": "K 线缺失",
                "data_quality": {"degraded_fields": degraded},
            }

        # 计算收益率
        stock_closes = [k.close for k in stock_klines if k.close > 0]
        index_closes = [k.close for k in index_klines if k.close > 0]
        r_stock = _daily_returns(stock_closes)
        r_index = _daily_returns(index_closes)

        # OLS
        ols_result = _ols_beta(r_stock, r_index)
        if ols_result is None:
            return {
                "stock_code": stock_code,
                "index_code": index_code,
                "window": window,
                "beta": None,
                "alpha": None,
                "alpha_annual": None,
                "r_squared": None,
                "volatility_pct": None,
                "n_observations": len(r_stock),
                "interpretation": "数据不足（<10 观测值）",
                "data_quality": {"degraded_fields": degraded + ["industry_beta.ols"]},
            }

        return {
            "stock_code": stock_code,
            "index_code": index_code,
            "window": window,
            **ols_result,
            "interpretation": _interpret_beta(ols_result["beta"]),
            "data_quality": {"degraded_fields": degraded},
        }
    except Exception as e:
        logger.warning("compute_beta 异常: %s", e)
        return {
            "stock_code": stock_code,
            "index_code": index_code,
            "window": window,
            "beta": None,
            "alpha": None,
            "alpha_annual": None,
            "r_squared": None,
            "volatility_pct": None,
            "n_observations": 0,
            "interpretation": f"异常: {type(e).__name__}",
            "data_quality": {"degraded_fields": ["industry_beta"]},
        }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="个股 beta 系数（手写 OLS）")
    parser.add_argument("stock_code", help="个股代码（如 sh600519）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--index", default=None, help="基准指数（None=动态选）")
    parser.add_argument("--window", type=int, default=60, help="K 线窗口（默认 60 日）")
    args = parser.parse_args()

    result = compute_beta(args.stock_code, index_code=args.index, window=args.window)
    if not result:
        print("计算失败")
        return

    if args.json:
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        idx = result["index_code"]
        print(f"📊 {result['stock_code']} vs {idx} ({result['window']}日 OLS)")
        print(f"  Beta: {result['beta']}")
        print(
            f"  Alpha: {result['alpha']} (年化 {result['alpha_annual'] * 100 if result['alpha_annual'] else 'N/A'}%)"
        )
        print(f"  R²: {result['r_squared']}")
        print(f"  年化波动率: {result['volatility_pct']}%")
        print(f"  观测值: {result['n_observations']}")
        print(f"  解读: {result['interpretation']}")
        dq = result.get("data_quality", {}).get("degraded_fields", [])
        if dq:
            print(f"  ⚠️ 降级: {', '.join(dq)}")


if __name__ == "__main__":
    main()

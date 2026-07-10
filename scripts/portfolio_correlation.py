#!/usr/bin/env python3
"""
组合相关性矩阵（v2.6.0 新增）。

基于 PortfolioManager.get_positions() 拉持仓列表，对每个持仓 +
候选个股 + 大盘基准 拉 60 日日 K 线，手写皮尔逊相关系数矩阵。

输出：
- 持仓 vs 持仓 的两两相关性矩阵
- 持仓 vs 大盘 的相关性
- 平均两两相关性（>0.7 高风险）
- 高相关对列表（>0.7 阈值，伪分散告警）
- 单只股票 vs 持仓组合的相关性均值（"加入组合风险"维度）

复用：
- portfolio.manager.PortfolioManager.get_positions()
- data.get_kline()        60 日日 K 线（1h TTL 缓存）
- statistics              手写相关系数

降级：
- 持仓为空 → 返回 portfolio_empty=True
- 个别持仓 K 线缺失 → 矩阵中标记 NaN（用 None 表示）
- 全部缺失 → 返回 None

用法:
  from portfolio_correlation import (
      compute_correlation_matrix,
      compute_stock_vs_portfolio,
  )
  matrix = compute_correlation_matrix(["sh600519", "sz000001"], window=60)
  vs = compute_stock_vs_portfolio("sh600519", ["sz000001", "sh601318"], window=60)
"""

import sys
import logging
import statistics
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 确保 scripts/ 在 import 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import get_kline  # noqa: E402 多源数据层
from industry_beta import _daily_returns  # noqa: E402 复用收益率计算

# ═══════════════════════════════════════════════════════════════
# 相关系数计算
# ═══════════════════════════════════════════════════════════════


def _pearson_corr(x: list, y: list) -> float | None:
    """皮尔逊相关系数 = Cov(x,y) / (σ_x * σ_y)。

    任一缺失 / 长度不足 / 方差为 0 → 返回 None。
    """
    n = min(len(x), len(y))
    if n < 10:
        return None

    x = x[:n]
    y = y[:n]

    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    cov_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    if var_x == 0 or var_y == 0:
        return None

    corr = cov_xy / (var_x * var_y) ** 0.5
    # 数值稳定性
    if corr > 1.0:
        corr = 1.0
    elif corr < -1.0:
        corr = -1.0
    return round(corr, 4)


def _load_returns(code: str, window: int = 60) -> list | None:
    """拉取 K 线并计算日收益率序列。失败返回 None。"""
    try:
        klines = get_kline(code, scale=240, datalen=window)
        if not klines:
            return None
        closes = [k.close for k in klines if k.close > 0]
        return _daily_returns(closes)
    except Exception as e:
        logger.debug("_load_returns(%s) 失败: %s", code, e)
        return None


# ═══════════════════════════════════════════════════════════════
# 矩阵构建
# ═══════════════════════════════════════════════════════════════


def compute_correlation_matrix(
    codes: list[str],
    index_code: str = "sh000300",
    window: int = 60,
    high_corr_threshold: float = 0.7,
) -> dict | None:
    """计算代码列表 + 基准指数的相关系数矩阵。

    Args:
        codes: 代码列表（持仓 + 可选个股）
        index_code: 基准指数代码（默认 sh000300 沪深300，会自动加进矩阵）
        window: K 线窗口（默认 60 日）
        high_corr_threshold: 高相关对阈值（默认 0.7）

    Returns:
        dict:
          {
            "codes": [..., index_code],        # 矩阵包含的代码（含基准）
            "window": 60,
            "matrix": {
              code_a: {code_b: corr, ...},
              ...
            },
            "avg_pairwise_corr": 0.42,
            "high_corr_pairs": [
              [code_a, code_b, corr],  # > threshold
            ],
            "interpretation": "持仓相关性适中，分散度可接受",
            "data_quality": {"degraded_fields": [...]}
          }
        所有 K 线缺失 → 返回 None
    """
    # 准备代码列表（含基准）
    all_codes = list(dict.fromkeys(codes + [index_code]))  # 去重保序

    # 拉每个代码的收益率
    returns_map = {}
    degraded = []
    for code in all_codes:
        r = _load_returns(code, window)
        if r is None:
            degraded.append(f"corr.{code}")
            continue
        returns_map[code] = r

    if not returns_map:
        return None

    # 计算矩阵
    matrix = {}
    valid_codes = list(returns_map.keys())
    for code_a in valid_codes:
        matrix[code_a] = {}
        for code_b in valid_codes:
            if code_a == code_b:
                matrix[code_a][code_b] = 1.0
            else:
                corr = _pearson_corr(returns_map[code_a], returns_map[code_b])
                matrix[code_a][code_b] = corr  # 可能是 None

    # 平均两两相关性（仅上三角，避免重复）
    pair_corrs = []
    for i, ca in enumerate(valid_codes):
        for cb in valid_codes[i + 1 :]:
            v = matrix.get(ca, {}).get(cb)
            if v is not None:
                pair_corrs.append(v)

    avg_pairwise = round(statistics.mean(pair_corrs), 4) if pair_corrs else None

    # 高相关对
    high_pairs = []
    for i, ca in enumerate(valid_codes):
        for cb in valid_codes[i + 1 :]:
            v = matrix.get(ca, {}).get(cb)
            if v is not None and abs(v) >= high_corr_threshold:
                high_pairs.append([ca, cb, v])

    # 解读
    interpretation = _interpret_matrix(avg_pairwise, high_pairs, len(valid_codes))

    return {
        "codes": all_codes,
        "window": window,
        "matrix": matrix,
        "avg_pairwise_corr": avg_pairwise,
        "high_corr_pairs": high_pairs,
        "interpretation": interpretation,
        "data_quality": {"degraded_fields": degraded},
    }


def _interpret_matrix(avg: float | None, high_pairs: list, n_codes: int) -> str:
    """组合相关性矩阵解读。"""
    if avg is None:
        return "数据不足"
    if n_codes <= 1:
        return "持仓数量不足（仅 1 只或仅基准）"

    # 高相关对占比
    high_pair_pct = len(high_pairs) / max(n_codes * (n_codes - 1) / 2, 1)

    if avg >= 0.7 or high_pair_pct >= 0.5:
        return f"⚠️ 高度集中（avg={avg:.2f}，{len(high_pairs)} 对高相关），伪分散风险"
    if avg >= 0.5:
        return f"🟡 中度集中（avg={avg:.2f}），板块暴露较多"
    if avg >= 0.3:
        return f"🟢 相关性适中（avg={avg:.2f}），分散度可接受"
    return f"✅ 高度分散（avg={avg:.2f}），组合对冲效果好"


# ═══════════════════════════════════════════════════════════════
# 个股 vs 组合相关性
# ═══════════════════════════════════════════════════════════════


def compute_stock_vs_portfolio(
    stock_code: str,
    portfolio_codes: list[str],
    window: int = 60,
) -> dict | None:
    """计算单只股票 vs 持仓组合的相关性均值（市场环境锚定的"加入组合风险"维度）。

    Args:
        stock_code: 个股代码
        portfolio_codes: 持仓代码列表
        window: K 线窗口

    Returns:
        dict:
          {
            "stock_code": "sh600519",
            "window": 60,
            "n_portfolio_codes": 5,
            "vs_portfolio_avg_corr": 0.55,    # 与持仓组合的相关性均值
            "diversification_benefit": "中",   # 高 (>0.7低 / 0.4-0.7中 / <0.4高)
            "data_quality": {"degraded_fields": [...]}
          }
    """
    if not portfolio_codes:
        return {
            "stock_code": stock_code,
            "window": window,
            "n_portfolio_codes": 0,
            "vs_portfolio_avg_corr": None,
            "diversification_benefit": "unknown",
            "note": "持仓为空，无法计算 vs_portfolio",
            "data_quality": {"degraded_fields": []},
        }

    # 拉个股 + 持仓的收益率
    stock_returns = _load_returns(stock_code, window)
    if stock_returns is None:
        return {
            "stock_code": stock_code,
            "window": window,
            "n_portfolio_codes": len(portfolio_codes),
            "vs_portfolio_avg_corr": None,
            "diversification_benefit": "unknown",
            "data_quality": {"degraded_fields": ["stock_vs_portfolio.stock_kline"]},
        }

    portfolio_returns = {}
    degraded = []
    for code in portfolio_codes:
        r = _load_returns(code, window)
        if r is None:
            degraded.append(f"stock_vs_portfolio.{code}")
            continue
        portfolio_returns[code] = r

    if not portfolio_returns:
        return {
            "stock_code": stock_code,
            "window": window,
            "n_portfolio_codes": len(portfolio_codes),
            "vs_portfolio_avg_corr": None,
            "diversification_benefit": "unknown",
            "data_quality": {"degraded_fields": degraded},
        }

    # 计算个股 vs 每个持仓的相关性
    corrs = []
    for code, r_p in portfolio_returns.items():
        c = _pearson_corr(stock_returns, r_p)
        if c is not None:
            corrs.append(c)

    if not corrs:
        return {
            "stock_code": stock_code,
            "window": window,
            "n_portfolio_codes": len(portfolio_codes),
            "vs_portfolio_avg_corr": None,
            "diversification_benefit": "unknown",
            "data_quality": {"degraded_fields": degraded},
        }

    avg_corr = round(statistics.mean(corrs), 4)
    benefit = _interpret_diversification(avg_corr)

    return {
        "stock_code": stock_code,
        "window": window,
        "n_portfolio_codes": len(portfolio_returns),
        "vs_portfolio_avg_corr": avg_corr,
        "diversification_benefit": benefit,
        "data_quality": {"degraded_fields": degraded},
    }


def _interpret_diversification(avg_corr: float) -> str:
    """分散化收益解读。"""
    if avg_corr >= 0.7:
        return "低（个股与组合高度相关，加入组合无分散价值）"
    if avg_corr >= 0.4:
        return "中（个股与组合相关性适中，部分分散价值）"
    return "高（个股与组合低相关，加入组合有显著分散价值）"


# ═══════════════════════════════════════════════════════════════
# Portfolio 集成（业务封装层）
# ═══════════════════════════════════════════════════════════════


def get_portfolio_codes() -> list[str]:
    """从 PortfolioManager 拉持仓代码列表。失败返回空 list。"""
    try:
        from portfolio.manager import PortfolioManager

        pm = PortfolioManager()
        positions = pm.get_positions()
        return [p["code"] for p in positions if p.get("code")]
    except Exception as e:
        logger.warning("PortfolioManager.get_positions 失败: %s", e)
        return []


def compute_full_portfolio_correlation(
    stock_code: str | None = None,
    window: int = 60,
) -> dict:
    """业务封装：从 PortfolioManager 拉持仓 + 跑矩阵 + 个股 vs 组合。

    Args:
        stock_code: 可选；提供时计算 vs_portfolio
        window: K 线窗口

    Returns:
        dict:
          {
            "portfolio_empty": False,
            "portfolio_codes": ["sh600519", ...],
            "matrix": {...},
            "avg_pairwise_corr": 0.42,
            "high_corr_pairs": [...],
            "vs_portfolio": {...} or None,
            "interpretation": "...",
            "data_quality": {...}
          }
        portfolio_empty 时 matrix=None。
    """
    portfolio_codes = get_portfolio_codes()
    if not portfolio_codes:
        return {
            "portfolio_empty": True,
            "portfolio_codes": [],
            "matrix": None,
            "avg_pairwise_corr": None,
            "high_corr_pairs": [],
            "vs_portfolio": None,
            "interpretation": "无持仓，跳过组合相关性分析（先在 /portfolio 建仓）",
            "data_quality": {"degraded_fields": []},
        }

    # 矩阵（含候选个股 + 基准）
    all_codes = portfolio_codes.copy()
    if stock_code and stock_code not in all_codes:
        all_codes.append(stock_code)

    matrix_payload = compute_correlation_matrix(
        codes=all_codes,
        index_code="sh000300",
        window=window,
    )

    # 个股 vs 组合
    vs_portfolio = None
    if stock_code:
        vs_portfolio = compute_stock_vs_portfolio(
            stock_code, portfolio_codes, window=window
        )

    return {
        "portfolio_empty": False,
        "portfolio_codes": portfolio_codes,
        "matrix": matrix_payload.get("matrix") if matrix_payload else None,
        "avg_pairwise_corr": (
            matrix_payload.get("avg_pairwise_corr") if matrix_payload else None
        ),
        "high_corr_pairs": (
            matrix_payload.get("high_corr_pairs") if matrix_payload else []
        ),
        "vs_portfolio": vs_portfolio,
        "interpretation": (
            matrix_payload.get("interpretation") if matrix_payload else "无数据"
        ),
        "data_quality": (
            matrix_payload.get("data_quality")
            if matrix_payload
            else {"degraded_fields": ["portfolio_correlation"]}
        ),
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="组合相关性矩阵")
    parser.add_argument("--stock", default=None, help="候选个股（计算 vs_portfolio）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--window", type=int, default=60, help="K 线窗口")
    parser.add_argument("--list", action="store_true", help="仅列出持仓代码")
    args = parser.parse_args()

    if args.list:
        codes = get_portfolio_codes()
        print(f"持仓代码 ({len(codes)}): {codes}")
        return

    result = compute_full_portfolio_correlation(
        stock_code=args.stock, window=args.window
    )
    if args.json:
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"📊 组合相关性分析 (window={args.window})")
        print("=" * 60)
        if result["portfolio_empty"]:
            print(f"  ⚠️ {result['interpretation']}")
            return

        print(f"  持仓数: {len(result['portfolio_codes'])}")
        for c in result["portfolio_codes"]:
            print(f"    - {c}")
        print()
        m = result["matrix"]
        if m:
            print(f"  平均两两相关性: {result['avg_pairwise_corr']}")
            print(f"  高相关对 (>=0.7): {len(result['high_corr_pairs'])} 对")
            for pair in result["high_corr_pairs"][:5]:
                print(f"    {pair[0]} <-> {pair[1]}: {pair[2]}")
        print(f"  解读: {result['interpretation']}")
        vp = result.get("vs_portfolio")
        if vp:
            print()
            print(f"  vs_portfolio ({vp['stock_code']}):")
            print(f"    平均相关性: {vp['vs_portfolio_avg_corr']}")
            print(f"    分散化收益: {vp['diversification_benefit']}")

        dq = result.get("data_quality", {}).get("degraded_fields", [])
        if dq:
            print(f"\n  ⚠️ 降级: {', '.join(dq)}")


if __name__ == "__main__":
    main()

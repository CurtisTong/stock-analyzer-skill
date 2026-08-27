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
from sector_etf_strength import (  # noqa: E402 行业重叠复用
    _load_stock_sector_map,
    _SECTOR_TO_ETF_PROXY,
)

# 模块级缓存 stock_sector_map（避免多次 IO）
_SSM_CACHE: dict = {"data": None}


def _get_stock_sector_map() -> dict:
    """加载股票→行业映射（带模块级缓存）。"""
    if _SSM_CACHE["data"] is None:
        _SSM_CACHE["data"] = _load_stock_sector_map()
    return _SSM_CACHE["data"]


def _industry_to_etf_proxy(industry: str) -> str | None:
    """行业名 → ETF 代理代码（合并 stock_sector_map.industry_proxy 与内置映射）。"""
    if not industry:
        return None
    ssm = _get_stock_sector_map()
    proxy = ssm.get("industry_proxy", {}).get(industry)
    if proxy:
        return proxy
    return _SECTOR_TO_ETF_PROXY.get(industry)


def _industry_of_code(code: str) -> tuple[str | None, str | None]:
    """股票代码 → (行业名, ETF 代理代码)（基于 stock_sector_map）。"""
    ssm = _get_stock_sector_map()
    industry = ssm.get("stocks", {}).get(code)
    if not industry:
        return None, None
    return industry, _industry_to_etf_proxy(industry)


# ═══════════════════════════════════════════════════════════════
# 行业重叠（候选股与持仓的行业集中度增量）
# ═══════════════════════════════════════════════════════════════


def compute_industry_overlap(
    stock_code: str,
    portfolio_positions: list,
    industry_limit: float = 0.30,
) -> dict:
    """计算候选股与持仓的行业重叠率。

    口径：候选股与各持仓都映射到"行业名 → ETF 代理代码"，用 ETF 代理对齐判断
    是否同行业（覆盖不同细分同大类的场景，如"汽车电子"与"智能汽车"都映射到
    智能汽车 ETF）。映射缺失的持仓用 position.industry/tags 名称兜底。

    Args:
        stock_code: 候选股代码
        portfolio_positions: 持仓列表（含 code/name/quantity/cost/tags/industry）
        industry_limit: 行业集中度上限（默认 30%，与 check_concentration 一致）

    Returns:
        dict:
          {
            "stock_code", "stock_industry", "stock_etf_proxy",
            "overlap_positions": [{code, name, industry, pct}],  # 同行业持仓
            "overlap_pct": 12.3,     # 重叠行业持仓占组合成本比例 %
            "overlap_count": 2,
            "concentration_warning": False,  # 重叠行业占比 > 20% 提示
            "message": "...",
          }
        候选股无法归属行业时返回 stock_industry=None + message 说明。
    """
    stock_industry, stock_proxy = _industry_of_code(stock_code)

    # 组合成本总额（分母）
    total_cost = sum(
        (p.get("cost") or 0) * (p.get("quantity") or 0) for p in portfolio_positions
    )

    overlap_positions = []
    for p in portfolio_positions:
        code = p.get("code")
        if not code or code == stock_code:
            continue
        ind, proxy = _industry_of_code(code)
        if not ind or not proxy:
            # 映射缺失兜底：用录入的 industry/tags 名称比对
            ind = ind or p.get("industry") or (p.get("tags") or [None])[0]
            proxy = _industry_to_etf_proxy(ind) if ind else None
        same = False
        if stock_proxy and proxy:
            same = stock_proxy == proxy
        elif stock_industry and ind:
            same = stock_industry == ind
        if not same:
            continue
        value = (p.get("cost") or 0) * (p.get("quantity") or 0)
        pct = (value / total_cost * 100) if total_cost > 0 else 0.0
        overlap_positions.append(
            {
                "code": code,
                "name": p.get("name") or "",
                "industry": ind or "未知",
                "pct": round(pct, 1),
            }
        )

    overlap_pct = round(sum(o["pct"] for o in overlap_positions), 1)
    warning = overlap_pct > industry_limit * 100 * 2 / 3  # >20% 即提示
    if not stock_industry:
        message = (
            f"候选股 {stock_code} 行业归属未知（不在 stock_sector_map），无法判断重叠"
        )
    elif not overlap_positions:
        message = f"候选股行业（{stock_industry}）与现有持仓无重叠，分散性良好"
    else:
        names = "、".join(
            f"{o['name'] or o['code']}({o['pct']}%)" for o in overlap_positions
        )
        action = (
            f"⚠️ 注意：重叠行业占组合 {overlap_pct}%，建议候选股新增仓位不超过 "
            f"{max(0, round(industry_limit * 100 - overlap_pct, 1))}% 以免触发 30% 硬约束"
            if warning
            else f"重叠行业占组合 {overlap_pct}%，仍处 30% 约束内"
        )
        message = f"候选股行业（{stock_industry}）与持仓 {len(overlap_positions)} 只重叠：{names}；{action}"

    return {
        "stock_code": stock_code,
        "stock_industry": stock_industry,
        "stock_etf_proxy": stock_proxy,
        "overlap_positions": overlap_positions,
        "overlap_pct": overlap_pct,
        "overlap_count": len(overlap_positions),
        "concentration_warning": warning,
        "message": message,
    }


# ═══════════════════════════════════════════════════════════════
# 相关系数计算
# ═══════════════════════════════════════════════════════════════

# 窗口声明（每次输出相关性都附带，避免用户把历史窗口当长期稳定）
WINDOW_NOTICE = "相关性基于有限历史窗口，窗口 ≠ 长期稳定，行情切换或极端行情（如熊市）下相关性普遍上升，负相关可能反转，勿据此过度外推"


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


def _corr_detailed(x: list, y: list) -> dict | None:
    """相关系数 + 显著性（低 R² + 负相关 ≠ 真正分散）。

    单变量回归中 R² = corr²；显著性用近似 t 检验（H0: ρ=0）：
        t = corr * sqrt((n - 2) / (1 - corr²))，|t| > 2 视为显著（α≈0.05）

    Returns:
        dict: {corr, r_squared, n, t_stat, significant}
        不可算返回 None。
    """
    corr = _pearson_corr(x, y)
    if corr is None:
        return None
    n = min(len(x), len(y))
    denom = 1 - corr * corr
    if denom <= 0:
        t_stat = None  # 完美相关
        significant = True
    else:
        t_stat = corr * (max(n - 2, 1) / denom) ** 0.5
        significant = t_stat is not None and abs(t_stat) > 2.0
    return {
        "corr": corr,
        "r_squared": round(corr * corr, 4),
        "n": n,
        "t_stat": round(t_stat, 3) if t_stat is not None else None,
        "significant": significant,
    }


def _half_window_stability(valid_codes: list[str], returns_map: dict) -> dict | None:
    """相关性稳定性（双半窗口对比，不额外拉数据）。

    将收益率序列切成前半段 / 后半段，分别计算每个两两对的相关系数，
    统计：符号翻转对数（supply 至少一个 |corr| >= 0.3）、最大变化幅度。

    Returns:
        dict | None:
          {n_pairs, sign_flips, max_delta, stable}
        可算对太少返回 None。
    """
    flips = 0
    deltas = []
    n_pairs = 0
    for i, ca in enumerate(valid_codes):
        ra = returns_map.get(ca)
        if ra is None:
            continue
        for cb in valid_codes[i + 1 :]:
            rb = returns_map.get(cb)
            if rb is None:
                continue
            n = min(len(ra), len(rb))
            if n < 20:
                continue
            half = n // 2
            c_full = _pearson_corr(ra[:n], rb[:n])
            c_half = _pearson_corr(ra[half:], rb[half:])
            if c_full is None or c_half is None:
                continue
            n_pairs += 1
            deltas.append(abs(c_full - c_half))
            if c_full * c_half < 0 and (abs(c_full) >= 0.3 or abs(c_half) >= 0.3):
                flips += 1

    if n_pairs == 0:
        return None
    max_delta = round(max(deltas), 4)
    flip_ratio = flips / n_pairs
    stable = flip_ratio < 0.2 and max_delta < 0.5
    return {
        "n_pairs": n_pairs,
        "sign_flips": flips,
        "flip_ratio": round(flip_ratio, 4),
        "max_delta": max_delta,
        "stable": stable,
    }


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
        "window_notice": WINDOW_NOTICE,
        "stability": _half_window_stability(valid_codes, returns_map),
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

    # 计算个股 vs 每个持仓的相关性（含显著性，）
    corrs = []
    significant_neg_pairs = 0
    neg_pairs = 0
    for code, r_p in portfolio_returns.items():
        detail = _corr_detailed(stock_returns, r_p)
        if detail is None:
            continue
        corrs.append(detail["corr"])
        if detail["corr"] < 0:
            neg_pairs += 1
            if detail["significant"]:
                significant_neg_pairs += 1

    if not corrs:
        return {
            "stock_code": stock_code,
            "window": window,
            "n_portfolio_codes": len(portfolio_returns),
            "vs_portfolio_avg_corr": None,
            "diversification_benefit": "unknown",
            "window_notice": WINDOW_NOTICE,
            "data_quality": {"degraded_fields": degraded},
        }

    avg_corr = round(statistics.mean(corrs), 4)
    # 负相关对中显著比例（显著负相关才有分散价值；低 R² 负相关多为噪声）
    neg_significant_ratio = significant_neg_pairs / neg_pairs if neg_pairs > 0 else 0.0
    benefit = _interpret_diversification(avg_corr, neg_significant_ratio)
    corr_confidence = _corr_confidence(avg_corr, neg_significant_ratio)

    return {
        "stock_code": stock_code,
        "window": window,
        "n_portfolio_codes": len(portfolio_returns),
        "vs_portfolio_avg_corr": avg_corr,
        "diversification_benefit": benefit,
        "negative_pairs": neg_pairs,
        "significant_negative_pairs": significant_neg_pairs,
        "neg_significant_ratio": round(neg_significant_ratio, 4),
        "corr_confidence": corr_confidence,
        "window_notice": WINDOW_NOTICE,
        "data_quality": {"degraded_fields": degraded},
    }


def _interpret_diversification(avg_corr: float, neg_significant_ratio: float) -> str:
    """分散化收益解读（低 R² 负相关 ≠ 真正分散）。"""
    if avg_corr >= 0.7:
        return "低（个股与组合高度相关，加入组合无分散价值）"
    if avg_corr >= 0.4:
        return "中（个股与组合相关性适中，部分分散价值）"
    if avg_corr >= 0:
        return "中偏弱（弱正相关，分散价值有限）"
    if avg_corr < -0.3 and neg_significant_ratio >= 0.5:
        return "高（显著负相关，加入组合有显著分散价值）"
    if avg_corr < -0.3:
        return (
            f"中（负相关较强，但显著性不足（{neg_significant_ratio:.0%} 通过检验），"
            "负相关可能不稳定）"
        )
    return (
        f"高存疑（负相关但 |corr|<0.3，低 R² 下可能为噪声，"
        f"仅 {neg_significant_ratio:.0%} 通过显著性检验，分散价值有限）"
    )


def _corr_confidence(avg_corr: float, neg_significant_ratio: float) -> str:
    """相关性结论置信度。"""
    if avg_corr is None:
        return "低"
    if avg_corr < 0 and neg_significant_ratio >= 0.5 and abs(avg_corr) >= 0.3:
        return "高"
    if abs(avg_corr) >= 0.5:
        return "中"
    return "低"


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


def get_positions_full() -> list:
    """从 PortfolioManager 拉完整持仓（含 cost/quantity/tags/industry）。失败返回空 list。"""
    try:
        from portfolio.manager import PortfolioManager

        pm = PortfolioManager()
        return pm.get_positions()
    except Exception as e:
        logger.warning("PortfolioManager.get_positions(full) 失败: %s", e)
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
            "window_notice": WINDOW_NOTICE,
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
    industry_overlap = None
    if stock_code:
        vs_portfolio = compute_stock_vs_portfolio(
            stock_code, portfolio_codes, window=window
        )
        # 候选股与持仓的行业重叠率
        try:
            industry_overlap = compute_industry_overlap(
                stock_code,
                get_positions_full(),
            )
        except Exception as e:  # noqa: BLE001 — 行业重叠失败不阻塞主链路
            logger.debug("compute_industry_overlap 失败: %s", e)
            industry_overlap = {
                "stock_code": stock_code,
                "message": "行业重叠计算失败（数据不足）",
            }

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
        "stability": matrix_payload.get("stability") if matrix_payload else None,
        "vs_portfolio": vs_portfolio,
        "industry_overlap": industry_overlap,
        "interpretation": (
            matrix_payload.get("interpretation") if matrix_payload else "无数据"
        ),
        "window_notice": WINDOW_NOTICE,
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
        st = result.get("stability")
        if st:
            print(
                f"  相关性稳定性: {'稳定' if st['stable'] else '⚠️ 不稳定'} "
                f"（{st['sign_flips']}/{st['n_pairs']} 对后半段符号翻转，最大变化 {st['max_delta']}）"
            )
        vp = result.get("vs_portfolio")
        if vp:
            print()
            print(f"  vs_portfolio ({vp['stock_code']}):")
            print(f"    平均相关性: {vp['vs_portfolio_avg_corr']}")
            print(f"    分散化收益: {vp['diversification_benefit']}")
            if vp.get("corr_confidence"):
                print(f"    结论置信度: {vp['corr_confidence']}")
        ov = result.get("industry_overlap")
        if ov:
            print()
            print(f"  行业重叠 ({ov.get('stock_industry') or '未知'}):")
            print(f"    {ov.get('message', '')}")
            if ov.get("concentration_warning"):
                print("    ⚠️ 需控制新增仓位，避免触发行业 30% 硬约束")
        print()
        print(f"  ⚠️ 窗口声明: {result.get('window_notice', WINDOW_NOTICE)}")

        dq = result.get("data_quality", {}).get("degraded_fields", [])
        if dq:
            print(f"\n  ⚠️ 降级: {', '.join(dq)}")


if __name__ == "__main__":
    main()

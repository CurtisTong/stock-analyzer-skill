"""Brinson 组合归因模型。

经典 Brinson 模型将组合超额收益归因为三类效应：
- 配置效应 (Allocation Effect)：低配/超配基准行业带来的贡献
- 选择效应 (Selection Effect)：行业内个股选择能力
- 交互效应 (Interaction Effect)：配置与选择的协同作用

Brinson 公式：
- 配置效应 = (w_p - w_b) × (r_b - R_b)
- 选择效应 = w_b × (r_p - r_b)
- 交互效应 = (w_p - w_b) × (r_p - r_b)
- 总超额 = 配置 + 选择 + 交互

其中：
- w_p: 组合行业权重
- w_b: 基准行业权重
- r_p: 组合行业收益率
- r_b: 基准行业收益率
- R_b: 基准总收益率

v2.4.0 新增。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BrinsonSectorResult:
    """单行业 Brinson 归因结果。"""

    sector: str = ""
    portfolio_weight: float = 0.0  # 组合行业权重（小数）
    benchmark_weight: float = 0.0  # 基准行业权重
    portfolio_return: float = 0.0  # 组合行业收益率
    benchmark_return: float = 0.0  # 基准行业收益率
    allocation_effect: float = 0.0  # 配置效应（百分点）
    selection_effect: float = 0.0  # 选择效应
    interaction_effect: float = 0.0  # 交互效应
    total_effect: float = 0.0  # 总效应 = 三者之和

    def to_dict(self) -> dict:
        return {
            "sector": self.sector,
            "portfolio_weight": round(self.portfolio_weight * 100, 2),
            "benchmark_weight": round(self.benchmark_weight * 100, 2),
            "portfolio_return_pct": round(self.portfolio_return * 100, 2),
            "benchmark_return_pct": round(self.benchmark_return * 100, 2),
            "allocation_pct": round(self.allocation_effect * 100, 3),
            "selection_pct": round(self.selection_effect * 100, 3),
            "interaction_pct": round(self.interaction_effect * 100, 3),
            "total_pct": round(self.total_effect * 100, 3),
        }


@dataclass
class BrinsonResult:
    """Brinson 归因汇总。"""

    sectors: List[BrinsonSectorResult] = field(default_factory=list)
    total_allocation: float = 0.0
    total_selection: float = 0.0
    total_interaction: float = 0.0
    total_excess_return: float = 0.0
    portfolio_return: float = 0.0
    benchmark_return: float = 0.0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "portfolio_return_pct": round(self.portfolio_return * 100, 2),
                "benchmark_return_pct": round(self.benchmark_return * 100, 2),
                "excess_return_pct": round(self.total_excess_return * 100, 2),
                "allocation_pct": round(self.total_allocation * 100, 3),
                "selection_pct": round(self.total_selection * 100, 3),
                "interaction_pct": round(self.total_interaction * 100, 3),
            },
            "sectors": [s.to_dict() for s in self.sectors],
        }


def brinson_attribution(
    portfolio_sector_returns: Dict[str, float],
    benchmark_sector_returns: Dict[str, float],
    portfolio_sector_weights: Dict[str, float],
    benchmark_sector_weights: Dict[str, float],
    period_return: float = None,
) -> BrinsonResult:
    """计算 Brinson 归因。

    Args:
        portfolio_sector_returns: {"科技": 0.15, "消费": 0.08, ...}
        benchmark_sector_returns: {"科技": 0.10, "消费": 0.12, ...}
        portfolio_sector_weights: {"科技": 0.3, "消费": 0.2, ...}（小数，总和为 1）
        benchmark_sector_weights: {"科技": 0.25, "消费": 0.25, ...}
        period_return: 总回报率（None 则从行业权重×收益率自动计算）

    Returns:
        BrinsonResult 包含每个行业的三种效应及汇总
    """
    # 全部行业并集
    sectors = set(portfolio_sector_returns) | set(benchmark_sector_returns)

    results = []
    total_allocation = 0.0
    total_selection = 0.0
    total_interaction = 0.0

    # 基准总收益
    if period_return is None:
        benchmark_return = sum(
            benchmark_sector_weights.get(s, 0) * benchmark_sector_returns.get(s, 0)
            for s in sectors
        )
    else:
        benchmark_return = period_return

    for sector in sectors:
        wp = portfolio_sector_weights.get(sector, 0)  # 组合权重
        wb = benchmark_sector_weights.get(sector, 0)  # 基准权重
        rp = portfolio_sector_returns.get(sector, 0)  # 组合行业收益
        rb = benchmark_sector_returns.get(sector, 0)  # 基准行业收益

        # Brinson 三大效应
        allocation = (wp - wb) * (rb - benchmark_return)
        selection = wb * (rp - rb)
        interaction = (wp - wb) * (rp - rb)
        total = allocation + selection + interaction

        results.append(
            BrinsonSectorResult(
                sector=sector,
                portfolio_weight=wp,
                benchmark_weight=wb,
                portfolio_return=rp,
                benchmark_return=rb,
                allocation_effect=allocation,
                selection_effect=selection,
                interaction_effect=interaction,
                total_effect=total,
            )
        )

        total_allocation += allocation
        total_selection += selection
        total_interaction += interaction

    # 组合总收益
    portfolio_return = sum(
        portfolio_sector_weights.get(s, 0) * portfolio_sector_returns.get(s, 0)
        for s in sectors
    )

    return BrinsonResult(
        sectors=results,
        total_allocation=total_allocation,
        total_selection=total_selection,
        total_interaction=total_interaction,
        total_excess_return=portfolio_return - benchmark_return,
        portfolio_return=portfolio_return,
        benchmark_return=benchmark_return,
    )


def brinson_from_holdings(
    positions: List[dict],
    quotes: Dict[str, float],
    benchmark_sector_weights: Dict[str, float] = None,
    benchmark_sector_returns: Dict[str, float] = None,
    period: str = "1M",
) -> BrinsonResult:
    """从持仓快速构造 Brinson 归因（使用默认基准：沪深300）。

    Args:
        positions: 持仓列表 [{code, name, cost, quantity, sector?}]
        quotes: {code: current_price} 行情
        benchmark_sector_weights/returns: 沪深300行业权重和收益率（None 时用默认估值）
        period: 期间（1M/3M/6M/1Y）
    """
    if not positions:
        return BrinsonResult()

    # 简化版：假设所有持仓属于"未指定"行业，使用沪深300做基准
    # 真实场景应从 quotes/tags 中提取 industry
    total_value = sum(
        quotes.get(p["code"], p.get("cost", 0)) * p.get("quantity", 0)
        for p in positions
    )
    if total_value <= 0:
        return BrinsonResult()

    # 持仓行业权重（按 tags 分组，缺失归"未分类"）
    portfolio_weights: Dict[str, float] = {}
    portfolio_returns: Dict[str, float] = {}

    for p in positions:
        code = p["code"]
        qty = p.get("quantity", 0)
        cost = p.get("cost", 0)
        current = quotes.get(code, cost)
        if qty <= 0:
            continue
        weight = current * qty / total_value
        ret = (current / cost - 1) if cost > 0 else 0
        # 用 tags[0] 或 "未分类"
        sector = (p.get("tags") or ["未分类"])[0]
        portfolio_weights[sector] = portfolio_weights.get(sector, 0) + weight
        # 加权平均收益
        old_w = portfolio_weights[sector] - weight
        old_r = portfolio_returns.get(sector, 0)
        portfolio_returns[sector] = (old_w * old_r + weight * ret) / portfolio_weights[sector]

    # 默认沪深300行业分布（中证指数官网近似权重）
    if benchmark_sector_weights is None:
        benchmark_sector_weights = {
            "金融": 0.22,
            "消费": 0.18,
            "信息技术": 0.15,
            "工业": 0.12,
            "医药": 0.10,
            "能源": 0.06,
            "材料": 0.07,
            "电信": 0.04,
            "公用": 0.04,
            "未分类": 0.02,
        }
    if benchmark_sector_returns is None:
        # 假设基准行业平均收益 0.05（5%）
        benchmark_sector_returns = {
            sector: 0.05 for sector in benchmark_sector_weights
        }

    # 补全 portfolio 中缺行业基准的（设为 0 权重）
    for sector in portfolio_weights:
        benchmark_sector_weights.setdefault(sector, 0)
        benchmark_sector_returns.setdefault(sector, 0.05)

    return brinson_attribution(
        portfolio_sector_returns=portfolio_returns,
        benchmark_sector_returns=benchmark_sector_returns,
        portfolio_sector_weights=portfolio_weights,
        benchmark_sector_weights=benchmark_sector_weights,
    )


def format_brinson_report(result: BrinsonResult) -> str:
    """格式化 Brinson 归因报告。"""
    if not result.sectors:
        return "⚠️ 持仓数据为空，无法生成归因报告"

    lines = []
    s = result.to_dict()["summary"]
    lines.append("## 📊 Brinson 归因报告")
    lines.append("")
    lines.append(f"组合收益: {s['portfolio_return_pct']:.2f}%")
    lines.append(f"基准收益: {s['benchmark_return_pct']:.2f}%")
    lines.append(f"超额收益: {s['excess_return_pct']:+.2f}%")
    lines.append("")
    lines.append("### 三大效应归因")
    lines.append(
        f"- 配置效应: {s['allocation_pct']:+.2f}% "
        f"({'✅ 行业配置贡献' if s['allocation_pct'] > 0 else '⚠️ 行业配置拖累'})"
    )
    lines.append(
        f"- 选择效应: {s['selection_pct']:+.2f}% "
        f"({'✅ 选股贡献' if s['selection_pct'] > 0 else '⚠️ 选股拖累'})"
    )
    lines.append(
        f"- 交互效应: {s['interaction_pct']:+.2f}%"
    )
    lines.append("")

    # 行业明细
    lines.append("### 行业明细")
    lines.append("| 行业 | 组合权重 | 基准权重 | 组合收益 | 基准收益 | 配置 | 选择 | 交互 | 总效应 |")
    lines.append("|------|---------|---------|---------|---------|------|------|------|--------|")
    for s in result.sectors:
        d = s.to_dict()
        lines.append(
            f"| {d['sector']} | {d['portfolio_weight']:.1f}% | "
            f"{d['benchmark_weight']:.1f}% | {d['portfolio_return_pct']:+.2f}% | "
            f"{d['benchmark_return_pct']:+.2f}% | {d['allocation_pct']:+.3f}% | "
            f"{d['selection_pct']:+.3f}% | {d['interaction_pct']:+.3f}% | "
            f"{d['total_pct']:+.3f}% |"
        )

    return "\n".join(lines)

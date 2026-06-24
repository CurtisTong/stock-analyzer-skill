"""持仓绩效归因分析：个股贡献、行业贡献、风险指标。"""

from dataclasses import dataclass
from common import to_float


@dataclass
class PerformanceMetrics:
    """绩效指标。"""

    total_return: float = 0.0  # 总收益率%
    annualized_return: float = 0.0  # 年化收益率%
    max_drawdown: float = 0.0  # 最大回撤%
    win_rate: float = 0.0  # 胜率%
    sharpe_ratio: float = 0.0  # 夏普比率
    total_profit: float = 0.0  # 总盈亏（元）
    position_count: int = 0  # 持仓数量

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PositionContribution:
    """个股贡献。"""

    code: str = ""
    name: str = ""
    cost: float = 0.0
    current_price: float = 0.0
    quantity: int = 0
    market_value: float = 0.0  # 当前市值
    profit: float = 0.0  # 盈亏金额
    profit_pct: float = 0.0  # 盈亏比例%
    weight: float = 0.0  # 持仓权重%
    contribution: float = 0.0  # 对组合的贡献%

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def calculate_position_contribution(
    positions: list,
    quotes: dict,
) -> list[PositionContribution]:
    """计算各持仓的贡献。

    Args:
        positions: 持仓列表 [{code, name, cost, quantity}]
        quotes: 行情数据 {code: {price, ...}}
    """
    contributions = []
    total_market_value = 0

    # 先计算总市值
    for pos in positions:
        code = pos.get("code", "")
        quote = quotes.get(code, {})
        price = to_float(quote.get("price", 0))
        quantity = pos.get("quantity", 0)
        total_market_value += price * quantity

    # 计算各持仓贡献
    for pos in positions:
        code = pos.get("code", "")
        name = pos.get("name", "")
        cost = to_float(pos.get("cost", 0))
        quantity = pos.get("quantity", 0)
        quote = quotes.get(code, {})
        price = to_float(quote.get("price", 0))

        market_value = price * quantity
        cost_value = cost * quantity
        profit = market_value - cost_value
        profit_pct = (price / cost - 1) * 100 if cost > 0 else 0
        weight = (
            (market_value / total_market_value * 100) if total_market_value > 0 else 0
        )
        contribution = (
            (profit / total_market_value * 100) if total_market_value > 0 else 0
        )

        contributions.append(
            PositionContribution(
                code=code,
                name=name,
                cost=cost,
                current_price=price,
                quantity=quantity,
                market_value=round(market_value, 2),
                profit=round(profit, 2),
                profit_pct=round(profit_pct, 2),
                weight=round(weight, 2),
                contribution=round(contribution, 2),
            )
        )

    # 按贡献排序
    contributions.sort(key=lambda c: c.contribution, reverse=True)
    return contributions


def calculate_portfolio_metrics(
    positions: list,
    quotes: dict,
    kline_data: dict = None,
) -> PerformanceMetrics:
    """计算组合整体绩效指标。

    Args:
        positions: 持仓列表
        quotes: 行情数据
        kline_data: 历史 K 线数据（用于计算回撤等）
    """
    contributions = calculate_position_contribution(positions, quotes)

    total_market_value = sum(c.market_value for c in contributions)
    total_cost = sum(c.cost * c.quantity for c in contributions)
    total_profit = total_market_value - total_cost
    total_return = (total_market_value / total_cost - 1) * 100 if total_cost > 0 else 0

    # 胜率
    winning = sum(1 for c in contributions if c.profit > 0)
    win_rate = (winning / len(contributions) * 100) if contributions else 0

    # 最大回撤（如果有 K 线数据）
    max_drawdown = 0.0
    if kline_data:
        max_drawdown = _calculate_max_drawdown(positions, kline_data, quotes)

    return PerformanceMetrics(
        total_return=round(total_return, 2),
        max_drawdown=round(max_drawdown, 2),
        win_rate=round(win_rate, 1),
        total_profit=round(total_profit, 2),
        position_count=len(positions),
    )


def _calculate_max_drawdown(positions: list, kline_data: dict, quotes: dict) -> float:
    """基于历史 K 线计算组合最大回撤（按日期对齐）。"""
    if not kline_data:
        return 0.0

    # 按日期合并各持仓市值：NAV[date] = Σ(close_i × qty_i)
    nav_by_date: dict[str, float] = {}
    for code, bars in kline_data.items():
        if not bars:
            continue
        pos = next((p for p in positions if p.get("code") == code), None)
        if not pos:
            continue
        quantity = pos.get("quantity", 0)
        if quantity <= 0:
            continue
        for bar in bars:
            day = bar.day if hasattr(bar, "day") else bar.get("day", "")
            close = bar.close if hasattr(bar, "close") else bar.get("close", 0)
            if day:
                nav_by_date[day] = nav_by_date.get(day, 0) + close * quantity

    if len(nav_by_date) < 2:
        return 0.0

    # 按日期排序后计算最大回撤
    nav_series = [nav_by_date[d] for d in sorted(nav_by_date)]
    peak = nav_series[0]
    max_dd = 0.0
    for nav in nav_series:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return max_dd


def format_performance_report(
    metrics: PerformanceMetrics,
    contributions: list[PositionContribution],
) -> str:
    """格式化绩效报告。"""
    lines = []
    lines.append("## 持仓绩效报告\n")

    # 整体指标
    lines.append("### 整体指标")
    lines.append(f"- 总收益率: **{metrics.total_return}%**")
    lines.append(f"- 总盈亏: **{metrics.total_profit:,.0f} 元**")
    lines.append(f"- 最大回撤: {metrics.max_drawdown}%")
    lines.append(f"- 胜率: {metrics.win_rate}%")
    lines.append(f"- 持仓数量: {metrics.position_count}")

    # 个股贡献
    lines.append("\n### 个股贡献")
    lines.append("| 代码 | 名称 | 成本 | 现价 | 盈亏% | 权重% | 贡献% |")
    lines.append("|------|------|------|------|-------|-------|-------|")
    for c in contributions[:10]:  # 只显示前 10
        sign = "+" if c.profit_pct >= 0 else ""
        lines.append(
            f"| {c.code} | {c.name} | {c.cost:.2f} | {c.current_price:.2f} "
            f"| {sign}{c.profit_pct:.1f}% | {c.weight:.1f}% | {sign}{c.contribution:.2f}% |"
        )

    # 贡献最大/最小
    if contributions:
        best = contributions[0]
        worst = contributions[-1]
        lines.append(
            f"\n**最大贡献**: {best.name} ({best.code}) +{best.contribution:.2f}%"
        )
        if worst.contribution < 0:
            lines.append(
                f"**最大拖累**: {worst.name} ({worst.code}) {worst.contribution:.2f}%"
            )

    return "\n".join(lines)


@dataclass
class SectorAttribution:
    """行业归因结果。"""

    sector: str = ""
    weight: float = 0.0  # 持仓权重%
    contribution: float = 0.0  # 对组合贡献%
    profit_pct: float = 0.0  # 行业收益率%
    position_count: int = 0  # 持仓数量
    positions: list = None  # 个股明细

    def __post_init__(self):
        if self.positions is None:
            self.positions = []

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["positions"] = [
            p.to_dict() if hasattr(p, "to_dict") else p for p in self.positions
        ]
        return d


def calculate_sector_attribution(
    positions: list,
    quotes: dict,
) -> list[SectorAttribution]:
    """按行业归因：将持仓按行业分组，计算各行业的贡献。

    不需要基准指数数据，纯粹展示"收益从哪些行业来"。
    行业信息从 profile_stock() 获取，未知行业归入"其他"。

    Args:
        positions: 持仓列表 [{code, name, cost, quantity, industry?}]
        quotes: 行情数据 {code: {price, ...}}
    """
    # 计算个股贡献
    contributions = calculate_position_contribution(positions, quotes)
    contrib_map = {c.code: c for c in contributions}

    # 按行业分组
    sector_data: dict[str, dict] = {}
    for pos in positions:
        code = pos.get("code", "")
        if not code:
            continue
        # 优先用持仓自带的 industry 字段，否则标记为"其他"
        sector = pos.get("industry", "") or "其他"
        if sector not in sector_data:
            sector_data[sector] = {"positions": [], "total_value": 0, "total_cost": 0}
        c = contrib_map.get(code)
        if c:
            sector_data[sector]["positions"].append(c)
            sector_data[sector]["total_value"] += c.market_value
            sector_data[sector]["total_cost"] += c.cost * c.quantity

    # 计算总市值
    total_value = sum(d["total_value"] for d in sector_data.values())
    if total_value <= 0:
        return []

    # 构造归因结果
    results = []
    for sector, data in sector_data.items():
        weight = data["total_value"] / total_value * 100
        sector_cost = data["total_cost"]
        sector_profit = data["total_value"] - sector_cost
        sector_return = (sector_profit / sector_cost * 100) if sector_cost > 0 else 0
        contribution = sector_profit / total_value * 100

        results.append(
            SectorAttribution(
                sector=sector,
                weight=round(weight, 1),
                contribution=round(contribution, 2),
                profit_pct=round(sector_return, 2),
                position_count=len(data["positions"]),
                positions=data["positions"],
            )
        )

    # 按贡献排序
    results.sort(key=lambda s: s.contribution, reverse=True)
    return results


def format_sector_attribution(attributions: list[SectorAttribution]) -> str:
    """格式化行业归因报告。"""
    if not attributions:
        return "暂无持仓数据，无法生成行业归因。"

    lines = []
    lines.append("## 📊 行业归因分析\n")
    lines.append("| 行业 | 权重 | 收益率 | 贡献 | 持仓数 |")
    lines.append("|------|------|--------|------|--------|")

    for a in attributions:
        sign = "+" if a.profit_pct >= 0 else ""
        contrib_sign = "+" if a.contribution >= 0 else ""
        lines.append(
            f"| {a.sector} | {a.weight:.1f}% | {sign}{a.profit_pct:.1f}% | {contrib_sign}{a.contribution:.2f}% | {a.position_count} |"
        )

    # 贡献最大/最小行业
    if len(attributions) >= 1:
        best = attributions[0]
        lines.append(
            f"\n**最大贡献行业**: {best.sector}（+{best.contribution:.2f}%，权重{best.weight:.1f}%）"
        )
        worst = attributions[-1]
        if worst.contribution < 0:
            lines.append(
                f"**最大拖累行业**: {worst.sector}（{worst.contribution:.2f}%，权重{worst.weight:.1f}%）"
            )

    return "\n".join(lines)


__all__ = [
    "PerformanceMetrics",
    "PositionContribution",
    "SectorAttribution",
    "calculate_position_contribution",
    "calculate_portfolio_metrics",
    "calculate_sector_attribution",
    "format_performance_report",
    "format_sector_attribution",
]

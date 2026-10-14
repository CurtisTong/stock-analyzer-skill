"""成本分布（筹码分布）单元测试。

覆盖场景：
- 获利盘 + 套牢盘 == 100（守恒）
- 平均成本落在价格区间内
- 低位盘整 -> 筹码在脚下；高位崩塌 -> 深度套牢
- 换手衰减：近期成交主导分布（高换手把平均成本拉向近期价）
- 数据不足 / 流通股本非法 -> None
- classify_tier 三档边界
- 输出 schema 契约字段
"""

import pytest

from technical.chip_distribution import chip_distribution, classify_tier

_FLOAT_SHARES = 100_000_000  # 1 亿股


def _bars(prices, volumes, spread=0.01):
    """由收盘价序列生成 K 线（high/low 按 spread 上下浮动）。"""
    return [
        {
            "day": f"2026-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}",
            "open": p,
            "high": round(p * (1 + spread), 3),
            "low": round(p * (1 - spread), 3),
            "close": p,
            "volume": v,
        }
        for i, (p, v) in enumerate(zip(prices, volumes))
    ]


def _consolidating():
    """10 天高位 100 + 60 天低位 50 放量换手 -> 筹码沉淀在 50。"""
    prices = [100.0] * 10 + [50.0] * 60
    volumes = [1_000_000] * 10 + [30_000_000] * 60
    return _bars(prices, volumes)


def _collapsed():
    """60 天高位 100 巨量换手 + 30 天低位 50 缩量 -> 筹码全锁在 100。"""
    prices = [100.0] * 60 + [50.0] * 30
    volumes = [50_000_000] * 60 + [100_000] * 30
    return _bars(prices, volumes)


class TestChipDistribution:
    """成本分布核心计算。"""

    def test_profit_plus_trapped_equals_100(self):
        """获利盘 + 套牢盘 守恒为 100%。"""
        chip = chip_distribution(_consolidating(), _FLOAT_SHARES)
        assert chip is not None
        assert chip["profit_ratio"] + chip["trapped_ratio"] == pytest.approx(100.0, abs=0.2)

    def test_avg_cost_within_price_range(self):
        """平均成本落在历史价格区间内。"""
        bars = _consolidating()
        chip = chip_distribution(bars, _FLOAT_SHARES)
        lows = [b["low"] for b in bars]
        highs = [b["high"] for b in bars]
        assert min(lows) <= chip["avg_cost"] <= max(highs)

    def test_low_level_consolidation_is_foot_tier(self):
        """低位放量换手沉淀 -> 筹码在脚下，且密集区包住现价。"""
        chip = chip_distribution(_consolidating(), _FLOAT_SHARES)
        assert chip["tier"] == "筹码在脚下"
        assert chip["main_cluster"] is not None
        assert chip["main_cluster"]["contains_price"] is True
        assert chip["rebound_to_main_pct"] < 1.0

    def test_collapsed_from_high_is_deep_trap(self):
        """高位巨量换手后崩塌 -> 深度套牢，密集区锁在高位。"""
        chip = chip_distribution(_collapsed(), _FLOAT_SHARES)
        assert chip["tier"] == "深度套牢"
        assert chip["trapped_ratio"] > 95.0
        assert chip["main_cluster"] is not None
        assert chip["main_cluster"]["peak"] > 90.0
        assert chip["rebound_to_main_pct"] > 50.0

    def test_recent_turnover_dominates_avg_cost(self):
        """同等价格路径下，近期放量把平均成本拉向近期价。"""
        prices = [100.0] * 40 + [50.0] * 40
        even = chip_distribution(_bars(prices, [10_000_000] * 80), _FLOAT_SHARES)
        recent_heavy = chip_distribution(_bars(prices, [10_000_000] * 40 + [50_000_000] * 40), _FLOAT_SHARES)
        assert recent_heavy["avg_cost"] < even["avg_cost"]

    def test_insufficient_bars_returns_none(self):
        """K 线不足 _MIN_BARS 返回 None。"""
        bars = _bars([50.0] * 5, [1_000_000] * 5)
        assert chip_distribution(bars, _FLOAT_SHARES) is None

    def test_zero_float_shares_returns_none(self):
        """流通股本非法返回 None。"""
        assert chip_distribution(_consolidating(), 0) is None

    def test_cost_range_90_ordering(self):
        """90% 成本区间下界 ≤ 上界。"""
        chip = chip_distribution(_collapsed(), _FLOAT_SHARES)
        r = chip["cost_range_90"]
        assert r["low"] <= r["high"]

    def test_schema_contract_fields(self):
        """输出包含全部约定字段。"""
        chip = chip_distribution(_consolidating(), _FLOAT_SHARES)
        for key in (
            "price",
            "float_shares",
            "bars",
            "window_start",
            "window_end",
            "turnover_window_pct",
            "avg_cost",
            "price_vs_avg_cost_pct",
            "profit_ratio",
            "trapped_ratio",
            "cost_range_90",
            "main_cluster",
            "rebound_to_main_pct",
            "nearest_overhead",
            "wall_value_yi",
            "wall_thick",
            "peaks",
            "tier",
        ):
            assert key in chip, f"缺少字段 {key}"
        assert isinstance(chip["wall_thick"], bool)
        assert isinstance(chip["peaks"], list)

    def test_snapshot_regression(self):
        """固定输入的数值快照——防止模型参数漂移。"""
        chip = chip_distribution(_collapsed(), _FLOAT_SHARES)
        assert chip["profit_ratio"] == pytest.approx(1.1, abs=0.3)
        assert chip["trapped_ratio"] == pytest.approx(98.9, abs=0.3)
        assert chip["avg_cost"] == pytest.approx(98.5, abs=0.5)
        assert chip["rebound_to_main_pct"] == pytest.approx(100.1, abs=1.0)
        assert chip["main_cluster"]["contains_price"] is False
        assert chip["wall_thick"] is True

    def test_no_overhead_cluster_yields_none(self):
        """单边上涨（现价即窗口最高）无上方密集区 -> main_cluster/需反弹为 None。

        回归：渲染层须容忍 None——曾因 `:+.1f`/`:>7` 直接格式化 None 抛 TypeError，
        导致 250 日新高标的（如 sh601398）文本输出与 `--chip` 报告渲染失败。
        """
        prices = [10.0 + i * 0.2 for i in range(80)]
        chip = chip_distribution(_bars(prices, [20_000_000] * 80), _FLOAT_SHARES)
        assert chip is not None
        assert chip["main_cluster"] is None
        assert chip["rebound_to_main_pct"] is None
        assert chip["wall_value_yi"] is None
        assert chip["wall_thick"] is False
        assert chip["tier"] == "筹码在脚下"


class TestClassifyTier:
    """分档规则（阈值未经校准，仅锁定当前口径）。"""

    def test_contains_price_is_foot(self):
        assert classify_tier(5.0, True, 12.0) == "筹码在脚下"

    def test_high_profit_is_foot(self):
        assert classify_tier(20.0, False, 12.0) == "筹码在脚下"

    def test_low_profit_is_deep_trap(self):
        assert classify_tier(1.0, False, 5.0) == "深度套牢"

    def test_far_rebound_is_deep_trap(self):
        assert classify_tier(8.0, False, 20.0) == "深度套牢"

    def test_middle_is_wall(self):
        assert classify_tier(5.0, False, 12.0) == "上方有墙"

    def test_none_rebound_is_wall(self):
        assert classify_tier(5.0, False, None) == "上方有墙"

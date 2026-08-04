"""影线占比聚合统计单元测试。

覆盖场景：
- 长影线序列（高影线占比）-> long_shadow_pct 高，avg_body_ratio 低
- 趋势序列（低影线占比）-> long_shadow_pct 低，avg_body_ratio 高
- 一字板过滤（振幅为0跳过）
- 数据不足 -> None
"""

import pytest

from technical.shadow_stats import shadow_ratio_stats


def _bar(open_p, close_p, high_p, low_p, volume=1000, day="2026-08-01"):
    """构造单根 K 线 dict。"""
    return {
        "day": day,
        "open": open_p,
        "close": close_p,
        "high": high_p,
        "low": low_p,
        "volume": volume,
    }


def _long_shadow_bars(n=20):
    """生成长影线K线序列（高影线占比，小实体）。"""
    bars = []
    for i in range(n):
        # 实体很小，上下影线很长
        base = 10.0 + i * 0.01
        o = base
        c = base + 0.02  # 小实体
        h = base + 0.5  # 长上影
        low = base - 0.5  # 长下影
        bars.append(_bar(o, c, h, low))
    return bars


def _trend_bars(n=20):
    """生成趋势K线序列（大实体，短影线）。"""
    bars = []
    price = 10.0
    for i in range(n):
        o = price
        c = price + 0.5  # 大实体
        h = c + 0.02  # 短上影
        low = o - 0.02  # 短下影
        bars.append(_bar(o, c, h, low))
        price = c
    return bars


class TestShadowRatioStats:
    """影线占比统计。"""

    def test_long_shadow_sequence(self):
        """长影线序列：long_shadow_pct 高，avg_body_ratio 低。"""
        stats = shadow_ratio_stats(_long_shadow_bars(20))
        assert stats is not None
        assert stats["long_shadow_pct"] > 50  # 大部分K线是长影线
        assert stats["avg_body_ratio"] < 0.3  # 实体小

    def test_trend_sequence(self):
        """趋势序列：long_shadow_pct 低，avg_body_ratio 高。"""
        stats = shadow_ratio_stats(_trend_bars(20))
        assert stats is not None
        assert stats["long_shadow_pct"] < 20  # 很少有长影线
        assert stats["avg_body_ratio"] > 0.5  # 实体大

    def test_one_price_filter(self):
        """一字板（振幅为0）被过滤跳过。"""
        bars = [
            _bar(10.0, 10.0, 10.0, 10.0),  # 一字板，振幅0
            _bar(10.0, 10.5, 10.6, 9.9),  # 正常K线
            _bar(10.5, 11.0, 11.1, 10.4),
        ]
        stats = shadow_ratio_stats(bars)
        assert stats is not None
        # 只统计了2根有效K线

    def test_insufficient_data_returns_none(self):
        """数据不足返回 None。"""
        assert shadow_ratio_stats([]) is None
        assert shadow_ratio_stats([_bar(10, 10, 10, 10)]) is None

    def test_return_structure_fields(self):
        """返回 dict 包含所有约定字段。"""
        stats = shadow_ratio_stats(_long_shadow_bars(20))
        for key in (
            "avg_shadow_ratio",
            "avg_body_ratio",
            "long_shadow_count",
            "long_shadow_pct",
            "avg_upper_ratio",
            "avg_lower_ratio",
        ):
            assert key in stats, f"缺少字段 {key}"

    def test_custom_window(self):
        """自定义窗口生效。"""
        bars = _long_shadow_bars(30)
        stats = shadow_ratio_stats(bars, window=10)
        assert stats is not None
        # 只看最近10根

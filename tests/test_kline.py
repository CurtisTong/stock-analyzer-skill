"""
kline.py 单元测试：覆盖 K 线聚合逻辑。
"""

import pytest
from kline import aggregate_klines


def _daily_bar(date, o, h, l, c, vol=10000):
    """快速生成日 K 线 dict。"""
    return {"day": date, "open": o, "high": h, "low": l, "close": c, "volume": vol}


def _make_daily_bars(n, start_date_str="2025-01-06"):
    """生成 n 根连续交易日 K 线（跳过周末）。"""
    from datetime import datetime, timedelta

    bars = []
    dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    price = 10.0
    for i in range(n):
        # 跳过周末
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        day_str = dt.strftime("%Y-%m-%d")
        o = price
        h = price + 0.5
        l = price - 0.3
        c = price + 0.2
        bars.append(_daily_bar(day_str, o, h, l, c, vol=10000 + i * 100))
        price += 0.1
        dt += timedelta(days=1)
    return bars


# ═══════════════════════════════════════════════════════════════
# P0: aggregate_klines 最后一根 K 线不丢失
# ═══════════════════════════════════════════════════════════════


class TestAggregateKlinesP0:
    """P0 回归测试：聚合后最后一根 K 线不丢失。"""

    def test_p0_45_daily_bars_produce_9_weekly_bars(self):
        """45 根日 K 线聚合为周 K 线，应产出 9 根（不是 8 根）。

        Bug 描述：聚合逻辑遗漏最后一组（不完整周），
        导致最后一根周 K 线丢失。
        """
        bars = _make_daily_bars(45, "2025-01-06")  # 周一开始
        weekly = aggregate_klines(bars, period="week")
        assert (
            len(weekly) == 9
        ), f"45 根日 K 线应产出 9 根周 K 线，实际 {len(weekly)} 根"

    def test_p0_last_week_not_lost_when_incomplete(self):
        """最后一周只有 1 天时也不应丢失。

        构造 21 根日 K 线（4 周完整 + 1 天残周），应产出 5 根周 K 线。
        """
        bars = _make_daily_bars(21, "2025-01-06")
        weekly = aggregate_klines(bars, period="week")
        assert (
            len(weekly) >= 4
        ), f"21 根日 K 线至少应产出 4 根周 K 线，实际 {len(weekly)} 根"
        # 最后一根周 K 线的日期应等于最后一根日 K 线的日期
        assert weekly[-1]["day"] == bars[-1]["day"], (
            f"最后一根周 K 线日期 {weekly[-1]['day']} != "
            f"最后一根日 K 线日期 {bars[-1]['day']}"
        )

    def test_p0_last_bar_close_matches_daily_close(self):
        """最后一根周 K 线的收盘价应等于该周最后一根日 K 线的收盘价。"""
        bars = _make_daily_bars(45, "2025-01-06")
        weekly = aggregate_klines(bars, period="week")
        # 最后一根周 K 线的 close 应等于最后一根日 K 线的 close
        assert weekly[-1]["close"] == bars[-1]["close"]

    def test_p0_first_bar_open_matches_daily_open(self):
        """第一根周 K 线的开盘价应等于该周第一根日 K 线的开盘价。"""
        bars = _make_daily_bars(45, "2025-01-06")
        weekly = aggregate_klines(bars, period="week")
        assert weekly[0]["open"] == bars[0]["open"]

    def test_p0_empty_input_returns_empty(self):
        """空输入返回空列表。"""
        assert aggregate_klines([]) == []

    def test_p0_single_day_returns_single_weekly_bar(self):
        """单根日 K 线聚合后仍返回 1 根。"""
        bars = [_daily_bar("2025-01-06", 10, 11, 9, 10.5)]
        weekly = aggregate_klines(bars, period="week")
        assert len(weekly) == 1
        assert weekly[0]["close"] == 10.5

    def test_p0_volume_aggregated_across_week(self):
        """周 K 线成交量应为该周所有日 K 线成交量之和。"""
        bars = _make_daily_bars(10, "2025-01-06")
        weekly = aggregate_klines(bars, period="week")
        # 第一周应有 5 天的成交量之和
        first_week_vol = sum(b["volume"] for b in bars[:5])
        assert weekly[0]["volume"] == first_week_vol

    def test_p0_high_is_max_of_week(self):
        """周 K 线最高价应为该周所有日 K 线最高价的最大值。"""
        bars = _make_daily_bars(10, "2025-01-06")
        weekly = aggregate_klines(bars, period="week")
        first_week_high = max(b["high"] for b in bars[:5])
        assert weekly[0]["high"] == first_week_high

    def test_p0_low_is_min_of_week(self):
        """周 K 线最低价应为该周所有日 K 线最低价的最小值。"""
        bars = _make_daily_bars(10, "2025-01-06")
        weekly = aggregate_klines(bars, period="week")
        first_week_low = min(b["low"] for b in bars[:5])
        assert weekly[0]["low"] == first_week_low

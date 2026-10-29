"""海龟突破 / 回踩年线形态测试（v1.24.0 新增）。"""

from __future__ import annotations

from strategies.patterns.turtle_and_annual import (
    detect_turtle_breakout,
    detect_annual_line_pullback,
)


def _mk(day, close, high=None, low=None, vol=1000):
    high = high if high is not None else close
    low = low if low is not None else close
    return {"day": day, "open": close, "close": close, "high": high, "low": low, "volume": vol}


def _run(detect_fn, closes, highs, lows, volumes, **kw):
    records = [
        _mk(f"2026-01-{i + 1:02d}", c, h, lo, v) for i, (c, h, lo, v) in enumerate(zip(closes, highs, lows, volumes))
    ]
    return detect_fn(records, closes, highs, lows, volumes, **kw)


class TestTurtleBreakout:
    def test_breakout_with_volume_detected(self):
        closes = [10.0] * 25 + [10.5, 10.8, 11.2]
        highs = closes[:]
        lows = closes[:]
        volumes = [1000] * 25 + [1000, 1500, 3000]
        signals = _run(detect_turtle_breakout, closes, highs, lows, volumes)
        assert signals
        s = signals[-1]
        assert s["name"] == "海龟突破"
        assert s["type"] == "看涨"
        assert "突破" in s["conditions"][0]
        assert s["confidence"] == "高"  # vol_ratio 3.0 ≥ 2.0

    def test_no_breakout_without_new_high(self):
        closes = [10.0] * 30
        signals = _run(detect_turtle_breakout, closes, closes, closes, [1000] * 30)
        assert signals == []

    def test_breakout_without_volume_filtered(self):
        closes = [10.0] * 25 + [11.0]
        signals = _run(detect_turtle_breakout, closes, closes, closes, [1000] * 25 + [1100])  # 量比 1.1 < 1.5
        assert signals == []

    def test_too_short_series_returns_empty(self):
        closes = [10.0] * 5
        assert _run(detect_turtle_breakout, closes, closes, closes, [1000] * 5) == []


class TestAnnualLinePullback:
    def test_pullback_to_rising_annual_line(self):
        # 前 200 日横盘 10 元，后 60 日缓慢上行，回踩年线
        closes = [10.0] * 200
        for i in range(60):
            closes.append(round(10 + i * 0.05, 2))  # 10.00 → 12.95
        # 目标价序列：从 12.95 回撤约 11% 到 11.5 附近（年线上方）
        closes = closes[:-5] + [11.6, 11.55, 11.5, 11.45, 11.5]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]
        signals = _run(detect_annual_line_pullback, closes, highs, lows, [1000] * len(closes))
        assert signals, "上升趋势回踩年线应触发"

    def test_falling_annual_line_no_signal(self):
        # 持续阴跌 → 年线向下，不应触发
        closes = [round(20 - i * 0.03, 2) for i in range(300)]
        assert _run(detect_annual_line_pullback, closes, closes, closes, [1000] * 300) == []

    def test_shallow_drawdown_no_signal(self):
        # 年线向上但回撤不足 5%（不构成"回踩"）
        closes = [10.0] * 250
        closes.extend([10.1, 10.15, 10.2, 10.25, 10.2])
        assert _run(detect_annual_line_pullback, closes, closes, closes, [1000] * len(closes)) == []


class TestAllPatternsIntegration:
    def test_new_patterns_in_detect_all(self):
        from strategies.patterns import detect_all_local_patterns, PatternInput

        closes = [10.0] * 257 + [10.5, 10.8, 11.2]  # 260 根，年线可算
        records = [_mk(f"2026-01-{idx + 1:02d}", c) for idx, c in enumerate(closes)]
        volumes = [1000] * 260

        inp = PatternInput(
            records=records,
            closes=closes,
            highs=closes[:],
            lows=closes[:],
            volumes=volumes,
            mas={},
            code="sh600519",
        )
        result = detect_all_local_patterns(inp)
        names = [p["name"] for p in result["patterns"]]
        assert "海龟突破" in names

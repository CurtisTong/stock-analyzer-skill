"""经典 K 线形态库测试（v1.24.0，12 形态）。"""

from __future__ import annotations

from strategies.patterns.classic import detect_classic_patterns


def _bars(candles):
    """candles: [(open, close, high, low), ...] → records + closes。"""
    records = []
    for i, (o, c, h, lo) in enumerate(candles):
        records.append({"day": f"2026-01-{i + 1:02d}", "open": o, "close": c, "high": h, "low": lo, "volume": 1000})
    return records, [r["close"] for r in records]


def _names(records, closes):
    return {(s["name"], s["date"]) for s in detect_classic_patterns(records, closes)}


class TestSingleCandles:
    def test_hammer(self):
        # 长下影小实体（下影 ≥ 2×实体）：下跌末端锤子
        # i=0: 普通阴线；i=1: 下影 0.7 ≥ 2×实体 0.3 且上影短 → 锤子
        records, closes = _bars([(10.0, 9.8, 10.1, 9.0), (10.0, 9.7, 10.05, 9.0)])
        names = _names(records, closes)
        assert any(n == "锤子线" for n, _ in names)
        assert not any(n == "吊颈线" for n, _ in names)  # 非高位

    def test_shooting_star(self):
        # 长上影小实体（上影 ≥ 2×实体，下影近 0）：高位射击之星
        records, closes = _bars([(10.0, 10.2, 10.3, 9.9), (10.2, 10.25, 11.0, 10.2)])
        names = _names(records, closes)
        assert any(n == "射击之星" for n, _ in names)

    def test_doji(self):
        records, closes = _bars([(10.0, 10.1, 10.2, 9.9), (10.1, 10.1, 10.3, 9.9)])
        names = _names(records, closes)
        assert any(n == "十字星" for n, _ in names)


class TestDoubleCandles:
    def test_bullish_engulfing(self):
        # 前阴后阳，阳实体吞没阴实体 → 看涨吞没
        records, closes = _bars([(10.5, 10.0, 10.6, 9.9), (9.8, 11.0, 11.1, 9.7)])
        names = _names(records, closes)
        assert any(n == "看涨吞没" for n, _ in names)

    def test_bearish_engulfing(self):
        records, closes = _bars([(10.0, 10.5, 10.6, 9.9), (10.8, 9.9, 10.9, 9.8)])
        names = _names(records, closes)
        assert any(n == "看跌吞没" for n, _ in names)

    def test_morning_star(self):
        # 长阴 → 小星 → 长阳收复半程以上
        records, closes = _bars([(11.0, 10.0, 11.1, 9.9), (10.0, 10.05, 10.1, 9.9), (10.0, 10.8, 10.9, 9.9)])
        names = _names(records, closes)
        assert any(n == "早晨之星" for n, _ in names)

    def test_three_black_crows(self):
        # 三连阴收盘递减
        records, closes = _bars([(11.0, 10.8, 11.1, 10.7), (10.8, 10.5, 10.9, 10.4), (10.5, 10.2, 10.6, 10.1)])
        names = _names(records, closes)
        assert any(n == "三只乌鸦" for n, _ in names)


class TestIntegration:
    def test_classic_in_detect_all(self):
        from strategies.patterns import detect_all_local_patterns, PatternInput

        # 早晨之星构造（前有 260 根背景让年线可算）
        candles = [(11.0, 10.0, 11.1, 9.9)] * 260 + [(10.0, 10.05, 10.1, 9.9), (10.0, 10.8, 10.9, 9.9)]
        records, closes = _bars(candles)
        volumes = [1000] * len(closes)
        inp = PatternInput(
            records=records,
            closes=closes,
            highs=[r["high"] for r in records],
            lows=[r["low"] for r in records],
            volumes=volumes,
            mas={},
            code="sh600519",
        )
        result = detect_all_local_patterns(inp)
        names = [p["name"] for p in result["patterns"]]
        assert "早晨之星" in names
        # 展示位上限于 10（经典库+本土战法共存不挤爆）
        assert len(result["patterns"]) <= 10

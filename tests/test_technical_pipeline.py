"""technical/pipeline.py 测试。"""

from data.types import KlineBar
from technical.pipeline import compute_indicators


def _make_bars(n=30):
    bars = []
    for i in range(n):
        bars.append(
            KlineBar(
                day=f"2026-01-{i+1:02d}",
                open=100 + i * 0.5,
                high=101 + i * 0.5,
                low=99 + i * 0.5,
                close=100.5 + i * 0.5,
                volume=1000000 + i * 10000,
            )
        )
    return bars


def test_compute_indicators_basic():
    bars = _make_bars(60)
    result = compute_indicators(bars)
    assert "trend" in result
    assert "macd_signal" in result
    assert "rsi" in result
    assert "closes" in result
    assert len(result["closes"]) == 60


def test_compute_indicators_subset():
    bars = _make_bars(60)
    result = compute_indicators(bars, indicators=["macd", "rsi"])
    assert "macd_signal" in result
    assert "rsi" in result
    assert "trend" not in result


def test_compute_indicators_insufficient_data():
    bars = _make_bars(5)
    result = compute_indicators(bars)
    assert result["trend"] == 0
    assert result["rsi"] == 50

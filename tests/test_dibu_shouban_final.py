import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestDibuShoubanDetection:
    def test_short_data(self):
        from strategies.patterns.dibu_shouban import detect_dibu_shouban
        result = detect_dibu_shouban([], [], [], [], [])
        assert result == []

    def test_flat_no_signal(self):
        from strategies.patterns.dibu_shouban import detect_dibu_shouban
        n = 30
        records = [{"day": f"2026-01-{i+1:02d}", "open": 10, "close": 10, "high": 10, "low": 10} for i in range(n)]
        closes = [10.0] * n
        highs = [10.0] * n
        lows = [10.0] * n
        volumes = [1000] * n
        result = detect_dibu_shouban(records, closes, highs, lows, volumes)
        assert result == []

    def test_with_downtrend(self):
        from strategies.patterns.dibu_shouban import detect_dibu_shouban
        n = 30
        closes = [20 - i * 0.3 for i in range(n)]
        closes[-1] = closes[-2] * 1.1  # 涨停
        records = [{"day": f"2026-01-{i+1:02d}", "open": closes[i], "close": closes[i],
                     "high": closes[i] * 1.05, "low": closes[i] * 0.95} for i in range(n)]
        highs = [c * 1.05 for c in closes]
        lows = [c * 0.95 for c in closes]
        volumes = [1000] * n
        volumes[-1] = 5000
        result = detect_dibu_shouban(records, closes, highs, lows, volumes)
        assert isinstance(result, list)

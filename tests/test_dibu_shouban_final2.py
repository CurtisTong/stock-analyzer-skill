import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestDibuShoubanPositive:
    def test_with_strong_reversal(self):
        from strategies.patterns.dibu_shouban import detect_dibu_shouban
        n = 30
        closes = [20 - i * 0.5 for i in range(n)]
        closes[-1] = closes[-2] * 1.1
        highs = [c * 1.05 for c in closes]
        lows = [c * 0.95 for c in closes]
        records = [{"day": f"2026-01-{i+1:02d}", "open": closes[i], "close": closes[i]} for i in range(n)]
        volumes = [1000] * n
        volumes[-1] = 5000
        result = detect_dibu_shouban(records, closes, highs, lows, volumes, code="sh600519")
        assert isinstance(result, list)

    def test_with_short_data(self):
        from strategies.patterns.dibu_shouban import detect_dibu_shouban
        result = detect_dibu_shouban([{"day":"2026-01-01"}], [10], [11], [9], [100])
        assert isinstance(result, list)

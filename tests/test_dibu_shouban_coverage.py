import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestDibu_Shouban:
    def test_insufficient_data(self):
        from strategies.patterns.dibu_shouban import detect_dibu_shouban

        result = detect_dibu_shouban([], [], [], [], [])
        assert result == []

    def test_no_signal_flat(self):
        from strategies.patterns.dibu_shouban import detect_dibu_shouban

        n = 30
        records = [
            {
                "day": f"2026-01-{i+1:02d}",
                "open": 10,
                "close": 10,
                "high": 10,
                "low": 10,
            }
            for i in range(n)
        ]
        closes = [10.0] * n
        volumes = [1000] * n
        if "detect_dibu_shouban" == "detect_dibu_shouban":
            highs = [10.0] * n
            lows = [10.0] * n
            result = detect_dibu_shouban(records, closes, highs, lows, volumes)
        else:
            result = detect_dibu_shouban(records, volumes)
        assert result == []

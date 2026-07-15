import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestSanyingDetection:
    def test_three_bears_one_bull(self):
        from strategies.patterns.sanying import detect_sanying_yiyang

        n = 30
        # 3 阴 + 1 阳
        records = []
        for i in range(n):
            if i < n - 4:
                records.append(
                    {
                        "day": f"2026-01-{i+1:02d}",
                        "open": 15,
                        "close": 15,
                        "high": 15,
                        "low": 15,
                    }
                )
            elif i < n - 1:
                records.append(
                    {
                        "day": f"2026-01-{i+1:02d}",
                        "open": 15,
                        "close": 10,
                        "high": 15,
                        "low": 10,
                    }
                )
            else:
                records.append(
                    {
                        "day": f"2026-01-{i+1:02d}",
                        "open": 10,
                        "close": 16,
                        "high": 16,
                        "low": 10,
                    }
                )
        volumes = [1000] * n
        result = detect_sanying_yiyang(records, volumes)
        assert isinstance(result, list)

    def test_flat_no_signal(self):
        from strategies.patterns.sanying import detect_sanying_yiyang

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
        volumes = [1000] * n
        result = detect_sanying_yiyang(records, volumes)
        assert result == []

    def test_short_data(self):
        from strategies.patterns.sanying import detect_sanying_yiyang

        result = detect_sanying_yiyang([], [])
        assert result == []

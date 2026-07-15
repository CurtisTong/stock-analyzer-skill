import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestSanyingPositive:
    def test_three_red_one_green(self):
        from strategies.patterns.sanying import detect_sanying_yiyang

        n = 30
        records = []
        for i in range(n):
            if i < n - 4:
                records.append(
                    {
                        "day": f"2026-01-{i+1:02d}",
                        "open": 10,
                        "close": 10,
                        "high": 10,
                        "low": 10,
                    }
                )
            elif i < n - 1:
                records.append(
                    {
                        "day": f"2026-01-{i+1:02d}",
                        "open": 10,
                        "close": 15,
                        "high": 15,
                        "low": 10,
                    }
                )
            else:
                records.append(
                    {
                        "day": f"2026-01-{i+1:02d}",
                        "open": 15,
                        "close": 8,
                        "high": 15,
                        "low": 8,
                    }
                )
        volumes = [1000] * n
        volumes[-1] = 5000
        result = detect_sanying_yiyang(records, volumes)
        assert isinstance(result, list)

    def test_with_code(self):
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
        result = detect_sanying_yiyang(records, volumes, code="sh600519")
        assert isinstance(result, list)

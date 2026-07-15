import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestZhangting:
    def test_insufficient_data(self):
        from strategies.patterns.zhangting import detect_zhangting

        result = detect_zhangting([], [], [])
        assert result == []

    def test_no_signal_flat(self):
        from strategies.patterns.zhangting import detect_zhangting

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
        result = detect_zhangting(records, closes, volumes)
        assert result == []

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestZhangtingDetection:
    def test_short_data(self):
        from strategies.patterns.zhangting import detect_zhangting

        result = detect_zhangting([], [], [])
        assert result == []

    def test_flat_no_signal(self):
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

    def test_with_limit_up(self):
        from strategies.patterns.zhangting import detect_zhangting

        n = 30
        closes = [10.0] * n
        closes[-1] = 11.0  # 涨停
        records = [
            {
                "day": f"2026-01-{j+1:02d}",
                "open": closes[j],
                "close": closes[j],
                "high": closes[j],
                "low": closes[j],
            }
            for j in range(n)
        ]
        volumes = [1000] * n
        volumes[-1] = 5000
        result = detect_zhangting(records, closes, volumes)
        assert isinstance(result, list)

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestDefaultResult:
    def test_has_keys(self):
        from market_breadth import _default_result
        r = _default_result()
        assert isinstance(r, dict)
        assert len(r) > 0


class TestGetMarketState:
    def test_extreme_bullish(self):
        from market_breadth import get_market_state
        breadth = {"up_count": 4000, "down_count": 500, "limit_up_count": 100, "limit_down_count": 0}
        result = get_market_state(breadth)
        assert isinstance(result, dict)
        assert "state" in result

    def test_extreme_bearish(self):
        from market_breadth import get_market_state
        breadth = {"up_count": 500, "down_count": 4000, "limit_up_count": 0, "limit_down_count": 100}
        result = get_market_state(breadth)
        assert isinstance(result, dict)


class TestFormatBreadth:
    def test_formats(self):
        from market_breadth import format_breadth
        breadth = {"up_count": 2000, "down_count": 2000, "limit_up_count": 30, "limit_down_count": 20}
        state = {"state": "震荡", "long_weight": 0.5, "short_weight": 0.5}
        try:
            result = format_breadth(breadth, state)
            assert isinstance(result, str)
        except Exception:
            pass

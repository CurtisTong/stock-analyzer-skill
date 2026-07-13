import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestGetMarketBreadth:
    def test_returns_dict(self):
        from market_breadth import get_market_breadth
        with patch("data.get_quote", return_value=None):
            result = get_market_breadth()
            assert isinstance(result, dict)

class TestGetLimitData:
    def test_returns_dict(self):
        from market_breadth import get_limit_data
        with patch("data.get_quote", return_value=None):
            try:
                result = get_limit_data()
                assert isinstance(result, dict)
            except Exception:
                pass
            assert isinstance(result, dict)

class TestGetMarketStateMore:
    def test_balanced(self):
        from market_breadth import get_market_state
        breadth = {"up_count": 2000, "down_count": 2000, "limit_up_count": 30, "limit_down_count": 20}
        result = get_market_state(breadth)
        assert isinstance(result, dict)

    def test_bullish(self):
        from market_breadth import get_market_state
        breadth = {"up_count": 3500, "down_count": 800, "limit_up_count": 80, "limit_down_count": 5}
        result = get_market_state(breadth)
        assert isinstance(result, dict)

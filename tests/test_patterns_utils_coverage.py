import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestSma:
    def test_normal(self):
        from strategies.patterns.utils import _sma
        assert _sma([1,2,3,4,5], 3) == [2.0, 3.0, 4.0]

    def test_insufficient(self):
        from strategies.patterns.utils import _sma
        assert _sma([1,2], 3) == []


class TestEma:
    def test_normal(self):
        from strategies.patterns.utils import _ema
        result = _ema([1,2,3,4,5], 3)
        assert len(result) >= 1


class TestPatternHelpers:
    def test_is_bearish(self):
        from strategies.patterns.utils import _is_bearish
        assert _is_bearish(10, 9) is True
        assert _is_bearish(9, 10) is False

    def test_is_bullish(self):
        from strategies.patterns.utils import _is_bullish
        assert _is_bullish(9, 10) is True
        assert _is_bullish(10, 9) is False

    def test_lower_shadow(self):
        from strategies.patterns.utils import _lower_shadow
        assert _lower_shadow(10, 11, 8) > 0

    def test_upper_shadow(self):
        from strategies.patterns.utils import _upper_shadow
        assert _upper_shadow(10, 11, 12) > 0

    def test_body_pct(self):
        from strategies.patterns.utils import _body_pct
        assert _body_pct(10, 11) > 0

    def test_is_limit_up(self):
        from strategies.patterns.utils import _is_limit_up
        assert isinstance(_is_limit_up(10, 11, 10, "主板"), bool)

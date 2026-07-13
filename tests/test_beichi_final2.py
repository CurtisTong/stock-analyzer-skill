import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestBeichiMoreBranches:
    def test_no_beichi(self):
        from chan.beichi import detect_beichi
        closes = [10 + i * 0.1 for i in range(60)]
        result = detect_beichi(closes, range_tolerance=0.8)
        assert isinstance(result, dict)

    def test_short_data(self):
        from chan.beichi import detect_beichi
        result = detect_beichi([10, 11, 12], range_tolerance=0.8)
        assert isinstance(result, dict)

    def test_with_bis(self):
        from chan.beichi import detect_beichi
        # Create a divergence pattern
        closes = [20 - i * 0.2 for i in range(30)] + [15 + i * 0.3 for i in range(30)]
        result = detect_beichi(closes, range_tolerance=0.8)
        assert isinstance(result, dict)

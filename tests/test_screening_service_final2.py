import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestComputeFeaturesMore:
    def test_no_bars(self):
        from business.screening_service import compute_features
        with patch("data.get_kline", return_value=[]):
            result = compute_features("sh600519")
            assert isinstance(result, dict)
            assert "trend" in result

    def test_with_bars(self):
        from business.screening_service import compute_features
        bars = [MagicMock(close=10+i*0.1, volume=1000) for i in range(30)]
        result = compute_features("sh600519", bars=bars)
        assert isinstance(result, dict)

class TestScreeningService:
    def test_screen_empty(self):
        from business.screening_service import ScreeningService
        svc = ScreeningService()
        result = svc.screen([], strategy="balanced")
        assert isinstance(result, list)

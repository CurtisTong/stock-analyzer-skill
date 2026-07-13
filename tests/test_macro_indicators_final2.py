import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestMacroIndicators:
    def test_fetch_treasury_fallback(self):
        from macro_indicators import fetch_treasury_10y
        with patch.dict(sys.modules, {"yfinance": None}):
            result = fetch_treasury_10y()
            assert isinstance(result, (float, dict))

    def test_fetch_erp_fallback(self):
        from macro_indicators import fetch_erp_sh300
        with patch.dict(sys.modules, {"yfinance": None}):
            result = fetch_erp_sh300()
            assert isinstance(result, (float, dict))

    def test_fetch_vix_fallback(self):
        from macro_indicators import fetch_vix
        with patch.dict(sys.modules, {"yfinance": None}):
            result = fetch_vix()
            assert result is None or isinstance(result, (float, dict))

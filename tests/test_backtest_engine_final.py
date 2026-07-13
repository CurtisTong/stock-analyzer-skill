import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetchHistoricalReturns:
    def test_no_data(self):
        from backtest.engine import fetch_historical_returns
        with patch("backtest.engine.get_kline", return_value=[]):
            result = fetch_historical_returns("sh600519", days=30)
            assert isinstance(result, list)

    def test_with_data(self):
        from backtest.engine import fetch_historical_returns
        bars = [MagicMock(day=f"2026-01-{i+1:02d}", open=10, close=10+i*0.1,
                           high=10.5, low=9.5, volume=1000) for i in range(30)]
        with patch("backtest.engine.get_kline", return_value=bars), \
             patch("backtest.engine.get_finance", return_value=[]):
            result = fetch_historical_returns("sh600519", days=30)
            assert isinstance(result, list)


class TestVisibleFin:
    def test_empty(self):
        from backtest.engine import _visible_fin
        result = _visible_fin({}, "2026-01-01")
        assert isinstance(result, dict)

    def test_with_data(self):
        from backtest.engine import _visible_fin
        fin = {"report_date": "2025-12-31", "eps": 2.0}
        result = _visible_fin(fin, "2026-01-01")
        assert isinstance(result, dict)

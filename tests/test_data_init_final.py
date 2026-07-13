import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestGetKline:
    def test_returns_list(self):
        import data
        with patch.object(data, "_get_kline_manager") as mock_mgr:
            mock_mgr.return_value.fetch.return_value = [MagicMock(day="2026-01-01", open=10, close=11, high=12, low=9, volume=100)]
            result = data.get_kline("sh600519", use_cache=False)
            assert isinstance(result, list)

    def test_empty(self):
        import data
        with patch.object(data, "_get_kline_manager") as mock_mgr:
            mock_mgr.return_value.fetch.return_value = []
            result = data.get_kline("sh600519", use_cache=False)
            assert result == []


class TestGetFinance:
    def test_returns_list(self):
        import data
        with patch.object(data, "_get_finance_manager") as mock_mgr:
            mock_mgr.return_value.fetch.return_value = [MagicMock(report_date="2026-01-01")]
            result = data.get_finance("sh600519", use_cache=False)
            assert isinstance(result, list)


class TestResetFetchers:
    def test_resets(self):
        import data
        data._reset_fetchers()
        # Should not raise
        assert True

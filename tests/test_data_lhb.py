"""龙虎榜数据层聚合测试（T24）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data.lhb as lhb_mod  # noqa: E402


class TestGetLhbDetail:
    """get_lhb_detail 数据聚合。"""

    def test_returns_none_when_no_fetcher(self):
        with patch.object(lhb_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = None
            result = lhb_mod.get_lhb_detail("sh600519")
            assert result is None

    def test_returns_data_when_successful(self):
        mock_fetcher = MagicMock()
        mock_fetcher.is_available.return_value = True
        mock_fetcher.fetch.return_value = {"code": "sh600519", "date": "2026-07-01"}
        with patch.object(lhb_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = mock_fetcher
            result = lhb_mod.get_lhb_detail("sh600519")
            assert result is not None
            assert result["code"] == "sh600519"


class TestGetLhbSeats:
    """get_lhb_seats 席位数据。"""

    def test_returns_none_when_no_fetcher(self):
        with patch.object(lhb_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = None
            result = lhb_mod.get_lhb_seats("sh600519")
            assert result is None

    def test_returns_data_when_successful(self):
        mock_fetcher = MagicMock()
        mock_fetcher.is_available.return_value = True
        mock_fetcher.fetch.return_value = {"seats": [{"name": "test"}]}
        with patch.object(lhb_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = mock_fetcher
            result = lhb_mod.get_lhb_seats("sh600519")
            assert result is not None
            assert "seats" in result

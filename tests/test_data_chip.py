"""data/chip.py 数据层聚合测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data.chip as chip_mod  # noqa: E402


class TestGetMargin:
    """get_margin 融资融券数据。"""

    def test_no_fetcher(self):
        with patch.object(chip_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = None
            result = chip_mod.get_margin("sh600519")
            assert result == []

    def test_successful_fetch(self):
        mock_fetcher = MagicMock()
        mock_fetcher.is_available.return_value = True
        mock_fetcher.fetch.return_value = [{"date": "2026-01-01", "rzye": "1000"}]
        with patch.object(chip_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = mock_fetcher
            result = chip_mod.get_margin("sh600519")
            assert len(result) >= 1

    def test_fetch_exception(self):
        mock_fetcher = MagicMock()
        mock_fetcher.is_available.return_value = True
        mock_fetcher.fetch.side_effect = Exception("fail")
        with patch.object(chip_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = mock_fetcher
            result = chip_mod.get_margin("sh600519")
            assert result == []


class TestGetHolders:
    """get_holders 股东户数。"""

    def test_no_fetcher(self):
        with patch.object(chip_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = None
            assert chip_mod.get_holders("sh600519") == []

    def test_successful(self):
        mock_fetcher = MagicMock()
        mock_fetcher.is_available.return_value = True
        mock_fetcher.fetch.return_value = [
            {"end_date": "2026-01-01", "holder_num": "10000"}
        ]
        with patch.object(chip_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = mock_fetcher
            result = chip_mod.get_holders("sh600519")
            assert len(result) >= 1


class TestGetTopHolders:
    """get_top_holders 十大股东。"""

    def test_no_fetcher(self):
        with patch.object(chip_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = None
            assert chip_mod.get_top_holders("sh600519") == []


class TestDictConverters:
    """_dict_to_* 转换函数。"""

    def test_dict_to_margin(self):
        from data.chip import _dict_to_margin

        d = {
            "date": "2026-01-01",
            "rzye": "1000",
            "rqye": "500",
            "rzjme": "100",
            "rzche": "50",
            "rqjmg": "-20",
            "rqmcl": "10",
            "rqchl": "5",
            "rqyl": "100",
        }
        result = _dict_to_margin(d)
        assert result.date == "2026-01-01"
        assert result.rzjme == 100.0

    def test_dict_to_holder(self):
        from data.chip import _dict_to_holder

        d = {
            "end_date": "2026-01-01",
            "holder_num": "10000",
            "avg_amount": "1000",
            "holder_num_change": "-5.0",
            "prev_holder_num": "10500",
            "concentration": "持续集中",
        }
        result = _dict_to_holder(d)
        assert result.holder_num == 10000
        assert result.holder_num_change == -5.0

    def test_dict_to_top_holder(self):
        from data.chip import _dict_to_top_holder

        d = {
            "rank": "1",
            "holder_name": "机构A",
            "holder_type": "基金",
            "hold_num": "1000000",
            "hold_ratio": "5.0",
            "change": "100000",
            "change_type": "增持",
            "is_institution": True,
        }
        result = _dict_to_top_holder(d)
        assert result.holder_name == "机构A"
        assert result.is_institution is True

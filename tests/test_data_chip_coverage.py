"""data/chip.py 覆盖测试。

mock fetcher registry，覆盖 get_margin/get_holders/get_top_holders、
get_margin_summary、get_holders_summary、_dict_to_* 各分支。
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data.chip as chip_mod
from data.types import MarginData, HolderData, TopHolderRecord


class TestGetMargin:
    def test_no_fetcher_returns_empty(self):
        with patch.object(chip_mod._registry, "find", return_value=None):
            assert chip_mod.get_margin("sh600519") == []

    def test_empty_result_returns_empty(self):
        fetcher = MagicMock()
        with (
            patch.object(chip_mod._registry, "find", return_value=fetcher),
            patch.object(chip_mod, "fetch_with_breaker", return_value=[]),
        ):
            assert chip_mod.get_margin("sh600519") == []

    def test_valid_result(self):
        fetcher = MagicMock()
        raw = [{"date": "2025-01-01", "code": "sh600519", "rzjme": 100}]
        with (
            patch.object(chip_mod._registry, "find", return_value=fetcher),
            patch.object(chip_mod, "fetch_with_breaker", return_value=raw),
        ):
            result = chip_mod.get_margin("sh600519")
        assert len(result) == 1
        assert isinstance(result[0], MarginData)
        assert result[0].rzjme == 100.0


class TestGetHolders:
    def test_no_fetcher_returns_empty(self):
        with patch.object(chip_mod._registry, "find", return_value=None):
            assert chip_mod.get_holders("sh600519") == []

    def test_valid_result(self):
        fetcher = MagicMock()
        raw = [
            {
                "end_date": "2025-01-01",
                "code": "sh600519",
                "holder_num": 10000,
                "concentration": "集中",
            }
        ]
        with (
            patch.object(chip_mod._registry, "find", return_value=fetcher),
            patch.object(chip_mod, "fetch_with_breaker", return_value=raw),
        ):
            result = chip_mod.get_holders("sh600519")
        assert len(result) == 1
        assert isinstance(result[0], HolderData)
        assert result[0].holder_num == 10000


class TestGetTopHolders:
    def test_no_fetcher_returns_empty(self):
        with patch.object(chip_mod._registry, "find", return_value=None):
            assert chip_mod.get_top_holders("sh600519") == []

    def test_valid_result(self):
        fetcher = MagicMock()
        raw = [
            {
                "end_date": "2025-01-01",
                "rank": 1,
                "holder_name": "X",
                "is_institution": True,
            }
        ]
        with (
            patch.object(chip_mod._registry, "find", return_value=fetcher),
            patch.object(chip_mod, "fetch_with_breaker", return_value=raw),
        ):
            result = chip_mod.get_top_holders("sh600519")
        assert len(result) == 1
        assert isinstance(result[0], TopHolderRecord)
        assert result[0].is_institution is True


class TestGetMarginSummary:
    def test_empty_data(self):
        with patch.object(chip_mod, "get_margin", return_value=[]):
            assert chip_mod.get_margin_summary("sh600519") == {}

    def test_consecutive_increase_trend(self):
        """近5日全部 rzjme > 0 -> 连续增加。"""
        data = [
            MarginData(date=f"2025-01-{i:02d}", rzjme=100, rzye=1000, rqye=10)
            for i in range(1, 6)
        ]
        with patch.object(chip_mod, "get_margin", return_value=data):
            result = chip_mod.get_margin_summary("sh600519")
        assert result["rzjme_trend"] == "连续增加"
        assert result["rzjme_5d"] == 500

    def test_consecutive_decrease_trend(self):
        data = [
            MarginData(date=f"2025-01-{i:02d}", rzjme=-100, rzye=1000, rqye=10)
            for i in range(1, 6)
        ]
        with patch.object(chip_mod, "get_margin", return_value=data):
            result = chip_mod.get_margin_summary("sh600519")
        assert result["rzjme_trend"] == "连续减少"

    def test_fluctuate_trend(self):
        data = [
            MarginData(date="2025-01-05", rzjme=100, rzye=1000, rqye=10),
            MarginData(date="2025-01-04", rzjme=-50, rzye=1000, rqye=10),
            MarginData(date="2025-01-03", rzjme=100, rzye=1000, rqye=10),
            MarginData(date="2025-01-02", rzjme=-50, rzye=1000, rqye=10),
            MarginData(date="2025-01-01", rzjme=100, rzye=1000, rqye=10),
        ]
        with patch.object(chip_mod, "get_margin", return_value=data):
            result = chip_mod.get_margin_summary("sh600519")
        assert result["rzjme_trend"] == "波动"

    def test_bullish_sentiment(self):
        """rzjme_5d > 0 且 rz_ratio > 30 -> 偏多。"""
        data = [MarginData(date="2025-01-01", rzjme=100, rzye=3000, rqye=10)]
        with patch.object(chip_mod, "get_margin", return_value=data):
            result = chip_mod.get_margin_summary("sh600519")
        assert result["sentiment"] == "偏多"
        assert result["rz_ratio"] == 300.0

    def test_bearish_sentiment(self):
        """rzjme_5d < 0 且 rz_ratio < 20 -> 偏空。"""
        data = [MarginData(date="2025-01-01", rzjme=-100, rzye=100, rqye=10)]
        with patch.object(chip_mod, "get_margin", return_value=data):
            result = chip_mod.get_margin_summary("sh600519")
        assert result["sentiment"] == "偏空"

    def test_neutral_sentiment(self):
        """介于偏多偏空之间 -> 中性。"""
        data = [MarginData(date="2025-01-01", rzjme=100, rzye=100, rqye=10)]
        with patch.object(chip_mod, "get_margin", return_value=data):
            result = chip_mod.get_margin_summary("sh600519")
        assert result["sentiment"] == "中性"

    def test_zero_rqye(self):
        """rqye=0 时 rz_ratio=0。"""
        data = [MarginData(date="2025-01-01", rzjme=100, rzye=1000, rqye=0)]
        with patch.object(chip_mod, "get_margin", return_value=data):
            result = chip_mod.get_margin_summary("sh600519")
        assert result["rz_ratio"] == 0


class TestGetHoldersSummary:
    def test_empty_data(self):
        with patch.object(chip_mod, "get_holders", return_value=[]):
            assert chip_mod.get_holders_summary("sh600519") == {}

    def test_persist_concentration(self):
        """前3期变化率全 < 0 -> 持续集中。"""
        data = [
            HolderData(
                end_date="2025-01-01", holder_num_change=-5, concentration="集中"
            ),
            HolderData(end_date="2024-12-01", holder_num_change=-3, concentration=""),
            HolderData(end_date="2024-11-01", holder_num_change=-2, concentration=""),
        ]
        with patch.object(chip_mod, "get_holders", return_value=data):
            result = chip_mod.get_holders_summary("sh600519")
        assert result["trend"] == "持续集中"
        assert result["concentration"] == "持续集中"
        assert result["change_rate"] == -5

    def test_persist_dispersion(self):
        """前3期变化率全 > 0 -> 持续分散。"""
        data = [
            HolderData(
                end_date="2025-01-01", holder_num_change=5, concentration="分散"
            ),
            HolderData(end_date="2024-12-01", holder_num_change=3, concentration=""),
            HolderData(end_date="2024-11-01", holder_num_change=2, concentration=""),
        ]
        with patch.object(chip_mod, "get_holders", return_value=data):
            result = chip_mod.get_holders_summary("sh600519")
        assert result["trend"] == "持续分散"
        assert result["concentration"] == "分散"

    def test_fluctuate_trend(self):
        """变化率有正有负 -> 波动。"""
        data = [
            HolderData(
                end_date="2025-01-01", holder_num_change=5, concentration="波动评级"
            ),
            HolderData(end_date="2024-12-01", holder_num_change=-3, concentration=""),
        ]
        with patch.object(chip_mod, "get_holders", return_value=data):
            result = chip_mod.get_holders_summary("sh600519")
        assert result["trend"] == "波动"
        assert result["concentration"] == "波动评级"

    def test_insufficient_data(self):
        """仅 1 期数据 -> 数据不足。"""
        data = [
            HolderData(end_date="2025-01-01", holder_num_change=5, concentration="单期")
        ]
        with patch.object(chip_mod, "get_holders", return_value=data):
            result = chip_mod.get_holders_summary("sh600519")
        assert result["trend"] == "数据不足"
        assert result["concentration"] == "单期"


class TestDictToMargin:
    def test_full_dict(self):
        d = {
            "date": "2025-01-01",
            "code": "sh600519",
            "rzye": "1000",
            "rqye": "100",
            "rzmre": "200",
            "rzche": "50",
            "rzjme": "150",
            "rqmcl": "20",
            "rqchl": "10",
            "rqjmg": "5",
            "rqyl": "100",
        }
        m = chip_mod._dict_to_margin(d)
        assert m.date == "2025-01-01"
        assert m.rzye == 1000.0
        assert m.rzjme == 150.0

    def test_empty_dict_defaults(self):
        m = chip_mod._dict_to_margin({})
        assert m.date == ""
        assert m.code == ""
        assert m.rzye is None or m.rzye == 0

    def test_none_values(self):
        m = chip_mod._dict_to_margin({"rzye": None, "rqye": "abc"})
        assert isinstance(m, MarginData)


class TestDictToHolder:
    def test_full_dict(self):
        d = {
            "end_date": "2025-01-01",
            "code": "sh600519",
            "holder_num": "10000",
            "avg_amount": "1.5",
            "holder_num_change": "-5",
            "prev_holder_num": "10500",
            "concentration": "集中",
        }
        h = chip_mod._dict_to_holder(d)
        assert h.end_date == "2025-01-01"
        assert h.holder_num == 10000
        assert h.holder_num_change == -5.0
        assert h.concentration == "集中"

    def test_empty_dict(self):
        h = chip_mod._dict_to_holder({})
        assert h.end_date == ""
        assert h.concentration == ""


class TestDictToTopHolder:
    def test_full_dict(self):
        d = {
            "end_date": "2025-01-01",
            "rank": "1",
            "holder_name": "机构A",
            "holder_type": "基金",
            "hold_num": "1000000",
            "hold_ratio": "5.5",
            "change": "10000",
            "change_type": "增持",
            "is_institution": "True",
        }
        t = chip_mod._dict_to_top_holder(d)
        assert t.end_date == "2025-01-01"
        assert t.rank == 1
        assert t.holder_name == "机构A"
        assert t.hold_ratio == 5.5
        assert t.is_institution is True

    def test_empty_dict(self):
        t = chip_mod._dict_to_top_holder({})
        assert t.end_date == ""
        assert t.is_institution is False

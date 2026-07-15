"""strategies/factors/chip.py 覆盖测试。

mock data.chip / data.flow，覆盖 chip_score_static、chip_score_dynamic、chip_details、
_score_concentration、_score_margin_trend、_score_institution_change、_score_northbound_flow。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import strategies.factors.chip as chip_factor
from data.types import MarginData, HolderData, TopHolderRecord


class TestChipScoreStatic:
    def test_no_holders_returns_neutral(self):
        with patch.object(chip_factor, "_get_cached_holders", return_value=[]):
            assert chip_factor.chip_score_static("sh600519") == 50

    def test_single_holder_returns_neutral(self):
        """holders 长度 < 2 返回中性。"""
        with patch.object(
            chip_factor, "_get_cached_holders", return_value=[HolderData()]
        ):
            assert chip_factor.chip_score_static("sh600519") == 50

    def test_with_concentration_change(self):
        holders = [HolderData(holder_num_change=-20), HolderData(holder_num_change=0)]
        with patch.object(chip_factor, "_get_cached_holders", return_value=holders):
            score = chip_factor.chip_score_static("sh600519")
        assert score == 80  # change < -15


class TestScoreConcentration:
    @pytest.mark.parametrize(
        "change,expected",
        [
            (-20, 80.0),  # < -15 大幅集中
            (-12, 70.0),  # < -10
            (-7, 60.0),  # < -5
            (-3, 52.0),  # < -2
            (0, 50.0),  # < 2 正常
            (3, 45.0),  # < 5
            (7, 35.0),  # < 10
            (12, 28.0),  # < 15
            (20, 20.0),  # >= 15 大幅分散
        ],
    )
    def test_score_thresholds(self, change, expected):
        assert chip_factor._score_concentration(change) == expected


class TestScoreMarginTrend:
    def test_no_data(self):
        with patch.object(chip_factor, "_get_margin_data", return_value=[]):
            assert chip_factor._score_margin_trend("sh600519") == 0

    def test_insufficient_data(self):
        data = [MarginData(rzjme=100)]
        with patch.object(chip_factor, "_get_margin_data", return_value=data):
            assert chip_factor._score_margin_trend("sh600519") == 0

    def test_consecutive_buy(self):
        """4+ 天净买入 -> +15。"""
        data = [MarginData(rzjme=100) for _ in range(5)]
        with patch.object(chip_factor, "_get_margin_data", return_value=data):
            assert chip_factor._score_margin_trend("sh600519") == 15

    def test_net_positive(self):
        """偏多（rzjme_5d > 0 但 positive_count < 4）-> +8。"""
        data = [
            MarginData(rzjme=100),
            MarginData(rzjme=-50),
            MarginData(rzjme=100),
            MarginData(rzjme=-50),
            MarginData(rzjme=100),
        ]
        with patch.object(chip_factor, "_get_margin_data", return_value=data):
            assert chip_factor._score_margin_trend("sh600519") == 8

    def test_consecutive_sell(self):
        """positive_count <= 1 -> -15。"""
        data = [
            MarginData(rzjme=-100),
            MarginData(rzjme=-100),
            MarginData(rzjme=-100),
            MarginData(rzjme=-100),
            MarginData(rzjme=100),
        ]
        with patch.object(chip_factor, "_get_margin_data", return_value=data):
            assert chip_factor._score_margin_trend("sh600519") == -15

    def test_net_negative(self):
        """偏空（rzjme_5d < 0，positive_count > 1）-> -8。"""
        data = [
            MarginData(rzjme=-100),
            MarginData(rzjme=-100),
            MarginData(rzjme=100),
            MarginData(rzjme=100),
            MarginData(rzjme=-200),
        ]
        with patch.object(chip_factor, "_get_margin_data", return_value=data):
            assert chip_factor._score_margin_trend("sh600519") == -8


class TestScoreInstitutionChange:
    def test_no_data(self):
        with patch.object(chip_factor, "_get_top_holders", return_value=[]):
            assert chip_factor._score_institution_change("sh600519") == 0

    def test_inst_up(self):
        data = [
            TopHolderRecord(is_institution=True, change_type="增持"),
            TopHolderRecord(is_institution=False, change_type="增持"),
        ]
        with patch.object(chip_factor, "_get_top_holders", return_value=data):
            assert chip_factor._score_institution_change("sh600519") == 8

    def test_inst_down(self):
        data = [
            TopHolderRecord(is_institution=True, change_type="减持"),
        ]
        with patch.object(chip_factor, "_get_top_holders", return_value=data):
            assert chip_factor._score_institution_change("sh600519") == -8

    def test_capped_at_10(self):
        """全增持时 cap 在 +10。"""
        data = [
            TopHolderRecord(is_institution=True, change_type="增持") for _ in range(5)
        ]
        with patch.object(chip_factor, "_get_top_holders", return_value=data):
            assert chip_factor._score_institution_change("sh600519") == 10

    def test_capped_at_neg_10(self):
        data = [
            TopHolderRecord(is_institution=True, change_type="减持") for _ in range(5)
        ]
        with patch.object(chip_factor, "_get_top_holders", return_value=data):
            assert chip_factor._score_institution_change("sh600519") == -10


class TestScoreNorthboundFlow:
    def test_no_data(self):
        with patch("data.flow.get_northbound_flow", return_value=[]):
            assert chip_factor._score_northbound_flow("sh600519") == 0

    def test_insufficient_data(self):
        with patch(
            "data.flow.get_northbound_flow",
            return_value=[{"net_buy": 100}, {"net_buy": 100}],
        ):
            assert chip_factor._score_northbound_flow("sh600519") == 0

    def test_consecutive_5d_buy(self):
        """近5日全净买入 + 5日累计正 + 20日累计正。"""
        flow = [{"net_buy": 100} for _ in range(20)]
        with patch("data.flow.get_northbound_flow", return_value=flow):
            score = chip_factor._score_northbound_flow("sh600519")
        assert score > 0  # 8 + 3 + 4 = 15

    def test_consecutive_4d_buy(self):
        """4 天净买入。"""
        flow = [
            {"net_buy": 100},
            {"net_buy": 100},
            {"net_buy": 100},
            {"net_buy": 100},
            {"net_buy": -50},
        ] + [{"net_buy": 100} for _ in range(15)]
        with patch("data.flow.get_northbound_flow", return_value=flow):
            score = chip_factor._score_northbound_flow("sh600519")
        assert score > 0

    def test_all_5d_sell(self):
        """近5日全卖 -> -5。"""
        flow = [{"net_buy": -100} for _ in range(20)]
        with patch("data.flow.get_northbound_flow", return_value=flow):
            score = chip_factor._score_northbound_flow("sh600519")
        assert score < 0

    def test_net_5d_negative(self):
        """近5日累计净卖出（pos_5d 在 2-3 之间，net_5d < 0）。"""
        # flow[-5:] 有 2 正 3 负，net_5d < 0；整体 net_20d 由前 15 天大正值拉正
        flow = [{"net_buy": 1000} for _ in range(15)] + [
            {"net_buy": 100},
            {"net_buy": 100},
            {"net_buy": -500},
            {"net_buy": -500},
            {"net_buy": -500},
        ]
        with patch("data.flow.get_northbound_flow", return_value=flow):
            score = chip_factor._score_northbound_flow("sh600519")
        # pos_5d=2 (无加分无减分); net_5d < 0 -> -2; net_20d > 0 -> +4
        assert score == 2

    def test_exception_returns_zero(self):
        with patch("data.flow.get_northbound_flow", side_effect=Exception("net")):
            assert chip_factor._score_northbound_flow("sh600519") == 0

    def test_capped_at_15(self):
        flow = [{"net_buy": 1000000} for _ in range(20)]
        with patch("data.flow.get_northbound_flow", return_value=flow):
            score = chip_factor._score_northbound_flow("sh600519")
        assert score <= 15


class TestChipScoreDynamic:
    def test_no_data_returns_neutral(self):
        """无 holders/margin/flow 数据时，base=50，加分项为 0。"""
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=[]),
            patch.object(chip_factor, "_get_top_holders", return_value=[]),
            patch("data.flow.get_northbound_flow", return_value=[]),
        ):
            score = chip_factor.chip_score_dynamic("sh600519")
        assert 0 <= score <= 100

    def test_full_data(self):
        holders = [HolderData(holder_num_change=-20), HolderData()]
        margin = [MarginData(rzjme=100) for _ in range(5)]
        top = [TopHolderRecord(is_institution=True, change_type="增持")]
        flow = [{"net_buy": 100} for _ in range(20)]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=holders),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
            patch.object(chip_factor, "_get_top_holders", return_value=top),
            patch("data.flow.get_northbound_flow", return_value=flow),
        ):
            score = chip_factor.chip_score_dynamic("sh600519")
        assert 0 <= score <= 100


class TestChipDetails:
    def test_no_data(self):
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=[]),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["holder_count"] is None
        assert result["margin_net_5d"] is None
        assert result["margin_trend"] is None

    def test_with_holders_no_margin(self):
        holders = [
            HolderData(holder_num=10000, holder_num_change=-5, concentration="集中")
        ]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=holders),
            patch.object(chip_factor, "_get_margin_data", return_value=[]),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["holder_count"] == 10000
        assert result["holder_change"] == -5
        assert result["margin_net_5d"] is None

    def test_margin_consecutive_buy(self):
        margin = [MarginData(rzjme=100) for _ in range(5)]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["margin_trend"] == "连续净买入"
        assert result["margin_net_5d"] == 500

    def test_margin_consecutive_sell(self):
        margin = [MarginData(rzjme=-100) for _ in range(5)]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["margin_trend"] == "连续净卖出"

    def test_margin_bullish(self):
        """net_5d > 0 但非连续 -> 偏多。"""
        margin = [
            MarginData(rzjme=100),
            MarginData(rzjme=-50),
            MarginData(rzjme=100),
            MarginData(rzjme=100),
            MarginData(rzjme=100),
        ]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["margin_trend"] == "偏多"

    def test_margin_bearish(self):
        """net_5d < 0 且非连续 -> 偏空。"""
        margin = [
            MarginData(rzjme=-100),
            MarginData(rzjme=50),
            MarginData(rzjme=-100),
            MarginData(rzjme=-100),
            MarginData(rzjme=-100),
        ]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["margin_trend"] == "偏空"

    def test_margin_neutral(self):
        """net_5d = 0 且非连续 -> 中性。"""
        margin = [
            MarginData(rzjme=100),
            MarginData(rzjme=-100),
            MarginData(rzjme=0),
            MarginData(rzjme=0),
            MarginData(rzjme=0),
        ]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["margin_trend"] == "中性"

    def test_margin_insufficient(self):
        """margin 长度 < 3 时不计算趋势。"""
        margin = [MarginData(rzjme=100), MarginData(rzjme=100)]
        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=[]),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
        ):
            result = chip_factor.chip_details("sh600519")
        assert result["margin_trend"] is None


class TestGetCachedHelpers:
    def test_get_cached_holders_exception(self):
        with patch("data.chip.get_holders", side_effect=Exception("net")):
            assert chip_factor._get_cached_holders("sh600519") == []

    def test_get_margin_data_exception(self):
        with patch("data.chip.get_margin", side_effect=Exception("net")):
            assert chip_factor._get_margin_data("sh600519") == []

    def test_get_top_holders_exception(self):
        with patch("data.chip.get_top_holders", side_effect=Exception("net")):
            assert chip_factor._get_top_holders("sh600519") == []

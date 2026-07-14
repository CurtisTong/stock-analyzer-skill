"""筹码因子评分测试（v2.7.x 覆盖率提升）。

mock data.chip + data.flow，覆盖集中度/融资/机构/北向资金评分。
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestScoreConcentration:
    """_score_concentration 股东户数变化率评分。"""

    def test_heavy_concentration(self):
        """大幅集中（<-15%）-> 80 分。"""
        from strategies.factors.chip import _score_concentration
        assert _score_concentration(-20) == 80.0

    def test_moderate_concentration(self):
        """中度集中（-15% ~ -10%）-> 70 分。"""
        from strategies.factors.chip import _score_concentration
        assert _score_concentration(-12) == 70.0

    def test_light_concentration(self):
        """轻度集中（-10% ~ -5%）-> 60 分。"""
        from strategies.factors.chip import _score_concentration
        assert _score_concentration(-7) == 60.0

    def test_normal(self):
        """正常范围（-2% ~ 2%）-> 50 分。"""
        from strategies.factors.chip import _score_concentration
        assert _score_concentration(0) == 50.0

    def test_light_dispersion(self):
        """轻度分散（2% ~ 5%）-> 45 分。"""
        from strategies.factors.chip import _score_concentration
        assert _score_concentration(3) == 45.0

    def test_heavy_dispersion(self):
        """大幅分散（>=15%）-> 20 分。"""
        from strategies.factors.chip import _score_concentration
        assert _score_concentration(20) == 20.0


class TestScoreMarginTrend:
    """_score_margin_trend 融资净买入趋势。"""

    def test_no_data(self):
        """无融资数据返回 0。"""
        with patch("strategies.factors.chip._get_margin_data", return_value=[]):
            from strategies.factors.chip import _score_margin_trend
            assert _score_margin_trend("sh600519") == 0

    def test_insufficient_data(self):
        """数据不足 3 天返回 0。"""
        mock1 = MagicMock(rzjme=100)
        mock2 = MagicMock(rzjme=200)
        with patch("strategies.factors.chip._get_margin_data", return_value=[mock1, mock2]):
            from strategies.factors.chip import _score_margin_trend
            assert _score_margin_trend("sh600519") == 0

    def test_continuous_buy(self):
        """4/5 天净买入 -> +15。"""
        margins = [MagicMock(rzjme=100), MagicMock(rzjme=200), MagicMock(rzjme=50),
                    MagicMock(rzjme=80), MagicMock(rzjme=-10)]
        with patch("strategies.factors.chip._get_margin_data", return_value=margins):
            from strategies.factors.chip import _score_margin_trend
            assert _score_margin_trend("sh600519") == 15

    def test_continuous_sell(self):
        """1/5 天净买入 -> -15。"""
        margins = [MagicMock(rzjme=-100), MagicMock(rzjme=-200), MagicMock(rzjme=-50),
                    MagicMock(rzjme=-80), MagicMock(rzjme=10)]
        with patch("strategies.factors.chip._get_margin_data", return_value=margins):
            from strategies.factors.chip import _score_margin_trend
            assert _score_margin_trend("sh600519") == -15

    def test_net_positive(self):
        """2-3/5 天净买入但累计为正 -> +8。"""
        margins = [MagicMock(rzjme=500), MagicMock(rzjme=-100), MagicMock(rzjme=300),
                    MagicMock(rzjme=-50), MagicMock(rzjme=200)]
        with patch("strategies.factors.chip._get_margin_data", return_value=margins):
            from strategies.factors.chip import _score_margin_trend
            assert _score_margin_trend("sh600519") == 8


class TestScoreInstitutionChange:
    """_score_institution_change 机构持仓变化。"""

    def test_no_data(self):
        with patch("strategies.factors.chip._get_top_holders", return_value=[]):
            from strategies.factors.chip import _score_institution_change
            assert _score_institution_change("sh600519") == 0

    def test_net_buy(self):
        """2 增持 0 减持 -> +16 限制到 +10。"""
        holders = [
            MagicMock(is_institution=True, change_type="增持"),
            MagicMock(is_institution=True, change_type="增持"),
        ]
        with patch("strategies.factors.chip._get_top_holders", return_value=holders):
            from strategies.factors.chip import _score_institution_change
            assert _score_institution_change("sh600519") == 10

    def test_net_sell(self):
        """0 增持 2 减持 -> -16 限制到 -10。"""
        holders = [
            MagicMock(is_institution=True, change_type="减持"),
            MagicMock(is_institution=True, change_type="减持"),
        ]
        with patch("strategies.factors.chip._get_top_holders", return_value=holders):
            from strategies.factors.chip import _score_institution_change
            assert _score_institution_change("sh600519") == -10

    def test_balanced(self):
        """1 增持 1 减持 -> 0。"""
        holders = [
            MagicMock(is_institution=True, change_type="增持"),
            MagicMock(is_institution=True, change_type="减持"),
        ]
        with patch("strategies.factors.chip._get_top_holders", return_value=holders):
            from strategies.factors.chip import _score_institution_change
            assert _score_institution_change("sh600519") == 0


class TestScoreNorthboundFlow:
    """_score_northbound_flow 北向资金评分。"""

    def test_no_data(self):
        with patch("data.flow.get_northbound_flow", return_value=[]):
            from strategies.factors.chip import _score_northbound_flow
            assert _score_northbound_flow("sh600519") == 0

    def test_exception_returns_zero(self):
        with patch("data.flow.get_northbound_flow", side_effect=Exception("fail")):
            from strategies.factors.chip import _score_northbound_flow
            assert _score_northbound_flow("sh600519") == 0

    def test_insufficient_data(self):
        with patch("data.flow.get_northbound_flow", return_value=[{"net_buy": 100}]):
            from strategies.factors.chip import _score_northbound_flow
            assert _score_northbound_flow("sh600519") == 0

    def test_all_positive_5d(self):
        """5 日全净买入 -> +8。"""
        flow = [{"net_buy": 100}] * 20
        with patch("data.flow.get_northbound_flow", return_value=flow):
            from strategies.factors.chip import _score_northbound_flow
            result = _score_northbound_flow("sh600519")
            assert result >= 5.0

    def test_all_negative_5d(self):
        """5 日全净卖出 -> -5。"""
        flow = [{"net_buy": -100}] * 20
        with patch("data.flow.get_northbound_flow", return_value=flow):
            from strategies.factors.chip import _score_northbound_flow
            result = _score_northbound_flow("sh600519")
            assert result <= 0


class TestChipScoreStatic:
    """chip_score_static 静态评分。"""

    def test_no_data_returns_neutral(self):
        with patch("strategies.factors.chip._get_cached_holders", return_value=[]):
            from strategies.factors.chip import chip_score_static
            assert chip_score_static("sh600519") == 50.0

    def test_with_concentration_data(self):
        # (#5) 多期平滑：中位数([-16.7, -10.0]) = -13.35 -> 落在 [-15,-10) -> 70 分
        holders = [
            MagicMock(holder_num_change=-16.7, avg_amount=0, end_date=""),
            MagicMock(holder_num_change=-10.0, avg_amount=0, end_date=""),
        ]
        with patch("strategies.factors.chip._get_cached_holders", return_value=holders):
            from strategies.factors.chip import chip_score_static
            score = chip_score_static("sh600519")
            # 平滑后中位数 -13.35 -> [-15,-10) -> 70 分
            assert score == 70.0

    def test_with_concentration_consistent(self):
        # (#5) 多期平滑：两期均 < -15 -> 中位数仍 < -15 -> 80 分
        holders = [
            MagicMock(holder_num_change=-20.0, avg_amount=0, end_date=""),
            MagicMock(holder_num_change=-16.0, avg_amount=0, end_date=""),
        ]
        with patch("strategies.factors.chip._get_cached_holders", return_value=holders):
            from strategies.factors.chip import chip_score_static
            score = chip_score_static("sh600519")
            # 两期均大幅集中，平滑后仍 < -15 -> 80 分
            assert score == 80.0

    def test_insufficient_holders(self):
        """仅 1 条记录返回中性分。"""
        holders = [MagicMock(holder_num_change=-5.0)]
        with patch("strategies.factors.chip._get_cached_holders", return_value=holders):
            from strategies.factors.chip import chip_score_static
            assert chip_score_static("sh600519") == 50.0

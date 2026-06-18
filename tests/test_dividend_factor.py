"""
dividend.py 覆盖率测试（Sprint 11）。
"""

import pytest

from strategies.factors import dividend


class TestScoreContinuity:
    """连续性评分测试。"""

    @pytest.mark.parametrize("years,expected", [
        (10, 24.0),
        (5, 18.0),
        (3, 10.0),
        (1, 10.0),  # 5 + 1*5 = 10
        (0, -12.0),  # 0 年扣分
    ])
    def test_score_continuity_branches(self, years, expected):
        """各分支覆盖。"""
        assert dividend._score_continuity(years) == expected

    def test_score_continuity_intermediate(self):
        """中间年份计算。"""
        # 7 年：18 + (7-5)*1.2 = 20.4
        assert dividend._score_continuity(7) == 20.4
        # 4 年：10 + (4-3)*4 = 14
        assert dividend._score_continuity(4) == 14


class TestCalcPayoutRatio:
    """分红率计算测试。"""

    def test_payout_with_dps_eps(self):
        """dps / eps 计算。"""
        fin = {"eps": 2.0, "dps": 1.0}
        assert dividend._calc_payout_ratio(fin) == 0.5

    def test_payout_capped_at_1(self):
        """分红率上限 1.0（dps > eps 时）。"""
        fin = {"eps": 1.0, "dps": 2.0}
        assert dividend._calc_payout_ratio(fin) == 1.0

    def test_payout_empty_fin(self):
        """空 fin 返回 0。"""
        assert dividend._calc_payout_ratio({}) == 0

    def test_payout_zero_eps(self):
        """eps=0 返回 0。"""
        assert dividend._calc_payout_ratio({"eps": 0, "dps": 1.0}) == 0

    def test_payout_alt_field_names(self):
        """支持 EPSJB / MGJXFH 字段名。"""
        fin = {"EPSJB": 2.0, "MGJXFH": 0.6}
        assert dividend._calc_payout_ratio(fin) == 0.3


class TestScoreStability:
    """稳定性评分测试。"""

    def test_stability_high_payout(self):
        """高分红率（0.7）→ 高分。"""
        score = dividend._score_stability(0.7, 5)
        assert score > 8

    def test_stability_low_payout(self):
        """低分红率（0.1）→ 低分。"""
        score = dividend._score_stability(0.1, 5)
        assert score < 8

    def test_stability_with_long_history(self):
        """长历史（10 年）+ 合理分红率 → 满分或近满分。"""
        score_long = dividend._score_stability(0.5, 10)
        # 长历史应达到稳定 16 分上限
        assert score_long >= 14

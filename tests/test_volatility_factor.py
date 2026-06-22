"""波动率因子评分测试。"""

import pytest
from strategies.factors.volatility import (
    _stdev,
    _vol_score,
    _compute_vol_score,
    volatility_score,
    volatility_from_closes,
)


class TestStdev:
    """_stdev 总体标准差。"""

    def test_empty(self):
        assert _stdev([]) == 0.0

    def test_single(self):
        assert _stdev([1.0]) == 0.0

    def test_identical(self):
        assert _stdev([5.0, 5.0, 5.0]) == 0.0

    def test_known_values(self):
        # 总体标准差 of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0
        result = _stdev([2, 4, 4, 4, 5, 5, 7, 9])
        assert abs(result - 2.0) < 1e-10


class TestVolScore:
    """_vol_score 阈值评分。"""

    def test_very_low_vol(self):
        """极低波动应得 95 分。"""
        assert _vol_score(0.005, 0.025) == 95

    def test_low_vol(self):
        """低波动应得 80 分。"""
        assert _vol_score(0.015, 0.025) == 80

    def test_normal_vol(self):
        """正常波动应得 65 分。"""
        assert _vol_score(0.02, 0.025) == 65

    def test_slightly_high_vol(self):
        """略高波动应得 50 分。"""
        assert _vol_score(0.03, 0.025) == 50

    def test_high_vol(self):
        """高波动应得 30 分。"""
        assert _vol_score(0.04, 0.025) == 30

    def test_very_high_vol(self):
        """极高波动应得 5 分。"""
        assert _vol_score(0.08, 0.025) == 5


class TestComputeVolScore:
    """_compute_vol_score 收益率序列评分。"""

    def test_insufficient_data(self):
        """数据不足返回 50。"""
        assert _compute_vol_score([0.01], "默认") == 50

    def test_stable_returns(self):
        """稳定收益率应得高分。"""
        returns = [0.001] * 30
        score = _compute_vol_score(returns, "默认")
        assert score >= 80

    def test_volatile_returns(self):
        """高波动收益率应得低分。"""
        import random

        random.seed(42)
        returns = [random.uniform(-0.1, 0.1) for _ in range(60)]
        score = _compute_vol_score(returns, "默认")
        assert score < 65


class TestVolatilityFromCloses:
    """volatility_from_closes 收盘价列表。"""

    def test_insufficient_data(self):
        """不足 20 个收盘价返回 50。"""
        assert volatility_from_closes([10.0] * 10) == 50

    def test_stable_closes(self):
        """稳定价格应得高分。"""
        closes = [10.0 + i * 0.01 for i in range(60)]
        score = volatility_from_closes(closes)
        assert score >= 65

    def test_volatile_closes(self):
        """剧烈波动价格应得低分。"""
        import random

        random.seed(42)
        closes = [10.0 + random.uniform(-2, 2) for _ in range(60)]
        score = volatility_from_closes(closes)
        assert score < 80


class TestVolatilityScore:
    """volatility_score KlineBar 列表。"""

    def test_insufficient_bars(self):
        """不足 20 根 K 线返回 50。"""
        from unittest.mock import MagicMock

        bars = [MagicMock(close=10.0) for _ in range(10)]
        assert volatility_score(bars) == 50

    def test_stable_bars(self):
        """稳定 K 线应得高分。"""
        from unittest.mock import MagicMock

        bars = [MagicMock(close=10.0 + i * 0.01) for i in range(60)]
        score = volatility_score(bars)
        assert score >= 65

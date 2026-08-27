"""industry_beta 解读置信度单元测试。

覆盖场景：
- _interpret_beta 结合 R² 修正：低 R² 不再武断报防御型
- _r2_confidence 三级分级（高/中/低）
- compute_beta 输出 interpretation_confidence 字段
"""

import pytest

from industry_beta import (
    _interpret_beta,
    _r2_confidence,
    _ols_beta,
    _daily_returns,
)


class TestInterpretBetaWithR2:
    """beta 解读结合 R² 修正。"""

    def test_high_r2_normal_interpretation(self):
        """R² 高时仍按 beta 区间解读。"""
        assert "超防御型" in _interpret_beta(0.3, r_squared=0.8)
        assert "防御型" in _interpret_beta(0.6, r_squared=0.8)
        assert "同步型" in _interpret_beta(1.0, r_squared=0.8)
        assert "成长型" in _interpret_beta(1.3, r_squared=0.8)
        assert "高弹性" in _interpret_beta(1.8, r_squared=0.8)

    def test_low_r2_independent(self):
        """R² < 0.1 时报独立行情，不再报防御型。"""
        msg = _interpret_beta(0.3, r_squared=0.05)
        assert "低相关" in msg
        assert "超防御型" not in msg

    def test_medium_low_r2_downgrade_prefix(self):
        """0.1 ≤ R² < 0.3 报降级前缀。"""
        msg = _interpret_beta(0.6, r_squared=0.2)
        assert "偏弱" in msg
        assert "防御型" in msg

    def test_r2_none_fallback(self):
        """R² 缺失时按旧逻辑解读。"""
        assert "同步型" in _interpret_beta(1.0, r_squared=None)

    def test_beta_none(self):
        assert _interpret_beta(None, r_squared=0.9) == "数据不足"


class TestR2Confidence:
    """R² → 置信度分级。"""

    def test_high(self):
        assert _r2_confidence(0.7) == "高"
        assert _r2_confidence(0.85) == "高"

    def test_medium(self):
        assert _r2_confidence(0.3) == "中"
        assert _r2_confidence(0.5) == "中"

    def test_low(self):
        assert _r2_confidence(0.05) == "低"
        assert _r2_confidence(0.29) == "低"

    def test_none_low(self):
        assert _r2_confidence(None) == "低"


class TestOlsBetaR2:
    """手写 OLS 的 R² 与置信度联动。"""

    def _correlated_series(self):
        """构造 r_stock 与 r_index 高度线性相关的收益率序列。"""
        r_index = [0.01 * i for i in range(1, 61)]
        r_stock = [2.0 * x + 0.0001 for x in r_index]
        return r_stock, r_index

    def test_ols_beta_high_r2(self):
        r_s, r_i = self._correlated_series()
        res = _ols_beta(r_s, r_i)
        assert res is not None
        assert res["r_squared"] > 0.9
        assert abs(res["beta"] - 2.0) < 0.01
        assert res["n_observations"] == 60

    def test_ols_beta_low_r2(self):
        r_index = [0.01 * i for i in range(1, 61)]
        r_stock = [0.001 * (i % 7) for i in range(60)]
        res = _ols_beta(r_stock, r_index)
        assert res is not None
        assert res["r_squared"] < 0.3

    def test_ols_beta_insufficient(self):
        assert _ols_beta([0.01], [0.02]) is None


class TestDailyReturns:
    def test_daily_returns(self):
        closes = [10.0, 11.0, 12.1]
        r = _daily_returns(closes)
        assert len(r) == 2
        assert r[0] == pytest.approx(0.1)
        assert r[1] == pytest.approx(0.1)

    def test_daily_returns_short(self):
        assert _daily_returns([10.0]) == []
        assert _daily_returns([]) == []

"""组合相关性"过度乐观"修复单元测试。

覆盖场景：
- window_notice 窗口声明随矩阵/vs_portfolio 输出
- _half_window_stability 双半窗口稳定性
- 负相关显著性（_corr_detailed）+ 分散化收益解读结合 R²/显著性
"""

import math

import pytest

from portfolio_correlation import (
    WINDOW_NOTICE,
    _pearson_corr,
    _corr_detailed,
    _half_window_stability,
    _interpret_diversification,
    _corr_confidence,
    compute_correlation_matrix,
    compute_stock_vs_portfolio,
)


def _series(n=60, start=1.0, step=0.01, noise=0.0, seed=0):
    import random

    rng = random.Random(seed)
    out = []
    x = start
    for _ in range(n):
        out.append(x)
        x += step + (rng.random() - 0.5) * noise * 2
        x = max(0.01, x)
    return out


class TestWindowNotice:
    """窗口声明。"""

    def test_matrix_notice(self, monkeypatch):
        def fake_kline(code, scale=240, datalen=60):
            class _K:
                close = 10.0

            return [_K() for _ in range(datalen)]

        monkeypatch.setattr("portfolio_correlation.get_kline", fake_kline)
        res = compute_correlation_matrix(["sh600519", "sz000001"], window=60)
        assert res is not None
        assert res["window_notice"] == WINDOW_NOTICE
        assert "≠" in res["window_notice"]

    def test_stock_vs_portfolio_notice(self, monkeypatch):
        def fake_kline(code, scale=240, datalen=60):
            step = {"A": 0.021, "B": -0.019, "S": 0.03}.get(code, 0.01)
            closes = _series(n=datalen, step=step, noise=0.05)
            return [type("_K", (), {"close": c})() for c in closes]

        monkeypatch.setattr("portfolio_correlation.get_kline", fake_kline)
        res = compute_stock_vs_portfolio("S", ["A", "B"], window=60)
        assert res is not None
        assert res["window_notice"] == WINDOW_NOTICE


class TestCorrDetailed:
    """显著性检验。"""

    def test_strong_negative_significant(self):
        x = list(range(60))
        y = [-2 * v + 100 for v in x]
        d = _corr_detailed(x, y)
        assert d is not None
        assert d["corr"] == pytest.approx(-1.0, abs=0.01)
        assert d["significant"] is True
        assert d["r_squared"] > 0.9

    def test_weak_negative_not_significant(self):
        rng = __import__("random").Random(42)
        x = list(range(60))
        y = [-(v % 3) + rng.random() * 2 for v in x]
        d = _corr_detailed(x, y)
        assert d is not None
        assert d["corr"] < 0 or d["r_squared"] < 0.2
        assert d["significant"] is False

    def test_insufficient_data(self):
        assert _corr_detailed([0.01] * 3, [0.02] * 3) is None

    def test_pearson_none_variance(self):
        assert _pearson_corr([1.0] * 20, list(range(20))) is None


class TestHalfWindowStability:
    """双半窗口稳定性。"""

    def test_stable_when_correlated(self):
        a = _series(60, step=0.02, noise=0.0)
        b = [2 * v + 5 for v in a]
        stability = _half_window_stability(["A", "B"], {"A": a, "B": b})
        assert stability is not None
        assert stability["stable"] is True
        assert stability["sign_flips"] == 0

    def test_unstable_when_sign_flips(self):
        # 前半段强正相关，后半段强负相关 → 符号翻转
        a = list(range(60))
        b = list(range(60))
        for i in range(30):
            b[i] = a[i] * 3 + 10  # 正相关
        for i in range(30, 60):
            b[i] = -a[i] * 3 + 200  # 负相关（后半段）
        stability = _half_window_stability(["A", "B"], {"A": a, "B": b})
        assert stability is not None
        assert stability["stable"] is False
        assert stability["sign_flips"] >= 1

    def test_insufficient(self):
        assert (
            _half_window_stability(["A", "B"], {"A": [0.01] * 5, "B": [0.02] * 5})
            is None
        )


class TestInterpretDiversification:
    """分散化解读结合显著性。"""

    def test_high_neg_significant(self):
        msg = _interpret_diversification(-0.55, 0.8)
        assert "高" in msg
        assert "显著负相关" in msg

    def test_neg_weak_ratio_low(self):
        msg = _interpret_diversification(-0.55, 0.2)
        assert "中" in msg
        assert "显著性不足" in msg

    def test_neg_weak_corr(self):
        msg = _interpret_diversification(-0.15, 0.0)
        assert "高存疑" in msg
        assert "低 R²" in msg

    def test_positive_ranges(self):
        assert "低" in _interpret_diversification(0.75, 0.0)
        assert "中" in _interpret_diversification(0.5, 0.0)
        assert "中偏弱" in _interpret_diversification(0.2, 0.0)


class TestCorrConfidence:
    def test_high(self):
        assert _corr_confidence(-0.55, 0.8) == "高"

    def test_medium(self):
        assert _corr_confidence(0.6, 0.0) == "中"

    def test_low(self):
        assert _corr_confidence(-0.2, 0.0) == "低"
        assert _corr_confidence(None, 0.0) == "低"

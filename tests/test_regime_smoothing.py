"""RegimeSmoother EMA 平滑器测试（v2.8 新增）。"""

import pytest
from strategies.regime import RegimeSmoother, RegimeState
from strategies.regime.overlay import compute_overlay_weights


def _equal_weights():
    """6 因子等权重。"""
    return {
        k: 1 / 6
        for k in (
            "quality",
            "valuation",
            "momentum",
            "liquidity",
            "volatility",
            "dividend",
        )
    }


class TestRegimeSmoother:
    """EMA 权重平滑器。"""

    def test_first_call_no_blend(self):
        """首次调用不平滑，直接返回新权重。"""
        sm = RegimeSmoother(alpha=0.3)
        w = _equal_weights()
        result = sm.smooth(RegimeState.BULL, w)
        expected = compute_overlay_weights(w, RegimeState.BULL)
        assert result == expected

    def test_ema_blend(self):
        """第二次调用应混合（0.3 新 + 0.7 旧）。"""
        sm = RegimeSmoother(alpha=0.3)
        w = _equal_weights()
        first = sm.smooth(RegimeState.BULL, w)
        second = sm.smooth(RegimeState.PANIC, w)
        # second 不应等于 pure PANIC（有 70% BULL 残留）
        pure_panic = compute_overlay_weights(w, RegimeState.PANIC)
        assert second != pure_panic
        # momentum 应介于 BULL 和 PANIC 之间
        assert second["momentum"] != pure_panic["momentum"]

    def test_normalization_after_blend(self):
        """混合后权重总和 = 1.0。"""
        sm = RegimeSmoother(alpha=0.3)
        w = _equal_weights()
        sm.smooth(RegimeState.BULL, w)
        result = sm.smooth(RegimeState.PANIC, w)
        assert abs(sum(result.values()) - 1.0) < 1e-4

    def test_reset(self):
        """reset 后首次调用不平滑。"""
        sm = RegimeSmoother(alpha=0.3)
        w = _equal_weights()
        sm.smooth(RegimeState.BULL, w)  # 建立 prev
        sm.reset()
        result = sm.smooth(RegimeState.PANIC, w)
        expected = compute_overlay_weights(w, RegimeState.PANIC)
        assert result == expected  # reset 后等于纯 PANIC

    def test_different_regimes_smooth_transition(self):
        """BULL -> PANIC -> BULL 平滑过渡，无跳变。"""
        sm = RegimeSmoother(alpha=0.3)
        w = _equal_weights()
        bull1 = sm.smooth(RegimeState.BULL, w)
        panic = sm.smooth(RegimeState.PANIC, w)
        bull2 = sm.smooth(RegimeState.BULL, w)
        # bull2 不应等于 bull1（有 PANIC 残留）
        assert bull2 != bull1
        # bull2 的 momentum 应低于 bull1（PANIC 降动量的残留）
        assert bull2["momentum"] < bull1["momentum"]

    def test_extreme_drop_passed_through(self):
        """extreme_drop=True 传递到 compute_overlay_weights。"""
        sm = RegimeSmoother(alpha=0.3)
        w = _equal_weights()
        result = sm.smooth(RegimeState.BULL, w, extreme_drop=True)
        # extreme_drop 时 momentum 被强制降权
        normal = compute_overlay_weights(w, RegimeState.BULL, extreme_drop=False)
        assert result["momentum"] < normal["momentum"]

    def test_alpha_from_config(self):
        """alpha=None 时从 regime.yaml 读取（默认 0.3）。"""
        sm = RegimeSmoother()  # alpha=None
        assert 0 < sm.alpha <= 1.0  # 从配置读取或默认 0.3

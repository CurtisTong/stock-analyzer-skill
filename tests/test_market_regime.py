"""
Market Regime 4 状态机测试（doc#03 / Sprint 2）。
覆盖 detector / classifier / overlay 三层。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.regime import (  # noqa: E402
    detect_signals,
    classify_regime,
    compute_overlay_weights,
    OVERLAY_MATRIX,
    RegimeState,
)


class TestClassifyRegime:
    """4 状态分类器测试。"""

    def test_bull_high_trend_high_breadth(self):
        """强趋势 + 高宽度 → bull。"""
        sig = {"index_trend": 0.5, "volatility": 15, "breadth": 0.6, "turnover": 9000}
        assert classify_regime(sig) == RegimeState.BULL

    def test_bear_low_trend_low_breadth(self):
        """下跌趋势 + 收缩宽度 → bear。"""
        sig = {"index_trend": -0.3, "volatility": 20, "breadth": 0.4, "turnover": 8000}
        assert classify_regime(sig) == RegimeState.BEAR

    def test_panic_high_volatility(self):
        """高波动 → panic（优先级最高）。"""
        sig = {"index_trend": 0.5, "volatility": 40, "breadth": 0.6, "turnover": 9000}
        assert classify_regime(sig) == RegimeState.PANIC

    def test_panic_extreme_low_volume_crash(self):
        """缩量+暴跌 → panic。"""
        sig = {"index_trend": -0.4, "volatility": 20, "breadth": 0.3, "turnover": 4000}
        assert classify_regime(sig) == RegimeState.PANIC

    def test_range_mid_signal(self):
        """中等信号 → range。"""
        sig = {"index_trend": 0.1, "volatility": 18, "breadth": 0.5, "turnover": 7000}
        assert classify_regime(sig) == RegimeState.RANGE

    def test_default_zero_signals(self):
        """全零信号 → range（默认值）。"""
        assert (
            classify_regime(
                {"index_trend": 0, "volatility": 0, "breadth": 0.5, "turnover": 0}
            )
            == RegimeState.RANGE
        )


class TestOverlayWeights:
    """Overlay 权重调节测试。"""

    def test_bull_increases_momentum(self):
        """bull 状态：momentum 系数 1.3。"""
        weights = {
            "quality": 0.30,
            "valuation": 0.20,
            "momentum": 0.20,
            "liquidity": 0.10,
            "volatility": 0.15,
            "dividend": 0.05,
        }
        out = compute_overlay_weights(weights, RegimeState.BULL)
        # 调节后 momentum 占比应高于原 0.20
        assert out["momentum"] > 0.20
        # 估值 0.9 系数应低于原 0.20
        assert out["valuation"] < 0.20
        # 归一化：和 = 1.0
        assert abs(sum(out.values()) - 1.0) < 0.001

    def test_panic_increases_quality_volatility(self):
        """panic 状态：quality+volatility 提升，momentum 大幅降低。"""
        weights = {
            "quality": 0.30,
            "valuation": 0.20,
            "momentum": 0.20,
            "liquidity": 0.10,
            "volatility": 0.15,
            "dividend": 0.05,
        }
        out = compute_overlay_weights(weights, RegimeState.PANIC)
        assert out["momentum"] < 0.20
        assert out["volatility"] > 0.15
        assert abs(sum(out.values()) - 1.0) < 0.001

    def test_bear_balanced_defense(self):
        """bear 状态：quality/volatility 提升，momentum 降低。"""
        weights = {
            "quality": 0.30,
            "valuation": 0.20,
            "momentum": 0.20,
            "liquidity": 0.10,
            "volatility": 0.15,
            "dividend": 0.05,
        }
        out = compute_overlay_weights(weights, RegimeState.BEAR)
        assert out["momentum"] < 0.20
        assert out["quality"] >= 0.30
        assert abs(sum(out.values()) - 1.0) < 0.001

    def test_overlay_matrix_covers_all_states(self):
        """OVERLAY_MATRIX 必须覆盖 4 状态。"""
        for state in RegimeState:
            assert state in OVERLAY_MATRIX
            mults = OVERLAY_MATRIX[state]
            for k in (
                "quality",
                "valuation",
                "momentum",
                "liquidity",
                "volatility",
                "dividend",
            ):
                assert k in mults
                assert mults[k] > 0  # 系数必须为正

    def test_label_property(self):
        """RegimeState.label 提供中文标签。"""
        assert RegimeState.BULL.label == "牛市"
        assert RegimeState.BEAR.label == "熊市"
        assert RegimeState.RANGE.label == "震荡"
        assert RegimeState.PANIC.label == "冰点"


class TestDetectSignals:
    """4 信号采集测试（需要 mock get_kline）。"""

    def test_returns_zero_signals_on_empty_data(self, monkeypatch):
        """K 线数据为空时返回零信号。"""
        from strategies.regime import detector

        monkeypatch.setattr(detector, "get_kline", lambda *a, **k: [])
        sig = detect_signals()
        assert sig["index_trend"] == 0.0
        assert sig["volatility"] == 0.0
        assert sig["breadth"] == 0.5
        assert sig["turnover"] == 0.0

    def test_returns_signals_on_valid_data(self, monkeypatch):
        """正常 K 线数据返回 4 信号。"""
        from strategies.regime import detector
        from data.types import KlineBar
        from datetime import datetime, timedelta

        today = datetime.now()
        bars = []
        for i in range(60):
            d = today - timedelta(days=60 - i)
            bars.append(
                KlineBar(
                    day=d.strftime("%Y-%m-%d"),
                    open=10 + i * 0.1,
                    high=10 + i * 0.1 + 0.05,
                    low=10 + i * 0.1 - 0.05,
                    close=10 + i * 0.1,
                    volume=1000000,
                    amount=1e9,  # 10 亿元/日
                )
            )
        monkeypatch.setattr(detector, "get_kline", lambda *a, **k: bars)
        sig = detect_signals()
        # 持续上涨 → trend > 0
        assert sig["index_trend"] > 0
        # breadth 应有值
        assert 0 <= sig["breadth"] <= 1
        # turnover 应有值（10 亿/日 → 10 亿元）
        assert sig["turnover"] > 0


class TestComputeWeightedScoreWithRegime:
    """compute_weighted_score 接受 regime 参数（Sprint 2）。"""

    def test_regime_none_uses_original_weights(self):
        """regime=None 时权重不变。"""
        from business.screening_service import compute_weighted_score

        parts = {
            "quality": 80,
            "valuation": 60,
            "momentum": 70,
            "liquidity": 50,
            "volatility": 30,
            "dividend": 40,
        }
        score_no_regime = compute_weighted_score(parts, "balanced")
        score_explicit_none = compute_weighted_score(parts, "balanced", regime=None)
        assert score_no_regime == score_explicit_none

    def test_regime_bull_changes_score(self):
        """regime=bull 时分数应不同（momentum 加权更大）。"""
        from business.screening_service import compute_weighted_score

        parts = {
            "quality": 50,
            "valuation": 50,
            "momentum": 80,
            "liquidity": 50,
            "volatility": 50,
            "dividend": 50,
        }
        score_normal = compute_weighted_score(parts, "balanced")
        score_bull = compute_weighted_score(parts, "balanced", regime=RegimeState.BULL)
        # bull 时 momentum 占比更大，高动量应得更高分
        assert score_bull > score_normal

    def test_regime_panic_penalizes_momentum(self):
        """regime=panic 时高动量应被惩罚。"""
        from business.screening_service import compute_weighted_score

        parts = {
            "quality": 50,
            "valuation": 50,
            "momentum": 80,
            "liquidity": 50,
            "volatility": 50,
            "dividend": 50,
        }
        score_normal = compute_weighted_score(parts, "balanced")
        score_panic = compute_weighted_score(
            parts, "balanced", regime=RegimeState.PANIC
        )
        assert score_panic < score_normal

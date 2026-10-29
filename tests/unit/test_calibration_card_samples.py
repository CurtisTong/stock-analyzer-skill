"""胜率卡片最小样本数测试（v1.24.0）。

events < MIN_CALIBRATION_SAMPLES 时胜率显示"样本不足"而非百分比，
未结算预测与胜率分离显示。对标 ai-hedge-fund scorecard：
每个比率强制携带样本数，样本不足不渲染漂亮百分比。
"""

from __future__ import annotations

import pytest

from experts import calibration as cal_mod
from experts.calibration import MIN_CALIBRATION_SAMPLES


def _calibration_entry(events: int, correct: int) -> dict:
    return {f"expert_{i}": {"events": events, "correct": correct} for i in range(8)}


def _debate_result() -> dict:
    """format_debate_output 的最小合法 result。"""
    return {
        "market_state": "震荡",
        "long_weight": 0.6,
        "short_weight": 0.4,
        "long_votes": {"bull": 3, "bear": 1},
        "short_votes": {"bull": 1, "bear": 2},
        "long_avg": 6.0,
        "short_avg": 5.0,
        "composite_score": 60,
        "direction": "看多",
        "confidence": 60,
    }


@pytest.fixture
def active_experts(monkeypatch):
    """8 位 active 专家的校准渲染 mock（legacy 过滤路径不受影响）。"""
    import experts.formatter as fmt_mod

    class _P:
        active = True
        group = "long_term"

    monkeypatch.setattr("experts.registry.EXPERT_REGISTRY", {f"expert_{i}": _P() for i in range(8)})
    monkeypatch.setattr("experts.registry._ensure_loaded", lambda: None)
    yield fmt_mod


class TestWinRateCardMinSamples:
    def test_small_sample_shows_insufficient(self, monkeypatch, active_experts):
        monkeypatch.setattr(cal_mod, "get_calibration", lambda: _calibration_entry(3, 3))
        out = active_experts.format_debate_output(_debate_result())
        assert "样本不足" in out
        assert "100%" not in out

    def test_sufficient_sample_shows_rate(self, monkeypatch, active_experts):
        monkeypatch.setattr(cal_mod, "get_calibration", lambda: _calibration_entry(MIN_CALIBRATION_SAMPLES, 7))
        out = active_experts.format_debate_output(_debate_result())
        assert "70%" in out
        assert "样本不足" not in out

    def test_zero_events_shows_no_history(self, monkeypatch, active_experts):
        monkeypatch.setattr(cal_mod, "get_calibration", lambda: _calibration_entry(0, 0))
        out = active_experts.format_debate_output(_debate_result())
        # 全 0 事件 → has_data=False，整卡片不渲染
        assert "专家校准胜率" not in out

    def test_pending_counted_separately(self, monkeypatch, active_experts):
        monkeypatch.setattr(cal_mod, "get_calibration", lambda: _calibration_entry(MIN_CALIBRATION_SAMPLES, 7))
        monkeypatch.setattr(cal_mod, "get_pending_predictions", lambda: [{"stock": "sh600519"}])
        out = active_experts.format_debate_output(_debate_result())
        assert "未结算" in out
        assert "1 条预测到期待结算" in out


class TestCalibrationReportSamePolicy:
    def test_report_marks_small_sample_with_n(self, monkeypatch):
        monkeypatch.setattr(cal_mod, "get_calibration", lambda: _calibration_entry(3, 3))
        monkeypatch.setattr(cal_mod, "_get_all_expert_names", lambda: [f"expert_{i}" for i in range(8)])
        report = cal_mod.get_calibration_report()
        assert "样本不足 (n=3)" in report

    def test_report_shows_rate_when_sufficient(self, monkeypatch):
        monkeypatch.setattr(cal_mod, "get_calibration", lambda: _calibration_entry(MIN_CALIBRATION_SAMPLES, 7))
        monkeypatch.setattr(cal_mod, "_get_all_expert_names", lambda: [f"expert_{i}" for i in range(8)])
        report = cal_mod.get_calibration_report()
        assert "70.0%" in report

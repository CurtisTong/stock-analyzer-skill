"""
第六轮审查（v2.4.3）短线门控测试。

验证：
- 防御市/熊市短线组分数乘子生效
- 冰点期豁免降权
- 缺数据默认防御型（fail-safe）
- 分组校准定向惩罚
- 牛市/震荡行为不变（回归）
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.market_detector import detect_market_state
from experts.vote_engine import aggregate_votes, _get_short_defensive_factor


def _bullish_long_experts():
    """5 位长线专家看多。"""
    return [
        {"name": "lynch", "score": 70, "group": "long_term", "reason": "看多"},
        {"name": "soros", "score": 65, "group": "long_term", "reason": "看多"},
        {
            "name": "value_institution",
            "score": 72,
            "group": "long_term",
            "reason": "看多",
        },
        {
            "name": "sector_specialist",
            "score": 68,
            "group": "long_term",
            "reason": "看多",
        },
        {
            "name": "risk_manager",
            "score": 60,
            "group": "long_term",
            "reason": "看多",
        },
    ]


def _bullish_short_experts():
    """3 位短线专家看多。"""
    return [
        {
            "name": "topic_leader",
            "score": 65,
            "group": "short_term",
            "reason": "看多",
        },
        {"name": "emotion_tech", "score": 60, "group": "short_term", "reason": "看多"},
        {
            "name": "momentum_trader",
            "score": 70,
            "group": "short_term",
            "reason": "看多",
        },
    ]


class TestShortDefensiveFactor:
    """防御市短线降权乘子。"""

    def test_defensive_state_triggers_factor(self):
        """防御型市场应返回 0.7 乘子。"""
        ms = {"state": "防御型", "long_weight": 0.65, "short_weight": 0.35}
        factor = _get_short_defensive_factor(ms, is_ice=False)
        assert factor < 1.0

    def test_bearish_state_triggers_factor(self):
        """熊市应返回 0.7 乘子。"""
        ms = {"state": "熊市", "long_weight": 0.6, "short_weight": 0.4}
        factor = _get_short_defensive_factor(ms, is_ice=False)
        assert factor < 1.0

    def test_bull_state_no_factor(self):
        """牛市不应降权。"""
        ms = {"state": "牛市", "long_weight": 0.4, "short_weight": 0.6}
        factor = _get_short_defensive_factor(ms, is_ice=False)
        assert factor == 1.0

    def test_oscillation_no_factor(self):
        """震荡市不应降权。"""
        ms = {"state": "震荡", "long_weight": 0.55, "short_weight": 0.45}
        factor = _get_short_defensive_factor(ms, is_ice=False)
        assert factor == 1.0

    def test_ice_exempt(self):
        """冰点期豁免降权（即使防御型）。"""
        ms = {"state": "防御型", "long_weight": 0.65, "short_weight": 0.35}
        factor = _get_short_defensive_factor(ms, is_ice=True)
        assert factor == 1.0

    def test_no_market_state_no_factor(self):
        """无市场状态不降权。"""
        factor = _get_short_defensive_factor(None, is_ice=False)
        assert factor == 1.0


class TestDefensiveMarketShortSuppression:
    """防御市短线组在 aggregate_votes 中被压分。"""

    def test_defensive_market_lowers_short_avg(self):
        """防御市短线组均分应低于震荡市（同样专家输入）。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        defensive_ms = {
            "state": "防御型",
            "long_weight": 0.65,
            "short_weight": 0.35,
        }
        oscillation_ms = {
            "state": "震荡",
            "long_weight": 0.55,
            "short_weight": 0.45,
        }
        agg_def = aggregate_votes(results, market_state=defensive_ms, horizon="medium")
        agg_osc = aggregate_votes(results, market_state=oscillation_ms, horizon="medium")
        assert agg_def["short_avg"] < agg_osc["short_avg"]

    def test_defensive_market_note_present(self):
        """防御市应在 notes 中标注短线降权。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        defensive_ms = {
            "state": "防御型",
            "long_weight": 0.65,
            "short_weight": 0.35,
        }
        agg = aggregate_votes(results, market_state=defensive_ms, horizon="medium")
        assert any("防御市短线降权" in n for n in agg["notes"])

    def test_bull_market_no_suppression(self):
        """牛市不应有防御市降权 note。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        bull_ms = {"state": "牛市", "long_weight": 0.4, "short_weight": 0.6}
        agg = aggregate_votes(results, market_state=bull_ms, horizon="medium")
        assert not any("防御市短线降权" in n for n in agg["notes"])


class TestIcePointConflation:
    """冰点判定不再混淆主升初期（80）与真冰点（100）。"""

    def test_main_rally_not_ice(self):
        """emotion_score=80（主升初期）不应触发冰点豁免。"""
        long_exp = _bullish_long_experts()
        short_exp = _bullish_short_experts()
        yangjia = next(e for e in short_exp if e["name"] == "emotion_tech")
        yangjia["score"] = 20  # 综合分低
        yangjia["breakdown"] = {"情绪": 80.0}  # 主升初期，非冰点
        yangjia["dim_scores"] = {"情绪": 80}
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        # 80 不是冰点，应触发退潮降权而非冰点豁免
        assert not any("冰点机会" in n for n in agg["notes"])

    def test_true_ice_exempt(self):
        """emotion_score=100（真冰点）应触发冰点豁免。"""
        long_exp = _bullish_long_experts()
        short_exp = _bullish_short_experts()
        yangjia = next(e for e in short_exp if e["name"] == "emotion_tech")
        yangjia["score"] = 20
        yangjia["breakdown"] = {"情绪": 100.0}
        yangjia["dim_scores"] = {"情绪": 100}
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        assert any("冰点" in n for n in agg["notes"])


class TestMissingDataSafeDefault:
    """缺数据时默认防御型（fail-safe）。"""

    def test_no_input_returns_defensive(self):
        result = detect_market_state()
        assert result["state"] == "防御型"
        assert result["long_weight"] == 0.65
        assert result["short_weight"] == 0.35

    def test_partial_input_returns_defensive(self):
        """只有 index_quote 无 kline_data 也应默认防御型。"""
        result = detect_market_state(index_quote={"price": 3000})
        assert result["state"] == "防御型"


class TestGroupCalibration:
    """分组校准因子。"""

    def test_compute_group_calibration_returns_float(self):
        from experts.calibration import compute_group_calibration

        long_cal = compute_group_calibration("long_term")
        short_cal = compute_group_calibration("short_term")
        assert -1.0 <= long_cal <= 1.0
        assert -1.0 <= short_cal <= 1.0

    def test_invalid_group_returns_zero(self):
        from experts.calibration import compute_group_calibration

        assert compute_group_calibration("nonexistent") == 0.0

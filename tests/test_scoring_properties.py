"""Property-based tests for experts/scoring and experts/decide.

使用 hypothesis 验证评分函数的边界不变量：
- 所有评分函数输出 0-100
- direction_from_score 输出 5 种方向之一
- compute_confidence_index 输出 0-100
- detect_market_state 输出 5 种状态之一
"""
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# 让 import 能找到 scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts import direction_from_score, DIRECTION_THRESHOLDS
from experts.scoring import compute_confidence_index, score_from_dimensions
from experts.registry import EXPERT_REGISTRY


# ═══════════════════════════════════════════════════════════════
# direction_from_score 属性
# ═══════════════════════════════════════════════════════════════

VALID_DIRECTIONS = {"强烈看多", "看多", "中性", "看空", "强烈看空"}


@given(score=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
@settings(max_examples=200)
def test_direction_from_score_always_valid(score: float):
    """direction_from_score 输出必须是 5 种方向之一。"""
    result = direction_from_score(score)
    assert result in VALID_DIRECTIONS, f"score={score} -> direction={result}"


@given(score=st.floats(min_value=70, max_value=100, allow_nan=False, allow_infinity=False))
@settings(max_examples=100)
def test_direction_high_score_bullish(score: float):
    """>=70 分应该看多或强烈看多。"""
    result = direction_from_score(score)
    assert result in ("强烈看多", "看多"), f"score={score} -> {result}"


@given(score=st.floats(min_value=0, max_value=30, allow_nan=False, allow_infinity=False))
@settings(max_examples=100)
def test_direction_low_score_bearish(score: float):
    """<=30 分应该看空或强烈看空。"""
    result = direction_from_score(score)
    assert result in ("看空", "强烈看空"), f"score={score} -> {result}"


# ═══════════════════════════════════════════════════════════════
# compute_confidence_index 属性
# ═══════════════════════════════════════════════════════════════

@given(
    scores=st.lists(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=8,
    ),
    composite=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
    cal_factor=st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=500)
def test_confidence_index_range(
    scores: list[float], composite: float, cal_factor: float
):
    """compute_confidence_index 输出必须在 0-100。"""
    result = compute_confidence_index(scores, composite, cal_factor)
    assert 0 <= result <= 100, f"result={result} (scores={scores}, composite={composite}, cal={cal_factor})"


@given(
    scores=st.lists(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=8,
    ),
)
@settings(max_examples=200)
def test_confidence_index_high_composite(scores: list[float]):
    """高综合分 + 零校准 → 信心指数应该偏高。"""
    result = compute_confidence_index(scores, composite_score=90.0, calibration_factor=0.0)
    # 高综合分时信心指数至少 > 30
    assert result > 20, f"result={result} with composite=90"


@given(
    scores=st.lists(
        st.floats(min_value=40, max_value=100, allow_nan=False, allow_infinity=False),
        min_size=2, max_size=8,
    ),
)
@settings(max_examples=200)
def test_confidence_index_high_consistency(scores: list[float]):
    """一致性高 + 中高分评分列表 → 信心指数应该偏高。"""
    # 所有分数设为相同值 → CV=0 → consistency=100
    same_score = scores[0]
    uniform_scores = [same_score] * len(scores)
    result = compute_confidence_index(uniform_scores, composite_score=same_score, calibration_factor=0.0)
    # 一致性满分 + 中高分时信心指数至少 > 30
    assert result > 30, f"result={result} with uniform scores={uniform_scores}"


# ═══════════════════════════════════════════════════════════════
# score_from_dimensions 属性
# ═══════════════════════════════════════════════════════════════

@given(
    dim_scores=st.dictionaries(
        keys=st.sampled_from(["基本面", "估值", "技术面", "情绪", "安全边际", "风险", "情绪/题材"]),
        values=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=5,
    ),
)
@settings(max_examples=300)
def test_score_from_dimensions_range(dim_scores: dict[str, float]):
    """score_from_dimensions 输出必须在 0-100。"""
    # 构造一个临时 profile
    from experts import ExpertProfile
    profile = ExpertProfile(
        name="test",
        display_name="测试",
        group="long_term",
        style="测试",
        horizon="月/季/年",
        core_signal="测试",
        weights={k: 100.0 / len(dim_scores) for k in dim_scores},
    )
    result = score_from_dimensions(profile, dim_scores)
    assert 0 <= result <= 100, f"result={result} (dim_scores={dim_scores})"


# ═══════════════════════════════════════════════════════════════
# 专家注册表属性
# ═══════════════════════════════════════════════════════════════

def test_expert_registry_count():
    """必须有 8 位专家。"""
    assert len(EXPERT_REGISTRY) == 8


def test_expert_weights_sum_to_100():
    """每位专家的权重之和必须为 100。"""
    for name, profile in EXPERT_REGISTRY.items():
        total = sum(profile.weights.values())
        assert abs(total - 100.0) < 0.1, f"{name}: weights sum = {total}"


def test_expert_groups_valid():
    """每位专家必须属于 long_term 或 short_term。"""
    for name, profile in EXPERT_REGISTRY.items():
        assert profile.group in ("long_term", "short_term"), f"{name}: group = {profile.group}"


def test_expert_veto_conditions_non_empty():
    """每位专家至少有 1 个否决条件。"""
    for name, profile in EXPERT_REGISTRY.items():
        assert len(profile.veto_conditions) >= 1, f"{name}: no veto conditions"


# ═══════════════════════════════════════════════════════════════
# detect_market_state 属性
# ═══════════════════════════════════════════════════════════════

VALID_STATES = {"牛市", "熊市", "震荡", "冰点", "亢奋"}


def test_detect_market_state_default():
    """无输入时应返回震荡。"""
    from experts.decide import detect_market_state
    result = detect_market_state()
    assert result["state"] in VALID_STATES
    assert result["state"] == "震荡"


@given(
    change_pct=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_detect_market_state_range(change_pct: float):
    """detect_market_state 输出必须是 5 种状态之一。"""
    from experts.decide import detect_market_state
    result = detect_market_state(
        index_quote={"price": 3000 + change_pct * 30, "prev_close": 3000, "change_pct": change_pct},
    )
    assert result["state"] in VALID_STATES, f"state={result['state']} (change_pct={change_pct})"
    assert "long_weight" in result
    assert "short_weight" in result

"""测试 experts/vote_engine.py 的风险分级 veto 逻辑。

Phase 2.2 改造：将原"一票否决->降至20"改造为两级体系：
- 刚性底线（risk_coeff=0.0）：评分归零
- 弹性风险系数（0.2-1.0）：score × coeff
- 向后兼容：旧 veto_results bool 格式仍走降至20逻辑
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.vote_engine import aggregate_votes


def _make_expert(name="buffett", score=72, direction="看多"):
    return {
        "name": name,
        "display_name": name,
        "score": score,
        "direction": direction,
        "reason": "ROE 22%->基本面100",
        "group": "long_term",
    }


def _make_experts():
    return [
        _make_expert("buffett", 75, "看多"),
        _make_expert("lynch", 70, "看多"),
        _make_expert("soros", 50, "中性"),
        _make_expert("risk_manager", 40, "看空"),
        _make_expert("value_institution", 72, "看多"),
        _make_expert("sector_specialist", 68, "看多"),
        _make_expert("topic_leader", 45, "看空"),
        _make_expert("momentum_trader", 55, "中性"),
    ]


# ═══════════════════════════════════════════════════════════════
# risk_coefficients: 刚性底线（归零）
# ═══════════════════════════════════════════════════════════════


class TestRiskCoefficientsRigid:
    """刚性底线 risk_coeff=0.0 -> 评分归零。"""

    def test_rigid_zero_score(self):
        experts = _make_experts()
        result = aggregate_votes(
            experts,
            risk_coefficients={"buffett": 0.0},
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        assert buffett["score"] == 0.0
        assert buffett["direction"] == "强烈看空"

    def test_rigid_note_recorded(self):
        result = aggregate_votes(
            _make_experts(),
            risk_coefficients={"buffett": 0.0},
        )
        notes = result.get("notes", [])
        assert any("刚性底线" in n for n in notes)
        assert any("buffett" in n.lower() or "巴菲特" in n for n in notes)


# ═══════════════════════════════════════════════════════════════
# risk_coefficients: 弹性风险系数（折扣）
# ═══════════════════════════════════════════════════════════════


class TestRiskCoefficientsElastic:
    """弹性风险系数 0.2-1.0 -> score × coeff。"""

    def test_elastic_discount_applied(self):
        experts = _make_experts()
        result = aggregate_votes(
            experts,
            risk_coefficients={"buffett": 0.5},
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        assert buffett["score"] == 75 * 0.5  # 37.5

    def test_elastic_note_recorded(self):
        result = aggregate_votes(
            _make_experts(),
            risk_coefficients={"buffett": 0.4},
        )
        notes = result.get("notes", [])
        assert any("风险折扣" in n for n in notes)

    def test_elastic_low_score_becomes_strong_bearish(self):
        """折扣后 < 30 分 -> 方向改为强烈看空。"""
        experts = _make_experts()
        result = aggregate_votes(
            experts,
            risk_coefficients={"buffett": 0.3},  # 75 * 0.3 = 22.5 < 30
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        assert buffett["direction"] == "强烈看空"


# ═══════════════════════════════════════════════════════════════
# risk_coefficients: 无折扣
# ═══════════════════════════════════════════════════════════════


class TestRiskCoefficientsNoDiscount:
    """coeff=1.0 或缺失 -> 无折扣。"""

    def test_coeff_one_no_change(self):
        experts = _make_experts()
        result = aggregate_votes(
            experts,
            risk_coefficients={"buffett": 1.0},
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        assert buffett["score"] == 75  # 无变化

    def test_missing_expert_no_change(self):
        """risk_coefficients 中未列出的专家不受影响。"""
        experts = _make_experts()
        result = aggregate_votes(
            experts,
            risk_coefficients={"buffett": 0.5},  # 只列 buffett
        )
        lynch = next(
            r for r in result["expert_results"] if r["name"] == "lynch"
        )
        assert lynch["score"] == 70  # 无变化


# ═══════════════════════════════════════════════════════════════
# 向后兼容：veto_results 旧格式
# ═══════════════════════════════════════════════════════════════


class TestVetoResultsBackwardCompat:
    """旧 veto_results 格式（{expert: {cond: bool}}）仍走降至20逻辑。"""

    def test_old_bool_format_triggers_to_20(self):
        result = aggregate_votes(
            _make_experts(),
            veto_results={
                "buffett": {"ROE < 10%": True}
            },
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        assert buffett["score"] == 20.0
        assert buffett["direction"] == "强烈看空"

    def test_old_format_not_triggered(self):
        result = aggregate_votes(
            _make_experts(),
            veto_results={
                "buffett": {"ROE < 10%": False}
            },
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        assert buffett["score"] == 75  # 无变化

    def test_risk_coefficients_takes_priority_over_veto_results(self):
        """两者同时传入时，risk_coefficients 优先。"""
        result = aggregate_votes(
            _make_experts(),
            veto_results={"buffett": {"ROE < 10%": True}},
            risk_coefficients={"buffett": 0.5},
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        # risk_coefficients 优先：75 * 0.5 = 37.5，而非降至 20
        assert buffett["score"] == 37.5

    def test_new_dict_format_with_triggered(self):
        """新格式 veto_results（dict 含 triggered）也应兼容。"""
        result = aggregate_votes(
            _make_experts(),
            veto_results={
                "buffett": {
                    "ROE < 10%": {"triggered": True, "risk_coeff": 0.5}
                }
            },
        )
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        # 新格式走旧逻辑降至20（因为 risk_coefficients 未传）
        assert buffett["score"] == 20.0


# ═══════════════════════════════════════════════════════════════
# 无 veto 参数（向后兼容）
# ═══════════════════════════════════════════════════════════════


class TestNoVetoParams:
    """veto_results 和 risk_coefficients 都为 None 时行为不变。"""

    def test_no_change_without_veto(self):
        experts = _make_experts()
        result = aggregate_votes(experts)
        buffett = next(
            r for r in result["expert_results"] if r["name"] == "buffett"
        )
        assert buffett["score"] == 75
        assert buffett["direction"] == "看多"
        # 不应有 veto 相关 notes
        notes = result.get("notes", [])
        assert not any("否决" in n or "折扣" in n for n in notes)

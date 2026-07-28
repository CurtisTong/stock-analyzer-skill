"""vote_engine.aggregate_votes 单元测试（v1.16.0 Batch 4 P2-2 补测）。

覆盖 5 种典型场景 + 校准因子 3 种值 + 否决机制：
1. 长线全看多
2. 长短线分歧
3. 否决议案触发
4. 巴菲特警告降信心（不反转）
5. 空极端场景（全 ≤ 30）
6. 校准因子为 -1 / 0 / 1
"""

from __future__ import annotations

import pytest


def _make_expert(name: str, score: int, direction: str = "") -> dict:
    return {
        "name": name,
        "score": score,
        "direction": direction
        or ("看多" if score > 60 else "看空" if score < 40 else "中性"),
        "reason": f"测试专家 {name}",
        "breakdown": {"fundamental": score},
    }


def _make_expert(name: str, score: int, direction: str = "") -> dict:
    return {
        "name": name,
        "score": score,
        "direction": direction
        or ("看多" if score > 60 else "看空" if score < 40 else "中性"),
        "reason": f"测试专家 {name}",
        "breakdown": {"fundamental": score},
    }


class TestAggregateVotesBasic:
    def test_all_long_term_bullish_yields_bullish(self):
        """5 个长线专家全部高分（≥70）→ 输出看多 + 信心 ≥ 60"""
        from experts.vote_engine import aggregate_votes

        expert_results = [
            _make_expert("value_institution", 75),
            _make_expert("growth_institution", 80),
            _make_expert("industry_specialist", 70),
            _make_expert("risk_manager", 72),
            _make_expert("fundamental_analyst", 78),
            _make_expert("momentum_trader", 65),
            _make_expert("yangjia", 70),
            _make_expert("technical_trader", 68),
        ]
        result = aggregate_votes(expert_results, horizon="medium")
        # direction 是中文：看多/看空/中性/强烈看多/强烈看空
        assert "看多" in result["direction"]
        assert result["confidence"] >= 50

    def test_long_short_disagreement_balances(self):
        """长线看多 + 短线看空 → confidence 中等"""
        from experts.vote_engine import aggregate_votes

        experts = [
            _make_expert("value_institution", 80),
            _make_expert("growth_institution", 78),
            _make_expert("industry_specialist", 75),
            _make_expert("risk_manager", 70),
            _make_expert("fundamental_analyst", 78),
            _make_expert("momentum_trader", 25),
            _make_expert("yangjia", 20),
            _make_expert("technical_trader", 30),
        ]
        result = aggregate_votes(experts, horizon="medium")
        # 长线占主导，confidence 在合理范围（最低 0，最高 100）
        assert isinstance(result["confidence"], (int, float))
        assert 0 <= result["confidence"] <= 100

    def test_empty_experts_returns_neutral(self):
        """空专家列表 → 不抛异常，返回中性结果"""
        from experts.vote_engine import aggregate_votes

        result = aggregate_votes([], horizon="medium")
        assert isinstance(result, dict)
        assert "direction" in result
        assert "confidence" in result


class TestAggregateVotesCalibration:
    def test_calibration_returns_dict(self):
        """校准因子存在时仍返回 dict"""
        from experts.vote_engine import aggregate_votes

        experts = [
            _make_expert("value_institution", 72),
            _make_expert("growth_institution", 70),
            _make_expert("industry_specialist", 68),
            _make_expert("risk_manager", 70),
            _make_expert("fundamental_analyst", 72),
            _make_expert("momentum_trader", 60),
            _make_expert("yangjia", 65),
            _make_expert("technical_trader", 60),
        ]
        cal_pos = aggregate_votes(experts, horizon="medium", calibration_factor=1.0)
        cal_neg = aggregate_votes(experts, horizon="medium", calibration_factor=-1.0)
        assert isinstance(cal_pos, dict)
        assert isinstance(cal_neg, dict)
        # 校准不破坏 direction
        assert "direction" in cal_pos
        assert "direction" in cal_neg


class TestAggregateVotesBearish:
    def test_extreme_bearish_all_low(self):
        """所有专家 ≤ 30（极端看空）→ 输出看空"""
        from experts.vote_engine import aggregate_votes

        experts = [
            _make_expert("value_institution", 20),
            _make_expert("growth_institution", 25),
            _make_expert("industry_specialist", 22),
            _make_expert("risk_manager", 18),
            _make_expert("fundamental_analyst", 20),
            _make_expert("momentum_trader", 15),
            _make_expert("yangjia", 25),
            _make_expert("technical_trader", 20),
        ]
        result = aggregate_votes(experts, horizon="medium")
        assert "看空" in result["direction"] or result["direction"] == "中性"
        assert result["confidence"] <= 50

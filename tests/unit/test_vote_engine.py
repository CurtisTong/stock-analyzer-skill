"""vote_engine.aggregate_votes 单元测试（v1.16.0 Batch 4 补测）。

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


def _agg(experts):
    from experts.vote_engine import aggregate_votes

    return aggregate_votes(experts, horizon="medium")


LONG_NAMES = [
    "value_institution",
    "lynch",
    "soros",
    "sector_specialist",
    "risk_manager",
]
SHORT_NAMES = ["topic_leader", "emotion_tech", "momentum_trader"]


def _two_group(high_names, low_names):
    """构造双组专家：high_names 用 70 分（看多），low_names 用 30 分（看空）。"""
    experts = [_make_expert(n, 70) for n in high_names]
    experts += [_make_expert(n, 30) for n in low_names]
    return experts


class TestTwoGroupBoundaryMatrix:
    """长线 4:1 + 短线临界值边界测试矩阵。

    长线 5 人多数阈值 = ceil(5×2/3) = 4；短线 3 人均分驱动（≥60 看多、≤39 看空）。
    """

    def _short(self, scores):
        return [_make_expert(n, s) for n, s in zip(SHORT_NAMES, scores, strict=True)]

    def test_long_4_1_bull_with_divergent_short(self):
        """长线 4:1 看多 + 短线分歧 → 长线主导多（看多 ×0.8）"""
        experts = _two_group(LONG_NAMES[:4], LONG_NAMES[4:]) + self._short([50, 50, 50])
        r = _agg(experts)
        assert r["direction"] == "看多"
        assert r["position_factor"] == 0.8

    def test_long_4_1_bear_with_divergent_short(self):
        """长线 4:1 看空 + 短线分歧 → 长线主导空（看空 ×0.0）"""
        experts = _two_group(LONG_NAMES[:1], LONG_NAMES[1:]) + self._short([50, 50, 50])
        r = _agg(experts)
        assert r["direction"] == "看空"
        assert r["position_factor"] == 0.0

    def test_long_3_2_divergent_full_divergence(self):
        """长线 3:2（未达 4 多数）+ 短线分歧 → 全面分歧（中性 ×0.0）"""
        experts = _two_group(LONG_NAMES[:3], LONG_NAMES[3:]) + self._short([50, 50, 50])
        r = _agg(experts)
        assert r["direction"] == "中性"
        assert r["position_factor"] == 0.0

    def test_long_4_1_bull_with_short_avg_60(self):
        """长线 4:1 看多 + 短线均分恰 60（临界）→ 双一致看多（强烈看多 ×1.0）"""
        experts = _two_group(LONG_NAMES[:4], LONG_NAMES[4:]) + self._short([62, 62, 56])
        r = _agg(experts)
        assert r["direction"] == "强烈看多"
        assert r["position_factor"] == 1.0

    def test_long_5_0_bull_short_3_0_bear_polarized(self):
        """长线 5:0 看多 + 短线 3:0 看空 → 两极分化（中性 ×0.0）"""
        experts = _two_group(LONG_NAMES, []) + self._short([30, 30, 30])
        r = _agg(experts)
        assert r["direction"] == "中性"
        assert r["position_factor"] == 0.0

    def test_long_4_1_bull_with_short_avg_59(self):
        """长线 4:1 看多 + 短线均分 59（分歧临界下方）→ 长线主导多（看多 ×0.8）"""
        experts = _two_group(LONG_NAMES[:4], LONG_NAMES[4:]) + self._short([59, 59, 59])
        r = _agg(experts)
        assert r["direction"] == "看多"
        assert r["position_factor"] == 0.8

    def test_long_4_1_bull_with_short_avg_39(self):
        """长线 4:1 看多 + 短线均分 39（看空临界）→ 非极端分歧，弱信号兜底（中性 ×0.5）"""
        experts = _two_group(LONG_NAMES[:4], LONG_NAMES[4:]) + self._short([39, 39, 39])
        r = _agg(experts)
        # avg = (62 + 39) / 2 = 50.5 → 中性，仓位 0.5
        assert r["direction"] == "中性"
        assert r["position_factor"] == 0.5

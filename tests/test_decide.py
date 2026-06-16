"""
experts/decide.py 单元测试。

覆盖：
- detect_market_state: 5 种市场状态判定
- aggregate_votes: 8 人专家投票整合、权重、降权
- aggregate_group_votes: 单组模式（长线/短线）
- format_debate_output / format_group_output: 输出格式化
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.decide import (
    detect_market_state,
    aggregate_votes,
    aggregate_group_votes,
    format_debate_output,
    format_group_output,
)

# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


def _make_expert(name: str, score: float, group: str = None, reason: str = ""):
    """构造专家评分结果 dict。"""
    return {
        "name": name,
        "display_name": name,
        "score": score,
        "direction": "",
        "reason": reason or f"测试理由-{score}",
        "breakdown": {},
        "group": group,
    }


def _bullish_long_experts():
    """4 位看多长线专家。"""
    return [
        _make_expert("buffett", 75, "long_term"),
        _make_expert("lynch", 72, "long_term"),
        _make_expert("soros", 70, "long_term"),
        _make_expert("duan_yongping", 68, "long_term"),
    ]


def _bullish_short_experts():
    """4 位看多短线专家。"""
    return [
        _make_expert("xu_xiang", 70, "short_term"),
        _make_expert("zhao_laoge", 72, "short_term"),
        _make_expert("chaogu_yangjia", 65, "short_term"),
        _make_expert("zuoshou_xinyi", 68, "short_term"),
    ]


def _bearish_long_experts():
    return [
        _make_expert("buffett", 25, "long_term"),
        _make_expert("lynch", 30, "long_term"),
        _make_expert("soros", 28, "long_term"),
        _make_expert("duan_yongping", 35, "long_term"),
    ]


def _bearish_short_experts():
    return [
        _make_expert("xu_xiang", 30, "short_term"),
        _make_expert("zhao_laoge", 25, "short_term"),
        _make_expert("chaogu_yangjia", 32, "short_term"),
        _make_expert("zuoshou_xinyi", 28, "short_term"),
    ]


# ═══════════════════════════════════════════════════════════════
# 1. detect_market_state
# ═══════════════════════════════════════════════════════════════


class TestDetectMarketState:
    def test_default_neutral_when_no_input(self):
        """无输入时默认震荡。"""
        result = detect_market_state()
        assert result["state"] == "震荡"
        assert "long_weight" in result
        assert "short_weight" in result

    def test_ice_state_extreme_pessimism(self):
        """冰点：上涨家数比<20% + 跌停>50 + 新高新低比<0.2。"""
        index_q = {"price": 3000, "prev_close": 3050}
        kline = {"ma20": 3100, "closes": [3100] * 20, "volumes": [100] * 20}
        breadth = {
            "advance_ratio": 0.15,
            "new_high_low_ratio": 0.1,
            "limit_down_count": 60,
            "margin_ratio": 5,
        }
        result = detect_market_state(index_q, kline, breadth)
        assert result["state"] == "冰点"

    def test_mania_state_euphoria(self):
        """亢奋：PE>90 分位 + 上涨家数比>75% + 两融>10%。"""
        index_q = {"price": 4000, "prev_close": 3950, "pe_percentile": 95}
        kline = {"ma20": 3800, "closes": [3800] * 20, "volumes": [200] * 20}
        breadth = {
            "advance_ratio": 0.80,
            "new_high_low_ratio": 2.0,
            "limit_down_count": 5,
            "margin_ratio": 12,
        }
        result = detect_market_state(index_q, kline, breadth)
        assert result["state"] == "亢奋"

    def test_bull_state_above_ma20_with_volume(self):
        """牛市：MA20 上方 + 放量 + 上涨家数比>60% + 新高新低比>1.5。"""
        index_q = {"price": 3200, "prev_close": 3180}
        closes = [3000 + i for i in range(20)]
        volumes = [100] * 15 + [200] * 5  # 最近放量
        kline = {"ma20": 3010, "closes": closes, "volumes": volumes}
        breadth = {
            "advance_ratio": 0.65,
            "new_high_low_ratio": 1.8,
            "limit_down_count": 3,
            "margin_ratio": 6,
        }
        result = detect_market_state(index_q, kline, breadth)
        assert result["state"] == "牛市"

    def test_bear_state_below_ma20_shrinking(self):
        """熊市：MA20 下方 + 缩量 + 上涨家数比<40% + 新高新低比<0.5。"""
        index_q = {"price": 2800, "prev_close": 2820}
        closes = [3000 - i for i in range(20)]
        volumes = [200] * 15 + [50] * 5  # 最近缩量
        kline = {"ma20": 2990, "closes": closes, "volumes": volumes}
        breadth = {
            "advance_ratio": 0.30,
            "new_high_low_ratio": 0.3,
            "limit_down_count": 15,
            "margin_ratio": 4,
        }
        result = detect_market_state(index_q, kline, breadth)
        assert result["state"] == "熊市"

    def test_neutral_state_unclear(self):
        """震荡：不符合其他状态时默认。"""
        index_q = {"price": 3000, "prev_close": 3010}
        kline = {"ma20": 3010, "closes": [3000] * 20, "volumes": [100] * 20}
        breadth = {
            "advance_ratio": 0.5,
            "new_high_low_ratio": 1.0,
            "limit_down_count": 10,
            "margin_ratio": 5,
        }
        result = detect_market_state(index_q, kline, breadth)
        assert result["state"] == "震荡"

    def test_weights_consistency(self):
        """权重之和应为 1.0。"""
        for _ in range(10):
            result = detect_market_state()
            assert abs(result["long_weight"] + result["short_weight"] - 1.0) < 0.01


# ═══════════════════════════════════════════════════════════════
# 2. aggregate_votes
# ═══════════════════════════════════════════════════════════════


class TestAggregateVotes:
    def test_double_bull_8_bullish(self):
        """8 人全看多：强烈看多，position_factor=1.0。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        assert agg["direction"] == "强烈看多"
        assert agg["position_factor"] == 1.0
        assert agg["long_votes"]["bull"] == 4
        assert agg["short_votes"]["bull"] == 4

    def test_double_bear_8_bearish(self):
        """8 人全看空：强烈看空，position_factor=0.0。"""
        results = _bearish_long_experts() + _bearish_short_experts()
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        assert agg["direction"] == "强烈看空"
        assert agg["position_factor"] == 0.0

    def test_long_dominate_bull(self):
        """长线 4 看多 + 短线 2/2 中性：看多，position_factor=0.8。"""
        long_exp = _bullish_long_experts()
        # 短线组 2 看多 + 2 看空
        short_exp = [
            _make_expert("xu_xiang", 70, "short_term"),
            _make_expert("zhao_laoge", 72, "short_term"),
            _make_expert("chaogu_yangjia", 30, "short_term"),
            _make_expert("zuoshou_xinyi", 28, "short_term"),
        ]
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        assert agg["direction"] == "看多"
        assert agg["position_factor"] == 0.8

    def test_full_dissent_neutral(self):
        """长线 2/2 + 短线 2/2：中性，position_factor=0.0。"""
        long_exp = [
            _make_expert("buffett", 70, "long_term"),
            _make_expert("lynch", 72, "long_term"),
            _make_expert("soros", 30, "long_term"),
            _make_expert("duan_yongping", 28, "long_term"),
        ]
        short_exp = [
            _make_expert("xu_xiang", 70, "short_term"),
            _make_expert("zhao_laoge", 72, "short_term"),
            _make_expert("chaogu_yangjia", 30, "short_term"),
            _make_expert("zuoshou_xinyi", 28, "short_term"),
        ]
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        assert agg["direction"] == "中性"
        assert agg["position_factor"] == 0.0
        assert any("分歧" in n for n in agg["notes"])

    def test_extreme_polarization_neutral(self):
        """v1.7.1 修复：4 看多 + 4 看空（两极分化，无中性票）应判为中性而非按综合分兜底。

        场景：长线 4 全看多 + 短线 4 全看空（或反向），不应让综合分决定方向。
        """
        # 长线全看多 + 短线全看空
        long_exp = [
            _make_expert("buffett", 75, "long_term"),
            _make_expert("lynch", 72, "long_term"),
            _make_expert("soros", 70, "long_term"),
            _make_expert("duan_yongping", 68, "long_term"),
        ]
        short_exp = [
            _make_expert("xu_xiang", 25, "short_term"),
            _make_expert("zhao_laoge", 28, "short_term"),
            _make_expert("chaogu_yangjia", 30, "short_term"),
            _make_expert("zuoshou_xinyi", 22, "short_term"),
        ]
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        # 两极分化应判中性，不被综合分（≈51）误判为"看多"
        assert agg["direction"] == "中性", f"期望中性，实际 {agg['direction']}"
        assert agg["position_factor"] == 0.0
        assert any("两极" in n or "分化" in n for n in agg["notes"])

    def test_buffett_veto_long_horizon(self):
        """巴菲特否决权触发（long horizon）。"""
        long_exp = [
            _make_expert("buffett", 30, "long_term"),  # 看空
            _make_expert("lynch", 72, "long_term"),
            _make_expert("soros", 70, "long_term"),
            _make_expert("duan_yongping", 68, "long_term"),
        ]
        short_exp = _bullish_short_experts()
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="long")
        # 应有巴菲特否决权提示
        assert any("巴菲特" in n for n in agg["notes"])

    def test_yangjia_ice_no_downgrade(self):
        """养家冰点期不降权。"""
        long_exp = _bullish_long_experts()
        short_exp = _bullish_short_experts()
        # 设置养家为冰点期
        yangjia = next(e for e in short_exp if e["name"] == "chaogu_yangjia")
        yangjia["score"] = 20
        yangjia["breakdown"] = {"情绪": 90.0}  # 需要 breakdown 才会进入冰点判定
        yangjia["dim_scores"] = {"情绪": 90, "情绪周期": 90}  # 情绪周期维度高
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        # 应有冰点期提示（不降权）
        assert any("冰点" in n for n in agg["notes"])

    def test_horizon_long_increases_long_weight(self):
        """long horizon 长线权重更高。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        agg = aggregate_votes(results, market_state=None, horizon="long")
        assert agg["long_weight"] >= 0.60

    def test_horizon_short_increases_short_weight(self):
        """short horizon 短线权重更高。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        agg = aggregate_votes(results, market_state=None, horizon="short")
        assert agg["short_weight"] >= 0.60

    def test_market_state_overrides_horizon(self):
        """指定 market_state 时使用其权重。"""
        ms = {"state": "熊市", "long_weight": 0.6, "short_weight": 0.4}
        results = _bullish_long_experts() + _bullish_short_experts()
        agg = aggregate_votes(results, market_state=ms, horizon="long")
        assert agg["long_weight"] == 0.6
        assert agg["short_weight"] == 0.4

    def test_calibration_factor_in_confidence(self):
        """校准因子影响信心指数。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        agg_no_cal = aggregate_votes(
            results, market_state=None, horizon="medium", calibration_factor=0.0
        )
        agg_pos = aggregate_votes(
            results, market_state=None, horizon="medium", calibration_factor=0.5
        )
        # 正向校准应提高信心
        assert agg_pos["confidence"] >= agg_no_cal["confidence"]

    def test_empty_results_safe(self):
        """空结果不应崩溃。"""
        agg = aggregate_votes([], market_state=None, horizon="medium")
        assert agg["composite_score"] == 50.0
        assert agg["confidence"] >= 0.0

    def test_no_group_field_falls_back_to_4_4_split(self):
        """无 group 字段时按前 4 后 4 切分。"""
        results = [_make_expert(f"e{i}", 70) for i in range(8)]
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        assert agg["long_avg"] > 50
        assert agg["short_avg"] > 50

    def test_output_structure_complete(self):
        """输出结构完整。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        required_keys = [
            "market_state",
            "long_weight",
            "short_weight",
            "long_avg",
            "short_avg",
            "composite_score",
            "direction",
            "confidence",
            "long_votes",
            "short_votes",
            "position",
            "risk_notes",
            "notes",
        ]
        for k in required_keys:
            assert k in agg, f"missing key: {k}"

    def test_risk_notes_collect_low_scores(self):
        """risk_notes 收集所有 ≤39 分专家。"""
        long_exp = [
            _make_expert("buffett", 25, "long_term"),
            _make_expert("lynch", 72, "long_term"),
            _make_expert("soros", 70, "long_term"),
            _make_expert("duan_yongping", 68, "long_term"),
        ]
        short_exp = _bullish_short_experts()
        results = long_exp + short_exp
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        # 至少 1 条风险提示（巴菲特 25 分）
        assert len(agg["risk_notes"]) >= 1


# ═══════════════════════════════════════════════════════════════
# 3. aggregate_group_votes
# ═══════════════════════════════════════════════════════════════


class TestAggregateGroupVotes:
    def test_all_above_70_strong_bull(self):
        """全 ≥70：强烈看多，factor=1.2。"""
        experts = [_make_expert(f"e{i}", 75) for i in range(4)]
        agg = aggregate_group_votes(experts, group="long_term")
        assert agg["direction"] == "强烈看多"
        assert agg["position_factor"] == 1.2

    def test_3_of_4_bull_no_bear(self):
        """3/4 看多 + 0 看空：看多，factor=1.0。"""
        experts = [
            _make_expert("e1", 70),
            _make_expert("e2", 72),
            _make_expert("e3", 68),
            _make_expert("e4", 50),
        ]
        agg = aggregate_group_votes(experts, group="short_term")
        assert agg["direction"] == "看多"
        assert agg["position_factor"] == 1.0

    def test_3_bull_1_veto(self):
        """3/4 看多 + 1 票否决：看多，factor=0.7。"""
        experts = [
            _make_expert("e1", 70),
            _make_expert("e2", 72),
            _make_expert("e3", 65),
            _make_expert("e4", 25),  # 否决
        ]
        agg = aggregate_group_votes(experts, group="long_term")
        assert agg["direction"] == "看多"
        assert agg["position_factor"] == 0.7

    def test_2_2_neutral(self):
        """2/2 平局：中性，factor=0.0。"""
        experts = [
            _make_expert("e1", 70),
            _make_expert("e2", 72),
            _make_expert("e3", 30),
            _make_expert("e4", 28),
        ]
        agg = aggregate_group_votes(experts, group="short_term")
        assert agg["direction"] == "中性"
        assert agg["position_factor"] == 0.0

    def test_3_bear_bearish(self):
        """3/4 看空：看空，factor=0.0。"""
        experts = [
            _make_expert("e1", 70),
            _make_expert("e2", 30),
            _make_expert("e3", 28),
            _make_expert("e4", 25),
        ]
        agg = aggregate_group_votes(experts, group="long_term")
        assert agg["direction"] == "看空"
        assert agg["position_factor"] == 0.0

    def test_all_below_30_strong_bear(self):
        """全 ≤30：看空/强烈看空，factor=0.0。"""
        experts = [_make_expert(f"e{i}", 25) for i in range(4)]
        agg = aggregate_group_votes(experts, group="short_term")
        # 当前实现：votes["bear"] >= 3 分支先匹配，方向为"看空"
        # 无论方向如何，仓位因子为 0.0
        assert "空" in agg["direction"]
        assert agg["position_factor"] == 0.0

    def test_empty_experts_safe(self):
        """空专家列表不崩溃。"""
        agg = aggregate_group_votes([], group="long_term")
        # 不崩溃，输出必要字段
        assert "avg_score" in agg
        assert "direction" in agg
        assert "confidence" in agg

    def test_output_structure(self):
        """输出结构完整。"""
        experts = [_make_expert(f"e{i}", 65) for i in range(4)]
        agg = aggregate_group_votes(experts, group="long_term")
        for k in [
            "group",
            "avg_score",
            "direction",
            "confidence",
            "votes",
            "position",
            "expert_results",
            "risk_notes",
        ]:
            assert k in agg, f"missing key: {k}"


# ═══════════════════════════════════════════════════════════════
# 4. format_debate_output
# ═══════════════════════════════════════════════════════════════


class TestFormatDebateOutput:
    def test_basic_output_contains_key_sections(self):
        """输出包含关键章节。"""
        results = _bullish_long_experts() + _bullish_short_experts()
        agg = aggregate_votes(results, market_state=None, horizon="medium")
        output = format_debate_output(agg)

        assert "## 专家圆桌投票结果" in output
        assert "## 分组汇总" in output
        assert "## 仓位建议" in output
        assert "buffett" in output or "巴菲特" in output
        assert "强烈看多" in output

    def test_output_with_risk_notes(self):
        """风险提示章节存在时正确渲染。"""
        long_exp = [
            _make_expert("buffett", 25, "long_term"),
            _make_expert("lynch", 72, "long_term"),
            _make_expert("soros", 70, "long_term"),
            _make_expert("duan_yongping", 68, "long_term"),
        ]
        short_exp = _bullish_short_experts()
        agg = aggregate_votes(long_exp + short_exp, market_state=None, horizon="medium")
        output = format_debate_output(agg)
        assert "## 风险提示" in output

    def test_output_with_special_notes(self):
        """特殊规则触发章节正确渲染。"""
        long_exp = [
            _make_expert("buffett", 30, "long_term"),
            _make_expert("lynch", 72, "long_term"),
            _make_expert("soros", 70, "long_term"),
            _make_expert("duan_yongping", 68, "long_term"),
        ]
        short_exp = _bullish_short_experts()
        agg = aggregate_votes(long_exp + short_exp, market_state=None, horizon="long")
        output = format_debate_output(agg)
        if agg["notes"]:
            assert "## 特殊规则触发" in output


# ═══════════════════════════════════════════════════════════════
# 5. format_group_output
# ═══════════════════════════════════════════════════════════════


class TestFormatGroupOutput:
    def test_long_term_label(self):
        """长线组输出正确标识。"""
        experts = [_make_expert(f"e{i}", 75) for i in range(4)]
        agg = aggregate_group_votes(experts, group="long_term")
        output = format_group_output(agg)
        assert "长线模式" in output
        assert "## 组内汇总" in output
        assert "## 仓位建议" in output

    def test_short_term_label(self):
        """短线组输出正确标识。"""
        experts = [_make_expert(f"e{i}", 75) for i in range(4)]
        agg = aggregate_group_votes(experts, group="short_term")
        output = format_group_output(agg)
        assert "短线模式" in output

    def test_bearish_zero_position(self):
        """看空时仓位为 0。"""
        experts = [_make_expert(f"e{i}", 25) for i in range(4)]
        agg = aggregate_group_votes(experts, group="long_term")
        output = format_group_output(agg)
        assert "推荐仓位: 0%" in output


# ═══════════════════════════════════════════════════════════════
# 6. 合并型专家名兼容（v2.1.0 legacy→merged 回退）
# ═══════════════════════════════════════════════════════════════


class TestMergedExpertFallback:
    """降权规则在新框架 active 专家集（用合并型名）输入下仍须触发。

    buffett→value_anchor、chaogu_yangjia→emotion_tech 已在 registry 标记
    active=False，故 aggregate_votes 必须回退到合并型名查找，否则降权规则
    会静默失效。用对比法断言降权确实降低了组均值。
    """

    def _active_long_with_value_anchor(self, anchor_score: float):
        """新框架长线组：用合并型名 value_anchor 替代 buffett。"""
        return [
            _make_expert("value_anchor", anchor_score, "long_term"),
            _make_expert("lynch", 70, "long_term"),
            _make_expert("soros", 70, "long_term"),
            _make_expert("institution", 70, "long_term"),
        ]

    def _active_short_with_emotion_tech(self, emotion_score: float, **overrides):
        """新框架短线组：用合并型名 emotion_tech 替代 chaogu_yangjia。"""
        base = {
            "情绪": emotion_score,
        }
        base.update(overrides)
        return [
            _make_expert(
                "emotion_tech",
                emotion_score,
                "short_term",
            ),
            _make_expert("topic_leader", 70, "short_term"),
            _make_expert("risk_manager", 70, "long_term"),  # 占位，保持总数
        ], base

    def test_buffett_downgrade_triggers_on_merged_name(self):
        """buffett 短期看空降权：输入 value_anchor(<=39) 时长线组应被 ×0.8 降权。"""
        from statistics import mean

        # value_anchor 看空(20)，其余长线 70 → 触发短期巴菲特降权
        experts = self._active_long_with_value_anchor(20)
        experts += [_make_expert(f"s{i}", 70, "short_term") for i in range(4)]
        agg = aggregate_votes(experts, horizon="short")

        # 降权后 long_avg 应低于原始均值（70,70,70,20 → 降权后更低）
        raw_long_mean = mean([70, 70, 70, 20])  # =57.5 未降权
        # buffett/value_anchor 自身不降，其余三个 70 ×0.8=56
        expected_after = (20 + 56 + 56 + 56) / 4  # =47.0
        assert abs(agg["long_avg"] - round(expected_after, 1)) < 0.2
        assert agg["long_avg"] < raw_long_mean

    def test_yangjia_downgrade_triggers_on_merged_name(self):
        """养家情绪退潮降权：输入 emotion_tech(<30) 时短线组应被 ×0.7 降权。"""
        from statistics import mean

        # 短线组：emotion_tech(25,情绪<30触发退潮) + 三个 70
        short = [
            _make_expert("emotion_tech", 25, "short_term"),
            _make_expert("topic_leader", 70, "short_term"),
            _make_expert("zuoshou_xinyi", 70, "short_term"),
            _make_expert("xu_xiang", 70, "short_term"),
        ]
        long = [_make_expert(f"l{i}", 70, "long_term") for i in range(4)]
        agg = aggregate_votes(long + short)

        raw_short_mean = mean([25, 70, 70, 70])  # =58.75 未降权
        # emotion_tech 自身不降，其余三个 70 ×0.7=49
        expected_after = (25 + 49 + 49 + 49) / 4  # =43.0
        assert abs(agg["short_avg"] - round(expected_after, 1)) < 0.2
        assert agg["short_avg"] < raw_short_mean

    def test_no_downgrade_when_score_neutral(self):
        """value_anchor 中性分(50) 时不应触发降权，long_avg 等于原始均值。"""
        from statistics import mean

        experts = self._active_long_with_value_anchor(50)
        experts += [_make_expert(f"s{i}", 70, "short_term") for i in range(4)]
        agg = aggregate_votes(experts, horizon="short")

        raw_long_mean = mean([50, 70, 70, 70])  # =65.0
        assert abs(agg["long_avg"] - round(raw_long_mean, 1)) < 0.2

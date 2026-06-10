"""
experts/ API 单元测试：覆盖 8 位专家注册表、方向判定、一票否决。
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from experts import (
    EXPERT_REGISTRY,
    ExpertProfile,
    get_expert,
    list_experts,
    list_long_term_experts,
    list_short_term_experts,
    direction_from_score,
    apply_veto,
    DIRECTION_THRESHOLDS,
)
from experts.scoring import (
    score_from_dimensions,
    dimension_breakdown,
    score_expert,
)


# ═══════════════════════════════════════════════════════════════
# 1. 注册表完整性
# ═══════════════════════════════════════════════════════════════
class TestRegistry:
    def test_total_experts(self):
        assert len(EXPERT_REGISTRY) == 8

    def test_all_long_term_have_md(self):
        long_term = list_long_term_experts()
        assert len(long_term) == 4
        names = {e.name for e in long_term}
        assert names == {"buffett", "lynch", "soros", "duan_yongping"}

    def test_all_short_term_have_md(self):
        short_term = list_short_term_experts()
        assert len(short_term) == 4
        names = {e.name for e in short_term}
        assert names == {"xu_xiang", "zhao_laoge", "chaogu_yangjia", "zuoshou_xinyi"}

    def test_each_expert_has_md_file(self):
        for e in EXPERT_REGISTRY.values():
            md = PROJECT_ROOT / e.md_path
            assert md.exists(), f"Missing MD: {e.md_path}"

    def test_weights_sum_to_100(self):
        """每位专家的 5 维度权重之和应为 100%（允许 ±0.1 浮点误差）。"""
        for e in EXPERT_REGISTRY.values():
            total = sum(e.weights.values())
            assert abs(total - 100.0) < 0.1, (
                f"{e.name} weights sum to {total}, not 100"
            )

    def test_weights_have_5_dimensions(self):
        for e in EXPERT_REGISTRY.values():
            assert len(e.weights) == 5, f"{e.name} has {len(e.weights)} dimensions"

    def test_each_expert_has_veto(self):
        for e in EXPERT_REGISTRY.values():
            assert len(e.veto_conditions) >= 1, f"{e.name} has no veto conditions"

    def test_expert_profile_is_frozen(self):
        """ExpertProfile 应不可变（dataclass frozen=True）。"""
        e = get_expert("buffett")
        with pytest.raises(Exception):
            e.name = "another"  # type: ignore


# ═══════════════════════════════════════════════════════════════
# 2. 查询函数
# ═══════════════════════════════════════════════════════════════
class TestQueries:
    def test_get_expert_valid(self):
        e = get_expert("buffett")
        assert e is not None
        assert e.display_name == "巴菲特"

    def test_get_expert_invalid(self):
        assert get_expert("nobody") is None

    def test_list_experts_no_filter(self):
        assert len(list_experts()) == 8

    def test_list_experts_filter_long(self):
        long = list_experts("long_term")
        assert all(e.group == "long_term" for e in long)

    def test_list_experts_filter_short(self):
        short = list_experts("short_term")
        assert all(e.group == "short_term" for e in short)

    def test_list_experts_filter_unknown(self):
        assert list_experts("unknown_group") == []


# ═══════════════════════════════════════════════════════════════
# 3. 方向判定
# ═══════════════════════════════════════════════════════════════
class TestDirection:
    def test_strong_buy(self):
        assert direction_from_score(100) == "强烈看多"
        assert direction_from_score(70) == "强烈看多"

    def test_buy(self):
        assert direction_from_score(69) == "看多"
        assert direction_from_score(60) == "看多"

    def test_neutral(self):
        assert direction_from_score(59) == "中性"
        assert direction_from_score(40) == "中性"

    def test_sell(self):
        assert direction_from_score(39) == "看空"
        assert direction_from_score(30) == "看空"

    def test_strong_sell(self):
        assert direction_from_score(29) == "强烈看空"
        assert direction_from_score(0) == "强烈看空"
        assert direction_from_score(-5) == "强烈看空"  # 越界保护

    def test_thresholds_ordered(self):
        """阈值列表应严格降序。"""
        for i in range(len(DIRECTION_THRESHOLDS) - 1):
            assert DIRECTION_THRESHOLDS[i][0] > DIRECTION_THRESHOLDS[i + 1][0]


# ═══════════════════════════════════════════════════════════════
# 4. 一票否决
# ═══════════════════════════════════════════════════════════════
class TestVeto:
    def test_apply_veto_no_results_returns_all(self):
        """未提供 veto_results 时返回全部条件（不预判）。"""
        e = get_expert("buffett")
        conds = apply_veto(e, stock_data={})
        assert conds == e.veto_conditions

    def test_apply_veto_with_results(self):
        e = get_expert("buffett")
        results = {cond: i < 1 for i, cond in enumerate(e.veto_conditions)}
        triggered = apply_veto(e, stock_data={}, veto_results=results)
        # 只有第一条触发
        assert len(triggered) == 1
        assert triggered[0] == e.veto_conditions[0]

    def test_apply_veto_none_triggered(self):
        e = get_expert("buffett")
        results = {cond: False for cond in e.veto_conditions}
        triggered = apply_veto(e, stock_data={}, veto_results=results)
        assert triggered == []


# ═══════════════════════════════════════════════════════════════
# 5. 长短线权重特征
# ═══════════════════════════════════════════════════════════════
class TestWeightCharacteristics:
    def test_long_term_weights_basics(self):
        """长线 4 人中至少 3 人基本面+估值权重 > 50%（索罗斯例外，他偏宏观）。"""
        basics_counts = []
        for e in list_long_term_experts():
            basics = e.weights.get("基本面", 0) + e.weights.get("估值", 0)
            basics_counts.append(basics)
        high_basics = sum(1 for b in basics_counts if b >= 50)
        assert high_basics >= 3, (
            f"Only {high_basics}/4 long-term experts have basics+valuation >= 50% "
            f"({basics_counts})"
        )

    def test_short_term_weights_market_sentiment(self):
        """短线 4 人技术面+情绪/题材权重应 > 50%。"""
        for e in list_short_term_experts():
            tech_mood = (
                e.weights.get("技术面", 0) +
                e.weights.get("情绪", 0) +
                e.weights.get("情绪/题材", 0) +
                e.weights.get("情绪/反身性", 0)
            )
            assert tech_mood >= 50, (
                f"{e.name} short-term but tech+mood only {tech_mood}%"
            )

    def test_yangjia_most_sentiment_focused(self):
        """养家应该是 8 人中情绪权重最高的。"""
        yangjia = get_expert("chaogu_yangjia")
        yangjia_sentiment = yangjia.weights.get("情绪", 0)
        for e in EXPERT_REGISTRY.values():
            if e.name == "chaogu_yangjia":
                continue
            other_sentiment = (
                e.weights.get("情绪", 0) +
                e.weights.get("情绪/题材", 0) +
                e.weights.get("情绪/反身性", 0)
            )
            assert yangjia_sentiment >= other_sentiment, (
                f"养家 sentiment {yangjia_sentiment}% should be highest, "
                f"but {e.name} has {other_sentiment}%"
            )


# ═══════════════════════════════════════════════════════════════
# 6. score_from_dimensions（按权重加总）
# ═══════════════════════════════════════════════════════════════
class TestScoreFromDimensions:
    def test_all_neutral_50_returns_50(self):
        profile = get_expert("buffett")
        score = score_from_dimensions(profile, {})
        assert 49 <= score <= 51

    def test_all_100_returns_100(self):
        profile = get_expert("buffett")
        dims = {dim: 100 for dim in profile.weights}
        score = score_from_dimensions(profile, dims)
        assert score == 100.0

    def test_all_0_returns_0(self):
        profile = get_expert("buffett")
        dims = {dim: 0 for dim in profile.weights}
        score = score_from_dimensions(profile, dims)
        assert score == 0.0

    def test_clamp_over_100(self):
        """维度分超过 100 应被钳制。"""
        profile = get_expert("buffett")
        dims = {"基本面": 200, "估值": 100, "技术面": 100, "情绪": 100, "安全边际": 100}
        # 基本面钳制到 100，权重 42% → 贡献 42
        score = score_from_dimensions(profile, dims)
        # 总分 = 42 + 28 + 5 + 5 + 20 = 100
        assert score == 100.0

    def test_clamp_negative(self):
        profile = get_expert("buffett")
        dims = {"基本面": -50, "估值": 100, "技术面": 100, "情绪": 100, "安全边际": 100}
        # 基本面钳制到 0，权重 42% → 贡献 0
        score = score_from_dimensions(profile, dims)
        # 总分 = 0 + 28 + 5 + 5 + 20 = 58
        assert score == 58.0

    def test_weighted_total(self):
        """手动验证加权计算。"""
        profile = get_expert("buffett")
        dims = {"基本面": 80, "估值": 60, "技术面": 40, "情绪": 50, "安全边际": 70}
        # 80*0.42 + 60*0.28 + 40*0.05 + 50*0.05 + 70*0.20
        expected = 80 * 0.42 + 60 * 0.28 + 40 * 0.05 + 50 * 0.05 + 70 * 0.20
        score = score_from_dimensions(profile, dims)
        assert abs(score - expected) < 0.01


# ═══════════════════════════════════════════════════════════════
# 7. dimension_breakdown
# ═══════════════════════════════════════════════════════════════
class TestDimensionBreakdown:
    def test_returns_all_dimensions(self):
        profile = get_expert("buffett")
        dims = {dim: 80 for dim in profile.weights}
        breakdown = dimension_breakdown(profile, dims)
        assert set(breakdown.keys()) == set(profile.weights.keys())

    def test_breakdown_sums_to_total(self):
        profile = get_expert("buffett")
        dims = {dim: 80 for dim in profile.weights}
        breakdown = dimension_breakdown(profile, dims)
        total = sum(breakdown.values())
        # 与 score_from_dimensions 应有微小浮点差异（breakdown 四舍五入）
        score = score_from_dimensions(profile, dims)
        assert abs(total - score) < 0.1


# ═══════════════════════════════════════════════════════════════
# 8. score_expert（端到端）
# ═══════════════════════════════════════════════════════════════
class TestScoreExpert:
    def test_returns_complete_structure(self):
        result = score_expert(get_expert("buffett"), {})
        assert "score" in result
        assert "direction" in result
        assert "breakdown" in result
        assert "dim_scores" in result

    def test_empty_stock_data_neutral(self):
        """空数据应给出中性分（50 ± 1）。"""
        result = score_expert(get_expert("buffett"), {})
        assert 49 <= result["score"] <= 51
        assert result["direction"] == "中性"

    def test_good_stock_buffett_score_high(self):
        """好股票 + 巴菲特应给高分。"""
        stock = {
            "quote": {"pe": 12, "pb": 1.5, "change_pct": 0.5},
            "finance": {"roe": 25, "net_profit_yoy": 30, "revenue_yoy": 20,
                        "gross_margin": 60, "debt_ratio": 25},
            "kline_features": {"trend": 1, "rsi": 50, "macd_signal": 1},
        }
        result = score_expert(get_expert("buffett"), stock)
        assert result["score"] >= 60, f"Expected >= 60, got {result['score']}"
        assert result["direction"] in ("看多", "强烈看多")

    def test_bad_stock_buffett_score_low(self):
        """垃圾股 + 巴菲特应给低分。"""
        stock = {
            "quote": {"pe": 80, "pb": 8, "change_pct": -5},
            "finance": {"roe": 2, "net_profit_yoy": -20, "revenue_yoy": -10,
                        "gross_margin": 5, "debt_ratio": 85},
            "kline_features": {"trend": -1, "rsi": 25, "macd_signal": -1},
        }
        result = score_expert(get_expert("buffett"), stock)
        assert result["score"] <= 40, f"Expected <= 40, got {result['score']}"
        assert result["direction"] in ("看空", "中性", "强烈看空")

    def test_different_experts_diverge_on_sentiment(self):
        """同一只票，短线 4 人 vs 长线 4 人应有显著不同分数。"""
        stock = {
            "quote": {"pe": 18, "pb": 3, "change_pct": 8},  # 接近涨停
            "finance": {"roe": 12, "net_profit_yoy": 10, "revenue_yoy": 8,
                        "gross_margin": 35, "debt_ratio": 50},
            "kline_features": {"trend": 1, "rsi": 75, "macd_signal": 1},
            "market_features": {"limit_up_count": 70, "limit_down_count": 3},
        }
        long_term_scores = [
            score_expert(e, stock)["score"] for e in list_long_term_experts()
        ]
        short_term_scores = [
            score_expert(e, stock)["score"] for e in list_short_term_experts()
        ]
        long_avg = sum(long_term_scores) / len(long_term_scores)
        short_avg = sum(short_term_scores) / len(short_term_scores)
        # 短线团（情绪/题材驱动）应该比长线团更乐观
        # 因为市场情绪 70 涨停+仅 3 跌停是好环境
        assert short_avg > long_avg, (
            f"短线团 ({short_avg:.1f}) 应高于长线团 ({long_avg:.1f})，"
            f"因为短线重情绪/题材，当前情绪面好"
        )

    def test_score_in_valid_range(self):
        """无论输入什么，分数应在 0-100 之间。"""
        weird_stocks = [
            {},
            {"quote": {"pe": -100, "pb": -10}, "finance": {"roe": -50}},
            {"quote": {"pe": 9999, "pb": 999}, "finance": {"roe": 9999, "debt_ratio": 0}},
        ]
        for stock in weird_stocks:
            result = score_expert(get_expert("buffett"), stock)
            assert 0 <= result["score"] <= 100
            assert result["direction"] in (
                "强烈看空", "看空", "中性", "看多", "强烈看多",
            )

"""
experts/scoring.py 单元测试：覆盖专家专属评分函数 + score_expert_precise。
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import (
    EXPERT_REGISTRY,
    get_expert,
    list_long_term_experts,
    list_short_term_experts,
)
from experts.scoring import (
    score_from_dimensions,
    score_expert,
    score_expert_precise,
    compute_confidence_index,
)

# ═══════════════════════════════════════════════════════════════
# 测试数据
# ═══════════════════════════════════════════════════════════════

GOOD_STOCK = {
    "quote": {"pe": 12, "pb": 1.5, "circulating_cap": 80, "price": 25.0},
    "finance": {
        "ROEJQ": 25,
        "PARENTNETPROFITTZ": 30,
        "TOTALOPERATEREVETZ": 20,
        "XSMLL": 60,
        "ZCFZL": 25,
        "EPSJB": 2.0,
        "MGJYXJJE": 2.5,
    },
    "kline_features": {"trend": 1, "rsi": 50, "macd_signal": 1},
    "kline_data": {
        "closes": [20 + i * 0.3 for i in range(30)],
        "volumes": [1000000 + i * 10000 for i in range(30)],
    },
    "market_features": {
        "limit_up_count": 60,
        "limit_down_count": 5,
        "advance_ratio": 0.55,
        "break_rate": 0.2,
        "limit_up_30d_count": 3,
        "sector_limit_up_count": 2,
    },
}

BAD_STOCK = {
    "quote": {"pe": 80, "pb": 8, "circulating_cap": 500, "price": 10.0},
    "finance": {
        "ROEJQ": 2,
        "PARENTNETPROFITTZ": -20,
        "TOTALOPERATEREVETZ": -10,
        "XSMLL": 5,
        "ZCFZL": 85,
        "EPSJB": -0.5,
        "MGJYXJJE": -0.3,
    },
    "kline_features": {"trend": -1, "rsi": 25, "macd_signal": -1},
    "kline_data": {
        "closes": [30 - i * 0.5 for i in range(30)],
        "volumes": [500000 - i * 5000 for i in range(30)],
    },
    "market_features": {
        "limit_up_count": 10,
        "limit_down_count": 60,
        "advance_ratio": 0.15,
        "break_rate": 0.7,
        "limit_up_30d_count": 0,
        "sector_limit_up_count": 0,
    },
}

EMPTY_STOCK = {}


# ═══════════════════════════════════════════════════════════════
# 1. score_expert_precise 基础结构
# ═══════════════════════════════════════════════════════════════


class TestScorePreciseStructure:
    def test_returns_complete_structure(self):
        profile = get_expert("buffett")
        result = score_expert_precise(profile, EMPTY_STOCK)
        assert "score" in result
        assert "direction" in result
        assert "breakdown" in result
        assert "dim_scores" in result
        assert result["method"] == "precise"

    def test_score_in_valid_range(self):
        for name, profile in EXPERT_REGISTRY.items():
            for stock in [GOOD_STOCK, BAD_STOCK, EMPTY_STOCK]:
                result = score_expert_precise(profile, stock)
                assert (
                    0 <= result["score"] <= 100
                ), f"{name}: score {result['score']} out of range"
                assert result["direction"] in (
                    "强烈看多",
                    "看多",
                    "中性",
                    "看空",
                    "强烈看空",
                )

    def test_all_dimensions_scored(self):
        """所有权重维度都应有评分。"""
        for name, profile in EXPERT_REGISTRY.items():
            result = score_expert_precise(profile, GOOD_STOCK)
            for dim in profile.weights:
                assert dim in result["dim_scores"], f"{name}: missing dimension '{dim}'"

    def test_method_is_precise(self):
        profile = get_expert("buffett")
        result = score_expert_precise(profile, GOOD_STOCK)
        assert result["method"] == "precise"


# ═══════════════════════════════════════════════════════════════
# 2. 好股票高分 / 差股票低分
# ═══════════════════════════════════════════════════════════════


class TestScoreDirection:
    def test_good_stock_direction(self):
        """好股票应被多数专家看多。"""
        long_experts = list_long_term_experts()
        buy_count = 0
        for e in long_experts:
            result = score_expert_precise(e, GOOD_STOCK)
            if result["score"] >= 60:
                buy_count += 1
        # 长线专家中至少一半应看多
        assert (
            buy_count >= 2
        ), f"Only {buy_count}/4 long-term experts bullish on good stock"

    def test_bad_stock_direction(self):
        """差股票应被多数专家看空或中性（养家除外——逆向策略在冰点看多）。"""
        contrarian_experts = {"chaogu_yangjia"}  # 冰点逆向
        for name, profile in EXPERT_REGISTRY.items():
            result = score_expert_precise(profile, BAD_STOCK)
            if name in contrarian_experts:
                # 养家在冰点市场（高跌停+高炸板率）逆向看多是正确行为
                continue
            # 其他专家差股票不应强烈看多
            assert (
                result["direction"] != "强烈看多"
            ), f"{name}: strongly bullish on bad stock (score={result['score']})"

    def test_empty_stock_no_crash(self):
        """空数据不应崩溃，评分在有效范围内。"""
        for name, profile in EXPERT_REGISTRY.items():
            result = score_expert_precise(profile, EMPTY_STOCK)
            assert (
                0 <= result["score"] <= 100
            ), f"{name}: score {result['score']} out of range on empty data"
            assert result["direction"] in (
                "强烈看多",
                "看多",
                "中性",
                "看空",
                "强烈看空",
            )


# ═══════════════════════════════════════════════════════════════
# 3. 专家差异化验证
# ═══════════════════════════════════════════════════════════════


class TestExpertDivergence:
    def test_experts_diverge_on_different_stocks(self):
        """不同专家对同一股票应有差异化评分。"""
        # 热门短线股（弱基本面+强情绪）
        hot_stock = {
            "quote": {"pe": 100, "pb": 5, "circulating_cap": 60},
            "finance": {
                "ROEJQ": 5,
                "PARENTNETPROFITTZ": 10,
                "ZCFZL": 60,
                "EPSJB": 0.1,
                "MGJYXJJE": 0.05,
            },
            "kline_features": {"trend": 1, "rsi": 60, "macd_signal": 1},
            "market_features": {
                "limit_up_count": 90,
                "limit_down_count": 3,
                "advance_ratio": 0.7,
                "break_rate": 0.15,
                "limit_up_30d_count": 5,
                "sector_limit_up_count": 4,
            },
        }
        long_avg = (
            sum(
                score_expert_precise(e, hot_stock)["score"]
                for e in list_long_term_experts()
            )
            / 4
        )
        short_avg = (
            sum(
                score_expert_precise(e, hot_stock)["score"]
                for e in list_short_term_experts()
            )
            / 4
        )
        # 短线专家对弱基本面+强情绪的股票应评分更高
        assert short_avg > long_avg, (
            f"Short-term ({short_avg:.1f}) > long-term ({long_avg:.1f}) "
            f"on weak-fundamentals hot stock"
        )

    def test_yangjia_dominates_sentiment(self):
        """养家在冰点市场应评分最高（冰点=机会）。"""
        cold_market = {
            **BAD_STOCK,
            "market_features": {
                "limit_up_count": 5,
                "limit_down_count": 60,
                "advance_ratio": 0.10,
                "break_rate": 0.7,
            },
        }
        yangjia = get_expert("chaogu_yangjia")
        result = score_expert_precise(yangjia, cold_market)
        # 养家在冰点应该情绪维度给高分
        assert (
            result["dim_scores"].get("情绪", 0) >= 80
        ), f"Yangjia sentiment={result['dim_scores'].get('情绪')} in cold market"

    def test_buffett_values_roe(self):
        """巴菲特对高 ROE 股票应给高基本面分。"""
        profile = get_expert("buffett")
        result = score_expert_precise(profile, GOOD_STOCK)
        assert (
            result["dim_scores"]["基本面"] >= 75
        ), f"Buffett fundamentals={result['dim_scores']['基本面']} for ROE=25"

    def test_xu_xiang_requires_limit_up(self):
        """徐翔对无涨停基因的股票应给低技术面分。"""
        no_limit_up = {
            **EMPTY_STOCK,
            "quote": {"circulating_cap": 80},
            "market_features": {"limit_up_30d_count": 0},
        }
        profile = get_expert("xu_xiang")
        result = score_expert_precise(profile, no_limit_up)
        assert (
            result["dim_scores"]["技术面"] == 0
        ), f"Xu Xiang tech={result['dim_scores']['技术面']} with no limit-up"


# ═══════════════════════════════════════════════════════════════
# 4. score_expert_precise vs score_expert 一致性
# ═══════════════════════════════════════════════════════════════


class TestPreciseVsFallback:
    def test_both_in_range(self):
        """两套评分都应在 0-100 范围。"""
        for name, profile in EXPERT_REGISTRY.items():
            precise = score_expert_precise(profile, GOOD_STOCK)
            fallback = score_expert(profile, GOOD_STOCK)
            assert 0 <= precise["score"] <= 100
            assert 0 <= fallback["score"] <= 100

    def test_precise_method_field(self):
        """precise 评分应标记 method='precise'。"""
        profile = get_expert("buffett")
        result = score_expert_precise(profile, GOOD_STOCK)
        assert result["method"] == "precise"


# ═══════════════════════════════════════════════════════════════
# 5. compute_confidence_index
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 5. 精确阈值边界测试（防止重构意外修改）
# ═══════════════════════════════════════════════════════════════


class TestThresholdBoundaries:
    """验证各专家评分函数的精确阈值边界。"""

    @pytest.mark.parametrize(
        "roe,expected",
        [
            (25, 100),
            (20, 100),
            (19.9, 75),
            (15, 75),
            (14.9, 40),
            (10, 40),
            (9.9, 0),
            (0, 0),
        ],
    )
    def test_buffett_fundamentals_roe(self, roe, expected):
        from experts.scoring.buffett import score

        result = score({"finance": {"ROEJQ": roe}})
        assert result["基本面"] == expected

    @pytest.mark.parametrize(
        "pe,expected",
        [
            (10, 100),
            (15, 100),
            (15.1, 60),
            (25, 60),
            (25.1, 25),
            (40, 25),
            (40.1, 0),
            (80, 0),
        ],
    )
    def test_buffett_valuation_pe(self, pe, expected):
        from experts.scoring.buffett import score

        result = score({"quote": {"pe": pe}})
        assert result["估值"] == expected

    @pytest.mark.parametrize(
        "peg,expected",
        [
            (0.3, 100),
            (0.5, 100),
            (0.51, 80),
            (1.0, 80),
            (1.01, 50),
            (1.5, 50),
            (1.51, 30),
            (2.0, 30),
            (2.01, 0),
            (3.0, 0),
        ],
    )
    def test_lynch_valuation_peg(self, peg, expected):
        from experts.scoring.lynch import score

        growth = 20
        pe = peg * growth
        result = score(
            {
                "quote": {"pe": pe},
                "finance": {"PARENTNETPROFITTZ": growth},
            }
        )
        assert result["估值"] == expected

    @pytest.mark.parametrize(
        "cap,expected",
        [
            (80, 100),
            (30, 100),
            (150, 100),
            (151, 60),
            (300, 60),
            (501, 0),
            (29, 0),
        ],
    )
    def test_xu_xiang_valuation_cap(self, cap, expected):
        from experts.scoring.xu_xiang import score

        result = score({"quote": {"circulating_cap": cap}})
        assert result["估值"] == expected

    @pytest.mark.parametrize(
        "limit_up,limit_down,break_rate,expected",
        [
            (5, 60, 0.7, 100),  # 冰点
            (100, 3, 0.15, 80),  # 主升
            (50, 15, 0.3, 50),  # 震荡
            (10, 40, 0.5, 0),  # 退潮
        ],
    )
    def test_yangjia_sentiment_cycle(self, limit_up, limit_down, break_rate, expected):
        from experts.scoring.chaogu_yangjia import score

        result = score(
            {
                "market_features": {
                    "limit_up_count": limit_up,
                    "limit_down_count": limit_down,
                    "break_rate": break_rate,
                },
            }
        )
        assert result["情绪"] == expected

    @pytest.mark.parametrize(
        "total_amount,limit_down,expected_risk",
        [
            (3000, 5, 20),  # 流动性枯竭
            (6999, 5, 20),  # 刚好低于阈值
            (7000, 5, 80),  # 刚好达到阈值，流动性正常
            (10000, 5, 80),  # 流动性充裕
            (0, 5, 80),  # total_amount=0 不触发流动性判断
        ],
    )
    def test_soros_liquidity_floor(self, total_amount, limit_down, expected_risk):
        from experts.scoring.soros import score

        result = score(
            {
                "market_features": {
                    "total_amount": total_amount,
                    "limit_down_count": limit_down,
                },
            }
        )
        assert result["风险"] == expected_risk, (
            f"Soros risk={result['风险']} for total_amount={total_amount}, "
            f"expected={expected_risk}"
        )


class TestPEPercentileAdjustment:
    """PE 历史分位调整：仅在基础分及格时才奖励历史低估。"""

    def test_garbage_stock_no_bonus(self):
        """PE=45（垃圾股）+ pe_percentile=15，不应加 15 分（基础分 0 < 25）。"""
        from experts.scoring.buffett import score

        result = score(
            {
                "quote": {"pe": 45, "pe_percentile": 15},
            }
        )
        assert (
            result["估值"] == 0
        ), f"PE=45 + percentile=15 should stay 0, got {result['估值']}"

    def test_reasonable_stock_gets_bonus(self):
        """PE=20（合理估值）+ pe_percentile=15，应加 15 分（基础分 60 >= 25）。"""
        from experts.scoring.buffett import score

        result_no_pct = score({"quote": {"pe": 20}})
        result_with_pct = score(
            {
                "quote": {"pe": 20, "pe_percentile": 15},
            }
        )
        assert (
            result_with_pct["估值"] == result_no_pct["估值"] + 15
        ), f"Expected +15 bonus, got {result_with_pct['估值']} vs {result_no_pct['估值']}"


class TestZhaoLaogeRiskGradual:
    """赵老哥风险评分：破20日线渐进式扣分（龙头低吸风格）。"""

    def _make_stock_with_closes(self, closes):
        """构造指定收盘价序列的股票数据。"""
        return {
            "kline_data": {
                "closes": closes,
                "volumes": [1000000] * len(closes),
            },
        }

    def test_above_ma20_risk_80(self):
        """close = ma20 * 1.02（高于20日线），risk=80。"""
        from experts.scoring.zhao_laoge import score

        base_price = 10.0
        closes = [base_price] * 20 + [base_price * 1.02]
        result = score(self._make_stock_with_closes(closes))
        assert result["风险"] == 80

    def test_shallow_break_ma20_risk_60(self):
        """close = ma20 * 0.98（浅破2%），risk=60。"""
        from experts.scoring.zhao_laoge import score

        base_price = 10.0
        closes = [base_price] * 20 + [base_price * 0.98]
        result = score(self._make_stock_with_closes(closes))
        assert result["风险"] == 60

    def test_moderate_break_ma20_risk_30(self):
        """close = ma20 * 0.92（中破8%），risk=30。"""
        from experts.scoring.zhao_laoge import score

        base_price = 10.0
        closes = [base_price] * 20 + [base_price * 0.92]
        result = score(self._make_stock_with_closes(closes))
        assert result["风险"] == 30

    def test_deep_break_ma20_risk_10(self):
        """close = ma20 * 0.85（深破15%），risk=10。"""
        from experts.scoring.zhao_laoge import score

        base_price = 10.0
        closes = [base_price] * 20 + [base_price * 0.85]
        result = score(self._make_stock_with_closes(closes))
        assert result["风险"] == 10

    def test_insufficient_data_risk_60(self):
        """数据不足20根K线，risk=60（回退默认值）。"""
        from experts.scoring.zhao_laoge import score

        closes = [10.0] * 10
        result = score(self._make_stock_with_closes(closes))
        assert result["风险"] == 60


class TestConfidenceIndex:
    def test_high_consistency_high_score(self):
        """一致高分应产生高信心指数。"""
        scores = [75, 78, 72, 76, 74, 77, 73, 75]
        ci = compute_confidence_index(scores, 75.0, 0.0)
        assert ci >= 60

    def test_low_consistency_low_score(self):
        """严重分歧应降低信心指数。"""
        scores = [90, 10, 80, 20, 70, 30, 60, 40]
        ci = compute_confidence_index(scores, 50.0, 0.0)
        assert ci < 60

    def test_calibration_factor_positive_boost(self):
        """正校准因子应提升信心指数。"""
        scores = [65, 68, 62, 66, 64, 67, 63, 65]
        ci_base = compute_confidence_index(scores, 65.0, 0.0)
        ci_cal = compute_confidence_index(scores, 65.0, 0.5)
        assert ci_cal > ci_base

    def test_calibration_factor_negative_reduce(self):
        """负校准因子应降低信心指数。"""
        scores = [65, 68, 62, 66, 64, 67, 63, 65]
        ci_base = compute_confidence_index(scores, 65.0, 0.0)
        ci_cal = compute_confidence_index(scores, 65.0, -0.5)
        assert ci_cal < ci_base

    def test_empty_scores(self):
        """空评分列表应返回中性信心。"""
        ci = compute_confidence_index([], 50.0, 0.0)
        assert 40 <= ci <= 60

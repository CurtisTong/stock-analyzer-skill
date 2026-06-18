"""
动量派（momentum_trader）评分函数单元测试。

人设要点：技术面 40% + 情绪/资金 25% + 风险 20% + 基本面 10% + 估值 5%
持仓周期：日/周/月（short_term）

核心场景：
- 完美多头排列 + 放量突破 + 板块共振 → 强烈看多
- 空头排列 → 看空
- 流动性枯竭 → 风险维度极低
- 亏损股 → 基本面低分（避免价值陷阱）
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.scoring import momentum_trader
from experts.registry import EXPERT_REGISTRY


def _build_kline(prices, base_volume=1_000_000):
    """构造最小可用 kline_data：closes/volumes/highs。"""
    closes = list(prices)
    highs = [p * 1.01 for p in closes]
    lows = [p * 0.99 for p in closes]
    volumes = [base_volume] * len(closes)
    return {"closes": closes, "volumes": volumes, "highs": highs, "lows": lows}


class TestMomentumTraderScore:
    """动量派评分函数测试。"""

    def test_returns_dict_with_all_dimensions(self):
        result = momentum_trader.score({"quote": {}, "finance": {}})
        assert isinstance(result, dict)
        assert set(result.keys()) == {"基本面", "估值", "技术面", "情绪/资金", "风险"}

    def test_all_in_range(self):
        result = momentum_trader.score({"quote": {}, "finance": {}})
        for v in result.values():
            assert 0 <= v <= 100, f"{v} 超出 [0, 100]"

    def test_perfect_uptrend_high_score(self):
        """完美多头排列 + 突破 60 日高 + 板块共振 → 技术面应接近满分。"""
        prices = [10 + i * 0.1 for i in range(120)]  # 单调上升 120 日
        result = momentum_trader.score({
            "quote": {"pe": 30, "amount": 10},
            "finance": {"ROEJQ": 15, "PARENTNETPROFITTZ": 10, "TOTALOPERATEREVETZ": 8},
            "kline_data": _build_kline(prices),
            "kline_features": {"trend": 1},
            "market_features": {
                "limit_up_count": 60,
                "sector_limit_up_count": 5,
                "advance_ratio": 0.6,
            },
        })
        assert result["技术面"] >= 90, f"完美多头技术面应≥90，实际 {result['技术面']}"

    def test_downtrend_low_score(self):
        """空头排列 → 技术面应接近 0。"""
        prices = [22 - i * 0.1 for i in range(120)]  # 单调下跌 120 日
        result = momentum_trader.score({
            "quote": {"pe": 30, "amount": 10},
            "finance": {"ROEJQ": 15},
            "kline_data": _build_kline(prices),
            "kline_features": {"trend": -1},
        })
        assert result["技术面"] <= 10, f"空头排列技术面应≤10，实际 {result['技术面']}"

    def test_loss_making_company_low_fundamental(self):
        """亏损股 → 基本面低分（动量派避免价值陷阱）。"""
        result = momentum_trader.score({
            "quote": {"pe": -5, "amount": 10},
            "finance": {"ROEJQ": -10, "PARENTNETPROFITTZ": -50},
            "kline_data": _build_kline([10 + i * 0.1 for i in range(120)]),
        })
        assert result["基本面"] <= 20, f"亏损股基本面应≤20，实际 {result['基本面']}"

    def test_liquidity_starved_high_risk_penalty(self):
        """流动性枯竭 → 风险维度应极低（动量派无法止损）。"""
        result = momentum_trader.score({
            "quote": {"amount": 0.5},  # 5 千万，远低于 2 亿阈值
            "finance": {"ROEJQ": 15},
            "kline_data": _build_kline([10 + i * 0.1 for i in range(120)]),
        })
        assert result["风险"] <= 30, f"流动性枯竭风险应≤30，实际 {result['风险']}"

    def test_liquid_stock_low_risk_penalty(self):
        """流动性充裕 → 风险维度应较高。"""
        result = momentum_trader.score({
            "quote": {"amount": 20},  # 20 亿
            "finance": {"ROEJQ": 15},
            "kline_data": _build_kline([10 + i * 0.1 for i in range(120)]),
        })
        assert result["风险"] >= 60, f"流动性充裕风险应≥60，实际 {result['风险']}"

    def test_sector_resonance_sentiment_bonus(self):
        """板块同涨 ≥3 家涨停 → 情绪/资金加分。"""
        prices = [10 + i * 0.05 for i in range(120)]
        result = momentum_trader.score({
            "quote": {"pe": 30, "amount": 10},
            "finance": {"ROEJQ": 15},
            "kline_data": _build_kline(prices),
            "market_features": {
                "limit_up_count": 50,
                "sector_limit_up_count": 5,
                "advance_ratio": 0.55,
            },
        })
        # 板块共振应把情绪/资金推到 ≥70
        assert result["情绪/资金"] >= 60, f"板块共振情绪/资金应≥60，实际 {result['情绪/资金']}"

    def test_isolated_breakthrough_sentiment_penalty(self):
        """孤立突破（板块无涨停）→ 情绪/资金扣分。"""
        prices = [10 + i * 0.05 for i in range(120)]
        result = momentum_trader.score({
            "quote": {"pe": 30, "amount": 10},
            "finance": {"ROEJQ": 15},
            "kline_data": _build_kline(prices),
            "market_features": {
                "limit_up_count": 10,
                "sector_limit_up_count": 0,
                "advance_ratio": 0.3,
            },
        })
        # 孤立突破 + 缩量 + 弱市 → 情绪/资金应偏低
        assert result["情绪/资金"] <= 50, f"孤立突破情绪/资金应≤50，实际 {result['情绪/资金']}"

    def test_breakthrough_60d_high_tech_bonus(self):
        """突破 60 日高 → 技术面应给额外加分。"""
        prices = [10] * 60 + [12] * 60  # 前 60 日横盘 10，后 60 日 12
        result = momentum_trader.score({
            "quote": {"pe": 30, "amount": 10},
            "finance": {"ROEJQ": 15},
            "kline_data": _build_kline(prices),
        })
        # 后段已突破前期高 10，但均线尚未完全多头（60 日均值 11），技术面应在 40-80 区间
        assert 40 <= result["技术面"] <= 90, f"突破 60 日高技术面应在 40-90，实际 {result['技术面']}"


class TestMomentumTraderProfile:
    """注册表与 yaml 一致性测试。"""

    def test_profile_registered(self):
        assert "momentum_trader" in EXPERT_REGISTRY

    def test_profile_is_active_short_term(self):
        p = EXPERT_REGISTRY["momentum_trader"]
        assert p.active is True
        assert p.group == "short_term"

    def test_weights_sum_to_100(self):
        p = EXPERT_REGISTRY["momentum_trader"]
        assert abs(sum(p.weights.values()) - 100.0) < 0.5

    def test_tech_weight_dominant(self):
        """技术面权重应最高（动量派核心）。"""
        p = EXPERT_REGISTRY["momentum_trader"]
        max_dim = max(p.weights, key=p.weights.get)
        assert max_dim == "技术面", f"技术面应为最高权重，实际最高为 {max_dim}"

    def test_veto_conditions_present(self):
        p = EXPERT_REGISTRY["momentum_trader"]
        assert len(p.veto_conditions) >= 3

    def test_yaml_round_trip(self):
        """registry → yaml → registry 字段完全一致。"""
        from experts.yaml_loader import round_trip
        assert round_trip(EXPERT_REGISTRY["momentum_trader"]) is True


class TestMomentumTraderScoringIntegration:
    """精确评分路径测试。"""

    def test_score_expert_precise_returns_momentum_result(self):
        from experts.scoring import score_expert_precise
        prices = [10 + i * 0.1 for i in range(120)]
        data = {
            "quote": {"pe": 30, "amount": 10},
            "finance": {"ROEJQ": 15, "PARENTNETPROFITTZ": 10, "TOTALOPERATEREVETZ": 8},
            "kline_data": _build_kline(prices),
            "market_features": {
                "limit_up_count": 60,
                "sector_limit_up_count": 5,
                "advance_ratio": 0.6,
            },
        }
        result = score_expert_precise(EXPERT_REGISTRY["momentum_trader"], data)
        # 完美多头 + 流动性 + 板块共振 + 略高 ROE → 应强烈看多
        assert result["score"] >= 60, f"完美场景应≥60分，实际 {result['score']}"
        assert result["direction"] in ("看多", "强烈看多")
        assert result["method"] == "precise"

    def test_score_with_reasoning_works(self):
        from experts.scoring import score_expert_with_reasoning
        result = score_expert_with_reasoning(
            EXPERT_REGISTRY["momentum_trader"],
            {"quote": {"amount": 10}, "finance": {"ROEJQ": 15}, "kline_data": _build_kline([10 + i * 0.1 for i in range(120)])},
        )
        assert "scores" in result
        assert "reasoning" in result
        assert "dimensions" in result
        assert len(result["reasoning"]) == 5  # 5 个维度

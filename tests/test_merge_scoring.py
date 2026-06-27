"""
测试 v2.1.1 合并型 scoring 函数：value_anchor/topic_leader/emotion_tech。

核心验证：
1. 合并函数能正常返回 0-100 范围的 dim_scores
2. 合并函数的输出 = legacy 函数的加权平均
3. 所有维度都来自 legacy 函数的并集
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.scoring import (
    value_anchor,
    topic_leader,
    emotion_tech,
    buffett,
    duan_yongping,
    xu_xiang,
    zhao_laoge,
    chaogu_yangjia,
    zuoshou_xinyi,
)
from experts.scoring._merge import weighted_merge

# ═══════════════════════════════════════════════════════════════
# weighted_merge helper 测试
# ═══════════════════════════════════════════════════════════════


class TestWeightedMerge:
    def test_empty_returns_empty(self):
        """空输入返回空 dict。"""
        assert weighted_merge([]) == {}
        assert weighted_merge([], weights=[]) == {}

    def test_single_expert_identity(self):
        """单 expert 时返回原 dict（权重归一为 1.0）。"""
        result = weighted_merge([{"基本面": 80, "估值": 60}])
        assert result == {"基本面": 80, "估值": 60}

    def test_two_expert_equal_weight(self):
        """两个 expert 等权：取算术平均。"""
        result = weighted_merge(
            [
                {"基本面": 80, "估值": 60},
                {"基本面": 60, "估值": 40},
            ]
        )
        assert result == {"基本面": 70.0, "估值": 50.0}

    def test_two_expert_custom_weight(self):
        """两个 expert 不等权：按权重平均。"""
        result = weighted_merge(
            [
                {"基本面": 80},
                {"基本面": 60},
            ],
            weights=[0.7, 0.3],
        )
        assert result == {"基本面": 74.0}

    def test_missing_dim_defaults_to_50(self):
        """缺失维度用 50 中性分填补。"""
        result = weighted_merge(
            [
                {"基本面": 80},
                {"估值": 60},
            ]
        )
        # 基本面: (80*0.5 + 50*0.5) = 65
        # 估值: (50*0.5 + 60*0.5) = 55
        assert result["基本面"] == 65.0
        assert result["估值"] == 55.0

    def test_weights_normalized(self):
        """权重自动归一化（sum 不必 = 1）。"""
        result = weighted_merge(
            [
                {"基本面": 80},
                {"基本面": 60},
            ],
            weights=[2.0, 2.0],
        )  # 等权，归一化后 0.5/0.5
        assert result == {"基本面": 70.0}

    def test_result_in_range(self):
        """所有输出维度值在 0-100 范围。"""
        result = weighted_merge(
            [
                {"dim1": 0, "dim2": 100},
                {"dim1": 100, "dim2": 0},
            ]
        )
        for v in result.values():
            assert 0 <= v <= 100


# ═══════════════════════════════════════════════════════════════
# value_anchor (buffett + duan_yongping)
# ═══════════════════════════════════════════════════════════════


class TestValueAnchor:
    """合并 buffett(0.55) + duan_yongping(0.45)。"""

    @pytest.fixture
    def sample_data(self):
        return {
            "quote": {"pe": 15, "pb": 2, "circulating_cap": 500},
            "finance": {"ROEJQ": 18, "ZCFZL": 40, "EPSJB": 2.5, "MGJYXJJE": 1.8},
            "kline_features": {"trend": 0.5, "rsi": 55, "macd_signal": 0.1},
        }

    def test_returns_dict(self, sample_data):
        """返回 dict。"""
        result = value_anchor.score(sample_data)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_in_range(self, sample_data):
        """所有维度在 0-100 范围。"""
        result = value_anchor.score(sample_data)
        for dim, v in result.items():
            assert 0 <= v <= 100, f"{dim}={v} out of range"

    def test_matches_weighted_average(self, sample_data):
        """合并结果 = buffett × 0.55 + duan_yongping × 0.45。"""
        buffett_score = buffett.score(sample_data)
        dyh_score = duan_yongping.score(sample_data)
        va_score = value_anchor.score(sample_data)

        for dim in buffett_score:
            if dim in dyh_score:
                expected = round(buffett_score[dim] * 0.55 + dyh_score[dim] * 0.45, 1)
                actual = va_score.get(dim, 50.0)
                assert abs(actual - expected) < 0.1, f"{dim}: {actual} != {expected}"

    def test_handles_empty_stock_data(self):
        """空 stock_data 不报错。"""
        result = value_anchor.score({})
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# topic_leader (xu_xiang + zhao_laoge)
# ═══════════════════════════════════════════════════════════════


class TestTopicLeader:
    """合并 xu_xiang(0.5) + zhao_laoge(0.5)。"""

    @pytest.fixture
    def sample_data(self):
        return {
            "quote": {"pe": 50, "pb": 5, "circulating_cap": 80},
            "finance": {"ROEJQ": 8, "ZCFZL": 60},
            "kline_features": {"trend": 1.0, "rsi": 75, "macd_signal": 0.5},
            "market_features": {
                "limit_up_count": 60,
                "limit_down_count": 5,
                "advance_ratio": 0.7,
                "nh_nl_ratio": 1.5,
            },
            "kline_data": {
                "closes": [10, 11, 12, 13, 14],
                "volumes": [100, 120, 150, 180, 200],
            },
        }

    def test_returns_dict(self, sample_data):
        result = topic_leader.score(sample_data)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_in_range(self, sample_data):
        result = topic_leader.score(sample_data)
        for dim, v in result.items():
            assert 0 <= v <= 100

    def test_matches_weighted_average_or_veto(self, sample_data):
        """合并评分 = 加权平均，或否决逻辑（任一子专家 < 10 分时取最低分）。"""
        xx_score = xu_xiang.score(sample_data)
        zl_score = zhao_laoge.score(sample_data)
        tl_score = topic_leader.score(sample_data)

        for dim in xx_score:
            if dim in zl_score:
                xx_v = xx_score[dim]
                zl_v = zl_score[dim]
                min_v = min(xx_v, zl_v)
                if min_v < 10:
                    # 否决逻辑：取最低分
                    expected = round(max(0.0, min_v), 1)
                else:
                    expected = round(xx_v * 0.5 + zl_v * 0.5, 1)
                actual = tl_score.get(dim, 50.0)
                assert abs(actual - expected) < 0.1, f"{dim}: {actual} != {expected}"


# ═══════════════════════════════════════════════════════════════
# emotion_tech (chaogu_yangjia + zuoshou_xinyi)
# ═══════════════════════════════════════════════════════════════


class TestEmotionTech:
    """合并 chaogu_yangjia(0.5) + zuoshou_xinyi(0.5)。"""

    @pytest.fixture
    def sample_data(self):
        return {
            "quote": {"pe": 60, "pb": 6, "circulating_cap": 50},
            "finance": {"ROEJQ": 5, "ZCFZL": 70},
            "kline_features": {"trend": 0.8, "rsi": 80, "macd_signal": 0.3},
            "market_features": {
                "limit_up_count": 30,
                "limit_down_count": 20,
                "advance_ratio": 0.5,
                "nh_nl_ratio": 0.8,
            },
            "kline_data": {
                "closes": [15, 14, 13, 12, 11],
                "volumes": [100, 200, 300, 400, 500],
            },
        }

    def test_returns_dict(self, sample_data):
        result = emotion_tech.score(sample_data)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_in_range(self, sample_data):
        result = emotion_tech.score(sample_data)
        for dim, v in result.items():
            assert 0 <= v <= 100

    def test_matches_weighted_average_or_veto(self, sample_data):
        """合并评分 = 加权平均，或否决逻辑（任一子专家 < 10 分时取最低分）。"""
        cyj_score = chaogu_yangjia.score(sample_data)
        zsxy_score = zuoshou_xinyi.score(sample_data)
        et_score = emotion_tech.score(sample_data)

        for dim in cyj_score:
            if dim in zsxy_score:
                cyj_v = cyj_score[dim]
                zsxy_v = zsxy_score[dim]
                min_v = min(cyj_v, zsxy_v)
                if min_v < 10:
                    # 否决逻辑：取最低分
                    expected = round(max(0.0, min_v), 1)
                else:
                    expected = round(cyj_v * 0.5 + zsxy_v * 0.5, 1)
                actual = et_score.get(dim, 50.0)
                assert abs(actual - expected) < 0.1, f"{dim}: {actual} != {expected}"

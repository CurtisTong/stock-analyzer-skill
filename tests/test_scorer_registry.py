"""
experts/scoring 注册表测试：验证 8 位专家评分函数都正确注册。
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import EXPERT_REGISTRY, get_expert
from experts.scoring import (
    score_expert_precise,
    _EXPERT_SCORING_FUNCTIONS,
)

# ═══════════════════════════════════════════════════════════════
# 1. 注册表完整性
# ═══════════════════════════════════════════════════════════════


class TestScorerRegistry:
    """验证所有专家评分函数都已注册。"""

    def test_all_experts_registered(self):
        """v2.2.0 起：8 legacy + 6 extended + 1 momentum = 15。"""
        expected_experts = {
            "buffett",
            "lynch",
            "soros",
            "duan_yongping",
            "xu_xiang",
            "zhao_laoge",
            "chaogu_yangjia",
            "zuoshou_xinyi",
            # v2.1.0 扩展视角
            "value_anchor",
            "topic_leader",
            "emotion_tech",
            "sector_specialist",
            "institution",
            "risk_manager",
            # v2.2.0 新增：动量派
            "momentum_trader",
        }
        registered = set(_EXPERT_SCORING_FUNCTIONS.keys())
        assert registered == expected_experts, (
            f"Missing: {expected_experts - registered}, "
            f"Extra: {registered - expected_experts}"
        )

    def test_registry_count(self):
        """v2.2.0：15 个专家（8 legacy + 6 extended + 1 momentum）。"""
        assert len(_EXPERT_SCORING_FUNCTIONS) == 15

    def test_all_scoring_functions_callable(self):
        """所有注册的评分函数都应可调用。"""
        for name, fn in _EXPERT_SCORING_FUNCTIONS.items():
            assert callable(fn), f"{name}: scoring function is not callable"

    @pytest.mark.parametrize("expert_name", list(EXPERT_REGISTRY.keys()))
    def test_expert_has_scorer(self, expert_name):
        """每位专家在 EXPERT_REGISTRY 中都应有对应的评分函数。"""
        assert (
            expert_name in _EXPERT_SCORING_FUNCTIONS
        ), f"{expert_name} in EXPERT_REGISTRY but not in _EXPERT_SCORING_FUNCTIONS"


# ═══════════════════════════════════════════════════════════════
# 2. 评分函数独立性
# ═══════════════════════════════════════════════════════════════


class TestScorerIndependence:
    """验证各专家评分函数独立工作。"""

    EMPTY_STOCK = {}
    GOOD_STOCK = {
        "quote": {"pe": 12, "pb": 1.5, "circulating_cap": 80, "price": 25.0},
        "finance": {
            "ROEJQ": 25,
            "PARENTNETPROFITTZ": 30,
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

    @pytest.mark.parametrize("expert_name", list(_EXPERT_SCORING_FUNCTIONS.keys()))
    def test_scorer_returns_dict(self, expert_name):
        """每位专家的评分函数应返回 dict。"""
        fn = _EXPERT_SCORING_FUNCTIONS[expert_name]
        result = fn(self.EMPTY_STOCK)
        assert isinstance(result, dict), f"{expert_name}: did not return dict"

    @pytest.mark.parametrize("expert_name", list(_EXPERT_SCORING_FUNCTIONS.keys()))
    def test_scorer_returns_valid_dimensions(self, expert_name):
        """每位专家的评分函数应返回正确数量的维度。"""
        profile = get_expert(expert_name)
        fn = _EXPERT_SCORING_FUNCTIONS[expert_name]
        result = fn(self.GOOD_STOCK)
        # 结果应包含至少一个维度
        assert len(result) > 0, f"{expert_name}: returned empty dict"
        # 所有返回的维度值应在 0-100 范围
        for dim, score in result.items():
            assert (
                0 <= score <= 100
            ), f"{expert_name}.{dim}={score} out of range [0, 100]"

    @pytest.mark.parametrize("expert_name", list(_EXPERT_SCORING_FUNCTIONS.keys()))
    def test_scorer_handles_empty_data(self, expert_name):
        """每位专家的评分函数应能处理空数据。"""
        fn = _EXPERT_SCORING_FUNCTIONS[expert_name]
        result = fn(self.EMPTY_STOCK)
        assert isinstance(result, dict)
        for dim, score in result.items():
            assert (
                0 <= score <= 100
            ), f"{expert_name}.{dim}={score} out of range on empty data"


# ═══════════════════════════════════════════════════════════════
# 3. score_expert_precise 端到端
# ═══════════════════════════════════════════════════════════════


class TestPreciseIntegration:
    """验证 score_expert_precise 通过注册表正确调用。"""

    def test_precise_uses_registry(self):
        """score_expert_precise 应使用注册表中的函数。"""
        profile = get_expert("buffett")
        result = score_expert_precise(profile, {})
        assert result["method"] == "precise"

    def test_precise_all_experts(self):
        """所有专家都应通过 precise 路径评分。"""
        for name, profile in EXPERT_REGISTRY.items():
            result = score_expert_precise(profile, {})
            assert (
                result["method"] == "precise"
            ), f"{name}: method={result['method']}, expected 'precise'"
            assert "score" in result
            assert "direction" in result
            assert "breakdown" in result
            assert "dim_scores" in result


# ═══════════════════════════════════════════════════════════════
# 4. 公共 API 导入
# ═══════════════════════════════════════════════════════════════


class TestPublicImports:
    """验证公共 API 的导入路径。"""

    def test_import_score_from_dimensions(self):
        """from experts.scoring import score_from_dimensions 应正常工作。"""
        from experts.scoring import score_from_dimensions

        assert callable(score_from_dimensions)

    def test_import_dimension_breakdown(self):
        """from experts.scoring import dimension_breakdown 应正常工作。"""
        from experts.scoring import dimension_breakdown

        assert callable(dimension_breakdown)

    def test_import_score_expert(self):
        """from experts.scoring import score_expert 应正常工作。"""
        from experts.scoring import score_expert

        assert callable(score_expert)

    def test_import_score_expert_precise(self):
        """from experts.scoring import score_expert_precise 应正常工作。"""
        from experts.scoring import score_expert_precise

        assert callable(score_expert_precise)

    def test_import_compute_confidence_index(self):
        """from experts.scoring import compute_confidence_index 应正常工作。"""
        from experts.scoring import compute_confidence_index

        assert callable(compute_confidence_index)

    def test_expert_score_functions_directly_importable(self):
        """各专家评分函数可从子模块直接导入。"""
        from experts.scoring.buffett import score as buffett_score
        from experts.scoring.lynch import score as lynch_score
        from experts.scoring.soros import score as soros_score
        from experts.scoring.zhao_laoge import score as zhao_score

        assert callable(buffett_score)
        assert callable(lynch_score)
        assert callable(soros_score)
        assert callable(zhao_score)

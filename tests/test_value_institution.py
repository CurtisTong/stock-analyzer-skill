"""测试 experts/scoring/value_institution.py：价值机构锚（合并）评分。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.scoring import value_institution


def _make_stock_data():
    return {
        "quote": {"pe": 15, "price": 100, "code": "sh600519", "pb": 3.0},
        "finance": {"ROEJQ": 20, "debt_ratio": 30, "fcf_yield": 10,
                    "net_profit_yoy": 15, "roe": 20,
                    "revenue_yoy": 10, "gross_margin": 30},
        "kline_features": {"ma20": 95, "trend": 1, "volatility": 0.2, "rsi": 60},
        "market_features": {"vix": 18, "sentiment": "neutral"},
    }


class TestGetBuffettWeights:
    def test_default_weights(self):
        """无 EXPERT_REGISTRY 时回退默认权重。"""
        with patch("experts.registry.EXPERT_REGISTRY", {}):
            weights = value_institution._get_buffett_weights()
        assert abs(weights["基本面"] - 0.42) < 0.01
        assert abs(weights["估值"] - 0.28) < 0.01

    def test_from_registry(self):
        """从注册表读取 buffett 权重。"""
        fake_profile = SimpleNamespace(weights={"基本面": 50, "估值": 30, "技术面": 5,
                                                 "情绪": 5, "安全边际": 10})
        with patch("experts.registry.EXPERT_REGISTRY", {"buffett": fake_profile}):
            weights = value_institution._get_buffett_weights()
        assert abs(weights["基本面"] - 0.50) < 0.01


class TestComputeBuffettSubScore:
    def test_basic(self):
        dims = {"基本面": 80, "估值": 70, "技术面": 50, "情绪": 50, "安全边际": 60}
        with patch("experts.registry.EXPERT_REGISTRY", {}):
            score = value_institution._compute_buffett_sub_score(dims)
        # 0.42*80 + 0.28*70 + 0.05*50 + 0.05*50 + 0.20*60 = 71.1
        assert 60 < score < 80

    def test_empty_dims(self):
        """空 dims → 0。"""
        with patch("experts.registry.EXPERT_REGISTRY", {}):
            score = value_institution._compute_buffett_sub_score({})
        assert score == 0


class TestValueInstitutionScore:
    def test_basic(self):
        """基础评分：value_anchor + institution 加权。"""
        with patch("experts.scoring.value_anchor.score",
                  return_value={"基本面": 80, "估值": 70, "技术面": 50,
                                 "情绪": 50, "安全边际": 60, "buffett_sub_score": 75}), \
             patch("experts.scoring.institution.score",
                  return_value={"基本面": 75, "估值": 65, "技术面": 50,
                                 "情绪": 50, "安全边际": 60}), \
             patch("experts.registry.EXPERT_REGISTRY", {}):
            result = value_institution.score(_make_stock_data())
        assert "基本面" in result
        assert "buffett_sub_score" in result
        assert "institution_sub_score" in result

    def test_with_registry(self):
        """有 EXPERT_REGISTRY 时使用 registry 权重。"""
        fake_va = SimpleNamespace(weights={"基本面": 50, "估值": 30, "技术面": 5,
                                             "情绪": 5, "安全边际": 10})
        fake_inst = SimpleNamespace(weights={"基本面": 50, "估值": 30, "技术面": 5,
                                              "情绪": 5, "安全边际": 10})
        with patch("experts.scoring.value_anchor.score",
                  return_value={"基本面": 80, "估值": 70, "技术面": 50,
                                 "情绪": 50, "安全边际": 60, "buffett_sub_score": 75}), \
             patch("experts.scoring.institution.score",
                  return_value={"基本面": 75, "估值": 65, "技术面": 50,
                                 "情绪": 50, "安全边际": 60}), \
             patch("experts.registry.EXPERT_REGISTRY",
                  {"value_anchor": fake_va, "institution": fake_inst}):
            result = value_institution.score(_make_stock_data())
        assert "institution_sub_score" in result
        # 应当用 registry 计算
        assert isinstance(result["institution_sub_score"], (int, float))

    def test_missing_buffett_sub_score_fallback(self):
        """buffett_sub_score 缺失时回退 35（禁用 buffett 警示）。"""
        with patch("experts.scoring.value_anchor.score",
                  return_value={"基本面": 80, "估值": 70, "技术面": 50,
                                 "情绪": 50, "安全边际": 60}), \
             patch("experts.scoring.institution.score",
                  return_value={"基本面": 75, "估值": 65, "技术面": 50,
                                 "情绪": 50, "安全边际": 60}), \
             patch("experts.registry.EXPERT_REGISTRY", {}):
            result = value_institution.score(_make_stock_data())
        # 回退到 35
        assert result["buffett_sub_score"] == 35.0


class TestValueInstitutionScoreWithReasoning:
    def test_basic(self):
        fake_profile = SimpleNamespace(
            display_name="value_institution", name="value_institution",
            weights={"基本面": 50, "估值": 30, "技术面": 5, "情绪": 5, "安全边际": 10},
        )
        with patch("experts.scoring.value_anchor.score",
                  return_value={"基本面": 80, "估值": 70, "技术面": 50,
                                 "情绪": 50, "安全边际": 60, "buffett_sub_score": 75}), \
             patch("experts.scoring.institution.score",
                  return_value={"基本面": 75, "估值": 65, "技术面": 50,
                                 "情绪": 50, "安全边际": 60}), \
             patch("experts.registry.EXPERT_REGISTRY",
                  {"value_institution": fake_profile}):
            result = value_institution.score_with_reasoning(_make_stock_data())
        assert "scores" in result
        assert "reasoning" in result
        assert "dimensions" in result
        assert "buffett_sub_score" in result
        assert "institution_sub_score" in result
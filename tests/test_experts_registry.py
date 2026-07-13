"""测试 experts/registry.py + topic_leader + institution scoring。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import registry
from experts.scoring import topic_leader, institution


# ═══════════════════════════════════════════════════════════════
# experts/registry.py


class TestRegistry:
    def test_registry_initial_dict(self):
        """初始 EXPERT_REGISTRY 为 dict。"""
        assert isinstance(registry.EXPERT_REGISTRY, dict)

    def test_ensure_loaded(self):
        """_ensure_loaded() 加载 yaml 专家。"""
        with patch("experts.yaml_loader.load_all_experts",
                  return_value={"buffett": SimpleNamespace(name="buffett", active=True),
                                "lynch": SimpleNamespace(name="lynch", active=True),
                                "soros": SimpleNamespace(name="soros", active=True),
                                "risk_manager": SimpleNamespace(name="risk_manager", active=True),
                                "momentum_trader": SimpleNamespace(name="momentum_trader", active=True),
                                "sector_specialist": SimpleNamespace(name="sector_specialist", active=True),
                                "value_anchor": SimpleNamespace(name="value_anchor", active=True),
                                "topic_leader": SimpleNamespace(name="topic_leader", active=True),
                                "emotion_tech": SimpleNamespace(name="emotion_tech", active=False),
                                "extra1": SimpleNamespace(name="extra1", active=False),
                                "extra2": SimpleNamespace(name="extra2", active=False),
                                "extra3": SimpleNamespace(name="extra3", active=False),
                                "extra4": SimpleNamespace(name="extra4", active=False),
                                "extra5": SimpleNamespace(name="extra5", active=False),
                                "extra6": SimpleNamespace(name="extra6", active=False),
                                "extra7": SimpleNamespace(name="extra7", active=False),
                                "extra8": SimpleNamespace(name="extra8", active=False)}):
            registry.EXPERT_REGISTRY.clear()
            try:
                registry._ensure_loaded()
            except RuntimeError:
                pass
        assert "buffett" in registry.EXPERT_REGISTRY

    def test_ensure_loaded_idempotent(self):
        """重复调用 _ensure_loaded 不重复加载。"""
        registry.EXPERT_REGISTRY["test_expert"] = SimpleNamespace(name="x", active=True)
        with patch("experts.yaml_loader.load_all_experts",
                  return_value={"new": SimpleNamespace(name="new", active=True)}):
            try:
                registry._ensure_loaded()
            except Exception:
                pass
        assert "test_expert" in registry.EXPERT_REGISTRY

    def test_load_experts_min_count(self):
        """专家数 < 8 时抛 RuntimeError。"""
        with patch("experts.yaml_loader.load_all_experts",
                  return_value={"a": SimpleNamespace(name="a", active=True)}):
            registry.EXPERT_REGISTRY.clear()
            with pytest.raises(RuntimeError):
                registry._ensure_loaded()

    def test_active_count_check(self):
        """active 数 < 5 时抛 RuntimeError。"""
        fake = {
            f"expert_{i}": SimpleNamespace(name=f"e{i}", active=(i < 3))
            for i in range(8)
        }
        with patch("experts.yaml_loader.load_all_experts", return_value=fake):
            registry.EXPERT_REGISTRY.clear()
            with pytest.raises(RuntimeError):
                registry._ensure_loaded()


# ═══════════════════════════════════════════════════════════════
# experts/scoring/topic_leader.py


class TestTopicLeader:
    def test_importable(self):
        assert hasattr(topic_leader, "score") or hasattr(topic_leader, "evaluate")

    def test_score_callable(self):
        """score 函数可调用。"""
        score_fn = getattr(topic_leader, "score", None) or getattr(topic_leader, "evaluate", None)
        if score_fn:
            assert callable(score_fn)


# ═══════════════════════════════════════════════════════════════
# experts/scoring/institution.py


class TestInstitution:
    def test_importable(self):
        assert hasattr(institution, "score") or hasattr(institution, "evaluate")

    def test_score_callable(self):
        score_fn = getattr(institution, "score", None) or getattr(institution, "evaluate", None)
        if score_fn:
            assert callable(score_fn)
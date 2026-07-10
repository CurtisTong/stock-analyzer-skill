"""
experts/yaml 机器可读版测试（Sprint 15 / D6 落地）。
"""

import sys
from pathlib import Path

import pytest

# 让 import 找得到 experts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestYamlLoad:
    """YAML 加载测试。"""

    def test_load_buffett_from_yaml(self):
        """加载 buffett.yaml 验证字段映射。"""
        from experts.yaml_loader import load_expert_from_yaml
        from experts.yaml_loader import YAML_DIR

        path = YAML_DIR / "buffett.yaml"
        if not path.exists():
            pytest.skip("buffett.yaml 不存在")

        profile = load_expert_from_yaml(path)
        assert profile.name == "buffett"
        assert profile.display_name == "巴菲特"
        assert profile.group == "long_term"
        assert "基本面" in profile.weights
        assert profile.weights["基本面"] == 42.0
        assert len(profile.veto_conditions) >= 1
        assert profile.active is False  # v2.1.0 deprecated

    def test_load_lynch_from_yaml(self):
        """加载 lynch.yaml。"""
        from experts.yaml_loader import load_expert_from_yaml, YAML_DIR

        path = YAML_DIR / "lynch.yaml"
        if not path.exists():
            pytest.skip("lynch.yaml 不存在")

        profile = load_expert_from_yaml(path)
        assert profile.name == "lynch"
        assert profile.active is True

    def test_dimension_name_normalized_on_load(self):
        """P0-06: YAML 中的别名维度名（如'情绪/题材'）加载后归一化为标准名（'情绪'）。"""
        from experts.yaml_loader import load_expert_from_yaml, YAML_DIR

        # momentum_trader.yaml 用"情绪/资金"，topic_leader/xu_xiang/zhao_laoge 用"情绪/题材"
        for fname in (
            "momentum_trader.yaml",
            "xu_xiang.yaml",
            "zhao_laoge.yaml",
            "soros.yaml",
        ):
            path = YAML_DIR / fname
            if not path.exists():
                continue
            profile = load_expert_from_yaml(path)
            # 不应有"情绪/xxx"别名键，应统一为"情绪"
            for dim in profile.weights:
                assert (
                    "/" not in dim
                ), f"{fname}: 维度名 '{dim}' 未归一化，应映射到标准名"


class TestYamlAll:
    """load_all_experts 测试。"""

    def test_load_all_returns_dict(self):
        """load_all_experts 返回 {name: profile} 字典。"""
        from experts.yaml_loader import load_all_experts

        experts = load_all_experts()
        assert isinstance(experts, dict)
        if experts:  # 至少有一些 yaml 时
            for name, profile in experts.items():
                assert isinstance(name, str)
                assert profile.name == name


class TestRoundTrip:
    """YAML round-trip 一致性测试。"""

    def test_round_trip_preserves_fields(self):
        """profile → yaml → profile 字段完全一致。"""
        from experts.yaml_loader import round_trip
        from experts.types import ExpertProfile

        original = ExpertProfile(
            name="test_expert",
            display_name="测试专家",
            group="long_term",
            style="测试风格",
            horizon="月/季",
            core_signal="测试信号",
            weights={
                "基本面": 30.0,
                "估值": 30.0,
                "技术面": 20.0,
                "情绪": 10.0,
                "风险": 10.0,
            },
            veto_conditions=["测试否决条件 1", "测试否决条件 2"],
            md_path="experts/test.md",
            active=True,
        )
        assert round_trip(original) is True

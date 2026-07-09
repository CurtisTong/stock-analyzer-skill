"""
YAML 专家配置完整性测试（B3 / P1-6 / P2-01）。

P2-01 (v2.0): 三源合一后，YAML 是唯一数据源。本测试守护：
1. 每个 experts/yaml/<name>.yaml 都能正确加载为 ExpertProfile
2. YAML 文件数 = 16，active = 8，legacy = 8
3. load_all_experts() 与运行时 EXPERT_REGISTRY 一致
4. schema 校验：坏数据应抛 ValueError

experts/*.md §九评分矩阵与 YAML weights 的一致性由 test_experts.py::TestWeightSync 守护。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.yaml_loader import YAML_DIR, load_all_experts, load_expert_from_yaml  # noqa: E402

# P2-01: 期望的专家列表（YAML 单源后，这是唯一权威定义）
_EXPECTED_EXPERT_NAMES = {
    "buffett", "chaogu_yangjia", "duan_yongping", "emotion_tech",
    "institution", "lynch", "momentum_trader", "risk_manager",
    "sector_specialist", "soros", "topic_leader", "value_anchor",
    "value_institution", "xu_xiang", "zhao_laoge", "zuoshou_xinyi",
}


# ═══════════════════════════════════════════════════════════════
# 1. YAML 文件完整性（P2-01: 替代原硬编码对等校验）
# ═══════════════════════════════════════════════════════════════


class TestYamlCompleteness:
    """YAML 文件完整性：每个 yaml 都能加载，数量和 active 数符合预期。"""

    @pytest.mark.parametrize("name", sorted(_EXPECTED_EXPERT_NAMES))
    def test_yaml_loads_cleanly(self, name):
        """每个期望专家的 YAML 文件存在且能正确加载。"""
        yaml_path = YAML_DIR / f"{name}.yaml"
        assert yaml_path.exists(), f"缺少 yaml: {yaml_path}"
        profile = load_expert_from_yaml(yaml_path)
        assert profile.name == name, f"{name}: name 字段不匹配"
        assert profile.display_name, f"{name}: display_name 为空"
        assert profile.group in ("long_term", "short_term"), f"{name}: group={profile.group}"
        assert profile.weights, f"{name}: weights 为空"
        assert profile.md_path, f"{name}: md_path 为空"

    def test_yaml_file_count(self):
        """yaml 文件数 = 16。"""
        yaml_files = list(YAML_DIR.glob("*.yaml"))
        assert len(yaml_files) == 16, f"yaml 文件数 {len(yaml_files)} != 16"

    def test_no_orphan_yaml_files(self):
        """没有孤儿 yaml（yaml 名都在期望列表中）。"""
        yaml_names = {p.stem for p in YAML_DIR.glob("*.yaml")}
        orphans = yaml_names - _EXPECTED_EXPERT_NAMES
        assert not orphans, f"yaml 文件无对应专家: {orphans}"

    def test_no_missing_yaml_files(self):
        """期望列表中的每个专家都有 yaml。"""
        yaml_names = {p.stem for p in YAML_DIR.glob("*.yaml")}
        missing = _EXPECTED_EXPERT_NAMES - yaml_names
        assert not missing, f"缺少 yaml: {missing}"

    def test_active_legacy_counts(self):
        """active=8, legacy=8。"""
        loaded = load_all_experts()
        active = [p for p in loaded.values() if p.active]
        legacy = [p for p in loaded.values() if not p.active]
        assert len(active) == 8, f"active 专家数 {len(active)} != 8: {[p.name for p in active]}"
        assert len(legacy) == 8, f"legacy 专家数 {len(legacy)} != 8: {[p.name for p in legacy]}"


# ═══════════════════════════════════════════════════════════════
# 2. load_all_experts 与 EXPERT_REGISTRY 运行时一致
# ═══════════════════════════════════════════════════════════════


class TestLoadAllExperts:
    """load_all_experts 返回的 profile 与运行时 EXPERT_REGISTRY 一致。"""

    def test_load_all_matches_registry(self):
        """load_all_experts() 结果 = 运行时 EXPERT_REGISTRY（yaml 已覆盖）。"""
        from experts.registry import EXPERT_REGISTRY

        loaded = load_all_experts()
        # 每个 yaml profile 应在 registry 中且字段一致
        for name, profile in loaded.items():
            assert name in EXPERT_REGISTRY, f"{name} 在 yaml 但不在 EXPERT_REGISTRY"
            reg = EXPERT_REGISTRY[name]
            assert profile.group == reg.group, f"{name}: group 漂移"
            assert profile.active == reg.active, f"{name}: active 漂移"
            assert profile.weights == reg.weights, f"{name}: weights 漂移"


# ═══════════════════════════════════════════════════════════════
# 3. schema 校验：坏数据应抛 ValueError
# ═══════════════════════════════════════════════════════════════


class TestYamlSchemaValidation:
    """load_expert_from_yaml 的 schema 校验（B3）。"""

    def _write_yaml(self, tmp_path, data: dict) -> Path:
        import yaml as yaml_mod

        path = tmp_path / "test_bad.yaml"
        path.write_text(yaml_mod.safe_dump(data, allow_unicode=True), encoding="utf-8")
        return path

    def test_missing_required_field_raises(self, tmp_path):
        """缺必填字段抛 ValueError。"""
        from experts.yaml_loader import load_expert_from_yaml

        path = self._write_yaml(tmp_path, {"name": "x", "display_name": "X"})
        with pytest.raises(ValueError, match="缺少必填字段"):
            load_expert_from_yaml(path)

    def test_bad_group_raises(self, tmp_path):
        """group 非 long_term/short_term 抛 ValueError。"""
        from experts.yaml_loader import load_expert_from_yaml

        path = self._write_yaml(
            tmp_path,
            {
                "name": "x", "display_name": "X", "group": "mid_term",
                "style": "s", "horizon": "h", "core_signal": "c",
                "weights": {"基本面": 100.0},
            },
        )
        with pytest.raises(ValueError, match="group"):
            load_expert_from_yaml(path)

    def test_weight_sum_deviation_raises(self, tmp_path):
        """权重加和偏离 100 超过 ±0.5 抛 ValueError。"""
        from experts.yaml_loader import load_expert_from_yaml

        path = self._write_yaml(
            tmp_path,
            {
                "name": "x", "display_name": "X", "group": "long_term",
                "style": "s", "horizon": "h", "core_signal": "c",
                "weights": {"基本面": 50.0, "估值": 30.0},  # sum=80, 偏差 20
            },
        )
        with pytest.raises(ValueError, match="加和"):
            load_expert_from_yaml(path)

    def test_non_dict_top_level_raises(self, tmp_path):
        """yaml 顶层非 dict 抛 ValueError。"""
        from experts.yaml_loader import load_expert_from_yaml
        import yaml as yaml_mod

        path = tmp_path / "list.yaml"
        path.write_text(yaml_mod.safe_dump(["not", "a", "dict"]), encoding="utf-8")
        with pytest.raises(ValueError, match="顶层应为 dict"):
            load_expert_from_yaml(path)

    def test_valid_yaml_loads_cleanly(self, tmp_path):
        """合法 yaml 正常加载（无异常）。"""
        from experts.yaml_loader import load_expert_from_yaml

        path = self._write_yaml(
            tmp_path,
            {
                "name": "test_ok", "display_name": "测试", "group": "long_term",
                "style": "s", "horizon": "h", "core_signal": "c",
                "weights": {"基本面": 40.0, "估值": 30.0, "技术面": 10.0, "情绪": 10.0, "风险": 10.0},
                "veto_conditions": ["条件1"],
                "md_path": "experts/test.md",
                "active": True,
            },
        )
        profile = load_expert_from_yaml(path)
        assert profile.name == "test_ok"
        assert profile.active is True

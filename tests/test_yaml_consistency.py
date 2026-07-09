"""
YAML 与硬编码 EXPERT_REGISTRY 一致性测试（B3 / P1-6）。

锁死漂移：每个 experts/yaml/<name>.yaml 加载后必须与 registry.py 中同名
硬编码 profile 一致。任一方改动（weights/veto_conditions/active/group 等）
必须同步，否则本测试失败。

已知的两类"表示层差异"（非真实漂移）按以下方式归一化后再比较：
1. 引号字符：PyYAML safe_dump 把含单引号的字符串转成双引号，veto_conditions
   对比时统一把双引号归一为单引号。
2. 维度名别名：yaml 用人设特色维度名（如"情绪/反身性"/"情绪/题材"），
   硬编码用基础名（"情绪"）；按 normalize_dim 归一后比较（C1 别名机制）。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.registry import _HARDCODED_PROFILES  # noqa: E402
from experts.types import normalize_dim  # noqa: E402
from experts.yaml_loader import YAML_DIR, load_all_experts, load_expert_from_yaml  # noqa: E402


def _norm_quotes(s: str) -> str:
    """把双引号归一为单引号（PyYAML safe_dump 的表示层差异）。"""
    return s.replace('"', "'")


def _normalize_weights(weights: dict) -> dict:
    """维度名按 normalize_dim 归一，使别名维度与标准维度可比。"""
    return {normalize_dim(k): v for k, v in weights.items()}


def _normalize_veto(veto: list) -> list:
    """veto_conditions 引号归一化。"""
    return [_norm_quotes(v) for v in veto]


# ═══════════════════════════════════════════════════════════════
# 1. 文件级完整性：每个硬编码 profile 都有对应 yaml
# ═══════════════════════════════════════════════════════════════


class TestYamlHardcodedParity:
    """yaml 文件与硬编码 profile 逐字段一致性（归一化后）。"""

    @pytest.mark.parametrize("name", sorted(_HARDCODED_PROFILES))
    def test_yaml_matches_hardcoded(self, name):
        """单个 expert：yaml 加载结果与硬编码 profile 一致（归一化后）。"""
        yaml_path = YAML_DIR / f"{name}.yaml"
        if not yaml_path.exists():
            pytest.fail(f"硬编码 profile {name} 缺少对应 yaml: {yaml_path}")

        hardcoded = _HARDCODED_PROFILES[name]
        loaded = load_expert_from_yaml(yaml_path)

        # 标量字段必须完全一致
        assert loaded.name == hardcoded.name, f"{name}: name"
        assert loaded.display_name == hardcoded.display_name, f"{name}: display_name"
        assert loaded.group == hardcoded.group, f"{name}: group"
        assert loaded.style == hardcoded.style, f"{name}: style"
        assert loaded.horizon == hardcoded.horizon, f"{name}: horizon"
        assert loaded.core_signal == hardcoded.core_signal, f"{name}: core_signal"
        assert loaded.active == hardcoded.active, f"{name}: active"
        assert loaded.md_path == hardcoded.md_path, f"{name}: md_path"

        # weights：维度名归一化后比较
        hw = _normalize_weights(hardcoded.weights)
        yw = _normalize_weights(loaded.weights)
        assert hw == yw, f"{name}: weights 归一化后不一致\n  硬编码: {hw}\n  yaml:    {yw}"

        # veto_conditions：引号归一化后比较
        hv = _normalize_veto(hardcoded.veto_conditions)
        yv = _normalize_veto(loaded.veto_conditions)
        assert hv == yv, f"{name}: veto_conditions 归一化后不一致\n  硬编码: {hv}\n  yaml:    {yv}"

    def test_yaml_file_count_matches_hardcoded(self):
        """yaml 文件数 = 硬编码 profile 数（16）。"""
        yaml_files = list(YAML_DIR.glob("*.yaml"))
        assert len(yaml_files) == len(_HARDCODED_PROFILES), (
            f"yaml 文件数 {len(yaml_files)} != 硬编码 profile 数 "
            f"{len(_HARDCODED_PROFILES)}"
        )

    def test_no_orphan_yaml_files(self):
        """没有孤儿 yaml（yaml 名都在硬编码 profile 中）。"""
        hardcoded_names = set(_HARDCODED_PROFILES)
        yaml_names = {p.stem for p in YAML_DIR.glob("*.yaml")}
        orphans = yaml_names - hardcoded_names
        assert not orphans, f"yaml 文件无对应硬编码 profile: {orphans}"


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

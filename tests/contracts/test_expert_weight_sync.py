"""experts/*.md §九 权重表 与 experts/yaml/*.yaml 的镜像一致性校验。

**背景**：registry.py 与 tests/contracts/test_expert_yaml_consistency.py
都声称"由 `test_experts.py::TestWeightSync` 校验（±2%）"，但全仓 grep
`TestWeightSync` 只有这两处注释命中——**实现根本不存在**，改 md 权重不会
让 CI 变红。本文件补上这个守护。

**校验内容**：每位专家 md §九「维度权重」表中的维度权重，与 YAML 中
`profile.weights` 归一化后的结果一致（±2 个百分点）。

**为什么是"镜像"而非"数据源"**：YAML 是唯一机器可读源（v2.0 起），
md 是人读档案。但两者长期手工同步，一旦漂移，读者看到的评分矩阵与
实际计算的权重不同——比"缺失守护"更隐蔽的失真。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from experts.registry import EXPERT_REGISTRY, _ensure_loaded
from experts.types import normalize_dim

# md 权重表行：| 维度 | **42%** | 核心指标 | 满分规则 |
_MD_WEIGHT_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*\*\*(\d+(?:\.\d+)?)%\*\*\s*\|")

# 容忍的偏差（百分点）——md 手工维护，允许四舍五入级误差
_TOLERANCE = 2.0

_EXPERTS_DIR = Path(__file__).resolve().parents[2] / "experts"

# 注册表是惰性加载的，参数化在收集阶段求值——必须在模块导入时显式加载，
# 否则 parametrize 拿到空集合，守护会静默失效（正是本文件要修的那类问题）。
_ensure_loaded()
_EXPERT_NAMES = sorted(EXPERT_REGISTRY.keys())


def _parse_md_weights(md_path: Path) -> dict[str, float]:
    """从专家 md 的 §九 维度权重表解析 {维度: 权重}。

    只取「### 维度权重」小节内的表格行，避免误抓文档其他位置的表格。
    """
    if not md_path.exists():
        return {}

    lines = md_path.read_text(encoding="utf-8").splitlines()
    in_section = False
    weights: dict[str, float] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("###") and "维度权重" in stripped:
            in_section = True
            continue
        if in_section and stripped.startswith("#"):
            # 下一个小节，结束
            break
        if not in_section:
            continue
        m = _MD_WEIGHT_ROW.match(stripped)
        if m:
            dim = m.group(1).strip()
            weights[dim] = float(m.group(2))
    return weights


def _yaml_weights(profile) -> dict[str, float]:
    """YAML 侧权重（键已由 yaml_loader 归一化）。"""
    return {normalize_dim(k): v for k, v in profile.weights.items()}


class TestWeightSync:
    """md §九 权重表 ↔ YAML 权重镜像一致性（±2 个百分点）。"""

    @pytest.fixture(autouse=True)
    def _load_registry(self):
        _ensure_loaded()

    @pytest.mark.parametrize("name", _EXPERT_NAMES)
    def test_md_weights_match_yaml(self, name):
        profile = EXPERT_REGISTRY[name]
        md_path = _EXPERTS_DIR / f"{name}.md"
        md_weights = _parse_md_weights(md_path)
        if not md_weights:
            pytest.skip(f"{name}.md 无 §九 维度权重表")

        yaml_weights = _yaml_weights(profile)

        # md 维度名归一化（md 里写的可能是"安全边际""风险"等非标准名）
        md_norm = {normalize_dim(k): v for k, v in md_weights.items()}

        assert set(md_norm.keys()) == set(yaml_weights.keys()), (
            f"{name}: md 与 YAML 的维度集合不一致——" f"md={sorted(md_norm.keys())}, yaml={sorted(yaml_weights.keys())}"
        )

        for dim, md_w in md_norm.items():
            yaml_w = yaml_weights[dim]
            assert (
                abs(md_w - yaml_w) <= _TOLERANCE
            ), f"{name}.{dim}: md 权重 {md_w}% 与 YAML {yaml_w}% 偏差超过 {_TOLERANCE} 个百分点"

    @pytest.mark.parametrize("name", _EXPERT_NAMES)
    def test_md_weights_sum_to_100(self, name):
        """md 权重表自身加和应为 100（±1，允许四舍五入）。"""
        md_path = _EXPERTS_DIR / f"{name}.md"
        md_weights = _parse_md_weights(md_path)
        if not md_weights:
            pytest.skip(f"{name}.md 无 §九 维度权重表")
        total = sum(md_weights.values())
        assert abs(total - 100.0) <= 1.0, f"{name}.md 权重加和 = {total}（期望 100±1）"

    def test_all_experts_have_md(self):
        """每位注册专家都应有对应的人设档案 md。"""
        missing = [n for n in EXPERT_REGISTRY if not (_EXPERTS_DIR / f"{n}.md").exists()]
        assert not missing, f"缺少人设档案 md: {missing}"

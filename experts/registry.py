"""
16 份专家人设的评分注册表（8 active + 8 legacy）。

数据来源：experts/yaml/*.yaml（单一机器可读源）。
experts/*.md 保留为叙事/案例文档（人类可读），其中 §九评分矩阵
由 test_experts.py::TestWeightSync 校验与 YAML weights 一致（±2%）。

加载流程：
  _ensure_loaded() -> yaml_loader.load_all_experts() -> EXPERT_REGISTRY

P2-01 (v2.0): 三源合一为 YAML 单源。原硬编码 ExpertProfile 快照已删除，
YAML 是唯一数据源。experts/*.md 仅保留叙事（§九 weights 表作为人类可读镜像）。
"""

import logging
from typing import Dict

from experts.types import ExpertProfile

logger = logging.getLogger(__name__)

EXPERT_REGISTRY: Dict[str, ExpertProfile] = {}

# P2-02: LEGACY_ALIAS / get_display_name 已删除（零运行时调用方，
# 运行时显示名统一从 ExpertProfile.display_name 读取）。


def _ensure_loaded() -> None:
    """从 experts/yaml/*.yaml 加载所有专家配置到 EXPERT_REGISTRY。

    P2-01 (v2.0): YAML 是唯一数据源，不再有硬编码回退。
    PyYAML 是硬依赖（pyproject.toml 已声明 pyyaml>=6.0）。

    v2.4.0 的不变量：
    - 注册表总数 = 16（8 legacy + 8 active：2 独立保留 + 2 合并型 + 3 补盲区 + 1 动量派）
    - active 专家数 = 8（lynch/soros 独立 + value_institution/topic_leader/emotion_tech
      + sector_specialist/risk_manager + momentum_trader）

    legacy（active=False）指已被合并视角取代、新框架不再调用的旧专家，
    仍保留在注册表中供向后兼容与 A/B 对比。

    合并型专家的权重映射：
    - value_institution = value_anchor(0.5) + institution(0.5)
      其中 value_anchor = buffett(0.55) + duan_yongping(0.45)
    - topic_leader = xu_xiang(0.5) + zhao_laoge(0.5)
    - emotion_tech = chaogu_yangjia(0.5) + zuoshou_xinyi(0.5)
    合并实现位于 experts/scoring/{value_institution,topic_leader,emotion_tech}.py。
    """
    if EXPERT_REGISTRY:
        return  # 已加载，避免重复

    from experts.yaml_loader import load_all_experts

    yaml_experts = load_all_experts()
    for name, profile in yaml_experts.items():
        EXPERT_REGISTRY[name] = profile

    total = len(EXPERT_REGISTRY)
    active_count = sum(1 for p in EXPERT_REGISTRY.values() if p.active)
    if total < 8:
        raise RuntimeError(
            f"Expected at least 8 experts in registry, "
            f"found {total}: {list(EXPERT_REGISTRY)}"
        )
    if active_count < 5:
        raise RuntimeError(
            f"Expected at least 5 active experts, found {active_count}: "
            f"{[p.name for p in EXPERT_REGISTRY.values() if p.active]}"
        )
    if total != 16 or active_count != 8:
        logger.warning(
            "专家数量变化: total=%d (期望16), active=%d (期望8)", total, active_count
        )

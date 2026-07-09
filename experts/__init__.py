"""
8 人专家圆桌（5 长线 + 3 短线）· 可调用 API。

本模块把 experts/*.md 的人设和评分矩阵沉淀为 Python 数据结构，
使 `stock` skill 的 debate 模式可在代码层查询专家维度权重和一票否决条件。

公开 API：
- EXPERT_REGISTRY: Dict[expert_name, ExpertProfile]
- get_expert(name) -> ExpertProfile | None
- list_experts(group=None) -> List[ExpertProfile]
- list_long_term_experts() -> List[ExpertProfile]
- list_short_term_experts() -> List[ExpertProfile]
- direction_from_score(score) -> str

每位专家的人设、案例、引用仍以 experts/<name>.md 为权威来源，
本模块只承载结构化字段（权重 + 否决条件 + 标签）。
"""

from typing import Dict, List, Optional

from experts.types import ExpertProfile, DIRECTION_THRESHOLDS, direction_from_score


# 导入注册表（放在模块底部以利用 dataclass 定义）
from .registry import (
    EXPERT_REGISTRY,
    LEGACY_ALIAS,
    get_display_name,
    _ensure_loaded,
)  # noqa: E402

_ensure_loaded()


def get_expert(name: str) -> Optional[ExpertProfile]:
    """按英文短名获取专家档案。"""
    return EXPERT_REGISTRY.get(name)


def list_experts(group: Optional[str] = None) -> List[ExpertProfile]:
    """列出专家。group 过滤：None=全部 / "long_term" / "short_term"。"""
    all_experts = list(EXPERT_REGISTRY.values())
    if group is None:
        return all_experts
    return [e for e in all_experts if e.group == group]


def list_long_term_experts() -> List[ExpertProfile]:
    """长线组专家：按 group='long_term' 过滤。"""
    return list_experts("long_term")


def list_short_term_experts() -> List[ExpertProfile]:
    """短线组专家：按 group='short_term' 过滤。"""
    return list_experts("short_term")


# ═══════════════════════════════════════════════════════════════
# v2.1.0 切换 API
# ═══════════════════════════════════════════════════════════════


def list_active_experts(group: Optional[str] = None) -> List[ExpertProfile]:
    """列出 active=True 的专家（v2.4.0 默认 8 人 = 5 长线 + 3 短线）。

    构成：lynch + soros + value_institution（3 长线独立/合并）+ sector_specialist +
    risk_manager（2 长线补盲区型）+ topic_leader + emotion_tech +
    momentum_trader（3 短线）。

    v2.4.0 变更：value_anchor + institution 合并为 value_institution。

    新框架默认调用此 API，legacy 8 人需显式 `list_legacy_experts()`。
    """
    all_experts = [p for p in EXPERT_REGISTRY.values() if p.active]
    if group is None:
        return all_experts
    return [p for p in all_experts if p.group == group]


def list_legacy_experts(group: Optional[str] = None) -> List[ExpertProfile]:
    """列出 active=False 的 legacy 专家（8 人）。

    legacy = 已被合并型视角取代、新框架不再调用的旧专家（buffett/
    duan_yongping/xu_xiang/zhao_laoge/chaogu_yangjia/zuoshou_xinyi/
    value_anchor/institution）。通过 `--use-legacy-experts` flag 让用户
    显式切回旧圆桌做 A/B 对比。
    """
    all_experts = [p for p in EXPERT_REGISTRY.values() if not p.active]
    if group is None:
        return all_experts
    return [p for p in all_experts if p.group == group]


__all__ = [
    "ExpertProfile",
    "EXPERT_REGISTRY",
    "LEGACY_ALIAS",
    "get_display_name",
    "get_expert",
    "list_experts",
    "list_long_term_experts",
    "list_short_term_experts",
    # v2.1.0 切换 API
    "list_active_experts",
    "list_legacy_experts",
    "direction_from_score",
    "DIRECTION_THRESHOLDS",
]

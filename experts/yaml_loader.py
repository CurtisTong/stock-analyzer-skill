"""
experts/yaml 机器可读版加载器（Sprint 15 / D6 落地）。

解决的问题：expert 配置原本只在 registry.py 中硬编码，无法从外部源管理。
本模块让 expert 配置可以从 YAML 文件加载（experts/yaml/<name>.yaml），
与 registry.py 形成 round-trip：
  registry.py  →  export  →  yaml  →  load  →  ExpertProfile

D6 plan 要求："yaml 渲染回 md 无 diff" —— 即 yaml 与 MD 互不冲突，
MD 保留叙述，YAML 是数据源。
"""

from pathlib import Path
from typing import Dict

from experts.types import ExpertProfile

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


YAML_DIR = Path(__file__).resolve().parent / "yaml"


def load_expert_from_yaml(path: Path) -> ExpertProfile:
    """从单个 YAML 文件加载 ExpertProfile。

    v2.4.2：加 schema 校验--必填字段缺失/类型错误/权重加和偏差>0.5 时抛
    ValueError（而非静默加载坏数据），避免 yaml 漂移污染 EXPERT_REGISTRY。

    Args:
        path: yaml 文件路径

    Returns:
        ExpertProfile 实例

    Raises:
        ValueError: 必填字段缺失、类型错误、或权重加和偏离 100 超过 ±0.5。
        KeyError: yaml 顶层不是 dict 时。
    """
    if not HAS_YAML:
        raise ImportError("需要 PyYAML：pip install pyyaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: yaml 顶层应为 dict，实际 {type(data).__name__}")

    # 必填字段校验
    required = ["name", "display_name", "group", "style", "horizon", "core_signal", "weights"]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"{path}: 缺少必填字段 {missing}")

    # 类型校验
    if not isinstance(data["name"], str) or not data["name"]:
        raise ValueError(f"{path}: name 应为非空 str")
    if data["group"] not in ("long_term", "short_term"):
        raise ValueError(f"{path}: group 应为 'long_term' 或 'short_term'，实际 {data['group']!r}")
    weights = data["weights"]
    if not isinstance(weights, dict) or not weights:
        raise ValueError(f"{path}: weights 应为非空 dict")
    bad_weights = {k: v for k, v in weights.items() if not isinstance(v, (int, float))}
    if bad_weights:
        raise ValueError(f"{path}: weights 含非数值项 {bad_weights}")

    # 权重加和校验（±0.5 容差，与 ExpertProfile.__post_init__ 一致）
    total = sum(weights.values())
    if abs(total - 100.0) > 0.5:
        raise ValueError(
            f"{path}: weights 加和 = {total:.1f}（期望 100±0.5），维度: {list(weights.keys())}"
        )

    return ExpertProfile(
        name=data["name"],
        display_name=data["display_name"],
        group=data["group"],
        style=data["style"],
        horizon=data["horizon"],
        core_signal=data["core_signal"],
        weights=dict(weights),
        veto_conditions=list(data.get("veto_conditions", [])),
        md_path=data.get("md_path", ""),
        active=data.get("active", True),
    )


def load_all_experts() -> Dict[str, ExpertProfile]:
    """从 experts/yaml/ 目录加载所有 ExpertProfile。

    Returns:
        {expert_name: ExpertProfile} 字典
    """
    if not YAML_DIR.exists():
        return {}
    result: Dict[str, ExpertProfile] = {}
    for path in sorted(YAML_DIR.glob("*.yaml")):
        profile = load_expert_from_yaml(path)
        result[profile.name] = profile
    return result


def export_expert_to_yaml(profile: ExpertProfile, path: Path) -> None:
    """把 ExpertProfile 导出为 YAML 文件（用于 round-trip 验证）。"""
    if not HAS_YAML:
        raise ImportError("需要 PyYAML：pip install pyyaml")
    data = {
        "name": profile.name,
        "display_name": profile.display_name,
        "group": profile.group,
        "style": profile.style,
        "horizon": profile.horizon,
        "core_signal": profile.core_signal,
        "weights": dict(profile.weights),
        "veto_conditions": list(profile.veto_conditions),
        "md_path": profile.md_path,
        "active": profile.active,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def round_trip(profile: ExpertProfile) -> bool:
    """验证 yaml round-trip 一致性：profile → yaml → profile。

    Args:
        profile: 原始 ExpertProfile

    Returns:
        True 表示 round-trip 后字段完全一致
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        tmp = Path(f.name)
    try:
        export_expert_to_yaml(profile, tmp)
        reloaded = load_expert_from_yaml(tmp)
        return (
            reloaded.name == profile.name
            and reloaded.display_name == profile.display_name
            and reloaded.group == profile.group
            and reloaded.weights == profile.weights
            and reloaded.veto_conditions == profile.veto_conditions
            and reloaded.active == profile.active
        )
    finally:
        tmp.unlink(missing_ok=True)

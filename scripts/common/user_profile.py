"""用户偏好配置模块。

从 `scripts/data/user_profile.yaml` 加载用户偏好，影响：
- 默认股票池（blacklist/whitelist）
- 默认策略
- 默认输出格式
- 持仓偏好（杠杆容忍度、风险等级）

v2.4.0 新增。

用法:
    from common.user_profile import load_user_profile, get_user_preference
    profile = load_user_profile()
    risk_level = get_user_preference("risk_tolerance", default="medium")
"""

from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

# 默认用户偏好
DEFAULT_USER_PROFILE = {
    "risk_tolerance": "medium",  # conservative / medium / aggressive
    "preferred_horizon": "medium",  # short / medium / long
    "default_strategy": "balanced",
    "output_format": "brief",  # brief / full
    "blacklist": [],  # 永不买入的代码列表
    "watchlist_priority": [],  # 自选优先级列表
    "position_limit": {
        "single_stock_max": 0.20,
        "top3_max": 0.50,
        "industry_max": 0.30,
    },
    "sector_exclusions": [],  # 排除板块（如"北交所"、"ST"）
    "notifications": {
        "price_alert": True,
        "strategy_signal": True,
        "research_alert": False,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归深合并：override 覆盖 base 的值，嵌套 dict 递归合并而非替换。

    确保 position_limit 等嵌套配置只覆盖用户指定的字段，
    保留未配置字段的默认值。
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _profile_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "user_profile.yaml"


def load_user_profile(path: Optional[str] = None) -> dict:
    """加载用户偏好配置（YAML），缺失时返回默认配置。

    Args:
        path: 自定义文件路径，默认 scripts/data/user_profile.yaml

    Returns:
        用户偏好 dict（缺字段时用默认填充）
    """
    p = Path(path) if path else _profile_path()
    if not p.exists():
        return dict(DEFAULT_USER_PROFILE)

    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML 不可用，跳过 YAML 解析")
        return dict(DEFAULT_USER_PROFILE)

    try:
        user_data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning("user_profile 解析失败: %s，使用默认", e)
        return dict(DEFAULT_USER_PROFILE)

    # 与默认合并（深合并，保留嵌套默认值）
    merged = _deep_merge(dict(DEFAULT_USER_PROFILE), user_data)
    return merged


def get_user_preference(key: str, default: Any = None) -> Any:
    """获取单个用户偏好。

    Args:
        key: 偏好键名（如 "risk_tolerance"）
        default: 默认值

    Returns:
        配置值
    """
    profile = load_user_profile()
    keys = key.split(".")
    value = profile
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
    return value if value is not None else default


def save_user_profile(profile: dict, path: Optional[str] = None) -> None:
    """保存用户偏好到 YAML。"""
    import yaml

    p = Path(path) if path else _profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

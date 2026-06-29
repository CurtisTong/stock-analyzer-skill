"""
行业差异化阈值管理。
从 data/industry_thresholds.json 加载，供因子评分使用。
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_industry_thresholds = None


def load_industry_thresholds() -> dict:
    """加载行业差异化阈值表。"""
    global _industry_thresholds
    if _industry_thresholds is None:
        from common import DATA_DIR

        path = DATA_DIR / "industry_thresholds.json"
        if path.exists():
            _industry_thresholds = json.loads(path.read_text(encoding="utf-8"))
        else:
            logger.warning(
                "industry_thresholds.json 缺失，所有行业差异化评分将退化为代码默认值"
            )
            _industry_thresholds = {}
    return _industry_thresholds


def get_industry_threshold(industry: str, key: str, default=None):
    """获取行业特定阈值。"""
    thresholds = load_industry_thresholds()
    industry_cfg = thresholds.get(industry, thresholds.get("默认", {}))
    return industry_cfg.get(key, default)

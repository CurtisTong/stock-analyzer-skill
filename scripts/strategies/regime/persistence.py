"""RegimeSmoother 跨日状态持久化。

复用 portfolio/_file_utils.py 的 atomic_write（原子写入 + 文件锁）。
复用 macro_indicators.py 的 TTL 过期模式。

状态文件：scripts/data/regime_state.json
TTL：7 天（覆盖任何假期周，包括国庆黄金周）
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

STATE_FILE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "regime_state.json"
)
STATE_TTL_SECONDS = 7 * 86400  # 7 天


def load_state() -> Optional[Dict[str, float]]:
    """加载上次平滑权重。过期或缺失返回 None。

    Returns:
        prev_weights dict 或 None
    """
    try:
        if not STATE_FILE.exists():
            return None
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(data["updated"])
        age = (datetime.now() - updated).total_seconds()
        if age > STATE_TTL_SECONDS:
            logger.debug("regime state expired (age=%ds)", int(age))
            return None
        return data.get("prev_weights")
    except Exception as e:
        logger.debug("regime state load failed: %s", e)
        return None


def save_state(prev_weights: Dict[str, float]):
    """原子写入平滑权重。

    复用 portfolio/_file_utils.atomic_write（文件锁 + tempfile + os.replace）。
    """
    try:
        from portfolio._file_utils import atomic_write

        data = {
            "updated": datetime.now().isoformat(),
            "prev_weights": prev_weights,
        }
        atomic_write(STATE_FILE, data)
    except Exception as e:
        logger.warning("regime state save failed: %s", e)

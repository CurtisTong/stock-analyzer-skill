"""efinance 财务数据源（需要 efinance 包）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import BaseFetcher

try:
    import efinance as ef
    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False


class EfinanceFinanceFetcher(BaseFetcher):
    """efinance 财务数据源 (优先级 5) - 需要安装 efinance 包。"""

    def __init__(self):
        super().__init__("efinance_finance", priority=5)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_EFINANCE:
            return None
        try:
            plain = code.lstrip("shszSHSZbjBJ")
            df = ef.stock.get_base_info(plain)
            if df is None or df.empty:
                return None
            # 返回最近 4 季数据
            return [df.to_dict()]
        except Exception:
            return None

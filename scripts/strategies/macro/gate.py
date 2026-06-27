"""
宏观安全垫门禁：VIX + TLT 双指标系统性风险检查。

设计原则：
- 阈值极端保守（RED 需 VIX>35），避免误报
- 数据不可用时降级为 GREEN（不阻断操作）
- 仅在 /market 和 /screener 输出顶部加标签
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)
from typing import Optional

from config.loader import safe_get


class MacroState(Enum):
    """宏观安全垫状态。"""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class MacroSafetyGate:
    """在选股/分析前检查系统性风险。"""

    def __init__(self):
        self._vix_cache: Optional[float] = None
        self._tlt_cache: Optional[float] = None
        self._cache_loaded = False

    def check(self) -> tuple[MacroState, str]:
        """返回 (状态, 消息)。

        Returns:
            (MacroState, 一行状态描述)
        """
        if not safe_get("macro.yaml", "enabled", True):
            return MacroState.GREEN, "🟢 宏观安全垫: 已禁用"

        vix = self._fetch_vix()
        tlt = self._fetch_tlt()

        # 获取阈值配置
        vix_yellow = safe_get("macro.yaml", "thresholds.vix_yellow", 25)
        vix_red = safe_get("macro.yaml", "thresholds.vix_red", 35)
        tlt_yellow = safe_get("macro.yaml", "thresholds.tlt_yellow", 85)
        tlt_red = safe_get("macro.yaml", "thresholds.tlt_red", 80)

        # 构建状态描述
        vix_str = f"VIX {vix:.1f}" if vix is not None else "VIX N/A"
        tlt_str = f"TLT ${tlt:.1f}" if tlt is not None else "TLT N/A"
        indicators = f"{vix_str} / {tlt_str}"

        # RED: 任一触发
        if (vix is not None and vix > vix_red) or (tlt is not None and tlt < tlt_red):
            return MacroState.RED, f"🔴 系统性风险 ({indicators})"

        # YELLOW: 任一触发
        if (vix is not None and vix > vix_yellow) or (
            tlt is not None and tlt < tlt_yellow
        ):
            return MacroState.YELLOW, f"🟡 避险升温 ({indicators})"

        return MacroState.GREEN, f"🟢 宏观稳定 ({indicators})"

    def _fetch_vix(self) -> Optional[float]:
        """通过 yfinance 获取 VIX。复用已有 fetcher。"""
        if self._cache_loaded:
            return self._vix_cache

        self._load_indicators()
        return self._vix_cache

    def _fetch_tlt(self) -> Optional[float]:
        """通过 yfinance 获取 TLT。复用已有 fetcher。"""
        if self._cache_loaded:
            return self._tlt_cache

        self._load_indicators()
        return self._tlt_cache

    def _load_indicators(self):
        """加载宏观指标数据。"""
        try:
            import yfinance as yf

            # VIX
            vix_ticker = yf.Ticker("^VIX")
            vix_info = vix_ticker.fast_info
            self._vix_cache = getattr(vix_info, "last_price", None)

            # TLT
            tlt_ticker = yf.Ticker("TLT")
            tlt_info = tlt_ticker.fast_info
            self._tlt_cache = getattr(tlt_info, "last_price", None)
        except Exception as e:
            # 数据不可用时降级为 None（GREEN）
            logger.debug("yfinance 获取 VIX/TLT 失败: %s", e)
            self._vix_cache = None
            self._tlt_cache = None
        finally:
            self._cache_loaded = True

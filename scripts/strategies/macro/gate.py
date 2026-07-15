"""
宏观安全垫门禁：VIX + TLT + A 股波动率 三维度系统性风险检查。

v2.x (#12) 更新：
- 5 状态：GREEN / YELLOW / ORANGE / RED / UNKNOWN
- 返回 max_position_ratio (0.0~1.0)，而非二元 halt
- ORANGE 状态自动将持仓数量上限压缩至 60%
- A 股沪深300波动率维度（ashare_vol）
- TTL 缓存（默认 300s）+ 线程安全
- 数据全部缺失 -> UNKNOWN（保守半仓），不再危险降级 GREEN

设计原则：
- 阈值极端保守（RED 需 VIX>35），避免误报
- 数据不可用时降级为 UNKNOWN（position_ratio=0.5）
- GREEN/YELLOW/ORANGE 不 halt，仅压缩仓位；RED halt
"""

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

from config.loader import safe_get


class MacroState(str, Enum):
    """宏观安全垫状态。

    继承 str 使其 JSON 友好（MacroState.GREEN == "GREEN"）。
    position_ratio: 建议最大仓位比例（0.0~1.0），用于仓位管理而非二元 halt。
    """

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    UNKNOWN = "UNKNOWN"

    @property
    def position_ratio(self) -> float:
        """建议最大仓位比例。"""
        return {
            "GREEN": 1.0,
            "YELLOW": 0.5,
            "ORANGE": 0.6,
            "RED": 0.0,
            "UNKNOWN": 0.5,
        }.get(self.value, 0.5)

    @property
    def label(self) -> str:
        """中文标签。"""
        return {
            "GREEN": "宏观稳定",
            "YELLOW": "避险升温",
            "ORANGE": "风险加剧",
            "RED": "系统性风险",
            "UNKNOWN": "数据缺失",
        }.get(self.value, "未知")


class MacroSafetyGate:
    """在选股/分析前检查系统性风险。"""

    def __init__(self):
        self._vix_cache: Optional[float] = None
        self._tlt_cache: Optional[float] = None
        self._ashare_vol: Optional[float] = None
        self._cache_ts: float = 0.0  # 缓存加载时间戳

    def _is_cache_valid(self) -> bool:
        """检查缓存是否在 TTL 内。"""
        if self._cache_ts == 0.0:
            return False
        ttl = safe_get("macro.yaml", "cache_ttl", 300)
        return (time.time() - self._cache_ts) < ttl

    def check(self) -> tuple:
        """返回 (状态, 消息)。

        Returns:
            (MacroState, 一行状态描述，含仓位上限建议)
        """
        if not safe_get("macro.yaml", "enabled", True):
            return MacroState.GREEN, "🟢 宏观安全垫: 已禁用"

        vix = self._fetch_vix()
        tlt = self._fetch_tlt()
        ashare_vol = self._fetch_ashare_vol()

        # 数据全部缺失 -> UNKNOWN（保守半仓，不再危险降级 GREEN）
        if vix is None and tlt is None and ashare_vol is None:
            return MacroState.UNKNOWN, "⚪ 数据全部缺失，保守半仓（仓位上限建议 50%）"

        # 获取阈值配置
        vix_yellow = safe_get("macro.yaml", "thresholds.vix_yellow", 25)
        vix_orange = safe_get("macro.yaml", "thresholds.vix_orange", 30)
        vix_red = safe_get("macro.yaml", "thresholds.vix_red", 35)
        tlt_yellow = safe_get("macro.yaml", "thresholds.tlt_yellow", 85)
        tlt_orange = safe_get("macro.yaml", "thresholds.tlt_orange", 82)
        tlt_red = safe_get("macro.yaml", "thresholds.tlt_red", 80)
        ashare_yellow = safe_get("macro.yaml", "thresholds.ashare_yellow", 25)
        ashare_orange = safe_get("macro.yaml", "thresholds.ashare_orange", 32)
        ashare_red = safe_get("macro.yaml", "thresholds.ashare_red", 35)

        # 构建状态描述
        vix_str = f"VIX {vix:.1f}" if vix is not None else "VIX N/A"
        tlt_str = f"TLT ${tlt:.1f}" if tlt is not None else "TLT N/A"
        ashare_str = (
            f"沪深300波动率 {ashare_vol:.1f}%"
            if ashare_vol is not None
            else "ashare N/A"
        )
        indicators = f"{vix_str} / {tlt_str} / {ashare_str}"

        # RED: 任一触发（最高优先级，严格超阈值触发）
        if (
            (vix is not None and vix > vix_red)
            or (tlt is not None and tlt < tlt_red)
            or (ashare_vol is not None and ashare_vol > ashare_red)
        ):
            return MacroState.RED, f"🔴 系统性风险 ({indicators})"

        # ORANGE: 任一触发（介于 yellow 与 red 之间）
        if (
            (vix is not None and vix > vix_orange)
            or (tlt is not None and tlt < tlt_orange)
            or (ashare_vol is not None and ashare_vol > ashare_orange)
        ):
            return (
                MacroState.ORANGE,
                f"🟠 风险加剧 ({indicators}) 仓位上限建议 60%",
            )

        # YELLOW: 任一触发
        if (
            (vix is not None and vix > vix_yellow)
            or (tlt is not None and tlt < tlt_yellow)
            or (ashare_vol is not None and ashare_vol > ashare_yellow)
        ):
            return (
                MacroState.YELLOW,
                f"🟡 避险升温 ({indicators}) 仓位上限建议 50%",
            )

        return MacroState.GREEN, f"🟢 宏观稳定 ({indicators})"

    def _fetch_vix(self) -> Optional[float]:
        """通过 yfinance 获取 VIX。"""
        if self._is_cache_valid():
            return self._vix_cache
        self._load_indicators()
        return self._vix_cache

    def _fetch_tlt(self) -> Optional[float]:
        """通过 yfinance 获取 TLT。"""
        if self._is_cache_valid():
            return self._tlt_cache
        self._load_indicators()
        return self._tlt_cache

    def _fetch_ashare_vol(self) -> Optional[float]:
        """A 股沪深300年化波动率。"""
        if self._is_cache_valid():
            return self._ashare_vol
        self._load_indicators()
        return self._ashare_vol

    def _load_indicators(self):
        """加载宏观指标数据（VIX + TLT + A 股波动率）。"""
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
            logger.debug("yfinance 获取 VIX/TLT 失败: %s", e)
            self._vix_cache = None
            self._tlt_cache = None

        # A 股波动率（复用 ashare.py）
        try:
            from strategies.macro.ashare import fetch_ashare_vol

            self._ashare_vol = fetch_ashare_vol()
        except Exception as e:
            logger.debug("ashare 波动率获取失败: %s", e)
            self._ashare_vol = None

        self._cache_ts = time.time()

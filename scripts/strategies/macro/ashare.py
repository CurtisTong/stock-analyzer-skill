"""A 股宏观波动率：沪深300 20日年化波动率。

复用 data.get_kline（已含 eastmoney/sina fetcher + 磁盘缓存），
复用 regime/detector.py 的 close-to-close 公式。
阈值与 regime classifier panic=35 对齐。
"""

import logging
import statistics
from typing import Optional

logger = logging.getLogger(__name__)


def fetch_ashare_vol(window: int = 20, code: str = "sh000300") -> Optional[float]:
    """返回沪深300年化波动率（百分比），失败返回 None。

    Args:
        window: 收益率窗口（默认 20 交易日）
        code: 指数代码（默认 sh000300 沪深300）

    Returns:
        年化波动率（如 18.5 表示 18.5%），数据不足或失败返回 None
    """
    try:
        from data import get_kline

        bars = get_kline(code, scale=240, datalen=max(window * 3, 60))
        if not bars or len(bars) < window + 1:
            return None

        closes = [float(b.close) for b in bars]
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] > 0
        ]
        recent = returns[-window:]
        if len(recent) < 2:
            return None

        daily_std = statistics.stdev(recent)
        annualized_vol = daily_std * (252**0.5) * 100  # 百分比
        return round(annualized_vol, 2)
    except Exception as e:
        logger.debug("A 股波动率获取失败: %s", e)
        return None

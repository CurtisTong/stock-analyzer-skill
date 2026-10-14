"""成本分布（筹码分布）取数入口。

职责：取 K 线（优先不复权）+ 流通股本 → 调用 technical.chip_distribution 计算。
供 `scripts/chip_dist.py` 与 `scripts/technical.py --chip` 复用。

口径说明：
- **不复权优先**（sina 直连），因为筹码成本 = 实际成交价；sina 失败时降级
  项目默认链路（前复权）并在 meta.adjust 标记 `qfq`。
- 流通股本由 `quote.circulating_cap ÷ price` 反算；腾讯源存在 `总市值 < 流通市值`
  的口径错位，此时仅记软标记 `cap_inconsistent`，不作降级。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from common import to_float

DEFAULT_WINDOW = 250
DEFAULT_BINS = 240


def _fetch_bars(code: str, window: int) -> tuple[list, str, list]:
    """取日 K。优先不复权（sina 直连），失败降级默认链路。

    Returns:
        (bars, adjust, degraded) —— adjust 为 "raw" 或 "qfq"
    """
    try:
        from fetchers.kline.sina_kline import SinaKlineFetcher

        recs = SinaKlineFetcher().fetch(code, scale=240, datalen=window)
        if recs:
            return recs, "raw", []
    except Exception:
        pass

    from data import get_kline

    bars = get_kline(code, 240, window)
    return [b.to_dict() for b in bars], "qfq", ["kline_adjust"]


def _float_shares(code: str, price: float) -> tuple[float, list, list]:
    """流通股本（股）。优先 quote.circulating_cap 反算，缺失时降级总股本。

    Returns:
        (float_shares, degraded, notes)
    """
    degraded: list = []
    notes: list = []
    try:
        from data import get_quote

        q = get_quote(code)
        circ = to_float(getattr(q, "circulating_cap", 0))
        total = to_float(getattr(q, "total_cap", 0))
        if circ > 0 and price > 0:
            if total > 0 and circ > total:
                notes.append("cap_inconsistent")
            return circ * 1e8 / price, degraded, notes
    except Exception:
        pass

    # 降级：用总股本（finance 净资产 ÷ 每股净资产）代替流通股本
    degraded.append("float_shares_fallback")
    try:
        from data import get_finance

        res = get_finance(code)
        recs = res[0] if isinstance(res, tuple) else res
        if recs:
            first = recs[0]
            d = first.to_dict() if hasattr(first, "to_dict") else first
            net_assets = to_float(d.get("net_assets"))
            bps = to_float(d.get("bps"))
            if net_assets > 0 and bps > 0:
                return net_assets * 1e8 / bps, degraded, notes
    except Exception:
        pass
    degraded.append("float_shares_unavailable")
    return 0.0, degraded, notes


def get_chip_distribution(
    code: str, window: int = DEFAULT_WINDOW, bins: int = DEFAULT_BINS
) -> tuple[Optional[dict], dict]:
    """计算单只标的的成本分布。

    Args:
        code: 已归一化或待归一化的股票代码（如 sh600989）
        window: 回看窗口（交易日）
        bins: 价格分档数

    Returns:
        (chip, meta)：chip 为 None 表示数据不足/流通股本不可用（meta.error 给出原因）
    """
    from common import normalize_quote_code
    from technical.chip_distribution import chip_distribution

    code = normalize_quote_code(code)
    meta: dict[str, Any] = {
        "code": code,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "window": window,
        "bins": bins,
        "degraded": [],
        "notes": [],
    }

    bars, adjust, degraded = _fetch_bars(code, window)
    meta["adjust"] = adjust
    meta["degraded"] = list(degraded)

    price = to_float(bars[-1].get("close")) if bars else 0.0
    fs, fs_degraded, fs_notes = _float_shares(code, price)
    meta["degraded"].extend(fs_degraded)
    meta["notes"].extend(fs_notes)

    if not bars:
        meta["error"] = "无 K 线数据"
        return None, meta

    chip = chip_distribution(bars, fs, price=price, bins=bins, window=window)
    if chip is None:
        meta["error"] = "数据不足或流通股本不可用"
    return chip, meta

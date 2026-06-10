"""资金面数据获取入口。

用法:
    from data.chip import get_margin, get_holders, get_top_holders

    margin = get_margin("sh600989", days=20)
    holders = get_holders("sh600989", periods=4)
    top_holders = get_top_holders("sh600989")
"""
import sys
import threading
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.types import MarginData, HolderData, TopHolderRecord
from common import to_float, to_int


# 延迟导入 fetchers（避免循环导入），线程安全
_fetchers_lock = threading.Lock()
_fetchers_loaded = False
_margin_fetcher = None
_holder_fetcher = None
_top_holder_fetcher = None


def _load_fetchers():
    global _fetchers_loaded, _margin_fetcher, _holder_fetcher, _top_holder_fetcher
    if _fetchers_loaded:
        return
    with _fetchers_lock:
        if _fetchers_loaded:
            return
        from fetchers.eastmoney_chip import MarginFetcher, HolderFetcher, TopHolderFetcher
        _margin_fetcher = MarginFetcher()
        _holder_fetcher = HolderFetcher()
        _top_holder_fetcher = TopHolderFetcher()
        _fetchers_loaded = True


def get_margin(code: str, days: int = 20) -> List[MarginData]:
    """获取融资融券数据。

    Args:
        code: 股票代码（如 sh600989, 600989）
        days: 获取天数，默认 20

    Returns:
        融资融券数据列表，失败返回空列表
    """
    _load_fetchers()
    result = _margin_fetcher.fetch(code, days=days)
    if not result:
        return []

    return [_dict_to_margin(d) for d in result]


def get_holders(code: str, periods: int = 4) -> List[HolderData]:
    """获取股东户数数据。

    Args:
        code: 股票代码
        periods: 获取期数，默认 4

    Returns:
        股东户数数据列表，失败返回空列表
    """
    _load_fetchers()
    result = _holder_fetcher.fetch(code, periods=periods)
    if not result:
        return []

    return [_dict_to_holder(d) for d in result]


def get_top_holders(code: str, date: str = "") -> List[TopHolderRecord]:
    """获取十大流通股东数据。

    Args:
        code: 股票代码
        date: 截止日期（空值取最新）

    Returns:
        十大流通股东数据列表，失败返回空列表
    """
    _load_fetchers()
    result = _top_holder_fetcher.fetch(code, date=date)
    if not result:
        return []

    return [_dict_to_top_holder(d) for d in result]


def get_margin_summary(code: str, days: int = 20) -> dict:
    """获取融资融券汇总数据（用于评分）。

    Returns:
        {
            "rzjme_5d": float,  # 近5日融资净买入
            "rzjme_trend": str, # 趋势（连续增加/连续减少/波动）
            "rz_ratio": float,  # 融资/融券比
            "sentiment": str,   # 杠杆情绪（偏多/中性/偏空）
        }
    """
    data = get_margin(code, days=days)
    if not data:
        return {}

    # 近5日融资净买入
    recent_5 = data[:5]
    rzjme_5d = sum(d.rzjme for d in recent_5)

    # 趋势判断
    rzjme_values = [d.rzjme for d in recent_5]
    if all(v > 0 for v in rzjme_values):
        rzjme_trend = "连续增加"
    elif all(v < 0 for v in rzjme_values):
        rzjme_trend = "连续减少"
    else:
        rzjme_trend = "波动"

    # 融资/融券比
    latest = data[0]
    rz_ratio = latest.rzye / latest.rqye if latest.rqye > 0 else 0

    # 杠杆情绪
    if rzjme_5d > 0 and rz_ratio > 30:
        sentiment = "偏多"
    elif rzjme_5d < 0 and rz_ratio < 20:
        sentiment = "偏空"
    else:
        sentiment = "中性"

    return {
        "rzjme_5d": rzjme_5d,
        "rzjme_trend": rzjme_trend,
        "rz_ratio": rz_ratio,
        "sentiment": sentiment,
    }


def get_holders_summary(code: str, periods: int = 4) -> dict:
    """获取股东户数汇总数据（用于评分）。

    Returns:
        {
            "concentration": str,  # 集中度评级（由多期趋势判断得出）
            "change_rate": float,  # 最新变化率
            "trend": str,          # 趋势
        }
    """
    data = get_holders(code, periods=periods)
    if not data:
        return {}

    # 趋势判断：通过多期股东户数变化判断集中度趋势
    if len(data) >= 2:
        changes = [d.holder_num_change for d in data[:3]]
        if all(c < 0 for c in changes):
            trend = "持续集中"
        elif all(c > 0 for c in changes):
            trend = "持续分散"
        else:
            trend = "波动"
    else:
        trend = "数据不足"

    # ���据趋势判断集中度评级
    if trend == "持续集中":
        concentration = "持续集中"
    elif trend == "持续分散":
        concentration = "分散"
    else:
        # 波动或数据不足时，取最新一期的原始评级
        concentration = data[0].concentration

    return {
        "concentration": concentration,
        "change_rate": data[0].holder_num_change,
        "trend": trend,
    }


# ---------- 内部转换函数 ----------

def _dict_to_margin(d: dict) -> MarginData:
    """将 fetcher 返回的 dict 转为 MarginData。"""
    return MarginData(
        date=d.get("date", ""),
        code=d.get("code", ""),
        rzye=to_float(d.get("rzye")),
        rqye=to_float(d.get("rqye")),
        rzmre=to_float(d.get("rzmre")),
        rzche=to_float(d.get("rzche")),
        rzjme=to_float(d.get("rzjme")),
        rqmcl=to_float(d.get("rqmcl")),
        rqchl=to_float(d.get("rqchl")),
        rqjmg=to_float(d.get("rqjmg")),
        rqyl=to_float(d.get("rqyl")),
    )


def _dict_to_holder(d: dict) -> HolderData:
    """将 fetcher 返回的 dict 转为 HolderData。"""
    return HolderData(
        end_date=d.get("end_date", ""),
        code=d.get("code", ""),
        holder_num=to_int(d.get("holder_num")),
        avg_amount=to_float(d.get("avg_amount")),
        holder_num_change=to_float(d.get("holder_num_change")),
        prev_holder_num=to_int(d.get("prev_holder_num")),
        concentration=d.get("concentration", ""),
    )


def _dict_to_top_holder(d: dict) -> TopHolderRecord:
    """将 fetcher 返回的 dict 转为 TopHolderRecord。"""
    return TopHolderRecord(
        end_date=d.get("end_date", ""),
        rank=to_int(d.get("rank")),
        holder_name=d.get("holder_name", ""),
        holder_type=d.get("holder_type", ""),
        hold_num=to_float(d.get("hold_num")),
        hold_ratio=to_float(d.get("hold_ratio")),
        change=to_float(d.get("change")),
        change_type=d.get("change_type", ""),
        is_institution=bool(d.get("is_institution")),
    )

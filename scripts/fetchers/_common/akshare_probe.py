"""akshare 接口变动探活模块。

akshare 本质是公开数据源的爬虫聚合层，版本更新频繁、接口签名经常变化
（如列名从"日期"变为"交易日"）。本模块用标杆股票做一次轻量调用，
校验返回 DataFrame 是否含预期列，探测接口是否已变动。

设计:
    - 探活不阻断：失败只返回 degraded 标记，由调用方决定是否降级。
    - 结果带 TTL 缓存（默认 10 分钟），避免每次 fetcher 调用都探活。
    - 接入 monitor/health.py：探活失败时在健康度矩阵标注。

参考: https://zhuanlan.zhihu.com/p/2067944129309446823
      文档第四节 "接口变动频繁 ... 要建立接口健康检查 + 降级机制"
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 探活结果缓存（进程级，TTL 秒）
_PROBE_CACHE: dict[str, tuple[float, "ProbeResult"]] = {}
_PROBE_TTL = 600  # 10 分钟


@dataclass
class ProbeResult:
    """探活结果。"""

    ok: bool
    message: str
    missing_columns: list[str] | None = None

    @property
    def degraded(self) -> bool:
        """接口是否已变动（不可信赖）。"""
        return not self.ok


def _get_cached(domain: str) -> ProbeResult | None:
    """读取未过期的缓存结果。"""
    entry = _PROBE_CACHE.get(domain)
    if entry and (time.time() - entry[0]) < _PROBE_TTL:
        return entry[1]
    return None


def _set_cached(domain: str, result: ProbeResult) -> None:
    _PROBE_CACHE[domain] = (time.time(), result)


def reset_probe_cache() -> None:
    """重置探活缓存（测试用）。"""
    _PROBE_CACHE.clear()


def probe_kline() -> ProbeResult:
    """探活 akshare 日线接口 stock_zh_a_hist。

    校验返回 DataFrame 包含期望的中文列名。列名缺失 -> 接口已变动。
    """
    cached = _get_cached("kline")
    if cached:
        return cached

    expected_cols = {"日期", "开盘", "收盘", "最高", "最低", "成交量"}
    # 列名可能的别名（akshare 历史上变更过的命名）
    aliases = {
        "日期": ("交易日", "date"),
        "开盘": ("open",),
        "收盘": ("close",),
        "最高": ("high",),
        "最低": ("low",),
        "成交量": ("volume", "成交量股"),
    }

    try:
        import akshare as ak
    except ImportError:
        result = ProbeResult(ok=False, message="akshare 未安装")
        _set_cached("kline", result)
        return result

    try:
        # 标杆股票：浦发银行 sh600000，数据稳定
        df = ak.stock_zh_a_hist(symbol="600000", period="daily", adjust="qfq")
        if df is None or df.empty:
            result = ProbeResult(ok=False, message="akshare 日线返回空")
            _set_cached("kline", result)
            return result

        actual_cols = set(df.columns)
        # 检查每个期望列（含别名）
        missing = []
        for col in expected_cols:
            if col in actual_cols:
                continue
            if any(a in actual_cols for a in aliases.get(col, ())):
                continue
            missing.append(col)

        if missing:
            result = ProbeResult(
                ok=False,
                message=f"akshare 日线接口列名变动: 缺失 {missing}，实际列 {sorted(actual_cols)}",
                missing_columns=missing,
            )
        else:
            result = ProbeResult(ok=True, message="akshare 日线接口正常")
        _set_cached("kline", result)
        return result
    except Exception as e:
        result = ProbeResult(ok=False, message=f"akshare 日线探活异常: {e}")
        _set_cached("kline", result)
        return result


def probe_finance() -> ProbeResult:
    """探活 akshare 财务接口 stock_financial_abstract。

    校验返回 DataFrame 包含期望的"指标"列。
    """
    cached = _get_cached("finance")
    if cached:
        return cached

    try:
        import akshare as ak
    except ImportError:
        result = ProbeResult(ok=False, message="akshare 未安装")
        _set_cached("finance", result)
        return result

    try:
        df = ak.stock_financial_abstract(symbol="600000")
        if df is None or df.empty:
            result = ProbeResult(ok=False, message="akshare 财务接口返回空")
            _set_cached("finance", result)
            return result

        actual_cols = set(df.columns)
        # akshare 财务摘要含 "指标" 列
        if "指标" not in actual_cols:
            result = ProbeResult(
                ok=False,
                message=f"akshare 财务接口列名变动: 缺失 '指标'，实际列 {sorted(actual_cols)}",
                missing_columns=["指标"],
            )
        else:
            result = ProbeResult(ok=True, message="akshare 财务接口正常")
        _set_cached("finance", result)
        return result
    except Exception as e:
        result = ProbeResult(ok=False, message=f"akshare 财务探活异常: {e}")
        _set_cached("finance", result)
        return result


def get_akshare_health() -> dict:
    """获取 akshare 各接口域的探活结果（供 health.py 调用）。

    Returns:
        {"kline": {"ok": bool, "message": str, "degraded": bool}, ...}
    """
    return {
        "kline": {
            "ok": probe_kline().ok,
            "message": probe_kline().message,
            "degraded": probe_kline().degraded,
        },
        "finance": {
            "ok": probe_finance().ok,
            "message": probe_finance().message,
            "degraded": probe_finance().degraded,
        },
    }

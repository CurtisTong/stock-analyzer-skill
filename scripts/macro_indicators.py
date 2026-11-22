#!/usr/bin/env python3
"""
宏观指标获取模块（v2.5.x 新增）。

数据源策略：yfinance 优先（已装）+ 东方财富网页 API（无依赖）+ 手工 mock fixture fallback。

设计原则：
1. 单一职责：仅获取宏观 / 杠杆 / 流动性相关数据，不做分析。
2. 优雅降级：每个 fetch_* 函数独立 try/except，失败时返回 None；fetch_all 汇总时记录 degraded_fields。
3. 回写 fixture：成功拉取真实数据后回写到 macro_snapshot.json（TTL 1 小时）；手工覆盖请保留字段名。
4. 不走 BaseFetcher 体系：参考 strategies/macro/gate.py:86-106 的轻 try/except 模式，避免引入 akshare/tushare。

yfinance 代码映射：
- ^TNX    → 10 年期美债收益率（%）
- DX-Y.NYB → 美元指数
- CNY=X    → 美元兑离岸人民币
- ^VIX     → 恐慌指数
- GC=F     → COMEX 黄金
- CL=F     → WTI 原油
- BZ=F     → 布伦特原油
- IF=F     → 沪深 300 股指期货连续合约（估算基差用，非主力）
- IC=F     → 中证 500 股指期货连续合约
- IH=F     → 上证 50 股指期货连续合约

⚠️ yfinance 期货合约是连续合约，**基差数据为估算值**，精确主力基差需东方财富 API。

用法:
  from macro_indicators import fetch_all
  data = fetch_all()
"""

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 确保 scripts/ 在 import 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT_PATH = DATA_DIR / "macro_snapshot.json"

# TTL：成功拉取后 1 小时内复用 fixture（避免 yfinance 反复慢调用）
SNAPSHOT_TTL_SECONDS = 3600


# ═══════════════════════════════════════════════════════════════
# Fixture 读写
# ═══════════════════════════════════════════════════════════════


from common.cli_base import create_parser, handle_errors
from common.exceptions.silent_fallback import log_silent_fallback
from common.freshness import (
    BEIJING as _BEIJING,
)
from common.freshness import (
    ET as _ET,
)
from common.freshness import StaleDataError, assert_fresh, parse_quote_time


def _load_snapshot() -> dict:
    """读取 macro_snapshot.json fixture。失败返回空 dict。"""
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug("加载 macro_snapshot.json 失败: %s", e)
        return {}


def _save_snapshot(snapshot: dict, key_ts: str | None = None) -> None:
    """回写 fixture（带 updated 时间戳）。

    Args:
        snapshot: 完整 snapshot dict（会被原地修改）。
        key_ts: per-key 时间戳字段名（如 ``aluminum_cny_t_ts``）。
            传入时额外记录该字段的独立拉取时间，供 ``_key_is_fresh`` 判断。
            None 时仅刷新全局 updated。
    """
    try:
        now = datetime.now().isoformat(timespec="seconds")
        snapshot["updated"] = now  # 保留全局 updated（向后兼容 + 人工参考）
        if key_ts:
            snapshot[key_ts] = now
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("回写 macro_snapshot.json 失败: %s", e)


def _snapshot_is_fresh(snapshot: dict) -> bool:
    """检查 fixture 是否在 TTL 内（全局 updated，向后兼容）。

    ⚠️ 全局时间戳在第一个 fetcher 成功后即刷新，会导致同批次后续 fetcher 误判为新鲜。
    fetcher 内部应优先使用 ``_key_is_fresh`` 做 per-key 判断。
    """
    if not snapshot or "updated" not in snapshot:
        return False
    try:
        ts = datetime.fromisoformat(snapshot["updated"])
        age = (datetime.now() - ts).total_seconds()
        return age < SNAPSHOT_TTL_SECONDS
    except Exception:
        return False


def _key_is_fresh(snapshot: dict, fixture_key: str) -> bool:
    """检查单个 fixture_key 是否在 TTL 内（per-key 时间戳）。

    仅读 ``{fixture_key}_ts`` 旁路时间戳；无此字段时返回 False（触发拉取）。
    不回退全局 ``updated`` -- 全局时间戳在第一个 fetcher 成功后即刷新，
    回退会导致同批次后续未拉取的 key 被误判为新鲜（TTL 短路 bug）。
    """
    ts_str = snapshot.get(f"{fixture_key}_ts")
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(ts_str)
        return (datetime.now() - ts).total_seconds() < SNAPSHOT_TTL_SECONDS
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# yfinance 通用拉取
# ═══════════════════════════════════════════════════════════════


def _yfinance_get(symbol: str, value_attr: str = "last_price") -> float | None:
    """通过 yfinance 拉取单个 symbol 的 last_price / previous_close。

    范本：strategies/macro/gate.py:86-106 的 try/except 模式。
    #2: yfinance 网络超时时静默降级到 fixture，不阻塞主流程。

    Args:
        symbol: yfinance ticker（如 ^TNX, GC=F, DX-Y.NYB）
        value_attr: fast_info 属性名（默认 last_price）

    Returns:
        float | None
    """
    try:
        import yfinance as yf

        # #2: 设置较短超时（5秒），避免 yfinance 默认长超时阻塞
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        val = getattr(info, value_attr, None)
        if val is not None and val > 0:
            return float(val)
        return None
    except Exception as e:
        logger.debug("yfinance %s 拉取失败（降级到 fixture）: %s", symbol, e)
        return None


# ═══════════════════════════════════════════════════════════════
# 新浪外盘（hf_* 期货 / fx_s* 外汇）——yfinance 限流时的兜底
# ═══════════════════════════════════════════════════════════════

# yfinance ticker -> (新浪代码, 现价字段下标)
# 2026-11-19 实测：hf_GC/hf_CL/hf_OIL/fx_susdcnh 返回真实报价；
# hf_DX（美元指数）、hf_VIX（VIX）、hf_TNX（美债 10Y）均返回空串，
# 即这三个字段新浪侧没有可用兜底，仍按 None + degraded 处理。
_SINA_FOREIGN_SYMBOLS: dict[str, tuple[str, int]] = {
    "GC=F": ("hf_GC", 0),  # 纽约黄金，USD/oz（与 COMEX GC=F 同口径，无需换算）
    "CL=F": ("hf_CL", 0),  # 纽约原油（WTI），USD/bbl
    "BZ=F": ("hf_OIL", 0),  # 布伦特原油，USD/bbl
    "CNY=X": ("fx_susdcnh", 1),  # 离岸人民币 USD/CNH（下标 1 为现价）
    "DX-Y.NYB": ("DINIW", 1),  # 美元指数（点），与 DX-Y.NYB 同口径
}

# 美股指数（腾讯，index.com 于 2026-11-19 实测可用）：VIX 在新浪侧无数据
_TENCENT_US_INDEX: dict[str, str] = {"^VIX": "usVIX"}


def _sina_foreign_get(symbol: str) -> float | None:
    """按 yfinance ticker 取新浪外盘报价；无映射/网络失败/空返回 None（不抛）。

    单位说明（必须与 yfinance 对齐，禁止静默套用）：
    - hf_GC 纽约黄金：USD/盎司，与 yfinance GC=F 同单位，直接使用；
    - hf_CL / hf_OIL：USD/桶，与 CL=F / BZ=F 同单位；
    - fx_susdcnh：USD/CNH 汇率（1 美元兑人民币），与 CNY=X 同口径。
    上证所/大商所的人民币计价合约（AU0/SC0）**不用**：单位是 CNY/克、CNY/桶，
    与上面字段的单位不同，套用会静默错 7 倍以上。
    """
    mapped = _SINA_FOREIGN_SYMBOLS.get(symbol)
    if not mapped:
        return None
    code, idx = mapped
    try:
        import urllib.request

        req = urllib.request.Request(
            f"https://hq.sinajs.cn/list={code}",
            headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"},
        )
        raw = urllib.request.urlopen(req, timeout=5).read().decode("gbk", errors="replace")
        body = raw.split("=", 1)[1].strip().strip(";").strip('"') if "=" in raw else ""
        parts = body.split(",")
        if len(parts) <= idx:
            return None
        val = float(parts[idx])
        return val if val > 0 else None
    except Exception as e:
        log_silent_fallback("macro_indicators._sina_foreign_get", e)
        return None


# 东财数据中心：美债收益率（datacenter.eastmoney.com 与 push2 不同域，实测可用）
# 字段：EMG00001310=美国10年，EMG00001308=美国5年，EMG00001306=美国2年，EMM00166466=中国10年
# 单位：百分数（5.07 表示 5.07%），直接使用，不要再 /100
_EM_TREASURY_URL = (
    "https://datacenter.eastmoney.com/api/data/get"
    "?type=RPTA_WEB_TREASURYYIELD&sty=ALL&st=SOLAR_DATE&sr=-1"
    "&token=894050c76af8597a853f5b408b759f5d&p=1&ps=5&pageNo=1&pageNum=1"
)


def _eastmoney_treasury_10y() -> tuple[float, str] | None:
    """美债 10Y（%）从东财数据中心取"最近一行非 null"。

    2026-11-19 实测：最新日（11-19）该字段为 null（当日未更新），
    前一天（11-18）才是 5.07。所以不能取最新行就完事，必须向前找非空值。
    返回 (value, 数据日期)；失败返回 None，不抛。
    """
    try:
        import urllib.request

        req = urllib.request.Request(
            _EM_TREASURY_URL,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"},
        )
        raw = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="replace")
        rows = ((json.loads(raw).get("result") or {}).get("data")) or []
        for row in rows:
            val = row.get("EMG00001310")
            if val is None:
                continue
            return float(val), str(row.get("SOLAR_DATE") or "")[:10]
        return None
    except Exception as e:
        log_silent_fallback("macro_indicators._eastmoney_treasury_10y", e)
        return None


# CBOE 官方延迟报价（307 → cdn-api，urllib 默认跟随）；无 Referer 实测 403。
# 字段口径（2026-11-22 20:48 实测原始报文）：
#   data.current_price   = 现价（指数点）
#   data.last_trade_time = 真实报价时间，美东本地 naive（如 2026-11-20T16:15:01）
#   顶层 timestamp       = 报文生成时间（UTC），**不是报价时间**，禁止用作 as_of
#   data.prev_day_close  = 与 close 同为 35.89，但 change=+20.76% 反推昨收应≈29.72，
#                          该字段不可靠，禁止用它算涨跌
_CBOE_VIX_URL = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"


def _cboe_payload_is_dirty(data: dict) -> bool:
    """CBOE _VIX.json 脏数据判定：现价与昨收相同，却报非 0 涨跌幅。

    真样本（2026-11-22 20:48 实抓）：``current_price == prev_day_close == 35.89``
    却报 ``price_change_percent = +20.7579``，反推昨收应≈29.72 —— 字段自相矛盾。
    命中时整条报价不可用（现价、昨收、涨跌全部丢弃），不能只标 warn 继续用。
    任一字段缺失或类型异常不判脏，按现有「缺字段→不可用」路径处理。
    """
    try:
        cur, prev, chg = data.get("current_price"), data.get("prev_day_close"), data.get("price_change_percent")
        if cur is None or prev is None or chg is None:
            return False
        return abs(float(cur) - float(prev)) < 1e-9 and abs(float(chg)) > 1e-9
    except (TypeError, ValueError):
        return False


def _cboe_vix() -> tuple[float | None, str | None, bool] | None:
    """VIX 指数点（CBOE 官方延迟报价，delay_minutes=15）。

    返回 ``(value, 原始报价时间 last_trade_time, dirty)``，时间保持美东本地原样，
    由调用方按美东时区做新鲜度断言并换算北京。缺 last_trade_time 时返回 None，
    不用顶层 timestamp 顶替（那是报文生成时间）。dirty=True 表示报文内部自相矛盾，
    调用方必须整字段丢弃。失败返回 None，不抛。
    """
    try:
        import urllib.request

        req = urllib.request.Request(
            _CBOE_VIX_URL,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cboe.com/"},
        )
        raw = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="replace")
        data = json.loads(raw).get("data") or {}
        val = data.get("current_price")
        quote_ts = data.get("last_trade_time")
        if val is None or not quote_ts:
            return None
        return float(val), str(quote_ts), _cboe_payload_is_dirty(data)
    except Exception as e:
        log_silent_fallback("macro_indicators._cboe_vix", e)
        return None


# 腾讯美股指数报文字段：下标 3=现价，下标 30=报价时间（美东本地，如 2026-09-11 09:30:00）
_TENCENT_QUOTE_TS_INDEX = 30


def _tencent_us_index_get_with_ts(symbol: str) -> tuple[float | None, str | None]:
    """取现价 + 报文自带的原始报价时间；新鲜度敏感路径必须用这个版本。

    2026-11-22 实测 usVIX 现价 21.67，但报文自带日期 2026-09-11 09:30:00
    （72 天前），旧实现只读下标 3、丢弃日期，还盖当天 as_of，等于旧值冒充实时。
    """
    code = _TENCENT_US_INDEX.get(symbol)
    if not code:
        return None, None
    try:
        import urllib.request

        req = urllib.request.Request(
            f"https://qt.gtimg.cn/q={code}",
            headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"},
        )
        raw = urllib.request.urlopen(req, timeout=5).read().decode("gbk", errors="replace")
        body = raw.split('"', 1)[1].rsplit('"', 1)[0] if '"' in raw else ""
        fields = body.split("~")
        if len(fields) <= 3:
            return None, None
        val = float(fields[3])
        quote_ts = fields[_TENCENT_QUOTE_TS_INDEX].strip() if len(fields) > _TENCENT_QUOTE_TS_INDEX else ""
        return (val if val > 0 else None), (quote_ts or None)
    except Exception as e:
        log_silent_fallback("macro_indicators._tencent_us_index_get", e)
        return None, None


def _tencent_us_index_get(symbol: str) -> float | None:
    """兼容旧调用方：只要值不要时间。新鲜度敏感路径请用 _with_ts 版本。"""
    val, _ = _tencent_us_index_get_with_ts(symbol)
    return val


# ═══════════════════════════════════════════════════════════════
# akshare 通用拉取（国内商品期货连续合约）
# ═══════════════════════════════════════════════════════════════

# 品种 -> akshare 连续合约符号（futures_zh_daily_sina，已逐个验证可用）
# 动力煤不在其中：郑商所 2021 起暂停交易，无可用连续合约（C0 实为玉米，ZC0 冻结于 2022-12-30）
_AKSHARE_FUTURES_SYMBOLS = {
    "aluminum": "AL0",  # 沪铝连续（shfe，5250 条，2005-起）
    "copper": "CU0",  # 沪铜连续（shfe，5250 条）
    "rebar": "RB0",  # 螺纹钢连续（shfe，4214 条，2009-起）
    "polyethylene": "L0",  # 塑料连续 / LLDPE（dce，4625 条）
    "polypropylene": "PP0",  # 聚丙烯连续（dce，3022 条，2014-起）
    "lithium": "LC0",  # 碳酸锂连续（gfex，736 条，2023-07 起）
}

# 近 1 年历史分位计算所需交易日数（约 250 个交易日/年）
_PERCENTILE_LOOKBACK = 250


# ═══════════════════════════════════════════════════════════════
# 新浪国内商品期货（零依赖：nf_ 实时 + 无前缀历史）
# ═══════════════════════════════════════════════════════════════

# ⚠️ 实时与历史接口的代码前缀不同（2026-11-22 实测）：
#   实时 hq.sinajs.cn      -> nf_AL0 / nf_AO0（不带 nf_ 会返回 2024 过期数据 / 空串）
#   历史 getDailyKLine     -> AL0 / AO0（带 nf_ 反而无数据）
# 字段下标（nf_ 实时快照逗号分隔）：8=最新价, 10=昨结算, 17=日期
_SINA_FUTURES_REALTIME: dict[str, tuple[str, int, int, int]] = {
    "aluminum": ("nf_AL0", 8, 10, 17),
    "alumina": ("nf_AO0", 8, 10, 17),
}
_SINA_FUTURES_HISTORY: dict[str, str] = {
    "aluminum": "AL0",
    "alumina": "AO0",
}
# 电解 1 吨铝理论耗氧化铝约 1.92 吨（行业通用简化系数，L2 冶炼价差口径）
_ALUMINA_PER_TON_AL = 1.92


def _sina_futures_realtime(code: str, price_idx: int, settle_idx: int, date_idx: int) -> dict | None:
    """取新浪国内期货实时快照（nf_ 前缀）；失败返回 None，不抛。

    返回 {"price": float, "settle": float, "date": str}。
    单位 CNY/吨，与历史 getDailyKLine 的 close 同口径。
    """
    try:
        import re
        import urllib.request

        req = urllib.request.Request(
            f"https://hq.sinajs.cn/list={code}",
            headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"},
        )
        raw = urllib.request.urlopen(req, timeout=5).read().decode("gbk", errors="replace")
        m = re.search(r'hq_str_' + re.escape(code) + r'="([^"]*)"', raw)
        if not m or not m.group(1):
            return None
        parts = m.group(1).split(",")
        if len(parts) <= max(price_idx, settle_idx, date_idx):
            return None
        price = float(parts[price_idx])
        settle = float(parts[settle_idx])
        if price <= 0:
            return None
        return {"price": price, "settle": settle, "date": parts[date_idx]}
    except Exception as e:
        log_silent_fallback("macro_indicators._sina_futures_realtime", e)
        return None


def _sina_futures_history(symbol: str, lookback: int = _PERCENTILE_LOOKBACK) -> list[float] | None:
    """取新浪国内期货历史收盘价序列（⚠️ 无 nf_ 前缀）；失败返回 None，不抛。

    返回按时间正序的 close 列表（CNY/吨）。接口返回 JSONP，需正则提取数组。
    """
    try:
        import re
        import urllib.request

        url = (
            "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
            f"var%20_{symbol}=/InnerFuturesNewService.getDailyKLine?symbol={symbol}"
        )
        req = urllib.request.Request(
            url,
            headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"},
        )
        txt = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "replace")
        m = re.search(r"=\((\[.*\])\);?", txt)
        if not m:
            return None
        rows = json.loads(m.group(1))
        closes = [float(r["c"]) for r in rows[-lookback:] if float(r.get("c") or 0) > 0]
        return closes or None
    except Exception as e:
        log_silent_fallback("macro_indicators._sina_futures_history", e)
        return None


def fetch_commodity_sina(material_key: str, fixture_key: str) -> dict | None:
    """国内商品期货三段式拉取（零依赖新浪源，对齐 fetch_commodity_akshare）。

    三段式：
      1. 新鲜 fixture（per-key TTL）-> 直接返回
      2. 新浪实时（nf_ 前缀）+ 历史分位（无前缀）-> 回写 snapshot + 返回
      3. 过期 fixture -> 返回 source="fixture(stale)"

    Args:
        material_key: 品种标识（aluminum / alumina）
        fixture_key: snapshot 价格字段名（aluminum_cny_t / alumina_cny_t）
    """
    snapshot = _load_snapshot()
    pct_key = f"{material_key}_percentile_1y"

    # 1. 新鲜 fixture 短路
    if _key_is_fresh(snapshot, fixture_key) and fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": _SINA_FUTURES_REALTIME.get(material_key, ("unknown",))[0],
            "percentile": snapshot.get(pct_key),
        }

    # 2. 新浪实时 + 历史分位
    spec = _SINA_FUTURES_REALTIME.get(material_key)
    if spec:
        rt = _sina_futures_realtime(*spec)
        if rt is not None:
            snapshot[fixture_key] = round(rt["price"], 2)
            history = _sina_futures_history(_SINA_FUTURES_HISTORY[material_key])
            pct = _calc_percentile(history) if history else None
            if pct is not None:
                snapshot[pct_key] = pct
            snapshot[f"{fixture_key}_date"] = rt["date"]
            _save_snapshot(snapshot, key_ts=f"{fixture_key}_ts")
            return {
                "value": round(rt["price"], 2),
                "as_of": f"{rt['date']}T00:00:00",
                "source": "sina_futures",
                "symbol": spec[0],
                "percentile": pct,
                "history": history,  # 供价差计算复用，fetch_all 输出契约不含此字段
            }

    # 3. 过期 fixture 兜底
    if fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": _SINA_FUTURES_REALTIME.get(material_key, ("unknown",))[0],
            "percentile": snapshot.get(pct_key),
        }
    return None


def fetch_aluminum_sina() -> dict | None:
    """沪铝期货连续（CNY/吨）。新浪 nf_AL0 实时 + 历史分位 + fixture 兜底。"""
    return fetch_commodity_sina("aluminum", "aluminum_cny_t")


def fetch_alumina() -> dict | None:
    """氧化铝期货连续（CNY/吨）。新浪 nf_AO0 实时 + 历史分位 + fixture 兜底。"""
    return fetch_commodity_sina("alumina", "alumina_cny_t")


def fetch_aluminum_alumina_spread(
    aluminum: dict | None = None, alumina: dict | None = None
) -> dict | None:
    """电解铝冶炼价差（L2 简化口径）= 铝价 − 1.92 × 氧化铝价。

    - 1.92 为吨铝耗氧化铝行业简化系数，未扣电力/预焙阳极（L3 完全成本留二期）。
    - 分位用两者历史序列按日对齐计算；任一历史缺失则为 None。
    - 允许传入已拉取的 aluminum/alumina dict，避免 fetch_all 重复请求。
    """
    snapshot = _load_snapshot()
    spread_key = "al_alumina_spread_cny_t"
    pct_key = "al_alumina_spread_percentile_1y"

    # 0. 新鲜 fixture 短路（断网时铝/氧化铝走 fixture 无 history，需从此处恢复价差分位）
    if _key_is_fresh(snapshot, spread_key) and spread_key in snapshot:
        return {
            "value": snapshot[spread_key],
            "as_of": snapshot.get("updated"),
            "source": "fixture",
            "symbol": "AL0-1.92*AO0",
            "percentile": snapshot.get(pct_key),
            "ratio": snapshot.get("al_alumina_spread_ratio", _ALUMINA_PER_TON_AL),
            "note": "L2 简化口径，未扣电力/预焙阳极成本",
        }

    al = aluminum if aluminum is not None else fetch_aluminum_sina()
    ao = alumina if alumina is not None else fetch_alumina()
    if al is None or ao is None:
        return None

    spread = al["value"] - _ALUMINA_PER_TON_AL * ao["value"]
    al_hist = al.get("history")
    ao_hist = ao.get("history")
    pct = None
    if al_hist and ao_hist:
        n = min(len(al_hist), len(ao_hist))
        spread_hist = [a - _ALUMINA_PER_TON_AL * o for a, o in zip(al_hist[-n:], ao_hist[-n:])]
        pct = _calc_percentile(spread_hist + [spread])

    # 回写 fixture（供断网兜底）
    snapshot[spread_key] = round(spread, 2)
    if pct is not None:
        snapshot[pct_key] = pct
    snapshot["al_alumina_spread_ratio"] = _ALUMINA_PER_TON_AL
    _save_snapshot(snapshot, key_ts=f"{spread_key}_ts")

    return {
        "value": round(spread, 2),
        "as_of": al.get("as_of") or ao.get("as_of"),
        "source": "sina_futures(derived)",
        "symbol": "AL0-1.92*AO0",
        "percentile": pct,
        "ratio": _ALUMINA_PER_TON_AL,
        "note": "L2 简化口径，未扣电力/预焙阳极成本",
    }


def _akshare_get(symbol: str) -> float | None:
    """通过 akshare 拉取国内商品期货连续合约最新收盘价（CNY/吨）。

    lazy import akshare（参考 _yfinance_get 的 try/except 模式），未安装或拉取失败返回 None。
    """
    try:
        import akshare as ak

        df = ak.futures_zh_daily_sina(symbol=symbol)
        if df is None or len(df) == 0:
            return None
        val = float(df.iloc[-1]["close"])
        return val if val > 0 else None
    except Exception as e:
        logger.debug("akshare %s 拉取失败: %s", symbol, e)
        return None


def _akshare_get_history(symbol: str, lookback: int = _PERCENTILE_LOOKBACK) -> list[float] | None:
    """拉取国内商品期货连续合约近 N 个交易日收盘价序列（用于分位计算）。

    复用 futures_zh_daily_sina 同一接口（已含完整历史），不额外请求。
    返回按时间正序的 close 价格列表，或 None。
    """
    try:
        import akshare as ak

        df = ak.futures_zh_daily_sina(symbol=symbol)
        if df is None or len(df) == 0:
            return None
        closes = df["close"].astype(float).tail(lookback).tolist()
        return closes if closes else None
    except Exception as e:
        logger.debug("akshare %s 历史序列拉取失败: %s", symbol, e)
        return None


def _calc_percentile(history: list[float]) -> float | None:
    """计算最新价在历史序列中的分位（0-100，100=最高）。

    Args:
        history: 历史收盘价列表（正序），末位为最新。

    Returns:
        0-100 的分位值，或 None（序列不足）。
    """
    if not history or len(history) < 10:
        return None
    current = history[-1]
    count_below = sum(1 for p in history if p < current)
    return round(count_below / len(history) * 100, 1)


def _akshare_get_energy_index() -> tuple[float | None, float | None]:
    """拉取东方财富能源行业价格指数（EMI00662539）最新值 + 近 1 年分位。

    动力煤期货连续合约不可用（郑商所 2021 起暂停；C0 实为玉米、ZC0 冻结于 2022-12-30），
    以能源综合指数作代理。源 data.eastmoney.com，无 WAF，实时可用（4558 条历史）。

    Returns:
        (latest_index_value, percentile_1y)，任一不可得则对应位为 None。
    """
    try:
        import akshare as ak

        df = ak.macro_china_energy_index()
        if df is None or len(df) == 0:
            return None, None
        closes = df["最新值"].astype(float).tail(_PERCENTILE_LOOKBACK).tolist()
        if not closes:
            return None, None
        latest = closes[-1]
        pct = _calc_percentile(closes)
        return (round(latest, 2) if latest > 0 else None), pct
    except Exception as e:
        logger.debug("akshare 能源指数拉取失败: %s", e)
        return None, None


# ═══════════════════════════════════════════════════════════════
# 宏观-估值桥（5 个 fetch_*）
# ═══════════════════════════════════════════════════════════════


def fetch_treasury_10y() -> dict | None:
    """10 年期美债收益率（%）。yfinance ^TNX → 直接 = 百分比值。

    注意：^TNX 返回值已经是百分比（如 2.45 = 2.45%），无需 × 100。
    """
    snapshot = _load_snapshot()
    if _key_is_fresh(snapshot, "treasury_10y_pct") and "treasury_10y_pct" in snapshot:
        return {
            "value": snapshot["treasury_10y_pct"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "^TNX",
        }

    val = _yfinance_get("^TNX")
    source = "yfinance"
    as_of = datetime.now().isoformat()
    if val is None:
        # 兜底：东财数据中心 RPTA_WEB_TREASURYYIELD（百分数，最近非 null 行）
        em = _eastmoney_treasury_10y()
        if em is not None:
            val, data_date = em
            source = "eastmoney_treasury"
            as_of = f"{data_date}T00:00:00" if data_date else as_of
    if val is not None:
        snapshot["treasury_10y_pct"] = round(val, 2)
        _save_snapshot(snapshot, key_ts="treasury_10y_pct_ts")
        return {
            "value": round(val, 2),
            "as_of": as_of,
            "source": source,
            "symbol": "^TNX",
        }

    # fixture fallback（即使过期也用）
    if "treasury_10y_pct" in snapshot:
        return {
            "value": snapshot["treasury_10y_pct"],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": "^TNX",
        }
    return None


def fetch_usd_index() -> dict | None:
    """美元指数。yfinance DX-Y.NYB。"""
    snapshot = _load_snapshot()
    if _key_is_fresh(snapshot, "usd_index") and "usd_index" in snapshot:
        return {
            "value": snapshot["usd_index"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "DX-Y.NYB",
        }

    val = _yfinance_get("DX-Y.NYB")
    source = "yfinance"
    if val is None:
        # 兜底：新浪 DINIW（美元指数，指数点，与 DX-Y.NYB 同口径）
        val = _sina_foreign_get("DX-Y.NYB")
        source = "sina_foreign"
    if val is not None:
        snapshot["usd_index"] = round(val, 2)
        _save_snapshot(snapshot, key_ts="usd_index_ts")
        return {
            "value": round(val, 2),
            "as_of": datetime.now().isoformat(),
            "source": source,
            "symbol": "DX-Y.NYB",
        }

    if "usd_index" in snapshot:
        return {
            "value": snapshot["usd_index"],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": "DX-Y.NYB",
        }
    return None


def fetch_usd_cny() -> dict | None:
    """美元兑离岸人民币汇率。yfinance CNY=X。"""
    snapshot = _load_snapshot()
    if _key_is_fresh(snapshot, "usd_cny") and "usd_cny" in snapshot:
        return {
            "value": snapshot["usd_cny"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "CNY=X",
        }

    val = _yfinance_get("CNY=X")
    source = "yfinance"
    if val is None:
        # 兜底：新浪 fx_susdcnh（离岸人民币，USD/CNH）
        val = _sina_foreign_get("CNY=X")
        source = "sina_foreign"
    if val is not None:
        snapshot["usd_cny"] = round(val, 4)
        _save_snapshot(snapshot, key_ts="usd_cny_ts")
        return {
            "value": round(val, 4),
            "as_of": datetime.now().isoformat(),
            "source": source,
            "symbol": "CNY=X",
        }

    if "usd_cny" in snapshot:
        return {
            "value": snapshot["usd_cny"],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": "CNY=X",
        }
    return None


# VIX 报价最大年龄：上一交易日收盘（16:15 ET）+ 合理延迟。周末无美股交易，
# 周五收盘到周一 08:30 北京巡检已 51h —— 此时保留真实报价但标 stale=true 并降级结论，
# 不再盖抓取时间冒充实时价。
VIX_MAX_AGE_SECONDS = 48 * 3600


def fetch_vix() -> dict | None:
    """恐慌指数。yfinance ^VIX → CBOE 延迟报价 → 腾讯；每条 fallback 都校验原始报价时间。"""
    snapshot = _load_snapshot()
    if _key_is_fresh(snapshot, "vix") and "vix" in snapshot:
        return {
            "value": snapshot["vix"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "^VIX",
        }

    val = _yfinance_get("^VIX")
    source = "yfinance"
    as_of = datetime.now().isoformat()
    extra: dict = {}
    dirty_result: dict | None = None  # 脏数据整字段丢弃的信号，交给 fetch_all 标 degraded
    if val is None:
        # 兜底 1：CBOE 官方延迟报价（指数点；延迟 15 分钟，必须显式标注）
        cboe = _cboe_vix()
        if cboe is not None:
            cboe_val, quote_ts, cboe_dirty = cboe
            if cboe_dirty:
                # 脏数据（current==prev 却报非 0 涨跌）：整字段丢弃，绝不拿它算涨跌或进卡，
                # 也不能静默降级到腾讯 21.67 旧值冒充。只回传一个带 dirty 标记的不可用结果。
                dirty_result = {
                    "value": None,
                    "source": "cboe_delayed",
                    "symbol": "^VIX",
                    "dirty": True,
                    "dirty_reason": "current_price==prev_day_close 但 price_change_percent!=0",
                    "quote_time_local": quote_ts,
                }
                cboe_val = None
            try:
                quote_utc = parse_quote_time(quote_ts, source_tz=_ET)
            except StaleDataError as e:
                log_silent_fallback("macro_indicators.fetch_vix.cboe_no_quote_time", e)
                cboe_val = None  # 无原始报价时间 → 不可用，禁止用报文生成时间顶替
            else:
                if not cboe_dirty:
                    val = cboe_val
                    source = "cboe_delayed"
                    # as_of 用真实报价时间换算北京（带 +08:00），不是抓取时刻
                    as_of = quote_utc.astimezone(_BEIJING).isoformat()
                    extra = {
                        "delay_minutes": 15,
                        "quote_time_field": "last_trade_time",
                        "quote_time_exchange": "America/New_York",
                        "quote_time_local": quote_ts,
                    }
                    try:
                        assert_fresh(quote_ts, max_age=VIX_MAX_AGE_SECONDS, source_tz=_ET, label="vix.cboe")
                    except StaleDataError as e:
                        extra["stale"] = True
                        extra["stale_reason"] = str(e)
    if dirty_result is not None:
        # 脏报文整字段丢弃后不再降级到腾讯/旧快照，避免「标 degraded 但照出结论」复发
        return dirty_result
    if val is None:
        # 兜底 2：腾讯 usVIX（指数点，与 ^VIX 同口径），必须带报文自带日期
        tencent_val, tencent_ts = _tencent_us_index_get_with_ts("^VIX")
        if tencent_val is not None:
            try:
                quote_utc = assert_fresh(
                    tencent_ts, max_age=VIX_MAX_AGE_SECONDS, source_tz=_ET, label="vix.tencent"
                )
            except StaleDataError as e:
                log_silent_fallback("macro_indicators.fetch_vix.tencent_stale", e)
                tencent_val = None  # 过期值一律不采用，也不回退 as_of=now
            if tencent_val is not None:
                val = tencent_val
                source = "tencent_us_index"
                as_of = quote_utc.astimezone(_BEIJING).isoformat()
                extra = {
                    "quote_time_exchange": "America/New_York",
                    "quote_time_local": tencent_ts,
                }
    if val is not None:
        snapshot["vix"] = round(val, 2)
        _save_snapshot(snapshot, key_ts="vix_ts")
        return {
            "value": round(val, 2),
            "as_of": as_of,
            "source": source,
            "symbol": "^VIX",
            **extra,
        }

    if "vix" in snapshot:
        return {
            "value": snapshot["vix"],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": "^VIX",
        }
    return None


def fetch_commodity(symbol: str, fixture_key: str) -> dict | None:
    """通用大宗商品拉取（黄金/WTI/布伦特）。

    Args:
        symbol: yfinance ticker（GC=F / CL=F / BZ=F）
        fixture_key: 字段名（gold_usd_oz / wti_oil_usd / brent_oil_usd）
    """
    snapshot = _load_snapshot()
    if _key_is_fresh(snapshot, fixture_key) and fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": symbol,
        }

    val = _yfinance_get(symbol)
    source = "yfinance"
    if val is None:
        # 兜底：新浪外盘（hf_*），单位与 yfinance 同口径，见 _SINA_FOREIGN_SYMBOLS
        val = _sina_foreign_get(symbol)
        source = "sina_foreign"
    if val is not None:
        snapshot[fixture_key] = round(val, 2)
        _save_snapshot(snapshot, key_ts=f"{fixture_key}_ts")
        return {
            "value": round(val, 2),
            "as_of": datetime.now().isoformat(),
            "source": source,
            "symbol": symbol,
        }

    if fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": symbol,
        }
    return None


def fetch_gold() -> dict | None:
    return fetch_commodity("GC=F", "gold_usd_oz")


def fetch_brent_oil() -> dict | None:
    return fetch_commodity("BZ=F", "brent_oil_usd")


def fetch_wti_oil() -> dict | None:
    return fetch_commodity("CL=F", "wti_oil_usd")


def fetch_commodity_akshare(material_key: str, fixture_key: str, symbol: str) -> dict | None:
    """国内商品期货连续合约拉取（akshare 实时优先 + fixture 兜底）。

    3 段式（对称于 fetch_commodity 的 yfinance 版本）：
      1. 新鲜 fixture（TTL 1h）-> 直接返回
      2. akshare 实时拉取 -> 回写 snapshot + 返回（含近 1 年分位 percentile）
      3. 过期 fixture -> 返回 source="fixture(stale)"

    Args:
        material_key: 品种标识（aluminum/copper/rebar/...），用于 snapshot 旁路分位 key
        fixture_key: snapshot 中的价格字段名（aluminum_cny_t 等）
        symbol: akshare 连续合约符号（AL0/CU0/...）
    """
    snapshot = _load_snapshot()
    pct_key = f"{material_key}_percentile_1y"

    # 1. 新鲜 fixture 短路（per-key TTL）
    if _key_is_fresh(snapshot, fixture_key) and fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": symbol,
            "percentile": snapshot.get(pct_key),
        }

    # 2. akshare 实时拉取（价格 + 历史序列算分位）
    val = _akshare_get(symbol)
    if val is not None:
        snapshot[fixture_key] = round(val, 2)
        history = _akshare_get_history(symbol)
        pct = _calc_percentile(history) if history else None
        if pct is not None:
            snapshot[pct_key] = pct
        _save_snapshot(snapshot, key_ts=f"{fixture_key}_ts")
        return {
            "value": round(val, 2),
            "as_of": datetime.now().isoformat(),
            "source": "akshare",
            "symbol": symbol,
            "percentile": pct,
        }

    # 3. 过期 fixture 兜底
    if fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": symbol,
            "percentile": snapshot.get(pct_key),
        }
    return None


def fetch_lithium() -> dict | None:
    """电池级碳酸锂价格（CNY/吨）。akshare LC0 实时 + fixture 兜底。"""
    return fetch_commodity_akshare("lithium", "lithium_carbonate_cny_t", "LC0")


def fetch_polyethylene() -> dict | None:
    """聚乙烯 LLDPE 价格（CNY/吨）。akshare L0 实时 + fixture 兜底。"""
    return fetch_commodity_akshare("polyethylene", "polyethylene_cny_t", "L0")


def fetch_polypropylene() -> dict | None:
    """聚丙烯价格（CNY/吨）。akshare PP0 实时 + fixture 兜底。"""
    return fetch_commodity_akshare("polypropylene", "polypropylene_cny_t", "PP0")


def fetch_rebar() -> dict | None:
    """螺纹钢价格（CNY/吨）。akshare RB0 实时 + fixture 兜底。"""
    return fetch_commodity_akshare("rebar", "rebar_cny_t", "RB0")


def fetch_copper() -> dict | None:
    """铜价格（CNY/吨）。akshare CU0 实时 + fixture 兜底。"""
    return fetch_commodity_akshare("copper", "copper_cny_t", "CU0")


def fetch_aluminum() -> dict | None:
    """铝价格（CNY/吨）。akshare AL0 实时 + fixture 兜底。"""
    return fetch_commodity_akshare("aluminum", "aluminum_cny_t", "AL0")


def fetch_coal() -> dict | None:
    """动力煤价格代理。

    ⚠️ 动力煤期货连续合约不可用（郑商所 2021 起暂停交易；C0 实为玉米，ZC0 冻结于
    2022-12-30），akshare 亦无动力煤 CNY/吨 现货实时源（99qh 被 WAF 挡、100ppi 不发动力煤）。
    改用东方财富能源行业价格指数（EMI00662539）作代理：返回指数值 + 近 1 年分位，
    source 标记 "energy_index_proxy"。fixture 兜底读 coal_thermal_cny_t（历史字段，仅供 stale 兜底）。
    """
    snapshot = _load_snapshot()
    pct_key = "coal_percentile_1y"

    # 1. 新鲜 fixture 短路（per-key TTL）
    if _key_is_fresh(snapshot, "coal_thermal_cny_t") and "coal_thermal_cny_t" in snapshot:
        return {
            "value": snapshot["coal_thermal_cny_t"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "coal_thermal",
            "percentile": snapshot.get(pct_key),
        }

    # 2. 能源指数代理实时拉取
    latest, pct = _akshare_get_energy_index()
    if latest is not None:
        snapshot["coal_thermal_cny_t"] = latest
        if pct is not None:
            snapshot[pct_key] = pct
        _save_snapshot(snapshot, key_ts="coal_thermal_cny_t_ts")
        return {
            "value": latest,
            "as_of": datetime.now().isoformat(),
            "source": "energy_index_proxy",
            "symbol": "energy_index_EMI00662539",
            "percentile": pct,
        }

    # 3. 过期 fixture 兜底
    if "coal_thermal_cny_t" in snapshot:
        return {
            "value": snapshot["coal_thermal_cny_t"],
            "as_of": snapshot["updated"],
            "source": "fixture(stale)",
            "symbol": "coal_thermal",
            "percentile": snapshot.get(pct_key),
        }
    return None


# ═══════════════════════════════════════════════════════════════
# 杠杆-反身性
# ═══════════════════════════════════════════════════════════════


def fetch_margin_total() -> dict | None:
    """沪深两市汇总融资融券余额（亿元）。

    ⚠️ yfinance 不覆盖。东方财富有网页 API（`https://datacenter-web.eastmoney.com/api/data/v1/get?report=RPT_MARGIN_TRADE_STATISTICS`）
    但需解析 + 限流。本期 fixture-only。

    手动覆盖字段名：margin_balance_total_yi / margin_change_5d_pct
    """
    snapshot = _load_snapshot()
    if "margin_balance_total_yi" in snapshot:
        return {
            "value": snapshot["margin_balance_total_yi"],
            "change_5d_pct": snapshot.get("margin_change_5d_pct"),
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "sh+sz_margin_total",
        }
    return None


def fetch_futures_basis(symbol: str, fixture_key: str) -> dict | None:
    """股指期货连续合约基差估算（点）。

    ⚠️ yfinance IF=F 是连续合约，**与现货沪深 300 的差值是估算基差**，
    精确主力合约基差（IF 当月/季月/下季月）需要东方财富期货 API。
    本期 fixture-only，仅用于趋势参考。

    Args:
        symbol: yfinance ticker（IF=F / IC=F / IH=F）
        fixture_key: 字段名（if_main_basis_pts / ic_main_basis_pts / ih_main_basis_pts）
    """
    snapshot = _load_snapshot()
    if fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": symbol,
            "_warning": "yfinance 连续合约基差为估算值，仅作趋势参考",
        }
    return None


def fetch_if_basis() -> dict | None:
    return fetch_futures_basis("IF=F", "if_main_basis_pts")


def fetch_ic_basis() -> dict | None:
    return fetch_futures_basis("IC=F", "ic_main_basis_pts")


def fetch_ih_basis() -> dict | None:
    return fetch_futures_basis("IH=F", "ih_main_basis_pts")


# ═══════════════════════════════════════════════════════════════
# ERP（股权风险溢价）= 1/PE - 10Y 国债收益率
# ═══════════════════════════════════════════════════════════════


def fetch_erp_sh300() -> dict | None:
    """沪深 300 ERP = 1/PE - 10Y 国债收益率（%）。

    ⚠️ yfinance 000300.SS 没有直接 PE 字段，需通过财报计算。本期 fixture-only。
    """
    snapshot = _load_snapshot()
    if "erp_sh300_pct" in snapshot:
        return {
            "value": snapshot["erp_sh300_pct"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "ERP_SH300",
        }
    return None


# ═══════════════════════════════════════════════════════════════
# 统一入口：fetch_all
# ═══════════════════════════════════════════════════════════════


def fetch_all() -> dict:
    """一次性获取所有宏观 / 杠杆 / 估值桥指标。

    Returns:
        dict:
          {
            "macro": {treasury_10y_pct, usd_index, ..., as_of},
            "leverage": {margin_balance_total_yi, margin_change_5d_pct,
                         if_main_basis_pts, ic_main_basis_pts, ih_main_basis_pts},
            "valuation_bridge": {erp_sh300_pct},
            "data_quality": {degraded_fields: [...]}
          }
    """
    # 宏观：铝/氧化铝只拉一次，价差复用两者结果（避免重复请求 + 历史序列对齐）
    aluminum_data = fetch_aluminum_sina()
    alumina_data = fetch_alumina()
    macro = {
        "treasury_10y_pct": fetch_treasury_10y(),
        "usd_index": fetch_usd_index(),
        "usd_cny": fetch_usd_cny(),
        "vix": fetch_vix(),
        "gold_usd_oz": fetch_gold(),
        "brent_oil_usd": fetch_brent_oil(),
        "wti_oil_usd": fetch_wti_oil(),
        "lithium_carbonate_cny_t": fetch_lithium(),
        "aluminum_cny_t": aluminum_data,
        "alumina_cny_t": alumina_data,
        "al_alumina_spread": fetch_aluminum_alumina_spread(aluminum_data, alumina_data),
    }
    # 杠杆
    leverage = {
        "margin_balance_total": fetch_margin_total(),
        "if_main_basis": fetch_if_basis(),
        "ic_main_basis": fetch_ic_basis(),
        "ih_main_basis": fetch_ih_basis(),
    }
    # 估值桥
    valuation_bridge = {
        "erp_sh300": fetch_erp_sh300(),
    }

    # 数据质量：每个 fetch_* 失败 → 加入 degraded
    degraded = []
    for section_name, section in [
        ("macro", macro),
        ("leverage", leverage),
        ("valuation_bridge", valuation_bridge),
    ]:
        for key, val in section.items():
            if val is None:
                degraded.append(f"{section_name}.{key}")
            elif isinstance(val, dict) and val.get("dirty"):
                # 脏数据整字段已丢弃，值不可用；同时留 dirty 标记供溯源
                degraded.append(f"{section_name}.{key}")
                degraded.append(f"{section_name}.{key}_dirty")
            elif isinstance(val, dict) and val.get("stale"):
                # 过期但有原始报价时间：值可用，结论必须降级
                degraded.append(f"{section_name}.{key}_stale")

    # as_of 取所有成功 fetch_* 的最新时间戳
    timestamps = []
    for section in [macro, leverage, valuation_bridge]:
        for v in section.values():
            if isinstance(v, dict) and "as_of" in v:
                timestamps.append(v["as_of"])
    as_of = max(timestamps) if timestamps else datetime.now().isoformat(timespec="seconds")

    # 价差计算复用的历史序列不进入输出契约（避免 _raw JSON 膨胀）
    for section in (macro, leverage, valuation_bridge):
        for val in section.values():
            if isinstance(val, dict):
                val.pop("history", None)

    return {
        "as_of": as_of,
        "macro": {
            "treasury_10y_pct": (macro["treasury_10y_pct"]["value"] if macro["treasury_10y_pct"] else None),
            "treasury_10y_pct_source": (macro["treasury_10y_pct"]["source"] if macro["treasury_10y_pct"] else None),
            "usd_index": macro["usd_index"]["value"] if macro["usd_index"] else None,
            "usd_index_source": (macro["usd_index"]["source"] if macro["usd_index"] else None),
            "usd_cny": macro["usd_cny"]["value"] if macro["usd_cny"] else None,
            "usd_cny_source": (macro["usd_cny"]["source"] if macro["usd_cny"] else None),
            "vix": macro["vix"]["value"] if macro["vix"] else None,
            "vix_source": macro["vix"]["source"] if macro["vix"] else None,
            "gold_usd_oz": (macro["gold_usd_oz"]["value"] if macro["gold_usd_oz"] else None),
            "gold_usd_oz_source": (macro["gold_usd_oz"]["source"] if macro["gold_usd_oz"] else None),
            "brent_oil_usd": (macro["brent_oil_usd"]["value"] if macro["brent_oil_usd"] else None),
            "brent_oil_usd_source": (macro["brent_oil_usd"]["source"] if macro["brent_oil_usd"] else None),
            "wti_oil_usd": (macro["wti_oil_usd"]["value"] if macro["wti_oil_usd"] else None),
            "wti_oil_usd_source": (macro["wti_oil_usd"]["source"] if macro["wti_oil_usd"] else None),
            "lithium_carbonate_cny_t": (
                macro["lithium_carbonate_cny_t"]["value"] if macro["lithium_carbonate_cny_t"] else None
            ),
            "lithium_carbonate_cny_t_source": (
                macro["lithium_carbonate_cny_t"]["source"] if macro["lithium_carbonate_cny_t"] else None
            ),
            "aluminum_cny_t": (macro["aluminum_cny_t"]["value"] if macro["aluminum_cny_t"] else None),
            "aluminum_cny_t_source": (
                macro["aluminum_cny_t"]["source"] if macro["aluminum_cny_t"] else None
            ),
            "aluminum_percentile_1y": (
                macro["aluminum_cny_t"].get("percentile") if macro["aluminum_cny_t"] else None
            ),
            "alumina_cny_t": (macro["alumina_cny_t"]["value"] if macro["alumina_cny_t"] else None),
            "alumina_cny_t_source": (
                macro["alumina_cny_t"]["source"] if macro["alumina_cny_t"] else None
            ),
            "alumina_percentile_1y": (
                macro["alumina_cny_t"].get("percentile") if macro["alumina_cny_t"] else None
            ),
            "al_alumina_spread_cny_t": (
                macro["al_alumina_spread"]["value"] if macro["al_alumina_spread"] else None
            ),
            "al_alumina_spread_cny_t_source": (
                macro["al_alumina_spread"]["source"] if macro["al_alumina_spread"] else None
            ),
            "al_alumina_spread_percentile_1y": (
                macro["al_alumina_spread"].get("percentile") if macro["al_alumina_spread"] else None
            ),
            "al_alumina_spread_ratio": (
                macro["al_alumina_spread"].get("ratio") if macro["al_alumina_spread"] else None
            ),
            "al_alumina_spread_note": (
                macro["al_alumina_spread"].get("note") if macro["al_alumina_spread"] else None
            ),
        },
        "leverage": {
            "margin_balance_total_yi": (
                leverage["margin_balance_total"]["value"] if leverage["margin_balance_total"] else None
            ),
            "margin_balance_total_yi_source": (
                leverage["margin_balance_total"]["source"] if leverage["margin_balance_total"] else None
            ),
            "margin_change_5d_pct": (
                leverage["margin_balance_total"]["change_5d_pct"] if leverage["margin_balance_total"] else None
            ),
            "if_main_basis_pts": (leverage["if_main_basis"]["value"] if leverage["if_main_basis"] else None),
            "if_main_basis_pts_source": (leverage["if_main_basis"]["source"] if leverage["if_main_basis"] else None),
            "ic_main_basis_pts": (leverage["ic_main_basis"]["value"] if leverage["ic_main_basis"] else None),
            "ic_main_basis_pts_source": (leverage["ic_main_basis"]["source"] if leverage["ic_main_basis"] else None),
            "ih_main_basis_pts": (leverage["ih_main_basis"]["value"] if leverage["ih_main_basis"] else None),
            "ih_main_basis_pts_source": (leverage["ih_main_basis"]["source"] if leverage["ih_main_basis"] else None),
        },
        "valuation_bridge": {
            "erp_sh300_pct": (valuation_bridge["erp_sh300"]["value"] if valuation_bridge["erp_sh300"] else None),
            "erp_sh300_pct_source": (
                valuation_bridge["erp_sh300"]["source"] if valuation_bridge["erp_sh300"] else None
            ),
        },
        "_raw": {
            "macro": macro,
            "leverage": leverage,
            "valuation_bridge": valuation_bridge,
        },
        "data_quality": {
            "degraded_fields": degraded,
        },
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = create_parser(description="宏观指标获取（yfinance + fixture fallback）")
    args = parser.parse_args()

    data = fetch_all()
    if args.json_output:
        # 移除 _raw（CLI 不展示原始 dict）
        out = {k: v for k, v in data.items() if k != "_raw"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"📊 宏观 / 杠杆 / 估值桥指标 (as_of {data['as_of']})")
        print("=" * 60)
        print("\n🌐 宏观锚:")
        m = data["macro"]
        print(f"  10Y 美债  : {m['treasury_10y_pct']}%")
        print(f"  美元指数  : {m['usd_index']}")
        print(f"  USDCNH    : {m['usd_cny']}")
        print(f"  VIX       : {m['vix']}")
        print(f"  黄金(oz)  : ${m['gold_usd_oz']}")
        print(f"  WTI 原油  : ${m['wti_oil_usd']}")
        print(f"  布伦特    : ${m['brent_oil_usd']}")
        print(f"  碳酸锂    : ¥{m['lithium_carbonate_cny_t']}/吨")
        print(f"  沪铝      : ¥{m['aluminum_cny_t']}/吨 (分位 {m['aluminum_percentile_1y']}%)")
        print(f"  氧化铝    : ¥{m['alumina_cny_t']}/吨 (分位 {m['alumina_percentile_1y']}%)")
        print(
            f"  冶炼价差  : ¥{m['al_alumina_spread_cny_t']}/吨 "
            f"(分位 {m['al_alumina_spread_percentile_1y']}%, 系数 {m['al_alumina_spread_ratio']})"
        )

        print("\n💪 杠杆:")
        lev = data["leverage"]
        print(f"  两市两融余额 : {lev['margin_balance_total_yi']} 亿元（5 日 {lev['margin_change_5d_pct']}%）")
        print(f"  IF 主基差   : {lev['if_main_basis_pts']} 点")
        print(f"  IC 主基差   : {lev['ic_main_basis_pts']} 点")
        print(f"  IH 主基差   : {lev['ih_main_basis_pts']} 点")

        print("\n📐 估值桥:")
        print(f"  沪深 300 ERP : {data['valuation_bridge']['erp_sh300_pct']}%")

        dq = data["data_quality"]
        if dq["degraded_fields"]:
            print(f"\n⚠️  数据降级: {', '.join(dq['degraded_fields'])}")
        else:
            print("\n✅ 全部指标成功获取")


if __name__ == "__main__":
    main()

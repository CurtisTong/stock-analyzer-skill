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

    Args:
        symbol: yfinance ticker（如 ^TNX, GC=F, DX-Y.NYB）
        value_attr: fast_info 属性名（默认 last_price）

    Returns:
        float | None
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        val = getattr(info, value_attr, None)
        if val is not None and val > 0:
            return float(val)
        return None
    except Exception as e:
        logger.debug("yfinance %s 拉取失败: %s", symbol, e)
        return None


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


def _akshare_get_history(
    symbol: str, lookback: int = _PERCENTILE_LOOKBACK
) -> list[float] | None:
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
    if val is not None:
        snapshot["treasury_10y_pct"] = round(val, 2)
        _save_snapshot(snapshot, key_ts="treasury_10y_pct_ts")
        return {
            "value": round(val, 2),
            "as_of": datetime.now().isoformat(),
            "source": "yfinance",
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
    if val is not None:
        snapshot["usd_index"] = round(val, 2)
        _save_snapshot(snapshot, key_ts="usd_index_ts")
        return {
            "value": round(val, 2),
            "as_of": datetime.now().isoformat(),
            "source": "yfinance",
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
    if val is not None:
        snapshot["usd_cny"] = round(val, 4)
        _save_snapshot(snapshot, key_ts="usd_cny_ts")
        return {
            "value": round(val, 4),
            "as_of": datetime.now().isoformat(),
            "source": "yfinance",
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


def fetch_vix() -> dict | None:
    """恐慌指数。yfinance ^VIX。"""
    snapshot = _load_snapshot()
    if _key_is_fresh(snapshot, "vix") and "vix" in snapshot:
        return {
            "value": snapshot["vix"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "^VIX",
        }

    val = _yfinance_get("^VIX")
    if val is not None:
        snapshot["vix"] = round(val, 2)
        _save_snapshot(snapshot, key_ts="vix_ts")
        return {
            "value": round(val, 2),
            "as_of": datetime.now().isoformat(),
            "source": "yfinance",
            "symbol": "^VIX",
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
    if val is not None:
        snapshot[fixture_key] = round(val, 2)
        _save_snapshot(snapshot, key_ts=f"{fixture_key}_ts")
        return {
            "value": round(val, 2),
            "as_of": datetime.now().isoformat(),
            "source": "yfinance",
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


def fetch_commodity_akshare(
    material_key: str, fixture_key: str, symbol: str
) -> dict | None:
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
    if (
        _key_is_fresh(snapshot, "coal_thermal_cny_t")
        and "coal_thermal_cny_t" in snapshot
    ):
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
    # 宏观
    macro = {
        "treasury_10y_pct": fetch_treasury_10y(),
        "usd_index": fetch_usd_index(),
        "usd_cny": fetch_usd_cny(),
        "vix": fetch_vix(),
        "gold_usd_oz": fetch_gold(),
        "brent_oil_usd": fetch_brent_oil(),
        "wti_oil_usd": fetch_wti_oil(),
        "lithium_carbonate_cny_t": fetch_lithium(),
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

    # as_of 取所有成功 fetch_* 的最新时间戳
    timestamps = []
    for section in [macro, leverage, valuation_bridge]:
        for v in section.values():
            if isinstance(v, dict) and "as_of" in v:
                timestamps.append(v["as_of"])
    as_of = (
        max(timestamps) if timestamps else datetime.now().isoformat(timespec="seconds")
    )

    return {
        "as_of": as_of,
        "macro": {
            "treasury_10y_pct": (
                macro["treasury_10y_pct"]["value"]
                if macro["treasury_10y_pct"]
                else None
            ),
            "usd_index": macro["usd_index"]["value"] if macro["usd_index"] else None,
            "usd_cny": macro["usd_cny"]["value"] if macro["usd_cny"] else None,
            "vix": macro["vix"]["value"] if macro["vix"] else None,
            "gold_usd_oz": (
                macro["gold_usd_oz"]["value"] if macro["gold_usd_oz"] else None
            ),
            "brent_oil_usd": (
                macro["brent_oil_usd"]["value"] if macro["brent_oil_usd"] else None
            ),
            "wti_oil_usd": (
                macro["wti_oil_usd"]["value"] if macro["wti_oil_usd"] else None
            ),
            "lithium_carbonate_cny_t": (
                macro["lithium_carbonate_cny_t"]["value"]
                if macro["lithium_carbonate_cny_t"]
                else None
            ),
        },
        "leverage": {
            "margin_balance_total_yi": (
                leverage["margin_balance_total"]["value"]
                if leverage["margin_balance_total"]
                else None
            ),
            "margin_change_5d_pct": (
                leverage["margin_balance_total"]["change_5d_pct"]
                if leverage["margin_balance_total"]
                else None
            ),
            "if_main_basis_pts": (
                leverage["if_main_basis"]["value"]
                if leverage["if_main_basis"]
                else None
            ),
            "ic_main_basis_pts": (
                leverage["ic_main_basis"]["value"]
                if leverage["ic_main_basis"]
                else None
            ),
            "ih_main_basis_pts": (
                leverage["ih_main_basis"]["value"]
                if leverage["ih_main_basis"]
                else None
            ),
        },
        "valuation_bridge": {
            "erp_sh300_pct": (
                valuation_bridge["erp_sh300"]["value"]
                if valuation_bridge["erp_sh300"]
                else None
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

    parser = argparse.ArgumentParser(
        description="宏观指标获取（yfinance + fixture fallback）"
    )
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    data = fetch_all()
    if args.json:
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

        print("\n💪 杠杆:")
        lev = data["leverage"]
        print(
            f"  两市两融余额 : {lev['margin_balance_total_yi']} 亿元（5 日 {lev['margin_change_5d_pct']}%）"
        )
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

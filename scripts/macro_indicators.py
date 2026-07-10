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


def _save_snapshot(snapshot: dict) -> None:
    """回写 fixture（带 updated 时间戳）。失败仅警告，不抛。"""
    try:
        snapshot["updated"] = datetime.now().isoformat(timespec="seconds")
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("回写 macro_snapshot.json 失败: %s", e)


def _snapshot_is_fresh(snapshot: dict) -> bool:
    """检查 fixture 是否在 TTL 内（避免 yfinance 反复慢调用）。"""
    if not snapshot or "updated" not in snapshot:
        return False
    try:
        ts = datetime.fromisoformat(snapshot["updated"])
        age = (datetime.now() - ts).total_seconds()
        return age < SNAPSHOT_TTL_SECONDS
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
# 宏观-估值桥（5 个 fetch_*）
# ═══════════════════════════════════════════════════════════════


def fetch_treasury_10y() -> dict | None:
    """10 年期美债收益率（%）。yfinance ^TNX → 直接 = 百分比值。

    注意：^TNX 返回值已经是百分比（如 2.45 = 2.45%），无需 × 100。
    """
    snapshot = _load_snapshot()
    if _snapshot_is_fresh(snapshot) and "treasury_10y_pct" in snapshot:
        return {
            "value": snapshot["treasury_10y_pct"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "^TNX",
        }

    val = _yfinance_get("^TNX")
    if val is not None:
        snapshot["treasury_10y_pct"] = round(val, 2)
        _save_snapshot(snapshot)
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
    if _snapshot_is_fresh(snapshot) and "usd_index" in snapshot:
        return {
            "value": snapshot["usd_index"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "DX-Y.NYB",
        }

    val = _yfinance_get("DX-Y.NYB")
    if val is not None:
        snapshot["usd_index"] = round(val, 2)
        _save_snapshot(snapshot)
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
    if _snapshot_is_fresh(snapshot) and "usd_cny" in snapshot:
        return {
            "value": snapshot["usd_cny"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "CNY=X",
        }

    val = _yfinance_get("CNY=X")
    if val is not None:
        snapshot["usd_cny"] = round(val, 4)
        _save_snapshot(snapshot)
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
    if _snapshot_is_fresh(snapshot) and "vix" in snapshot:
        return {
            "value": snapshot["vix"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "^VIX",
        }

    val = _yfinance_get("^VIX")
    if val is not None:
        snapshot["vix"] = round(val, 2)
        _save_snapshot(snapshot)
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
    if _snapshot_is_fresh(snapshot) and fixture_key in snapshot:
        return {
            "value": snapshot[fixture_key],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": symbol,
        }

    val = _yfinance_get(symbol)
    if val is not None:
        snapshot[fixture_key] = round(val, 2)
        _save_snapshot(snapshot)
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


def fetch_lithium() -> dict | None:
    """电池级碳酸锂价格（CNY/吨）。yfinance 不覆盖 → 仅 fixture。"""
    snapshot = _load_snapshot()
    if "lithium_carbonate_cny_t" in snapshot:
        return {
            "value": snapshot["lithium_carbonate_cny_t"],
            "as_of": snapshot["updated"],
            "source": "fixture",
            "symbol": "lithium_carbonate",
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

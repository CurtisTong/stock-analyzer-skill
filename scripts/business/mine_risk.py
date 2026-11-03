"""(#research) 排雷数据源：商誉/净资产、大股东质押比例。

2026-11-02 skill 审查 P0：research financial 模式的排雷清单要求
商誉/净资产、质押比例等 6 个信号，但其中数据层命中 0 次（缓存
5131 条记录无 GOODWILL/PLEDGE_RATIO 字段）——"排雷"实际无数据支撑。

本模块经 akshare 提供三个真实数据源（均 2026-11-03 实测可用）：
- 商誉：ak.stock_sy_jz_em(date=年报期) → 商誉、商誉占净资产比例（全市场年报，~2600 行）
- 质押：ak.stock_gpzy_pledge_ratio_em() → 质押比例%（全市场最新交易日，~2300 行）
- 应收：ak.stock_zcfz_em(date=报告期) → 应收账款（全市场资产负债表，~5200 行；
  本期 vs 去年同期算同比增速，供 research "应收增速 vs 2×营收增速"信号）

阈值口径（与 scripts/config/limits.yaml 对齐说明）：
- research 文档口径：商誉/净资产 > 30% 排雷（本模块直接输出该比例）
- screener 流水线口径：limits.yaml goodwill_ratio 30/50（商誉/总资产）、
  pledge_ratio 70/85——两套分母/阈值不同，勿混用
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# 资产负债表报告期候选（最近优先，用于应收账款本期+去年同期）
_ZCFZQuarterSuffixes = ("1231", "0930", "0630", "0331")

# 商誉接口按年报期查询；从最近年份倒推尝试（2026-11-03 实测：2025 期返回空，
# 20241231 可用），最多回退 3 年
_GOODWILL_DATES_TO_TRY = 3


def _normalize_code(code: str) -> str:
    """6 位纯数字代码（akshare 接口的 股票代码 列为 6 位数字）。"""
    c = str(code).strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if c.startswith(prefix):
            c = c[2:]
    return c


def _ak():
    import akshare  # 延迟导入，无 akshare 时给出可读降级

    return akshare


def fetch_goodwill(code: str) -> dict | None:
    """商誉数据（商誉占净资产比例，小数：0.10 = 10%）。

    Returns:
        {goodwill, goodwill_to_net_assets, report_date, source} 或 None
        （无商誉记录 / 接口失败 / 超出回退年限）
    """
    c = _normalize_code(code)
    try:
        ak = _ak()
        year = datetime.now().year
        for back in range(_GOODWILL_DATES_TO_TRY):
            date_str = f"{year - 1 - back}1231"
            try:
                df = ak.stock_sy_jz_em(date=date_str)
            except Exception as e:  # 单期失败继续回退
                logger.debug("商誉接口 %s 失败: %s", date_str, e)
                continue
            if df is None or df.empty:
                continue
            row = df[df["股票代码"].astype(str).str.zfill(6) == c]
            if row.empty:
                continue
            r = row.iloc[0]
            ratio = r.get("商誉占净资产比例")
            return {
                "goodwill": float(r.get("商誉") or 0),
                "goodwill_to_net_assets": float(ratio) if ratio == ratio and ratio is not None else None,
                "report_date": date_str[:4] + "-12-31",
                "source": "akshare stock_sy_jz_em",
            }
        return None
    except ImportError:
        logger.warning("akshare 未安装，商誉数据不可用")
        return None
    except Exception as e:
        logger.warning("商誉数据获取失败: %s", e)
        return None


def fetch_pledge_ratio(code: str) -> dict | None:
    """大股东质押比例（百分比数值：75.09 = 75.09%，全市场最新交易日快照）。

    Returns:
        {pledge_ratio_pct, trade_date, source} 或 None
    """
    c = _normalize_code(code)
    try:
        ak = _ak()
        df = ak.stock_gpzy_pledge_ratio_em()
        if df is None or df.empty:
            return None
        row = df[df["股票代码"].astype(str).str.zfill(6) == c]
        if row.empty:
            # 无质押记录不等于 None 数据缺失——多数公司质押比例为 0，
            # 接口只列出质押中的公司；无记录按 0 处理（排雷语义正确）
            return {
                "pledge_ratio_pct": 0.0,
                "trade_date": None,
                "source": "akshare stock_gpzy_pledge_ratio_em(无记录=0)",
            }
        r = row.iloc[0]
        return {
            "pledge_ratio_pct": float(r.get("质押比例") or 0),
            "trade_date": str(r.get("交易日期") or ""),
            "source": "akshare stock_gpzy_pledge_ratio_em",
        }
    except ImportError:
        logger.warning("akshare 未安装，质押数据不可用")
        return None
    except Exception as e:
        logger.warning("质押数据获取失败: %s", e)
        return None


def _num(v):
    """NaN/None 安全取数（NaN != NaN），不可用返回 None。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def fetch_receivables(code: str, max_lookback: int = 8) -> dict | None:
    """应收账款同比增速（本期 vs 去年同期，东财资产负债表 stock_zcfz_em）。

    Returns:
        {
            "receivables": 本期应收账款(元),
            "receivables_yoy_pct": 同比增速%（去年同期缺失/<=0 时 None）,
            "report_date": "YYYYMMDD",
            "source": ...,
        } 或 None（全期次失败 / 无该股记录）
    """
    c = _normalize_code(code)
    try:
        ak = _ak()
        today = datetime.now()
        candidates = [f"{y}{md}" for y in (today.year, today.year - 1) for md in _ZCFZQuarterSuffixes][:max_lookback]
        latest = None
        for d in candidates:
            try:
                df = ak.stock_zcfz_em(date=d)
            except Exception as e:
                logger.debug("资产负债表 %s 获取失败: %s", d, e)
                continue
            if df is None or df.empty:
                continue
            row = df[df["股票代码"].astype(str).str.zfill(6) == c]
            if row.empty:
                continue
            ar = _num(row.iloc[0].get("资产-应收账款"))
            if ar is None:
                continue
            latest = (d, ar)
            break
        if latest is None:
            return None
        d_cur, ar_cur = latest
        prior_date = f"{int(d_cur[:4]) - 1}{d_cur[4:]}"
        ar_prior = None
        try:
            df_p = ak.stock_zcfz_em(date=prior_date)
            if df_p is not None and not df_p.empty:
                row = df_p[df_p["股票代码"].astype(str).str.zfill(6) == c]
                if not row.empty:
                    ar_prior = _num(row.iloc[0].get("资产-应收账款"))
        except Exception as e:
            logger.debug("资产负债表 %s 获取失败: %s", prior_date, e)
        yoy = None
        if ar_prior is not None and ar_prior > 0:
            yoy = (ar_cur - ar_prior) / ar_prior * 100
        return {
            "receivables": ar_cur,
            "receivables_yoy_pct": yoy,
            "report_date": d_cur,
            "source": "akshare stock_zcfz_em",
        }
    except ImportError:
        logger.warning("akshare 未安装，应收账款数据不可用")
        return None
    except Exception as e:
        logger.warning("应收账款数据获取失败: %s", e)
        return None


RESEARCH_GOODWILL_THRESHOLD_PCT = 30.0  # research 文档口径：商誉/净资产 > 30% 排雷
RESEARCH_PLEDGE_THRESHOLD_PCT = 60.0  # research 文档口径：质押 > 60% 高风险


def get_mine_risk(code: str, revenue_yoy: float | None = None) -> dict:
    """排雷数据汇总（research financial 模式 Step 1 数据源）。

    Args:
        code: 股票代码
        revenue_yoy: 营收同比增速%（来自 finance.py 的 revenue_yoy）。
            提供时应用"应收增速 > 2×营收增速"排雷规则；缺省仅输出应收增速
            由调用方自行对照。

    Returns:
        {
            "code": ...,
            "goodwill": {...} | None,
            "pledge": {...} | None,
            "receivables": {...} | None,
            "flags": ["商誉/净资产 42.3% > 30% 排雷线", ...],
            "degraded": [字段...],
        }
    """
    out: dict = {
        "code": code,
        "goodwill": None,
        "pledge": None,
        "receivables": None,
        "flags": [],
        "degraded": [],
    }

    gw = fetch_goodwill(code)
    out["goodwill"] = gw
    if gw is None:
        out["degraded"].append("goodwill")
    else:
        ratio = gw.get("goodwill_to_net_assets")
        if ratio is not None and ratio * 100 > RESEARCH_GOODWILL_THRESHOLD_PCT:
            out["flags"].append(f"商誉/净资产 {ratio*100:.1f}% > {RESEARCH_GOODWILL_THRESHOLD_PCT:.0f}% 排雷线")

    pl = fetch_pledge_ratio(code)
    out["pledge"] = pl
    if pl is None:
        out["degraded"].append("pledge")
    else:
        pr = pl.get("pledge_ratio_pct")
        if pr is not None and pr > RESEARCH_PLEDGE_THRESHOLD_PCT:
            out["flags"].append(f"质押比例 {pr:.1f}% > {RESEARCH_PLEDGE_THRESHOLD_PCT:.0f}% 高风险线")

    rc = fetch_receivables(code)
    out["receivables"] = rc
    if rc is None:
        out["degraded"].append("receivables")
    else:
        ar_yoy = rc.get("receivables_yoy_pct")
        if ar_yoy is not None and revenue_yoy is not None and revenue_yoy > 0 and ar_yoy > 2 * revenue_yoy:
            out["flags"].append(f"应收增速 {ar_yoy:.1f}% > 2×营收增速（{revenue_yoy:.1f}%），收入质量需核查")

    return out


def main():
    parser = argparse.ArgumentParser(description="排雷数据：商誉/净资产 + 大股东质押（research 排雷数据源）")
    parser.add_argument("code", help="股票代码（sh600989 / 600989）")
    parser.add_argument(
        "--revenue-yoy",
        type=float,
        default=None,
        help="营收同比增速%%（来自 finance.py）；提供时应用应收增速 2× 排雷规则",
    )
    parser.add_argument("-j", "--json", dest="json_output", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    result = get_mine_risk(args.code, revenue_yoy=args.revenue_yoy)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"🔍 排雷数据 {result['code']}")
    gw = result["goodwill"]
    if gw:
        ratio = gw.get("goodwill_to_net_assets")
        ratio_str = f"{ratio*100:.1f}%" if ratio is not None else "N/A"
        print(f"  商誉: {gw['goodwill']/1e8:.2f} 亿 | 商誉/净资产: {ratio_str} | 报告期: {gw['report_date']}")
    else:
        print("  商誉: 数据不可用（降级）")
    pl = result["pledge"]
    if pl:
        print(f"  质押比例: {pl['pledge_ratio_pct']:.1f}% | 交易日: {pl.get('trade_date') or '-'}")
    else:
        print("  质押: 数据不可用（降级）")
    for f in result["flags"]:
        print(f"  🚩 {f}")
    if result["degraded"]:
        print(f"  ⚠️ 降级字段: {', '.join(result['degraded'])}")
    print("  数据源: akshare（东财）| 不构成投资建议")


if __name__ == "__main__":
    main()

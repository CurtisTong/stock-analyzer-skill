#!/usr/bin/env python3
"""
市场环境锚定编排器（v2.5.0 新增）。

聚合大盘状态 + 市场宽度 + 板块 ETF 强度 + 个股 vs 板块 RPS，为 /stock 的
full / debate / technical 三个模式统一提供前置"市场环境锚定"数据。

设计原则：
1. 复用优先：detect_market_state / market_breadth / sector_etf_strength 都已存在，
   不重写，import 调用。
2. 优雅降级：每个数据源独立 try/except，任一失败只影响对应字段，不阻塞主流程。
3. 双输出：JSON（供 LLM/编排器消费）+ Markdown（供终端阅读）。

用法:
  market_anchor.py sh600519                  # 单股全量（Markdown）
  market_anchor.py sh600519 -j               # JSON
  market_anchor.py sh600519 --no-sector      # 跳过板块（technical 模式用）
  market_anchor.py sh600519 -j --no-sector   # 仅大盘 + 宽度（轻量）
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

# 确保 scripts/ 在 import 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import get_quotes, get_kline  # noqa: E402 多源数据层

# 复用：直接 import，不重写
from experts.market_detector import detect_market_state  # noqa: E402
import market_breadth  # noqa: E402  get_market_breadth()
import sector_etf_strength  # noqa: E402  analyze()


# ═══════════════════════════════════════════════════════════════
# 数据采集：大盘 + 宽度 + 板块
# ═══════════════════════════════════════════════════════════════

def _fetch_index_snapshot(index_code: str = "sh000300") -> dict | None:
    """获取大盘指数实时行情（用于 detect_market_state 的 index_quote 入参）。

    Returns:
        dict 含 price / change_pct / pe_percentile，失败返回 None。
    """
    try:
        quotes = get_quotes([index_code], use_cache=True)
        if not quotes:
            return None
        q = quotes[0]
        if not q or not q.has_basic_data():
            return None
        return {
            "code": q.code,
            "name": q.name,
            "price": q.price,
            "prev_close": getattr(q, "prev_close", None),
            "change_pct": q.change_pct,
            "pe": getattr(q, "pe", None),
            "pe_percentile": 50,  # 缺省中位数
        }
    except Exception as e:
        print(f"[market_anchor] 大盘拉取失败: {e}", file=sys.stderr)
        return None


def _fetch_index_kline(index_code: str = "sh000300", datalen: int = 30) -> dict | None:
    """获取大盘指数日 K 线，用于 detect_market_state 的 kline_data 入参。

    Returns:
        dict 含 closes / ma20 / volumes，失败返回 None。
    """
    try:
        klines = get_kline(index_code, scale=240, datalen=datalen)
        if not klines:
            return None
        closes = [k.close for k in klines]
        volumes = [k.volume for k in klines]
        ma20 = sum(closes[-20:]) / min(len(closes), 20) if closes else 0
        return {
            "closes": closes,
            "volumes": volumes,
            "ma20": round(ma20, 2),
        }
    except Exception as e:
        print(f"[market_anchor] 大盘 K 线拉取失败: {e}", file=sys.stderr)
        return None


def _fetch_breadth() -> dict | None:
    """获取市场宽度（涨跌家数 + 涨跌停家数）。复用 market_breadth.get_market_breadth()。

    Returns:
        dict 含 up_count / down_count / limit_up_count / limit_down_count
            / advance_ratio / new_high_low_ratio 等，失败返回 None。
    """
    try:
        breadth = market_breadth.get_market_breadth()
        # 转换为 detect_market_state 期望的格式
        up = breadth.get("up_count", 0)
        down = breadth.get("down_count", 0)
        total = up + down
        advance_ratio = up / total if total > 0 else 0.5
        return {
            "up_count": up,
            "down_count": down,
            "limit_up_count": breadth.get("limit_up_count", 0),
            "limit_down_count": breadth.get("limit_down_count", 0),
            "up_ratio": breadth.get("up_ratio", 0),
            "advance_ratio": round(advance_ratio, 3),
            "new_high_low_ratio": 1.0,  # 缺省 1.0（detect_market_state 会按中位处理）
            "margin_ratio": 0,           # 缺省 0
        }
    except Exception as e:
        print(f"[market_anchor] 市场宽度拉取失败: {e}", file=sys.stderr)
        return None


# ═══════════════════════════════════════════════════════════════
# 顶层编排
# ═══════════════════════════════════════════════════════════════

def analyze(
    stock_code: str | None = None,
    fetch_sector: bool = True,
    index_code: str = "sh000300",
) -> dict:
    """一次性返回"市场环境锚定"完整数据。

    Args:
        stock_code: 可选。提供时输出 stock_sector_compare。
        fetch_sector: 是否拉板块 ETF（technical 模式可关）。
        index_code: 大盘指数代码，默认 sh000300 沪深300。

    Returns:
        dict，含 as_of / regime / index_change_pct / breadth / sector_strength
            / stock_sector_compare / data_quality。
        任一字段缺失都标记为 null 并加入 degraded_fields。
    """
    as_of = datetime.now().isoformat(timespec="seconds")
    degraded = []

    # 1. 大盘指数行情 + K 线
    index_quote = _fetch_index_snapshot(index_code)
    if not index_quote:
        degraded.append("index")
    index_kline = _fetch_index_kline(index_code)
    if not index_kline:
        degraded.append("index_kline")

    # 2. 市场宽度
    breadth = _fetch_breadth()
    if not breadth:
        degraded.append("breadth")

    # 3. 调用 detect_market_state 判定 regime（复用现有逻辑，不重写）
    # 缺数据时 detect_market_state 内部默认返回"防御型"（v2.4.3 fail-safe）
    regime_result = {}
    try:
        regime_result = detect_market_state(
            index_quote=index_quote,
            kline_data=index_kline,
            breadth_data=breadth,
        )
        # 缺数据时强制 confidence=low（不冒泡）
        confidence = "high" if not degraded else "low"
    except Exception as e:
        print(f"[market_anchor] detect_market_state 失败: {e}", file=sys.stderr)
        regime_result = {
            "state": "防御型",
            "long_weight": 0.65,
            "short_weight": 0.35,
            "reason": "数据缺失默认防御型（fail-safe）",
        }
        confidence = "low"
        if "regime" not in degraded:
            degraded.append("regime")

    regime_state = regime_result.get("state", "防御型")
    # 枚举映射到英文 enum（与 schema 一致）
    regime_enum = {
        "牛市": "bull",
        "熊市": "bear",
        "震荡": "sideways",
        "冰点": "panic",
        "亢奋": "euphoria",
        "防御型": "defensive",
    }.get(regime_state, "unknown")

    # 4. 板块 ETF 强度（可选）
    sector_payload = None
    if fetch_sector:
        try:
            sector_payload = sector_etf_strength.analyze(
                stock_code=stock_code,
                fetch_index=False,  # 已在大盘里拉过，避免重复
            )
        except Exception as e:
            print(f"[market_anchor] 板块拉取失败: {e}", file=sys.stderr)
            degraded.append("sector")

    # 5. 组装输出
    return {
        "as_of": as_of,
        "regime": regime_enum,
        "regime_label_zh": regime_state,
        "regime_confidence": confidence,
        "regime_reason": regime_result.get("reason", ""),
        "long_weight": regime_result.get("long_weight"),
        "short_weight": regime_result.get("short_weight"),
        "index_code": index_code,
        "index_change_pct": (
            round(index_quote["change_pct"], 2) if index_quote else None
        ),
        "breadth": breadth,
        "sector_strength": {
            "etfs": sector_payload["etfs"] if sector_payload else [],
            "top": sector_payload["strong_sectors"] if sector_payload else [],
            "bottom": sector_payload["weak_sectors"] if sector_payload else [],
            "data_quality": sector_payload["data_quality"] if sector_payload else None,
        } if fetch_sector else None,
        "stock_sector_compare": (
            sector_payload["stock_sector_compare"] if sector_payload else None
        ),
        "data_quality": {
            "index_ok": index_quote is not None,
            "index_kline_ok": index_kline is not None,
            "breadth_ok": breadth is not None,
            "sector_ok": sector_payload is not None,
            "degraded_fields": degraded,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Markdown 格式化
# ═══════════════════════════════════════════════════════════════

def _md_regime_emoji(regime: str) -> str:
    return {
        "bull": "🟢",
        "bear": "🔴",
        "sideways": "🟡",
        "panic": "⚠️",
        "euphoria": "🔥",
        "defensive": "🛡️",
        "unknown": "❓",
    }.get(regime, "❓")


def to_markdown(payload: dict) -> str:
    """生成"市场环境锚定"小节的 Markdown 输出。"""
    lines = []
    regime_zh = payload["regime_label_zh"]
    regime_en = payload["regime"]
    emoji = _md_regime_emoji(regime_en)
    conf = payload["regime_confidence"]
    idx_chg = payload["index_change_pct"]

    lines.append(f"## 📊 市场环境锚定")
    lines.append("")
    lines.append(f"{emoji} **市场状态**: {regime_zh} ({conf}) — {payload['regime_reason']}")
    if idx_chg is not None:
        lines.append(f"📈 **大盘指数**: {payload['index_code']} 当日 {idx_chg:+.2f}%")
    else:
        lines.append(f"📈 **大盘指数**: ⚠️ 数据缺失")

    b = payload.get("breadth") or {}
    if b:
        lines.append(
            f"🌐 **市场宽度**: 上涨 {b.get('up_count', 0)} 家 / 下跌 {b.get('down_count', 0)} 家"
        )
        lines.append(
            f"        涨停 {b.get('limit_up_count', 0)} 家 / 跌停 {b.get('limit_down_count', 0)} 家"
        )
    else:
        lines.append(f"🌐 **市场宽度**: ⚠️ 数据缺失")

    ss = payload.get("sector_strength")
    if ss and ss.get("etfs"):
        top_names = []
        for code in ss["top"][:3]:
            etf = next((e for e in ss["etfs"] if e["code"] == code), None)
            if etf and etf.get("change_pct") is not None:
                top_names.append(f"{etf['name']} {etf['change_pct']:+.2f}%")
        bottom_names = []
        for code in ss["bottom"][:3]:
            etf = next((e for e in ss["etfs"] if e["code"] == code), None)
            if etf and etf.get("change_pct") is not None:
                bottom_names.append(f"{etf['name']} {etf['change_pct']:+.2f}%")
        if top_names:
            lines.append(f"🔥 **强势板块**: {', '.join(top_names)}")
        if bottom_names:
            lines.append(f"💀 **弱势板块**: {', '.join(bottom_names)}")

    comp = payload.get("stock_sector_compare")
    if comp:
        lines.append("")
        lines.append(f"### 🎯 个股 vs 板块 vs 大盘 ({comp['stock_code']})")
        if comp.get("stock_sectors"):
            lines.append(f"- 所属板块: {', '.join(comp['stock_sectors'])}")
        if comp.get("matched_etf_name"):
            lines.append(f"- 匹配 ETF: {comp['matched_etf']} {comp['matched_etf_name']}")
        if comp.get("stock_change_pct") is not None:
            lines.append(f"- 个股涨跌: {comp['stock_change_pct']:+.2f}%")
        if comp.get("sector_change_pct") is not None:
            lines.append(f"- 板块涨跌: {comp['sector_change_pct']:+.2f}%")
        if comp.get("index_change_pct") is not None:
            lines.append(f"- 大盘涨跌: {comp['index_change_pct']:+.2f}%")
        if comp.get("rps_vs_sector") is not None:
            lines.append(f"- RPS vs 板块: {comp['rps_vs_sector']:+.2f}pp")
        if comp.get("rps_vs_index") is not None:
            lines.append(f"- RPS vs 大盘: {comp['rps_vs_index']:+.2f}pp")
        lines.append(f"- **结论**: {comp['verdict']}")
        if comp.get("data_quality", {}).get("degraded_fields"):
            lines.append(
                f"- ⚠️ 降级字段: {', '.join(comp['data_quality']['degraded_fields'])}"
            )

    dq = payload["data_quality"]
    if dq["degraded_fields"]:
        lines.append("")
        lines.append(f"⚠️ **数据降级**: {', '.join(dq['degraded_fields'])}")
    lines.append("")
    lines.append(f"📊 数据时间戳: {payload['as_of']} | 数据源: quote.py / market_breadth.py / sector_etf_strength.py")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="市场环境锚定编排器")
    parser.add_argument("stock_code", nargs="?", help="股票代码（如 sh600519），可选")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--no-sector", action="store_true", help="跳过板块拉取（technical 模式用）")
    parser.add_argument("--index", default="sh000300", help="大盘指数代码（默认 sh000300）")
    args = parser.parse_args()

    payload = analyze(
        stock_code=args.stock_code,
        fetch_sector=not args.no_sector,
        index_code=args.index,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(payload))


if __name__ == "__main__":
    main()

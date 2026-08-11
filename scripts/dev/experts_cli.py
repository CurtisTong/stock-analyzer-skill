#!/usr/bin/env python3
"""8 位 active 专家量化评分 CLI（debate 模式基线参考）。

Usage:
  python3 scripts/dev/experts_cli.py sz002192                  # 单股全 8 人
  python3 scripts/dev/experts_cli.py sz002192 sz002335 sz002497  # 多股对比
  python3 scripts/dev/experts_cli.py sz002192 --long           # 仅长线 5 人
  python3 scripts/dev/experts_cli.py sz002192 --short          # 仅短线 3 人
  python3 scripts/dev/experts_cli.py sz002192 -j                # JSON 输出

输出包含：
- 每位专家的 score / direction / dim_scores / breakdown
- 跨股横向对比表（综合分排名 + 方向分布）
- 与 debate 模式 LLM 推理分的差异提示（当量化与 LLM 分差异 >15 时）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# 让脚本能 import 项目根目录的模块
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from experts import list_active_experts  # noqa: E402
from experts.scoring import score_expert_precise  # noqa: E402

TREND_MAP = {
    "多头排列": 1,
    "上升浪": 1,
    "bull": 1,
    "空头排列": -1,
    "下跌浪": -1,
    "bear": -1,
    "交叉震荡": 0,
    "盘整": 0,
    "sideways": 0,
}


def fetch_json(cmd: list[str], timeout: int = 60) -> dict:
    """子进程调用脚本，解析 JSON。失败返回 {'error': ...}。"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if r.returncode != 0:
        return {"error": r.stderr.strip()[:300]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": f"non-json output: {r.stdout[:200]}"}


def build_stock_data(code: str) -> tuple[dict, dict]:
    """从 quote/finance/kline/market_anchor 构造 score_expert_precise 入参。

    Returns:
        (stock_data, raw_meta)
    """
    code_lower = code.lower()
    code_upper = code.upper()

    raw_meta: dict = {"code": code_upper}

    # 1. 行情
    quote_resp = fetch_json(["python3", "scripts/quote.py", code_lower, "-j"])
    raw_meta["quote"] = quote_resp
    quote = {}
    if isinstance(quote_resp, list) and quote_resp:
        quote = quote_resp[0]
    elif isinstance(quote_resp, dict) and "error" not in quote_resp:
        quote = quote_resp

    # 2. 财务（取最近 1 期作为代表）
    fin_resp = fetch_json(["python3", "scripts/finance.py", "-c", code_lower, "-j"])
    raw_meta["finance_raw"] = fin_resp
    fin = {}
    if isinstance(fin_resp, dict) and code_upper in fin_resp:
        records = fin_resp[code_upper]
        if records:
            fin = records[0]  # 最新一期

    # 3. 技术面：取完整 JSON（含 MA/MACD/KDJ/RSI/缠论等所有数值），
    # 报告模板需要这些数值填占位。--quick 只用于终端人读，不进 stock_data。
    tech = fetch_json(["python3", "scripts/technical.py", code_lower, "-j"])
    raw_meta["tech"] = tech  # 保留完整 JSON，报告引用 raw_meta.tech 填占位
    trend = 0
    rsi = 50
    macd_signal = 0
    if isinstance(tech, dict) and not tech.get("error"):
        features = tech.get("features") or {}
        ma_sys = features.get("ma_system") or {}
        align = ma_sys.get("alignment", "")
        trend = TREND_MAP.get(align, 0)
        if "多头" in align:
            trend = 1
        elif "空头" in align:
            trend = -1
        # RSI：features.rsi.value 或 features.rsi 顶层（取决于脚本版本）
        rsi_data = features.get("rsi", 50)
        if isinstance(rsi_data, dict):
            rsi = rsi_data.get("value", rsi_data.get("rsi", 50))
        else:
            rsi = rsi_data
        # MACD 信号：bar >0 → 1，bar <0 → -1
        macd_data = features.get("macd", {}) or {}
        macd_bar = macd_data.get("macd_bar", 0)
        if macd_bar > 0:
            macd_signal = 1
        elif macd_bar < 0:
            macd_signal = -1

    # 4. 市场特征（从 market_anchor）
    ma = fetch_json(
        ["python3", "scripts/market_anchor.py", code_lower, "--no-sector", "-j"]
    )
    raw_meta["market_anchor"] = ma
    breadth = (
        ma.get("breadth", {}) if isinstance(ma, dict) and not ma.get("error") else {}
    )

    stock_data = {
        "quote": {
            "pe": quote.get("pe"),
            "pb": quote.get("pb"),
            "price": quote.get("price"),
            "circulating_cap": quote.get("circulating_cap"),
            "pe_percentile": 50,  # 暂无历史分位 API，留中性
        },
        "finance": {
            "roe": fin.get("roe"),
            "net_profit_yoy": fin.get("net_profit_yoy"),
            "debt_ratio": fin.get("debt_ratio"),
            "eps": fin.get("eps"),
            "ocf_per_share": fin.get("ocf_per_share"),
        },
        "kline_features": {
            "trend": trend,
            "rsi": rsi,
            "macd_signal": macd_signal,
        },
        "market_features": {
            "limit_up_count": breadth.get("limit_up_count", 0),
            "limit_down_count": breadth.get("limit_down_count", 0),
            "advance_ratio": breadth.get("advance_ratio", 0.5),
            "break_rate": (
                breadth.get("broken_limit_rate", 0) / 100
                if breadth.get("broken_limit_rate")
                else 0
            ),
            "limit_up_30d_count": 0,
            "sector_limit_up_count": 0,
        },
    }
    return stock_data, raw_meta


def run_for_stock(code: str, group_filter: str | None = None) -> dict:
    """单只票跑全部/分组专家，返回每专家评分 + 综合。"""
    stock_data, raw_meta = build_stock_data(code)
    profiles = list_active_experts()
    if group_filter == "long":
        profiles = [p for p in profiles if p.group == "long_term"]
    elif group_filter == "short":
        profiles = [p for p in profiles if p.group == "short_term"]

    expert_results = []
    for p in profiles:
        res = score_expert_precise(p, stock_data)
        expert_results.append(
            {
                "name": p.name,
                "group": p.group,
                "score": res["score"],
                "direction": res["direction"],
                "method": res["method"],
                "dim_scores": res.get("dim_scores", {}),
            }
        )

    composite = (
        sum(r["score"] for r in expert_results) / len(expert_results)
        if expert_results
        else 50
    )
    return {
        "code": code.upper(),
        "stock_data": stock_data,
        "expert_results": expert_results,
        "composite_score": round(composite, 1),
        # 保留完整 raw_meta（含 technical 完整 JSON），
        # 报告作者引用 raw_meta.tech.features.ma_system 等填模板占位。
        "raw_meta": raw_meta,
    }


def render_table(results: list[dict]) -> str:
    """渲染跨股横向对比表。"""
    if not results:
        return "(无数据)"
    lines = []
    headers = [
        "代码",
        "综合分",
        "林奇",
        "索罗斯",
        "价值机构",
        "行业专家",
        "风控官",
        "题材龙头",
        "情绪技术",
        "动量派",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    by_code = {r["code"]: {e["name"]: e for e in r["expert_results"]} for r in results}
    for r in sorted(results, key=lambda x: -x["composite_score"]):
        row = [r["code"], f"{r['composite_score']:.1f}"]
        for name in [
            "lynch",
            "soros",
            "value_institution",
            "sector_specialist",
            "risk_manager",
            "topic_leader",
            "emotion_tech",
            "momentum_trader",
        ]:
            e = by_code[r["code"]].get(name)
            row.append(f"{e['score']:.0f}/{e['direction'][:1]}" if e else "-")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="8 位 active 专家量化评分 CLI")
    parser.add_argument("codes", nargs="+", help="股票代码列表")
    parser.add_argument("--long", action="store_true", help="仅长线 5 人")
    parser.add_argument("--short", action="store_true", help="仅短线 3 人")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    group = "long" if args.long else ("short" if args.short else None)

    out = []
    for code in args.codes:
        try:
            r = run_for_stock(code, group_filter=group)
            out.append(r)
        except Exception as e:  # noqa: BLE001
            out.append({"code": code.upper(), "error": str(e)})

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 终端表格输出
    print(
        f"\n# 量化评分 · {'长线5' if args.long else ('短线3' if args.short else '全部8')}"
    )
    print(render_table(out))
    print("\n# 方向标签说明：多=看多，空=看空，中=中性")
    print(
        "# 注意：此为量化基线，debate 模式应与 LLM 推理分对比，差异 >15 须说明原因。\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

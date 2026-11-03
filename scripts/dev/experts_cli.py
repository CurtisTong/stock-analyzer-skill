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
# experts 层的 vote_engine/calibration 依赖 scripts/ 下的 config/data/common
# （experts 包对 scripts/ 有隐式 sys.path 依赖，见 experts/calibration.py 注释）
sys.path.insert(0, str(ROOT / "scripts"))

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
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
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
    rsi: float = 50
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
            rsi_val = rsi_data.get("value", rsi_data.get("rsi", 50))
            rsi = rsi_val if isinstance(rsi_val, (int, float)) else 50
        else:
            rsi = rsi_data if isinstance(rsi_data, (int, float)) else 50
        # MACD 信号：bar >0 → 1，bar <0 → -1
        macd_data = features.get("macd", {}) or {}
        macd_bar = macd_data.get("macd_bar", 0)
        if not isinstance(macd_bar, (int, float)):
            macd_bar = 0
        if macd_bar > 0:
            macd_signal = 1
        elif macd_bar < 0:
            macd_signal = -1

    # 4. 市场特征（从 market_anchor）
    ma = fetch_json(["python3", "scripts/market_anchor.py", code_lower, "--no-sector", "-j"])
    raw_meta["market_anchor"] = ma
    breadth = (ma.get("breadth") or {}) if isinstance(ma, dict) and not ma.get("error") else {}

    # 数据缺失一律置 None（不填 0/50 兜底）——
    # 评分层会区分"不可得"与"可得但差"：置 0 会让缺失被当成最差信号，
    # 置 50 会把无信息伪装成中性票（见 experts/scoring/availability.py）。
    # 行业分类——周期位置否决（veto_evaluator._check_cycle_position）需要它
    # 推断周期股。行情 API 的 industry 字段常为空（akshare 补全失败时），
    # 用 classifier.infer_industry 的关键词兜底推断。
    industry = quote.get("industry") or ""
    if not industry:
        try:
            from classifier import infer_industry

            industry = infer_industry(quote.get("name") or "", code, "")
        except Exception:
            industry = ""

    stock_data = {
        "code": code_upper,
        "industry": industry,
        "quote": {
            "pe": quote.get("pe"),
            "pb": quote.get("pb"),
            "price": quote.get("price"),
            "circulating_cap": quote.get("circulating_cap"),
            # PE 历史分位暂无 API，取不到就留 None（估值维度走中性处理）
            "pe_percentile": quote.get("pe_percentile"),
            "name": quote.get("name"),
            "amount": quote.get("amount"),
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
            "limit_up_count": breadth.get("limit_up_count"),
            "limit_down_count": breadth.get("limit_down_count"),
            "advance_ratio": breadth.get("advance_ratio"),
            "break_rate": (breadth.get("broken_limit_rate", 0) / 100 if breadth.get("broken_limit_rate") else 0),
            # 近30日涨停次数与板块涨停数当前无数据源，留 None
            "limit_up_30d_count": breadth.get("limit_up_30d_count"),
            "sector_limit_up_count": breadth.get("sector_limit_up_count"),
            # （v1.26.0）标记宽度数据是否降级——market_anchor 在指数 API 异常时
            # 会把 breadth 各字段填 0 并置 _degraded=True。若不区分，
            # "0 家涨停"会被当成真实值：养家情绪=0 → merge veto → 整个短线组
            # 被系统性打成看空（实测 emotion_tech 从 49.8 掉到 12.1）。
            # 降级时这些字段置 None，由评分层按"数据不可得"处理。
            "_degraded": bool(breadth.get("_degraded")),
            "_degraded_reason": breadth.get("_degraded_reason", ""),
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
                "abstain": res.get("abstain", False),
                "abstain_reason": res.get("abstain_reason", ""),
                "method": res["method"],
                "dim_scores": res.get("dim_scores", {}),
            }
        )

    # 弃权专家（score=None）不参与综合分——与 vote_engine 的投票基数口径一致
    scored = [r["score"] for r in expert_results if r["score"] is not None]
    composite = sum(scored) / len(scored) if scored else 50
    return {
        "code": code.upper(),
        "stock_data": stock_data,
        "expert_results": expert_results,
        "composite_score": round(composite, 1),
        "abstained": len(expert_results) - len(scored),
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
            if not e:
                row.append("-")
            elif e["score"] is None:
                row.append("弃权")  # 数据不足弃权，不计入投票基数
            else:
                row.append(f"{e['score']:.0f}/{e['direction'][:1]}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def run_debate_for_stock(code: str, group_filter: str | None = None, record: bool = True) -> dict:
    """跑完整 debate 闭环（v1.26.0 新增）。

    把量化评分接到 `experts.decide.run_debate` 编排器上，闭合此前断掉的
    校准回路：

        量化评分 → 市场环境判定 → run_debate（回灌校准因子 → 投票聚合 →
        风险分级 → 落库预测）→ 格式化输出

    此前 `run_debate` 全仓无生产调用方——校准因子算了没人用、预测没人
    落库，整套自校准机制在生产上是空转的。SKILL.md 步骤 5 只说"用
    run_debate 编排器"却没给命令，agent 无法接线。

    Args:
        code: 股票代码
        group_filter: "long"/"short"/None（None = 全部 8 人）
        record: 是否落库预测（False = 试跑不污染校准库）

    Returns:
        run_debate 的结果 dict + code/stock_data
    """
    from experts.decide import run_debate

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
                "display_name": p.display_name,
                "group": p.group,
                "score": res["score"],
                "direction": res["direction"],
                "abstain": res.get("abstain", False),
                "abstain_reason": res.get("abstain_reason", ""),
                "method": res["method"],
                "dim_scores": res.get("dim_scores", {}),
                "breakdown": res.get("breakdown", {}),
            }
        )

    # 市场环境：直接用 market_anchor 已判定的 regime（它内部走
    # experts.market_detector 唯一权威口径）。缺数据 → 防御型 fail-safe。
    market_state = None
    anchor = raw_meta.get("market_anchor") or {}
    if isinstance(anchor, dict) and not anchor.get("error") and anchor.get("regime"):
        market_state = {
            "state": anchor["regime"],
            "long_weight": anchor.get("long_weight", 0.55),
            "short_weight": anchor.get("short_weight", 0.45),
            "reason": anchor.get("regime_reason", ""),
        }

    result = run_debate(
        code.lower(),
        expert_results,
        market_state=market_state,
        stock_data=stock_data,
        record=record,
    )
    result["code"] = code.upper()
    result["stock_data"] = stock_data
    return result


def render_reasoning(code: str, group_filter: str | None = None) -> str:
    """渲染每位专家的评分明细（含三元组：原始分 × 权重 = 贡献值）。

    SKILL.md 发言规则要求「展示维度拆分（breakdown）时，必须输出
    `原始分 × 权重 = 贡献值` 三元组」——此前该能力（experts/scoring 的
    reasoning 链）无任何生产入口，agent 只能自行拼装。本函数把它接上。
    """
    from experts.registry import EXPERT_REGISTRY, _ensure_loaded
    from experts.scoring import format_generic_reasoning, score_expert_with_reasoning

    _ensure_loaded()
    stock_data, _ = build_stock_data(code)
    profiles = list_active_experts()
    if group_filter == "long":
        profiles = [p for p in profiles if p.group == "long_term"]
    elif group_filter == "short":
        profiles = [p for p in profiles if p.group == "short_term"]

    blocks = []
    for p in profiles:
        profile = EXPERT_REGISTRY.get(p.name, p)
        result = score_expert_with_reasoning(profile, stock_data)
        blocks.append(format_generic_reasoning(result))
    return "\n\n".join(blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description="8 位 active 专家量化评分 CLI")
    parser.add_argument("codes", nargs="+", help="股票代码列表")
    parser.add_argument("--long", action="store_true", help="仅长线 5 人")
    parser.add_argument("--short", action="store_true", help="仅短线 3 人")
    parser.add_argument(
        "--debate",
        action="store_true",
        help="跑完整 debate 闭环（回灌校准因子 + 投票聚合 + 落库预测 + 格式化输出）",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="debate 模式下不落库预测（试跑不污染校准历史）",
    )
    parser.add_argument(
        "--reasoning",
        action="store_true",
        help="输出每位专家的评分明细（三元组：原始分 × 权重 = 贡献值）",
    )
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    group = "long" if args.long else ("short" if args.short else None)

    # reasoning 模式：输出维度拆分明细（SKILL.md 三元组展示规则）
    if args.reasoning:
        for code in args.codes:
            print(f"\n{'=' * 60}\n# {code.upper()}")
            print(render_reasoning(code, group_filter=group))
        return 0

    # debate 模式：走 run_debate 编排器，闭合校准回路
    if args.debate:
        from experts.formatter import format_debate_output

        out = []
        for code in args.codes:
            try:
                out.append(run_debate_for_stock(code, group_filter=group, record=not args.no_record))
            except Exception as e:  # noqa: BLE001
                out.append({"code": code.upper(), "error": str(e)})

        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
            return 0

        for r in out:
            if r.get("error"):
                print(f"\n# {r['code']} 失败: {r['error']}")
                continue
            print(f"\n{'=' * 60}\n# {r['code']}")
            print(format_debate_output(r))
        return 0

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
    print(f"\n# 量化评分 · {'长线5' if args.long else ('短线3' if args.short else '全部8')}")
    print(render_table(out))
    print("\n# 方向标签说明：多=看多，空=看空，中=中性")
    print("# 注意：此为量化基线，debate 模式应与 LLM 推理分对比，差异 >15 须说明原因。\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

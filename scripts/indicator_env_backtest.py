#!/usr/bin/env python3
"""指标信号 × 市场环境 条件回测（逐日重放，与 technical 模块同源）。

方法：
  1. 指标信号：对每只股票逐日重放 technical 模块指标函数（macd_full/kdj_full/
     rsi_features/bollinger + incremental_ma + 量价突破），每个交易日 t 只引用
     ≤t 的数据（与实盘当日计算完全一致，无未来函数）；信号一律边沿触发
     （前一交易日未触发、当日触发才记录），避免连续状态样本自相关。
  2. 市场环境：对上证指数逐日重放 scoring.detect_market_environment 多日窗口
     口径（近 5 日均值涨跌幅 → 强势/弱势/震荡），同一环境标签供所有股票当日
     信号分组。冰点/亢奋依赖换手率与市场宽度数据，历史不可回补，不参与分组。
  3. 收益口径：信号在 t 日收盘确认，以 t 日收盘价入场，t+N 日收盘出场
     （N ∈ {1,3,5,10,20}）。多头信号成功率 = 收益>0 占比；
     空头信号成功率 = 收益<0 占比（作为卖出/回避信号的有效性）。
  4. 每个环境给出"随机日基准上涨率"（base rate），成功率必须与基准比较。

用法：
  PYTHONPATH=scripts:. python3 scripts/indicator_env_backtest.py \
      --output docs/archive/reviews/indicator-env-backtest-2026-10-29.md
  PYTHONPATH=scripts:. python3 scripts/indicator_env_backtest.py --codes sh600989,sh600276
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT / "scripts"))
sys.path.insert(0, str(PKG_ROOT))

from fetchers.kline.tencent_kline import TencentKlineFetcher  # noqa: E402
from technical.core import _EPS  # noqa: E402
from technical.moving_average import incremental_ma  # noqa: E402
from technical.macd import macd_full  # noqa: E402
from technical.kdj import kdj_full  # noqa: E402
from technical.rsi import rsi_features  # noqa: E402
from technical.boll import bollinger  # noqa: E402
from technical.scoring import detect_market_environment  # noqa: E402

# 推演股票池：宝丰能源（原 5 股样本内最优）+ 恒瑞医药（原最差）+ 三只不同行业
# /不同波动特征股票（消费白马/成长高波/金融低波），跨 2024-03 → 今 窗口
DEFAULT_CODES = [
    ("sh600989", "宝丰能源"),
    ("sh600276", "恒瑞医药"),
    ("sh600519", "贵州茅台"),
    ("sz300750", "宁德时代"),
    ("sh600036", "招商银行"),
]
INDEX_CODE = "sh000001"
HOLD_DAYS = [1, 3, 5, 10, 20]
WARMUP = 65  # MACD(26+9)+背离 lookback 60 需要的最小历史
BOARD = "主板"

SIG_META = {
    # key: (名称, 方向 bull/bear/neutral)
    "macd_gold": ("MACD金叉", "bull"),
    "macd_dead": ("MACD死叉", "bear"),
    "macd_div_bottom": ("MACD底背离", "bull"),
    "macd_div_top": ("MACD顶背离", "bear"),
    "kdj_gold": ("KDJ金叉", "bull"),
    "kdj_dead": ("KDJ死叉", "bear"),
    "kdj_gold_oversold": ("KDJ金叉+超卖", "bull"),
    "kdj_dead_overbought": ("KDJ死叉+超买", "bear"),
    "kdj_dunhua_high": ("KDJ高位钝化", "bull"),
    "kdj_dunhua_low": ("KDJ低位钝化", "bear"),
    "rsi_oversold": ("RSI超卖(<30)", "bull"),
    "rsi_overbought": ("RSI超买(>70)", "bear"),
    "boll_lower_touch": ("BOLL首次触下轨", "bull"),
    "boll_upper_touch": ("BOLL首次触上轨", "bear"),
    "boll_squeeze": ("BOLL极度收窄(变盘)", "neutral"),
    "ma_gold_5_10": ("MA5上穿MA10", "bull"),
    "ma_dead_5_10": ("MA5下穿MA10", "bear"),
    "ma_bull_align_new": ("多头排列初成", "bull"),
    "ma_bear_align_new": ("空头排列初成", "bear"),
    "vol_breakout": ("放量突破20日高", "bull"),
    "vol_breakdown": ("放量跌破20日低", "bear"),
}


def fetch_qfq(code: str, datalen: int = 800) -> list[dict]:
    """腾讯前复权日线（除息跳空不污染均线/MACD）。"""
    rows = TencentKlineFetcher().fetch(code, scale=240, datalen=datalen) or []
    return [r for r in rows if isinstance(r, dict) and r.get("day")]


def compute_market_env(index_bars: list[dict]) -> dict[str, str]:
    """逐日重放 detect_market_environment（近5日窗口口径），返回 date → state。

    指数换手率不可得（传 0），换手率分支（亢奋/冰点）自动跳过，
    环境取值 ⊆ {强势, 弱势, 震荡}。
    """
    closes = [float(b["close"]) for b in index_bars]
    dates = [b["day"] for b in index_bars]
    pcts = [0.0] + [
        round((closes[i] / closes[i - 1] - 1) * 100, 2) if closes[i - 1] else 0.0 for i in range(1, len(closes))
    ]
    env: dict[str, str] = {}
    for t in range(len(closes)):
        if t < 6:
            continue
        recent = [{"change_pct": p} for p in pcts[max(0, t - 5) : t]]
        idx_quote = {"price": closes[t], "change_pct": pcts[t], "turnover": 0}
        try:
            env[dates[t]] = detect_market_environment(idx_quote, recent_quotes=recent)["state"]
        except Exception:
            env[dates[t]] = "震荡"
    return env


def replay_signals(bars: list[dict]) -> list[dict]:
    """逐日重放指标，返回边沿触发的信号事件列表。

    返回元素: {t, day, key, note}（收益由调用方按 t 计算）。
    """
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    vols = [float(b["volume"]) for b in bars]
    dates = [b["day"] for b in bars]
    n = len(closes)

    ma5 = incremental_ma(closes, 5)
    ma10 = incremental_ma(closes, 10)
    ma20 = incremental_ma(closes, 20)
    # 滚动均量（前5日均量，不含当日）
    avg_vol5 = [float("nan")] * n
    for i in range(6, n):
        avg_vol5[i] = sum(vols[i - 5 : i]) / 5

    events = []
    prev_fired: set[str] = set()
    for t in range(WARMUP, n):
        c_t, h_t, l_t = closes[: t + 1], highs[: t + 1], lows[: t + 1]
        day = dates[t]
        fired = set()

        macd = macd_full(c_t)
        if macd:
            if macd["signal"] == 1:
                fired.add("macd_gold")
            elif macd["signal"] == -1:
                fired.add("macd_dead")
            div = macd.get("divergence")
            if div == "底背离(看涨)":
                fired.add("macd_div_bottom")
            elif div == "顶背离(看跌)":
                fired.add("macd_div_top")

        kdj = kdj_full(c_t, h_t, l_t, board=BOARD)
        if kdj:
            sig = kdj["signal"]
            if kdj.get("钝化"):
                if "高位钝化" in sig:
                    fired.add("kdj_dunhua_high")
                elif "低位钝化" in sig:
                    fired.add("kdj_dunhua_low")
            elif "金叉" in sig:
                fired.add("kdj_gold_oversold" if "超卖" in sig else "kdj_gold")
            elif "死叉" in sig:
                fired.add("kdj_dead_overbought" if "超买" in sig else "kdj_dead")

        rsi = rsi_features(c_t)
        if rsi:
            if rsi["signal"] == 1:
                fired.add("rsi_oversold")
            elif rsi["signal"] == -1:
                fired.add("rsi_overbought")

        boll = bollinger(c_t)
        boll_prev = bollinger(closes[:t]) if t >= 1 else None
        if boll and boll_prev:
            pos, pos_prev = boll["position"], boll_prev["position"]
            if pos < 0.1 <= pos_prev:
                fired.add("boll_lower_touch")
            elif pos > 0.9 >= pos_prev:
                fired.add("boll_upper_touch")
            bw, bw_prev = boll["bandwidth"], boll_prev["bandwidth"]
            if bw < 0.05 <= bw_prev:
                fired.add("boll_squeeze")

        if ma5[t] > ma10[t] and ma5[t - 1] <= ma10[t - 1]:
            fired.add("ma_gold_5_10")
        elif ma5[t] < ma10[t] and ma5[t - 1] >= ma10[t - 1]:
            fired.add("ma_dead_5_10")
        align_bull = ma5[t] > ma10[t] > ma20[t]
        align_bull_prev = ma5[t - 1] > ma10[t - 1] > ma20[t - 1]
        if align_bull and not align_bull_prev:
            fired.add("ma_bull_align_new")
        align_bear = ma5[t] < ma10[t] < ma20[t]
        align_bear_prev = ma5[t - 1] < ma10[t - 1] < ma20[t - 1]
        if align_bear and not align_bear_prev:
            fired.add("ma_bear_align_new")

        if avg_vol5[t] == avg_vol5[t] and avg_vol5[t] > 0:  # NaN 安全
            hi20 = max(closes[t - 20 : t])
            lo20 = min(closes[t - 20 : t])
            heavy = vols[t] > 2.5 * avg_vol5[t]
            if heavy and closes[t] > hi20:
                fired.add("vol_breakout")
            elif heavy and closes[t] < lo20:
                fired.add("vol_breakdown")

        # 边沿触发统一过滤：状态型信号（RSI 超买超卖/MACD 背离/KDJ 钝化等）
        # 在状态持续期间每日重触发，前一日已触发的 key 不再记录，避免样本自相关
        new_fired = fired - prev_fired
        prev_fired = fired
        for key in new_fired:
            events.append({"t": t, "day": day, "key": key})
    return events


def outcomes(closes: list[float], t: int) -> dict[int, float]:
    """信号日 t 收盘入场，t+N 日收盘出场收益（%）。数据不足的 N 丢弃。"""
    out = {}
    for nd in HOLD_DAYS:
        if t + nd < len(closes):
            out[nd] = round((closes[t + nd] / closes[t] - 1) * 100, 3)
    return out


def run_stock(code: str, name: str, env: dict[str, str]) -> dict:
    bars = fetch_qfq(code)
    if len(bars) < WARMUP + 30:
        return {"code": code, "name": name, "error": f"K线不足({len(bars)}根)"}
    closes = [float(b["close"]) for b in bars]
    dates = [b["day"] for b in bars]
    events = replay_signals(bars)

    # 去掉指数环境未覆盖的日期（指数与个股交易日应一致，防御性跳过）
    samples = []
    for ev in events:
        state = env.get(ev["day"])
        if state is None:
            continue
        direction = SIG_META[ev["key"]][1]
        rets = outcomes(closes, ev["t"])
        samples.append(
            {
                "code": code,
                "name": name,
                "day": ev["day"],
                "key": ev["key"],
                "direction": direction,
                "env": state,
                "rets": rets,
            }
        )

    # BOLL 极度收窄的变盘幅度（10 日绝对波动与方向占比）
    squeeze_extra = []
    for s in samples:
        if s["key"] == "boll_squeeze" and 10 in s["rets"]:
            squeeze_extra.append(abs(s["rets"][10]))
    return {
        "code": code,
        "name": name,
        "bars": len(bars),
        "kline_start": dates[0],
        "kline_end": dates[-1],
        "n_events": len(events),
        "samples": samples,
        "squeeze_abs_ret10": round(sum(squeeze_extra) / len(squeeze_extra), 2) if squeeze_extra else None,
    }


def agg_cell(samples: list[dict], key: str, state: str, nd: int) -> dict | None:
    """信号×环境×周期的单格统计。多头 win=ret>0，空头 win=ret<0。"""
    direction = SIG_META[key][1]
    rets = [s["rets"][nd] for s in samples if s["key"] == key and s["env"] == state and nd in s["rets"]]
    if len(rets) < 5:  # 样本下限：不足 5 个不给成功率结论
        return {"n": len(rets)} if rets else None
    wins = [r for r in rets if (r > _EPS if direction == "bull" else r < -_EPS)]
    rets_sorted = sorted(rets)
    med = rets_sorted[len(rets_sorted) // 2]
    return {
        "n": len(rets),
        "win_rate": round(len(wins) / len(rets) * 100, 1),
        "avg_ret": round(sum(rets) / len(rets), 2),
        "med_ret": round(med, 2),
    }


def base_rate(index_bars: list[dict], env: dict[str, str]) -> dict:
    """各环境下随机日 t+N 收盘上涨的基准率（用指数自身计算）。"""
    closes = [float(b["close"]) for b in index_bars]
    dates = [b["day"] for b in index_bars]
    by_state = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for t in range(WARMUP, len(closes)):
        state = env.get(dates[t])
        if not state:
            continue
        for nd in HOLD_DAYS:
            if t + nd < len(closes):
                by_state[state][nd][1] += 1
                if closes[t + nd] > closes[t]:
                    by_state[state][nd][0] += 1
    return {
        state: {nd: {"up_rate": round(v[0] / v[1] * 100, 1), "n": v[1]} for nd, v in days.items()}
        for state, days in by_state.items()
    }


def fmt_cell(cell: dict | None) -> str:
    if not cell:
        return "—"
    if "win_rate" not in cell:
        return f"{cell['n']}†"
    return f"{cell['win_rate']}%({cell['n']}) {cell['avg_ret']:+.1f}%"


def build_report(stocks: list[dict], env: dict[str, str], base: dict, args) -> str:
    all_samples = [s for st in stocks for s in st.get("samples", [])]
    states = [s for s in ("强势", "震荡", "弱势") if any(base.get(s))]
    pool_desc = "、".join(f"{st['name']}({st['code']})" for st in stocks)
    lines = []
    lines.append("# 指标信号 × 市场环境 条件回测报告（真实推演）\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(
        f"回测窗口: {min(st.get('kline_start', '9999') for st in stocks)} → "
        f"{max(st.get('kline_end', '') for st in stocks)}（腾讯前复权日线）"
    )
    lines.append(f"股票池: {pool_desc}")
    lines.append(f"市场环境: 上证指数({INDEX_CODE}) 逐日重放 detect_market_environment 近5日窗口口径")
    lines.append("")
    lines.append(
        "> 口径：信号 t 日收盘确认并按收盘价入场，t+N 收盘出场；多头成功率=涨占比，"
        "空头成功率=跌占比（作为卖出信号有效性）；样本 <5 只显示 † 不下结论。"
        "冰点/亢奋环境依赖换手率与市场宽度数据，历史不可回补，未参与分组。"
    )
    lines.append("")

    # 1. 基准率
    lines.append("## 1. 各市场环境随机日基准上涨率（base rate）\n")
    lines.append("| 环境 | 1日 | 3日 | 5日 | 10日 | 20日 |")
    lines.append("|------|-----|-----|-----|------|------|")
    for st in states:
        row = [f"**{st}**"]
        for nd in HOLD_DAYS:
            b = base.get(st, {}).get(nd)
            row.append(f"{b['up_rate']}% (n={b['n']})" if b else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 2. 全池信号×环境矩阵
    lines.append("## 2. 信号成功率 × 市场环境（5 股合并）\n")
    for nd in HOLD_DAYS:
        lines.append(f"### 信号后 {nd} 日收益\n")
        lines.append("| 信号 | 方向 | " + " | ".join(f"{st}环境" for st in states) + " |")
        lines.append("|------|------|" + "|".join(["------"] * len(states)) + "|")
        for key, (label, direction) in SIG_META.items():
            if direction == "neutral":
                continue
            row = [f"{label}", "多" if direction == "bull" else "空"]
            for st in states:
                row.append(fmt_cell(agg_cell(all_samples, key, st, nd)))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    # 3. BOLL 极度收窄变盘统计
    lines.append("## 3. BOLL 极度收窄（bandwidth<0.05）变盘统计\n")
    for st in stocks:
        if st.get("squeeze_abs_ret10") is not None:
            sq = [s for s in st.get("samples", []) if s["key"] == "boll_squeeze" and 10 in s["rets"]]
            up = len([s for s in sq if s["rets"][10] > 0])
            lines.append(
                f"- {st['name']}: 触发 {len(sq)} 次，后10日平均绝对波动 "
                f"{st['squeeze_abs_ret10']}%，其中上涨 {up}/{len(sq)} 次"
            )
    lines.append("")

    # 4. 逐股真实推演
    lines.append("## 4. 逐股真实推演（信号后 5 日成功率，全环境合并）\n")
    lines.append("| 股票 | K线区间 | " + " | ".join(f"{st}" for st in states) + " |")
    lines.append("|------|---------|" + "|".join(["------"] * len(states)) + "|")
    for st in stocks:
        samples = st.get("samples", [])
        by_key_env = defaultdict(list)
        for s in samples:
            if 5 in s["rets"]:
                by_key_env[(s["key"], s["env"])].append(s["rets"][5])
        cells = []
        for state in states:
            parts = []
            for key, (label, direction) in SIG_META.items():
                rets = by_key_env.get((key, state))
                if not rets or len(rets) < 3:
                    continue
                wins = [r for r in rets if (r > 0 if direction == "bull" else r < 0)]
                parts.append(f"{label} {len(wins)}/{len(rets)}")
            cells.append("<br>".join(parts) if parts else "—")
        lines.append(
            f"| {st['name']}<br>{st.get('kline_start','')}→{st.get('kline_end','')} | "
            f"{st.get('bars','?')}根 | " + " | ".join(cells) + " |"
        )
    lines.append("")

    # 5. 结论（延后由分析填入）
    lines.append("## 5. 方法与局限\n")
    lines.append(
        "- 指标计算与实盘同源：逐日调用 technical 模块 macd_full/kdj_full/rsi_features/bollinger，"
        "每日仅用 ≤t 数据；信号边沿触发去自相关。"
    )
    lines.append("- 前复权数据（腾讯 qfq），除息跳空不产生假信号；volume 为手（腾讯口径），仅用于倍数比较。")
    lines.append(
        "- 局限：① 未计交易成本与滑点；② 单一指数环境标签（沪深全市场宽度不可回补）；"
        "③ 样本期 2024-03 起，未覆盖更早牛熊；④ 空头信号在 A 股无直接做空收益，"
        "成功率仅代表'回避/减仓'有效性。"
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="指标信号×市场环境条件回测")
    parser.add_argument("--codes", help="逗号分隔股票代码（默认 5 只推演池）")
    parser.add_argument("--datalen", type=int, default=800)
    parser.add_argument("--output", help="markdown 报告输出路径")
    parser.add_argument("--json-out", help="原始样本 JSON 输出路径")
    args = parser.parse_args()

    if args.codes:
        codes = [(c.strip(), c.strip()) for c in args.codes.split(",") if c.strip()]
    else:
        codes = DEFAULT_CODES

    print(f"⏳ 拉取指数 {INDEX_CODE} ...")
    index_bars = fetch_qfq(INDEX_CODE, args.datalen)
    if len(index_bars) < WARMUP + 30:
        print(f"❌ 指数 K 线不足: {len(index_bars)}")
        return
    env = compute_market_env(index_bars)
    from collections import Counter

    print(f"✅ 环境标签 {len(env)} 天: {dict(Counter(env.values()))}")

    base = base_rate(index_bars, env)

    stocks = []
    for code, name in codes:
        print(f"⏳ 逐日重放 {name}({code}) ...")
        result = run_stock(code, name, env)
        if "error" in result:
            print(f"   ❌ {result['error']}")
            continue
        from collections import Counter as C2

        cnt = C2((s["key"], s["env"]) for s in result["samples"])
        top = ", ".join(f"{k[0]}[{k[1]}]×{v}" for k, v in cnt.most_common(5))
        print(f"   ✅ {result['bars']} 根 K 线, 信号事件 {result['n_events']} 个; top: {top}")
        stocks.append(result)

    if not stocks:
        print("❌ 无可用股票数据")
        return

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"env_counts": dict(Counter(env.values())), "base_rate": base, "stocks": stocks},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"📝 JSON 已写入: {out}")

    report = build_report(stocks, env, base, args)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"📝 报告已写入: {out}")
    else:
        print(report)


if __name__ == "__main__":
    main()

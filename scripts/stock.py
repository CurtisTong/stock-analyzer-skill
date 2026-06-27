#!/usr/bin/env python3
"""
个股五层分析（v1.3.2 接入 business/StockAnalysisService）。

用法:
  python3 scripts/stock.py sh600989           # 五层分析
  python3 scripts/stock.py sh600989 -j        # JSON 输出
  python3 scripts/stock.py sh600989 --no-finance  # 跳过财务（加速）

业务层入口：scripts/business/stock_analysis.py::StockAnalysisService.analyze
本脚本只负责：参数解析 + 业务层调用 + 结果渲染。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from business import StockAnalysisService


def render_text(result: dict) -> str:
    """把五层分析结果渲染为可读文本。"""
    lines = []
    code = result.get("code", "")
    name = result.get("name", "(未知)")
    price = result.get("price", 0)
    change_pct = result.get("change_pct", 0)

    # 标题行
    trend_icon = "🟢" if change_pct >= 0 else "🔴"
    lines.append(f"{'━' * 40}")
    lines.append(f"{trend_icon} {name}（{code}）")
    lines.append(f"   现价 {price:.2f}  涨跌 {change_pct:+.2f}%")
    lines.append(f"{'━' * 40}")

    # 数据缺失警告
    for w in result.get("data_warnings", []):
        lines.append(f"  {w}")
    if "warning" in result:
        lines.append(f"  ⚠ {result['warning']}")

    # 1. 行业画像
    if "profile" in result:
        p = result["profile"]
        lines.append(f"\n🏷 行业画像")
        lines.append(f"   类型: {p.get('type', '?')}  行业: {p.get('industry', '?')}")

    # 2. K 线 + 缠论
    if "kline_count" in result:
        lines.append(f"\n📈 K 线（{result['kline_count']} 根）")
    if "chan" in result:
        chan = result["chan"]
        if chan.get("valid"):
            lines.append(
                f"   缠论: 分型{chan.get('fenxing_count', 0)} 笔{chan.get('bi_count', 0)} "
                f"中枢{chan.get('zhongshu_count', 0)}  位置: {chan.get('current_position', '?')}"
            )
        else:
            lines.append(f"   缠论: {chan.get('error', '数据不足')}")

    # 3. 技术面
    if "technical" in result:
        t = result["technical"]
        ma_icon = {"多头": "🟢", "空头": "🔴", "交叉": "🟡"}.get(t.get("ma", ""), "⚪")
        lines.append(f"\n📊 技术面")
        lines.append(
            f"   均线 {ma_icon}{t.get('ma', '?')}  "
            f"MACD {t.get('macd_signal', 0):+d}  "
            f"KDJ {t.get('kdj', '?')}  "
            f"RSI {t.get('rsi', 0):.1f}"
        )
        lines.append(
            f"   BOLL 位置 {t.get('boll_position', 0.5):.2f}  "
            f"量价 {t.get('volume_signal', 0):+d}"
        )
        if t.get("patterns"):
            lines.append(
                f"   形态: {', '.join(p.get('name', str(p)) for p in t['patterns'][:3])}"
            )

    # 4. 财务摘要
    if "finance" in result:
        f = result["finance"]
        lines.append(f"\n💰 财务")
        lines.append(
            f"   EPS {f.get('eps', 0):.2f}  ROE {f.get('roe', 0):.2f}%  "
            f"净利同比 {f.get('net_profit_yoy', 0):+.2f}%"
        )
        lines.append(
            f"   营收同比 {f.get('revenue_yoy', 0):+.2f}%  "
            f"毛利率 {f.get('gross_margin', 0):.2f}%  "
            f"负债率 {f.get('debt_ratio', 0):.2f}%"
        )

    # 5. 综合评分
    if "score" in result:
        s = result["score"]
        score_val = s.get("score", 0)
        grade = s.get("grade", "?")
        score_icon = "🟢" if score_val >= 70 else "🟡" if score_val >= 50 else "🔴"
        lines.append(f"\n{'━' * 40}")
        lines.append(f"{score_icon} 综合评分: {score_val:.1f}  评级: {grade}")
        if s.get("buy_signals"):
            lines.append(f"   📌 买入信号: {'; '.join(s['buy_signals'][:3])}")
        if s.get("sell_signals"):
            lines.append(f"   ⚠️ 卖出信号: {'; '.join(s['sell_signals'][:3])}")

    lines.append(f"{'━' * 40}")
    return "\n".join(lines)


def render_brief(result: dict) -> str:
    """brief 模式：一句话结论 + 关键数据表 + 操作建议（<500字）。"""
    lines = []
    code = result.get("code", "")
    name = result.get("name", "(未知)")
    price = result.get("price", 0)
    change_pct = result.get("change_pct", 0)

    # 一句话结论
    s = result.get("score", {})
    grade = s.get("grade", "?")
    score_val = s.get("score", 0)
    lines.append(
        f"{code} {name} | 现价 {price} ({change_pct:+.2f}%) | "
        f"综合评分 {score_val:.1f} 评级 {grade}"
    )

    # 关键数据表（紧凑单行）
    parts = []
    t = result.get("technical", {})
    if t:
        parts.append(f"MA:{t.get('ma', '?')}")
        parts.append(f"RSI:{t.get('rsi', 0):.0f}")
        parts.append(f"MACD:{t.get('macd_signal', 0):+d}")
    fin = result.get("finance", {})
    if fin:
        parts.append(f"ROE:{fin.get('roe', 0):.1f}%")
        parts.append(f"净利YoY:{fin.get('net_profit_yoy', 0):+.0f}%")
    if parts:
        lines.append(" | ".join(parts))

    # 操作建议
    buy = s.get("buy_signals", [])
    sell = s.get("sell_signals", [])
    if score_val >= 75:
        action = "关注买入"
    elif score_val >= 55:
        action = "观望"
    else:
        action = "谨慎回避"
    advice_parts = [action]
    if buy:
        advice_parts.append(f"买入信号: {buy[0]}")
    if sell:
        advice_parts.append(f"卖出信号: {sell[0]}")
    lines.append(" → ".join(advice_parts))

    return "\n".join(lines)


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = argparse.ArgumentParser(description="个股五层分析")
    parser.add_argument("code", help="股票代码（带 sh/sz/bj 前缀）")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--no-finance", action="store_true", help="跳过财务分析")
    parser.add_argument("--no-technical", action="store_true", help="跳过技术分析")
    parser.add_argument("--no-chan", action="store_true", help="跳过缠论分析")
    parser.add_argument(
        "--with-backtest",
        action="store_true",
        help="附加近 60 日回测胜率（需运行 backtest.py）",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="简要模式：一句话结论 + 关键数据 + 操作建议",
    )
    args = parser.parse_args()

    svc = StockAnalysisService()
    result = svc.analyze(
        args.code,
        include_technical=not args.no_technical,
        include_finance=not args.no_finance,
        include_chan=not args.no_chan,
    )

    # 附加回测胜率（直接函数调用，避免 subprocess 开销）
    if args.with_backtest:
        try:
            from backtest.metrics import run_backtest

            bt = run_backtest("balanced", [args.code], days=60)
            result["backtest"] = {
                "win_rate": bt.get("win_rate_pct"),
                "total_return": bt.get("total_return_pct"),
                "sharpe": bt.get("sharpe_ratio"),
                "max_drawdown": bt.get("max_drawdown_pct"),
            }
        except Exception as e:
            result["backtest_error"] = str(e)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.brief:
        print(render_brief(result))
    else:
        print(render_text(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        from common.exceptions import format_error

        print(f"❌ {format_error(e)}", file=sys.stderr)
        sys.exit(1)

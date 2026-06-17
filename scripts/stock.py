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

    lines.append(f"=== {code} {name} ===")
    lines.append(f"现价: {price}    涨跌: {change_pct:+.2f}%")
    if "warning" in result:
        lines.append(f"⚠ {result['warning']}")
    lines.append("")

    # 1. 行业画像
    if "profile" in result:
        p = result["profile"]
        lines.append(
            f"【行业画像】类型: {p.get('type', '?')}  行业: {p.get('industry', '?')}"
        )

    # 2. K 线
    if "kline_count" in result:
        lines.append(f"\n【K 线】已加载 {result['kline_count']} 根")
    if "chan" in result:
        chan = result["chan"]
        if chan.get("valid"):
            lines.append(
                f"【缠论】分型 {chan.get('fenxing_count', 0)}  笔 {chan.get('bi_count', 0)}  "
                f"中枢 {chan.get('zhongshu_count', 0)}  当前位置: {chan.get('current_position', '?')}"
            )
        else:
            lines.append(f"【缠论】{chan.get('error', '数据不足')}")

    # 3. 技术面
    if "technical" in result:
        t = result["technical"]
        lines.append(
            f"\n【技术面】均线 {t.get('ma', '?')}  "
            f"MACD {t.get('macd_signal', 0):+d}  "
            f"KDJ {t.get('kdj', '?')}  "
            f"RSI {t.get('rsi', 0):.1f}  "
            f"BOLL 位置 {t.get('boll_position', 0.5):.2f}  "
            f"量价 {t.get('volume_signal', 0):+d}"
        )
        if t.get("patterns"):
            lines.append(
                f"        形态: {', '.join(p.get('name', str(p)) for p in t['patterns'][:3])}"
            )

    # 4. 财务摘要
    if "finance" in result:
        f = result["finance"]
        lines.append(
            f"\n【财务】EPS {f.get('eps', 0):.2f}  ROE {f.get('roe', 0):.2f}%  "
            f"净利同比 {f.get('net_profit_yoy', 0):+.2f}%  "
            f"营收同比 {f.get('revenue_yoy', 0):+.2f}%  "
            f"毛利率 {f.get('gross_margin', 0):.2f}%  "
            f"负债率 {f.get('debt_ratio', 0):.2f}%"
        )

    # 5. 综合评分
    if "score" in result:
        s = result["score"]
        lines.append(
            f"\n【综合评分】{s.get('score', 0):.1f}  评级: {s.get('grade', '?')}"
        )
        if s.get("buy_signals"):
            lines.append(f"        买入信号: {'; '.join(s['buy_signals'][:3])}")
        if s.get("sell_signals"):
            lines.append(f"        卖出信号: {'; '.join(s['sell_signals'][:3])}")

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
    args = parser.parse_args()

    svc = StockAnalysisService()
    result = svc.analyze(
        args.code,
        include_technical=not args.no_technical,
        include_finance=not args.no_finance,
        include_chan=not args.no_chan,
    )

    # 附加回测胜率
    if args.with_backtest:
        try:
            import subprocess

            bt_result = subprocess.run(
                ["python3", "scripts/backtest.py", args.code, "--days", "60", "-j"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(Path(__file__).resolve().parent.parent),
            )
            if bt_result.returncode == 0:
                bt_data = json.loads(bt_result.stdout)
                if "balanced" in bt_data:
                    result["backtest"] = {
                        "win_rate": bt_data["balanced"].get("win_rate"),
                        "total_return": bt_data["balanced"].get("total_return"),
                        "sharpe": bt_data["balanced"].get("sharpe"),
                        "max_drawdown": bt_data["balanced"].get("max_drawdown"),
                    }
        except Exception as e:
            result["backtest_error"] = str(e)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()

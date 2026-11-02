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
from common.cli_base import create_parser, handle_errors
from common.formatters import format_footer, format_output, now_str


def render_text(result: dict) -> str:
    """把五层分析结果渲染为可读文本。

    遵循 ``common.formatters`` 统一输出约定：保留原分段结构，
    但在末尾附加数据时间戳 + 数据源 footer，使每个 skill 输出结构一致。
    """
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
        lines.append("\n🏷 行业画像")
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
        lines.append("\n📊 技术面")
        lines.append(
            f"   均线 {ma_icon}{t.get('ma', '?')}  "
            f"MACD {t.get('macd_signal', 0):+d}  "
            f"KDJ {t.get('kdj', '?')}  "
            f"RSI {t.get('rsi', 0):.1f}"
        )
        lines.append(f"   BOLL 位置 {t.get('boll_position', 0.5):.2f}  " f"量价 {t.get('volume_signal', 0):+d}")
        if t.get("patterns"):
            lines.append(
                f"   形态: {', '.join((p.get('name') or p.get('type') or '未知形态') for p in t['patterns'][:3])}"
            )

    # 4. 财务摘要
    if "finance" in result:
        f = result["finance"]
        lines.append("\n💰 财务")

        # None 透传--格式化为 "-"
        def _f2(v, spec):
            return format(v, spec) if v is not None else "-"

        # 口径标注（防线5）：EPS 旁标 [单季/累计/年报 日期]，防 LLM 误算 PE
        eps_caliber = f.get("eps_caliber", "")
        caliber_tag = f"  [{eps_caliber}]" if eps_caliber else ""
        lines.append(
            f"   EPS {_f2(f.get('eps'), '.2f')}{caliber_tag}  "
            f"ROE {_f2(f.get('roe'), '.2f')}%  "
            f"净利同比 {_f2(f.get('net_profit_yoy'), '+.2f')}%"
        )
        lines.append(
            f"   营收同比 {_f2(f.get('revenue_yoy'), '+.2f')}%  "
            f"毛利率 {_f2(f.get('gross_margin'), '.2f')}%  "
            f"负债率 {_f2(f.get('debt_ratio'), '.2f')}%"
        )
        # 单季 EPS 追加年化提示行，防止 LLM 直接 price/eps
        if f.get("eps_annualized_hint") is not None:
            lines.append(
                f"   ⚠ 单季EPS年化≈{_f2(f.get('eps_annualized_hint'), '.2f')}  " f"（仅供参考，估值请用TTM/年报口径）"
            )
        if "warning" in f:
            lines.append(f"   {f['warning']}")

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

    # 6. 回测附加（--with-backtest）
    if "backtest" in result:
        bt = result["backtest"]
        lines.append("\n📊 近 60 日回测")
        lines.append(
            f"   胜率 {bt.get('win_rate', 0) or 0:.1f}%  "
            f"累计收益 {bt.get('total_return', 0) or 0:+.2f}%  "
            f"夏普 {bt.get('sharpe', 0) or 0:.2f}"
        )
        lines.append(f"   最大回撤 {bt.get('max_drawdown', 0) or 0:.2f}%")
    elif "backtest_error" in result:
        lines.append(f"\n⚠ 回测失败: {str(result['backtest_error'])[:100]}")

    # 统一 footer：数据时间戳 + 数据源（按 12 个 skill 共享约定）。
    data_time = result.get("data_time") or now_str()
    sources = result.get("data_sources") or ["行情", "财务", "K线"]
    failed = result.get("data_failed") or []
    # 错误模式 footer 加 ⚠️ 警示（数据降级）让 SKILL 渲染层立即识别。
    degraded = bool(failed or result.get("data_warnings"))
    footer = format_footer(
        data_time=data_time,
        sources=sources,
        failed_sources=failed,
        ttl_sec=900,
        degraded=degraded,
    )
    if footer:
        lines.append(footer)

    return "\n".join(lines)


def render_brief(result: dict) -> str:
    """brief 模式：使用 ``format_output`` 走统一一句话结论模板（<500字）。"""
    code = result.get("code", "")
    name = result.get("name", "(未知)")
    price = result.get("price", 0)
    change_pct = result.get("change_pct", 0)

    s = result.get("score", {})
    grade = s.get("grade", "?")
    score_val = s.get("score", 0)
    buy = s.get("buy_signals", [])
    sell = s.get("sell_signals", [])

    # 一句话结论：以综合评分定基调（信号列表补充多空方向）
    if score_val >= 75:
        action = "关注买入"
    elif score_val >= 55:
        action = "观望"
    else:
        action = "谨慎回避"
    if buy and not sell:
        action = "关注买入"
    elif sell and not buy:
        action = "谨慎回避"
    # 首行 emoji 按评级定调（涨跌已用 +/-% 数字表达）——此前按涨跌取 🟢/🔴，
    # 评分为"谨慎回避"时前面却是 🟢，用户误读为多头方向。
    trend_icon = "🟢" if score_val >= 75 else "🟡" if score_val >= 55 else "🔴"
    conclusion = (
        f"{trend_icon} {name}（{code}）现价 {price:.2f}（{change_pct:+.2f}%）｜"
        f"综合评分 {score_val:.1f}（{grade}）｜{action}"
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

        def _f_brief(v, spec):
            return format(v, spec) if v is not None else "-"

        parts.append(f"ROE:{_f_brief(fin.get('roe'), '.1f')}%")
        parts.append(f"净利YoY:{_f_brief(fin.get('net_profit_yoy'), '+.0f')}%")
        # 口径标注（防线5）：brief 紧凑版，提示 LLM 单季 EPS 不可直接算 PE
        caliber = fin.get("eps_caliber", "")
        if caliber:
            parts.append(f"EPS口径:{caliber}")
    body_lines = []
    if parts:
        body_lines.append(" | ".join(parts))
    advice_parts = []
    if buy:
        advice_parts.append(f"买入信号: {buy[0]}")
    if sell:
        advice_parts.append(f"卖出信号: {sell[0]}")
    if advice_parts:
        body_lines.append(" → ".join(advice_parts))

    return format_output(
        conclusion=conclusion,
        data_time=result.get("data_time") or now_str(),
        sources=result.get("data_sources") or ["行情", "财务", "K线"],
        failed_sources=result.get("data_failed") or [],
        ttl_sec=900,
        body="\n".join(body_lines) if body_lines else None,
        emoji="🎯",
    )


def _attach_backtest(result: dict, code: str) -> None:
    """附加近 60 日回测胜率（--with-backtest，直接函数调用避免 subprocess 开销）。

    run_backtest 的文档化失败路径返回 {"error": ...}，必须走 backtest_error
    降级展示（render_text 的 "⚠ 回测失败" 分支 + data_failed 护栏条），
    不得把缺字段渲染成 0% 胜率——回测失败与"没跑赢"必须可区分。
    """
    try:
        from backtest.metrics import run_backtest

        bt = run_backtest("balanced", [code], days=60)
        if "error" in bt:
            result["backtest_error"] = str(bt["error"])
            result.setdefault("data_failed", []).append("回测胜率")
        else:
            result["backtest"] = {
                "win_rate": bt.get("win_rate_pct"),
                "total_return": bt.get("total_return_pct"),
                "sharpe": bt.get("sharpe_ratio"),
                "max_drawdown": bt.get("max_drawdown_pct"),
            }
    except Exception as e:
        # M4: --with-backtest 失败时显式标 data_failed，
        # 让 render_footer 在 SKILL.md 约定的"数据护栏条"中体现降级。
        result["backtest_error"] = str(e)
        result.setdefault("data_failed", []).append("回测胜率")


def _known_code(code: str) -> bool:
    """代码是否在本地任意已知池（all_stocks.json / sector_stocks.json）。

    仅用于"代码不存在"判定兜底：本地池没有 ≠ 一定不存在（预置池可能过期），
    但配合行情 0 价 + 全部数据降级，足以区分"输错代码"与"数据源临时故障"。
    """
    import json

    digits = "".join(ch for ch in code.lower() if ch.isdigit())
    data_dir = Path(__file__).resolve().parent / "data"
    for fname in ("all_stocks.json", "sector_stocks.json", "sector_stocks.default.json"):
        p = data_dir / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for value in (data.values() if isinstance(data, dict) else []):
            if isinstance(value, dict):
                value = value.get("codes", value.get("stocks", []))
            if isinstance(value, list):
                for c in value:
                    if "".join(ch for ch in str(c).lower() if ch.isdigit()) == digits:
                        return True
    return False


def _check_data_blackout(result: dict, raw_code: str):
    """假研判防护（user-P0-2）：行情 0 价 + 主要数据全部降级时返回错误文案。

    区分"代码不存在"与"数据源临时故障"：本地已知池没有该代码 → 大概率
    输错/已退市；在池内 → 数据源问题。返回 None 表示可正常渲染。
    """
    price = result.get("price", 0)
    failed = result.get("data_failed", [])
    if price not in (None, 0) or len(failed) < 2:
        return None
    if not _known_code(raw_code):
        return (
            "未找到该股票的任何数据：代码可能不存在、已退市，或输入有误\n"
            "【根因】行情/财务/K线三类数据全部失败，且本地股票池未收录该代码\n"
            "【下一步】① 核对代码（支持 sh600519 / 600519 / 贵州茅台 三种写法）"
            "；② 先跑 /screener 看当前可交易标的；③ 确认真代码仍报错 → 数据源故障，稍后重试"
        )
    return (
        "数据源全部不可用，暂时无法分析该股票\n"
        "【根因】行情/财务/K线数据请求全部失败（限频或网络）\n"
        "【下一步】① 等 60 秒再试；② /screener init default 走离线预置数据；"
        "③ 加 --debug 查看具体失败链"
    )


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = create_parser(description="个股五层分析")
    parser.add_argument("code", help="股票代码（带 sh/sz/bj 前缀）")
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
    parser.add_argument(
        "--finance-periods",
        type=int,
        default=8,
        help="财务数据期数（默认 8 季，full/debate 模式推荐；最少 1 季）",
    )
    args = parser.parse_args()

    svc = StockAnalysisService()
    result = svc.analyze(
        args.code,
        include_technical=not args.no_technical,
        include_finance=not args.no_finance,
        include_chan=not args.no_chan,
        finance_periods=args.finance_periods,
    )

    # 假研判防护（user-P0-2）：数据全降级时输出三明治错误而非 🟢 综合评分
    blackout_msg = _check_data_blackout(result, args.code)
    if blackout_msg:
        print(f"❌ {blackout_msg}", file=sys.stderr)
        sys.exit(2)

    # 附加回测胜率（--with-backtest）
    if args.with_backtest:
        _attach_backtest(result, args.code)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.brief:
        print(render_brief(result))
    else:
        print(render_text(result))


if __name__ == "__main__":
    with handle_errors():
        main()

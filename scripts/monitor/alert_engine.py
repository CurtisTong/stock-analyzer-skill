"""
策略信号引擎：计算持仓+自选股的关键点位，盘中触及即推送。

业务逻辑已拆分至 monitor 子包：
  - rules.py       预警分级配置 + 预警检查
  - data_fetch.py  技术分析数据获取
  - levels.py      关键点位计算
  - scanner.py     持仓+自选股扫描
  - notifier.py    盘中检查与推送
  - briefing.py    盘前简报数据计算

本文件只保留 re-export、纯文本渲染函数和 CLI 入口。

用法:
  python3 scripts/monitor/alert_engine.py scan               # 扫描全部，输出关键点位
  python3 scripts/monitor/alert_engine.py scan --json        # JSON 输出
  python3 scripts/monitor/alert_engine.py levels sh600989    # 单股关键点位
  python3 scripts/monitor/alert_engine.py check              # 盘中检查，触发推送
  python3 scripts/monitor/alert_engine.py check --dry-run    # 只输出不推送
  python3 scripts/monitor/alert_engine.py briefing [--json]  # 盘前简报
"""

import json
import sys
import os
from datetime import datetime

# 确保 scripts/ 在 sys.path（直接运行 scripts/monitor/alert_engine.py 时需要）
_scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# ── re-export：保持外部兼容性 ──
from monitor.rules import ALERT_LEVELS, _LEVEL_META, get_alert_level, _check_alerts
from monitor.data_fetch import _fetch_technical_data
from monitor.levels import compute_key_levels
from monitor.scanner import scan_all, _get_pm
from monitor.notifier import check_and_push, _get_nm, _reset_cache
from monitor.briefing import compute_briefing

from common import normalize_quote_code


def render_scan(results: list) -> str:
    """渲染扫描结果为可读文本。"""
    lines = []
    lines.append(f"📊 关键点位扫描 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"扫描标的: {len(results)} 只")
    lines.append("")

    for r in results:
        code = r["code"]
        name = r.get("name", code)
        price = r.get("price", 0)
        change = r.get("change_pct", 0)
        error = r.get("error")

        if error:
            lines.append(f"❌ {name}({code}): {error}")
            continue

        icon = "🔴" if change < 0 else "🟢" if change > 0 else "⚪"
        lines.append(f"{icon} {name}({code}) | 现价 {price} | {change:+.2f}%")

        levels = r.get("levels", {})

        # 支撑位
        supports = levels.get("supports", [])
        if supports:
            items = [f"{s['level']}({s.get('source', '')})" for s in supports[:3]]
            lines.append(f"  支撑: {' / '.join(items)}")

        # 压力位
        resistances = levels.get("resistances", [])
        if resistances:
            items = [f"{r['level']}({r.get('source', '')})" for r in resistances[:3]]
            lines.append(f"  压力: {' / '.join(items)}")

        # 均线
        ma_vals = levels.get("ma_values", {})
        if ma_vals:
            items = [f"{k}={v}" for k, v in ma_vals.items()]
            lines.append(f"  均线: {' | '.join(items)}")

        # MACD
        macd_info = levels.get("macd", {})
        if macd_info:
            sig = levels.get("macd_signal", "")
            bar = macd_info.get("bar_trend", "")
            lines.append(
                f"  MACD: DIF={macd_info.get('dif')} DEA={macd_info.get('dea')} | {sig or bar}"
            )

        # 目标价
        if levels.get("target_buy"):
            lines.append(f"  目标买入: {levels['target_buy']}")
        if levels.get("target_sell"):
            lines.append(f"  目标卖出: {levels['target_sell']}")

        # 预警
        alerts = r.get("alerts", [])
        if alerts:
            for a in alerts:
                urgent_mark = "🔴" if a.get("urgent") else "🟡"
                lines.append(f"  {urgent_mark} 预警: {a['message']}")

        lines.append("")

    return "\n".join(lines)


def render_levels(code: str) -> str:
    """渲染单股关键点位。"""
    pm = _get_pm()
    pos = pm.get_position(code)
    watch = pm.get_watch(code)
    r = compute_key_levels(code, position=pos, watch=watch)
    return render_scan([r])


def render_briefing(data: dict) -> str:
    """渲染盘前简报为可读文本。

    Args:
        data: compute_briefing() 返回的结构化数据

    Returns:
        拼装好的简报文本
    """
    market_lines = data.get("market_lines", [])
    overnight_lines = data.get("overnight_lines", [])
    northbound_lines = data.get("northbound_lines", [])
    pos_lines = data.get("pos_lines", [])
    alert_lines = data.get("alerts", [])
    positions_count = data.get("positions_count", 0)
    portfolio = data.get("portfolio", {})
    total_pnl = portfolio.get("total_pnl", 0)
    total_pnl_pct = portfolio.get("total_pnl_pct", 0)

    lines = [
        f"📊 盘前简报 | {data['timestamp']}",
        "",
        "━━ 市场状态 ━━",
    ]
    lines.extend(market_lines)

    if overnight_lines:
        lines.append("")
        lines.append("━━ 隔夜外盘 ━━")
        lines.extend(overnight_lines)

    if northbound_lines:
        lines.append("")
        lines.append("━━ 北向资金 ━━")
        lines.extend(northbound_lines)

    lines.append("")
    lines.append(f"━━ 持仓概要（{positions_count} 只）━━")
    if pos_lines:
        lines.extend(pos_lines)
        pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
        lines.append(f"  {pnl_icon} 总盈亏: {total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)")
    else:
        lines.append("  （暂无持仓）")

    if alert_lines:
        lines.append("")
        lines.append("━━ 关键预警 ━━")
        lines.extend(alert_lines)

    lines.append("")
    lines.append("━━ 建议 ━━")
    if not positions_count:
        lines.append("  📌 无持仓，可运行 /screener 选股")
    elif total_pnl_pct < -5:
        lines.append("  ⚠️ 组合浮亏较大，关注止损位")
    elif total_pnl_pct > 10:
        lines.append("  📈 组合浮盈良好，注意止盈纪律")
    else:
        lines.append("  ✅ 组合状态正常，保持纪律")

    return "\n".join(lines)


def daily_briefing(as_json: bool = False) -> dict:
    """盘前简报（薄包装）：compute_briefing + render_briefing。

    保留 as_json 参数仅为向后兼容，实际不影响数据计算。
    """
    data = compute_briefing()
    data["summary"] = render_briefing(data)
    return data


def main():
    args = sys.argv[1:]
    if not args:
        print("用法:")
        print("  alert_engine.py scan [--json]                  # 扫描全部标的")
        print("  alert_engine.py levels <code>                  # 单股关键点位")
        print("  alert_engine.py check [--dry-run] [--level L]  # 盘中检查+推送")
        print("  alert_engine.py briefing [--json]              # 盘前简报")
        print("")
        print("推送级别 (--level):")
        print("  urgent    - 只推送紧急预警（止损、涨跌停附近）")
        print("  important - 推送重要+紧急预警（默认）")
        print("  normal    - 推送所有预警")
        sys.exit(1)

    cmd = args[0]

    if cmd == "scan":
        results = scan_all()
        if "--json" in args:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(render_scan(results))

    elif cmd == "levels":
        if len(args) < 2:
            print("用法: alert_engine.py levels <code>")
            sys.exit(1)
        code = normalize_quote_code(args[1])
        print(render_levels(code))

    elif cmd == "check":
        dry_run = "--dry-run" in args

        # 解析 --level 参数
        level = "important"  # 默认推送重要+紧急
        if "--level" in args:
            level_idx = args.index("--level")
            if level_idx + 1 < len(args):
                level = args[level_idx + 1]
                if level not in _LEVEL_META:
                    print(f"无效的级别: {level}，可选: {', '.join(_LEVEL_META.keys())}")
                    sys.exit(1)

        summary = check_and_push(dry_run=dry_run, level=level)
        if "--json" in args:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            mode = "（dry-run）" if dry_run else ""
            level_name = _LEVEL_META.get(level, {}).get("name", level)
            print(f"📡 盘中检查{mode} | {summary['timestamp']}")
            print(f"推送级别: {level_name}")
            print(
                f"扫描: {summary['scanned']} | 预警: {summary['alerts']} | 过滤: {summary.get('filtered', 0)} | 推送: {summary['pushed']}"
            )
            for d in summary.get("details", []):
                status = "✅" if d.get("pushed") else "⏭️"
                level_icon = {"urgent": "🔴", "important": "🟡", "normal": "🟢"}.get(
                    d.get("level", ""), "⚪"
                )
                print(
                    f"  {status} {level_icon} {d['name']}({d['code']}): {d['message']}"
                )

    elif cmd == "briefing":
        result = daily_briefing(as_json="--json" in args)
        if "--json" in args:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["summary"])

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

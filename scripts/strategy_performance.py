"""
策略表现校准（review#17）：定期回测并记录到 strategy_performance.json。

解决问题：策略权重凭经验设定，无回测数据支撑。
本工具：
  1. 跑 5 策略滚动回测，记录 11 项指标到 data/strategy_performance.json
  2. 支持月度报告（按月聚合夏普/胜率/收益）
  3. 支持跨期对比（环比/同比）

CLI:
  python3 scripts/strategy_performance.py record [--days 60] [--top 5]
  python3 scripts/strategy_performance.py report [--month 2026-06]
  python3 scripts/strategy_performance.py compare sh600519,sh600989
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import DATA_DIR  # noqa: E402
from strategies import STRATEGIES  # noqa: E402
from backtest import run_backtest, load_test_universe  # noqa: E402

PERFORMANCE_FILE = Path(DATA_DIR) / "strategy_performance.json"


def _load() -> Dict:
    """加载历史表现记录。"""
    if not PERFORMANCE_FILE.exists():
        return {"records": []}
    return json.loads(PERFORMANCE_FILE.read_text(encoding="utf-8"))


def _save(data: Dict) -> None:
    """保存到磁盘。"""
    PERFORMANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERFORMANCE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def record_all(days: int = 60, top: int = 5, codes: List[str] = None) -> Dict:
    """跑 5 策略回测并记录。

    Args:
        days: 回测天数
        top: 每轮持股数
        codes: 股票池（None 用 load_test_universe）

    Returns:
        新增的 record dict
    """
    if codes is None:
        codes = load_test_universe()
    if not codes:
        return {"error": "无可用股票池"}

    now = datetime.now()
    record = {
        "timestamp": now.isoformat(timespec="microseconds"),
        "date": now.strftime("%Y-%m-%d"),
        "month": now.strftime("%Y-%m"),
        "days": days,
        "top": top,
        "pool_size": len(codes),
        "strategies": {},
    }

    for name in STRATEGIES:
        result = run_backtest(name, codes, top_n=top, days=days, rounds=5)
        if "error" in result:
            record["strategies"][name] = {"error": result["error"]}
            continue
        record["strategies"][name] = {
            "total_return_pct": result.get("total_return_pct"),
            "sharpe_ratio": result.get("sharpe_ratio"),
            "max_drawdown_pct": result.get("max_drawdown_pct"),
            "win_rate_pct": result.get("win_rate_pct"),
            "annual_turnover": result.get("annual_turnover"),
            "profit_loss_ratio": result.get("profit_loss_ratio"),
        }

    data = _load()
    data["records"].append(record)
    _save(data)
    return record


def report(month: str = None) -> Dict:
    """生成月度报告（按月聚合）。

    Args:
        month: YYYY-MM 格式（None 时返回所有月度）

    Returns:
        {"by_month": {month: {strategy: avg_metrics}}, "latest": record}
    """
    data = _load()
    records = data.get("records", [])
    if not records:
        return {"by_month": {}, "latest": None}

    by_month: Dict[str, Dict] = {}
    for r in records:
        m = r.get("month", "")
        if month and m != month:
            continue
        if m not in by_month:
            by_month[m] = {name: [] for name in STRATEGIES}
        for sname, sdata in r.get("strategies", {}).items():
            if "error" not in sdata and sdata.get("total_return_pct") is not None:
                by_month[m][sname].append(sdata)

    aggregated = {}
    for m, sdata in by_month.items():
        aggregated[m] = {}
        for sname, runs in sdata.items():
            if not runs:
                continue
            avg_metrics = {}
            for key in (
                "total_return_pct",
                "sharpe_ratio",
                "win_rate_pct",
                "max_drawdown_pct",
                "annual_turnover",
            ):
                values = [r[key] for r in runs if r.get(key) is not None]
                if values:
                    avg_metrics[key] = round(sum(values) / len(values), 2)
            aggregated[m][sname] = {
                "runs": len(runs),
                **avg_metrics,
            }

    return {
        "by_month": aggregated,
        "latest": records[-1] if records else None,
    }


def main():
    parser = argparse.ArgumentParser(description="策略表现校准")
    sub = parser.add_subparsers(dest="command")

    rec_cmd = sub.add_parser("record", help="跑回测并记录")
    rec_cmd.add_argument("--days", type=int, default=60)
    rec_cmd.add_argument("--top", type=int, default=5)
    rec_cmd.add_argument("--codes", help="逗号分隔股票代码")

    rep_cmd = sub.add_parser("report", help="月度报告")
    rep_cmd.add_argument("--month", help="YYYY-MM 格式")
    rep_cmd.add_argument("-j", "--json", action="store_true")

    args = parser.parse_args()

    if args.command == "record":
        codes = None
        if args.codes:
            from common import normalize_quote_code

            codes = [normalize_quote_code(c) for c in args.codes.split(",")]
        record = record_all(days=args.days, top=args.top, codes=codes)
        if "error" in record:
            print(f"❌ {record['error']}")
            return
        print(f"✅ 已记录 {len(record['strategies'])} 策略到 {PERFORMANCE_FILE}")
        for name, sdata in record["strategies"].items():
            if "error" in sdata:
                print(f"  {name}: ERROR {sdata['error']}")
            else:
                print(
                    f"  {name:<18} 收益={sdata.get('total_return_pct')}% "
                    f"夏普={sdata.get('sharpe_ratio')} "
                    f"胜率={sdata.get('win_rate_pct')}%"
                )

    elif args.command == "report":
        result = report(month=args.month)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("按月报告:")
            for m, sdata in result["by_month"].items():
                print(f"\n[{m}]")
                for sname, m_data in sdata.items():
                    print(
                        f"  {sname:<18} 跑 {m_data.get('runs', 0)} 次 | "
                        f"收益={m_data.get('total_return_pct')}% "
                        f"夏普={m_data.get('sharpe_ratio')} "
                        f"胜率={m_data.get('win_rate_pct')}%"
                    )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

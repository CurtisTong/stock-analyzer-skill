"""
性能压测脚本：测量 screener / backtest 端到端耗时。

用法:
  python3 scripts/perf_bench.py screener --codes sh600519,sh600989 --rounds 3
  python3 scripts/perf_bench.py backtest --codes sh600519,sh600989 --rounds 3
  python3 scripts/perf_bench.py all
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _parse_codes(s: str) -> List[str]:
    from common import normalize_quote_code

    return [normalize_quote_code(c) for c in s.split(",")]


def bench_screener(codes: List[str], rounds: int) -> dict:
    """对每只股票跑 screener.analyze_code，测量耗时。"""
    from screener import analyze_code
    import argparse

    args = argparse.Namespace(
        min_amount=5000,
        min_cap=40,
        exclude_loss=False,
        no_regime=True,
        no_normalize=True,
    )
    durations = []
    for i in range(rounds):
        t0 = time.perf_counter()
        for code in codes:
            quote = {"code": code, "name": f"Stock-{code}"}
            analyze_code(quote, "balanced", args)
        t1 = time.perf_counter()
        durations.append(t1 - t0)
    return {
        "module": "screener.analyze_code",
        "codes": len(codes),
        "rounds": rounds,
        "total_seconds": round(sum(durations), 3),
        "avg_per_round": round(statistics.mean(durations), 3),
        "stdev": round(statistics.stdev(durations), 3) if len(durations) >= 2 else 0,
        "per_stock_ms": round(
            statistics.mean(durations) * 1000 / max(len(codes), 1), 2
        ),
    }


def bench_backtest(codes: List[str], rounds: int) -> dict:
    """对每只股票跑 backtest.run_backtest，测量耗时。"""
    from backtest import run_backtest

    durations = []
    for i in range(rounds):
        t0 = time.perf_counter()
        result = run_backtest("balanced", codes, top_n=3, days=20, rounds=2)
        t1 = time.perf_counter()
        durations.append(t1 - t0)
        if "error" in result:
            return {
                "module": "backtest.run_backtest",
                "error": result["error"],
                "durations": [round(d, 3) for d in durations],
            }
    return {
        "module": "backtest.run_backtest",
        "codes": len(codes),
        "rounds": rounds,
        "total_seconds": round(sum(durations), 3),
        "avg_per_round": round(statistics.mean(durations), 3),
        "stdev": round(statistics.stdev(durations), 3) if len(durations) >= 2 else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="性能压测")
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--codes", default="sh600519,sh600989,sh600000,sh600036,sh601318"
    )
    common.add_argument("--rounds", type=int, default=3)

    sub.add_parser("all", parents=[common], help="跑所有压测")
    sub.add_parser("screener", parents=[common], help="压测 screener")
    sub.add_parser("backtest", parents=[common], help="压测 backtest")
    sub.add_parser("save", parents=[common], help="压测并保存到 JSON")

    args = parser.parse_args()
    codes = _parse_codes(args.codes)

    if not args.command:
        parser.print_help()
        return

    results = []
    if args.command in ("screener", "all", "save"):
        results.append(("screener", bench_screener(codes, args.rounds)))
    if args.command in ("backtest", "all", "save"):
        results.append(("backtest", bench_backtest(codes, args.rounds)))

    for name, r in results:
        print(f"\n[{name}]")
        if "error" in r:
            print(f"  ERROR: {r['error']}")
        else:
            for k, v in r.items():
                print(f"  {k}: {v}")

    if args.command == "save":
        from common import DATA_DIR
        from common.version import __version__
        import json
        from datetime import datetime

        out_path = Path(DATA_DIR) / "perf_benchmarks.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "version": __version__,
            "timestamp": datetime.now().isoformat(timespec="microseconds"),
            "codes": codes,
            "rounds": args.rounds,
            "results": dict(results),
        }
        out_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✅ 基准已保存到 {out_path}")


if __name__ == "__main__":
    main()

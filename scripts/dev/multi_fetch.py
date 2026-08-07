#!/usr/bin/env python3
"""多代码批量数据获取（解决 finance/kline/technical 不支持批量的问题）。

Usage:
  python3 scripts/dev/multi_fetch.py finance sh600519 sh600036 sh000858 -j
  python3 scripts/dev/multi_fetch.py kline sh600519 sh600036 sh000858
  python3 scripts/dev/multi_fetch.py technical sh600519 sh600036 --quick

支持的子命令：finance / kline / technical / market_anchor / events
所有子命令的结果会合并到一个 JSON dict，key 为代码（统一大写）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_MAP = {
    "finance": "scripts/finance.py",
    "kline": "scripts/kline.py",
    "technical": "scripts/technical.py",
    "market_anchor": "scripts/market_anchor.py",
    "events": "scripts/events.py",
    "quote": "scripts/quote.py",
}


def run_one(script: str, code: str, extra_args: list[str]) -> tuple[str, object]:
    """执行单只票的脚本，捕获 JSON 输出。

    Returns:
        (code_upper, parsed_json_or_raw_text)
    """
    cmd = ["python3", script]
    if Path(script).name == "finance.py":
        cmd += ["-c", code]
    elif Path(script).name == "market_anchor.py":
        cmd += [code, "-j"]
    elif Path(script).name == "events.py":
        cmd += [code]
    elif Path(script).name == "technical.py":
        # 默认输出完整 JSON（含 MA/MACD/KDJ/RSI/缠论等所有数值字段），
        # 报告模板需要这些数值填占位（如 [X.XX]）。
        # 用 --quick 才会压缩成一行表格（仅适合终端快扫）。
        cmd += [code]
    elif Path(script).name == "quote.py":
        cmd += [code]
    else:
        # kline
        cmd += [code]
    cmd += list(extra_args)
    if "-j" not in cmd and "--json" not in cmd:
        cmd += ["-j"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return code.upper(), {"error": "timeout"}
    if result.returncode != 0:
        return code.upper(), {"error": result.stderr.strip()[:300]}
    out = result.stdout.strip()
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        return code.upper(), {"raw": out[:500]}
    # 解包：finance.py -c 顶层是 {code: data}，避免双层嵌套
    upper = code.upper()
    if isinstance(parsed, dict) and len(parsed) == 1 and upper in parsed:
        parsed = parsed[upper]
    return upper, parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="批量数据获取（合并 N 只票结果）")
    parser.add_argument("kind", choices=sorted(SCRIPT_MAP.keys()), help="数据种类")
    parser.add_argument("codes", nargs="+", help="股票代码列表")
    parser.add_argument("--no-json", action="store_true", help="不要 JSON 输出")
    args, extra = parser.parse_known_args()

    script = SCRIPT_MAP[args.kind]
    merged: dict[str, object] = {}
    for code in args.codes:
        upper, payload = run_one(script, code, extra)
        merged[upper] = payload
        if isinstance(payload, dict) and "error" in payload:
            print(f"[WARN] {upper}: {payload['error']}", file=sys.stderr)

    print(json.dumps(merged, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

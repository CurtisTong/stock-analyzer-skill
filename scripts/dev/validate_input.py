#!/usr/bin/env python3
"""校验/解析股票代码或日期输入（CLI 封装，调用 common.validators）。

给 unit / e2e / CLI 三层复用同一份基础逻辑：
- product code: `from common.validators import resolve_code, validate_date`
- e2e test: `python3 scripts/dev/validate_input.py code sh600519`
- 单元测试: 直接调函数

用法：
    python3 scripts/dev/validate_input.py code sh600519           # 标准化代码
    python3 scripts/dev/validate_input.py code 茅台               # 中文名 → 代码
    python3 scripts/dev/validate_input.py date 2026-07-20         # 校验日期
    python3 scripts/dev/validate_input.py range 2026-01-01 2026-12-31  # 校验区间

退出码：
    0 = 校验通过
    1 = 校验失败或参数错误
    2 = 子命令错误
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 确保 scripts/ 在 pythonpath（独立运行时）
_PKG_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _PKG_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from common.exceptions import ValidationError  # noqa: E402
from common.validators import (  # noqa: E402
    resolve_code,
    validate_date,
    validate_date_range,
)


def cmd_code(args: argparse.Namespace) -> int:
    """处理 'code' 子命令。"""
    try:
        result = resolve_code(args.input)
    except ValidationError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "ValidationError",
                    "field": e.field,
                    "value": e.value_str,
                    "reason": str(e),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"ok": True, "code": result}, ensure_ascii=False))
    return 0


def cmd_date(args: argparse.Namespace) -> int:
    """处理 'date' 子命令。"""
    ok = validate_date(args.input)
    print(json.dumps({"ok": ok, "date": args.input}, ensure_ascii=False))
    return 0 if ok else 1


def cmd_range(args: argparse.Namespace) -> int:
    """处理 'range' 子命令。"""
    try:
        validate_date_range(args.start, args.end)
    except ValidationError as e:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "ValidationError",
                    "field": e.field,
                    "reason": str(e),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "start": args.start,
                "end": args.end,
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_input",
        description="校验/解析股票代码或日期输入（CLI 封装 common.validators）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_code = sub.add_parser("code", help="标准化股票代码或解析中文名")
    p_code.add_argument("input", help="股票代码或中文名")
    p_code.set_defaults(func=cmd_code)

    p_date = sub.add_parser("date", help="校验 YYYY-MM-DD 日期格式与有效性")
    p_date.add_argument("input", help="日期字符串")
    p_date.set_defaults(func=cmd_date)

    p_range = sub.add_parser("range", help="校验 [start, end] 日期区间")
    p_range.add_argument("start")
    p_range.add_argument("end")
    p_range.set_defaults(func=cmd_range)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

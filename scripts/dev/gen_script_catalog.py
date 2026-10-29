#!/usr/bin/env python3
"""维护脚本目录 markdown（skills/_shared/references/script-catalog.md）中的脚本清单表。

只负责两个 marker 之间的**受管区域**（脚本数量行 + 清单表），区域外的
手写章节（多代码批量调用约定 / JSON 输出 / 开发辅助脚本）原样保留：

    <!-- BEGIN GENERATED: python3 scripts/dev/gen_script_catalog.py -->
    > N 个脚本，自动生成（`scripts/dev/gen_script_catalog.py`）。

    | 脚本 | 用途 | 常用参数 |
    |------|------|----------|
    ...
    <!-- END GENERATED -->

用途描述取自各脚本模块 docstring 首行；常用参数取自 argparse 声明
（使用 `common.cli_base.create_parser` 的脚本一律含 `-j`）。

用法：
  python3 scripts/dev/gen_script_catalog.py              # 刷新受管区域
  python3 scripts/dev/gen_script_catalog.py --check      # 校验受管区域是否最新（CI 用）
  python3 scripts/dev/gen_script_catalog.py --stdout     # 输出到 stdout，不写文件
"""

import argparse
import ast
import re
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PKG_ROOT / "scripts"
CATALOG_PATH = PKG_ROOT / "skills" / "_shared" / "references" / "script-catalog.md"

_BEGIN = "<!-- BEGIN GENERATED: python3 scripts/dev/gen_script_catalog.py -->"
_END = "<!-- END GENERATED -->"

# 不纳入 catalog 的脚本（辅助/内部脚本）
_EXCLUDED = {
    "__init__",
    "conftest",
}

# 常用参数列最多展示的 flag 数（完整列表见各脚本 -h 与 commands.json）
_MAX_FLAGS = 5

# 公共参数定义所在模块（create_parser 会自动加上这 4 个）
_CLI_BASE = SCRIPTS_DIR / "common" / "cli_base.py"


def _literal(node):
    """安全求值 AST 字面量（仅标量/标量列表），失败返回 None。"""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool, type(None))):
        return node.value
    if isinstance(node, ast.List):
        out = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, (int, float, str, bool)):
                out.append(elt.value)
            else:
                return None
        return out
    return None


def _param_from_call(node: ast.Call) -> dict | None:
    """从 add_argument(...) 调用提取参数契约。"""
    flags = []
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-"):
            flags.append(arg.value)
    if not flags:
        return None
    kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
    param = {
        "flags": flags,
        "required": bool(_literal(kwargs.get("required")) or False),
        "help": _literal(kwargs.get("help")) or "",
    }
    default = _literal(kwargs.get("default"))
    if default is not None:
        param["default"] = default
    choices = _literal(kwargs.get("choices"))
    if choices:
        param["choices"] = choices
    type_node = kwargs.get("type")
    if isinstance(type_node, ast.Name):
        param["type"] = type_node.id
    elif isinstance(type_node, ast.Attribute):
        param["type"] = type_node.attr
    elif isinstance(type_node, ast.Call) and isinstance(type_node.func, ast.Name):
        param["type"] = type_node.func.id
    action = _literal(kwargs.get("action"))
    if action:
        param["action"] = action
    return param


def _extract_params(files: list[Path]) -> list[dict]:
    """从一组 Python 文件里静态提取全部 argparse 参数。

    用 AST 而非正则：正则只能抓到 add_argument 的第一个位置参数，
    且会漏掉参数名/默认值/choices——那正是"命令契约"要提供的信息。
    """
    params: list[dict] = []
    seen_flags: set[str] = set()
    for filepath in files:
        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(filepath))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
                continue
            param = _param_from_call(node)
            if param is None:
                continue
            # 同一 flag 只保留首次出现
            key = param["flags"][0]
            if key in seen_flags:
                continue
            seen_flags.add(key)
            params.append(param)
    return params


def _candidate_files(filepath: Path) -> list[Path]:
    """脚本的参数可能定义在自身，也可能在同名子包（thin-wrapper 场景）。

    例：scripts/backtest.py 是 4 行 wrapper，真正的 argparse 在
    scripts/backtest/cli.py —— 只扫脚本自身会得到"零参数"的错误契约。
    """
    files = [filepath]
    pkg_dir = SCRIPTS_DIR / filepath.stem
    if pkg_dir.is_dir():
        files.extend(sorted(pkg_dir.glob("*.py")))
    return files


def _extract_argparse_hint(filepath: Path) -> str:
    """提取脚本声明的参数（短选项在前，最多 _MAX_FLAGS 个）。

    与命令契约同源（含 cli_base 公共参数），保证 md 表格与 JSON 一致。
    """
    params = _collect_contract_params(filepath)
    if not params:
        return ""
    declared: list[str] = []
    for p in params:
        for flag in p["flags"]:
            declared.append(flag)
    short = [f for f in declared if not f.startswith("--")]
    long = [f for f in declared if f.startswith("--")]
    unique: list[str] = []
    for flag in short + long:
        if flag not in unique:
            unique.append(flag)
    return "、".join(unique[:_MAX_FLAGS])


def _uses_cli_base(files: list[Path]) -> bool:
    """是否使用了 common.cli_base.create_parser（自带 -j/--json 等公共参数）。"""
    for filepath in files:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "create_parser(" in source:
            return True
    return False


def _is_cli_module(filepath: Path) -> bool:
    """判断脚本是否是 CLI 入口（声明了 argparse 参数）。

    scripts/ 下混有纯库模块（chan.py 兼容层、classifier.py 供 import 使用），
    它们没有命令行接口。契约里必须标注 cli=false，否则 LLM 会把
    "无参数"误解为"该命令不接受任何输入"。
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "add_argument":
                return True
            if isinstance(func, ast.Name) and func.id == "ArgumentParser":
                return True
        if isinstance(node, ast.Name) and node.id == "create_parser":
            return True
    return False


def _collect_contract_params(filepath: Path) -> list[dict]:
    """收集某脚本的完整参数契约（含公共参数）。"""
    files = _candidate_files(filepath)
    params = _extract_params(files)
    if _uses_cli_base(files):
        base_params = _extract_params([_CLI_BASE])
        existing = {p["flags"][0] for p in params}
        for p in base_params:
            if p["flags"][0] not in existing:
                params.append(p)
                existing.add(p["flags"][0])
    # 位置参数（无 "-" 前缀）不计入 flag 契约
    return [p for p in params if all(f.startswith("-") for f in p["flags"])]


def _extract_docstring(filepath: Path) -> str:
    """提取 Python 文件模块 docstring 的第一行（作为用途描述）。"""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
        docstring = ast.get_docstring(tree)
        if docstring:
            # 取第一段第一行
            first_line = docstring.strip().splitlines()[0].strip()
            # 去掉末尾句号
            return first_line.rstrip("。.")
        return ""
    except (SyntaxError, UnicodeDecodeError):
        return ""


def list_scripts() -> list[dict]:
    """扫描 scripts/ 目录，返回脚本信息列表。"""
    scripts = []
    for py in sorted(SCRIPTS_DIR.glob("*.py")):
        stem = py.stem
        if stem in _EXCLUDED or stem.startswith("_"):
            continue
        desc = _extract_docstring(py)
        flags = _extract_argparse_hint(py)
        scripts.append(
            {
                "name": stem,
                "path": f"scripts/{py.name}",
                "description": desc or "（无描述）",
                "flags": flags,
                "flags_list": [f for f in flags.split("、") if f],
            }
        )
    return scripts


# v1.24.0 机器可读命令契约：LLM 直接消费 command→params→schema
CONTRACTS_PATH = PKG_ROOT / "skills" / "_shared" / "references" / "commands.json"


def build_region() -> str:
    """生成受管区域内容（含 BEGIN/END marker）。"""
    scripts = list_scripts()
    lines = [
        _BEGIN,
        f"> {len(scripts)} 个脚本，自动生成（`scripts/dev/gen_script_catalog.py`）。",
        "",
        "| 脚本 | 用途 | 常用参数 |",
        "|------|------|----------|",
    ]
    for s in scripts:
        cmd = f"`python3 {s['path']}`"
        # 转义 markdown 管道符
        desc = s["description"].replace("|", "\\|")
        flags = (s["flags"] or "—").replace("|", "\\|")
        lines.append(f"| {cmd} | {desc} | {flags} |")
    lines.append(_END)
    return "\n".join(lines)


def splice(existing: str, region: str) -> str:
    """把受管区域替换进既有文档，区域外内容原样保留。"""
    begin = existing.find(_BEGIN)
    end = existing.find(_END)
    if begin == -1 or end == -1 or end < begin:
        raise SystemExit(f"❌ {CATALOG_PATH.name} 缺少受管区域 marker，无法安全替换：\n   {_BEGIN}\n   {_END}")
    return existing[:begin] + region + existing[end + len(_END) :]


def _build_contract_payload() -> dict:
    """构造命令契约 payload（与 _emit_commands_json 同源，供 --check-json 用）。"""
    import json
    from datetime import datetime, timezone

    scripts = list_scripts()
    commands = []
    for s in scripts:
        py = SCRIPTS_DIR / Path(s["path"]).name
        params = _collect_contract_params(py)
        all_flags: list[str] = []
        for p in params:
            for flag in p["flags"]:
                if flag not in all_flags:
                    all_flags.append(flag)
        commands.append(
            {
                "name": s["name"],
                "path": s["path"],
                "description": s["description"],
                # cli=false 表示该脚本是供 import 的库模块，没有命令行接口
                "cli": _is_cli_module(py),
                "flags": all_flags,
                "params": [
                    {
                        "flags": p["flags"],
                        "required": p.get("required", False),
                        **({"default": p["default"]} if "default" in p else {}),
                        **({"choices": p["choices"]} if "choices" in p else {}),
                        **({"type": p["type"]} if "type" in p else {}),
                        **({"action": p["action"]} if "action" in p else {}),
                        **({"help": p["help"]} if p.get("help") else {}),
                    }
                    for p in params
                ],
            }
        )
    return {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tool": "gen_script_catalog.py --emit-json",
            "count": len(commands),
            "version": "2",
            "catalog_marker": "BEGIN/END 受管区域一致",
            "param_source": "ast-static-analysis",
        },
        "commands": commands,
    }


def _check_contract() -> int:
    """校验 commands.json 是否与当前脚本声明一致（CI 守卫）。

    v1.24.0 复审发现：commands.json 不受任何 CI/pre-commit 校验，
    可无限期腐化而无人察觉。参数契约是 LLM 直接消费的产物，
    必须与源码同源。
    """
    import json

    if not CONTRACTS_PATH.exists():
        print(f"❌ {CONTRACTS_PATH.name} 不存在，请运行:")
        print("   python3 scripts/dev/gen_script_catalog.py --emit-json")
        return 1
    try:
        actual = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ {CONTRACTS_PATH.name} 解析失败: {e}")
        return 1

    expected = _build_contract_payload()
    # generated_at 每次生成都变，比对时忽略
    actual_meta = {k: v for k, v in (actual.get("_meta") or {}).items() if k != "generated_at"}
    expected_meta = {k: v for k, v in expected["_meta"].items() if k != "generated_at"}
    if actual_meta != expected_meta or actual.get("commands") != expected.get("commands"):
        print(f"❌ {CONTRACTS_PATH.name} 与脚本声明不一致，请运行:")
        print("   python3 scripts/dev/gen_script_catalog.py --emit-json")
        return 1
    print(f"✅ {CONTRACTS_PATH.name} 已最新（{expected['_meta']['count']} 个命令）")
    return 0


def main():
    parser = argparse.ArgumentParser(description="维护脚本目录的受管清单区域")
    parser.add_argument("--check", action="store_true", help="校验受管区域是否最新（CI 用）")
    parser.add_argument("--check-json", action="store_true", help="校验 commands.json 是否最新（CI 用）")
    parser.add_argument("--stdout", action="store_true", help="输出刷新后的全文到 stdout，不写文件")
    # v1.24.0：机器可读命令契约（OpenBB --list-commands/--describe 同构）
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="写 skills/_shared/references/commands.json（command→params 契约，LLM 直接消费）",
    )
    args = parser.parse_args()

    if args.check_json:
        raise SystemExit(_check_contract())

    existing = CATALOG_PATH.read_text(encoding="utf-8") if CATALOG_PATH.exists() else ""
    region = build_region()
    updated = splice(existing, region)

    if args.emit_json:
        import json
        from datetime import datetime, timezone

        payload = _build_contract_payload()
        CONTRACTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✅ 写命令契约 {payload['_meta']['count']} 个 -> {CONTRACTS_PATH.relative_to(PKG_ROOT)}")
        return

    if args.stdout:
        print(updated)
        return

    if args.check:
        if existing.strip() != updated.strip():
            print("❌ script-catalog.md 受管区域不是最新，请运行:")
            print("   python3 scripts/dev/gen_script_catalog.py")
            import difflib

            diff = difflib.unified_diff(
                existing.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile="当前",
                tofile="期望",
                n=1,
            )
            print("".join(diff), end="")
            raise SystemExit(1)
        print(f"✅ script-catalog.md 已最新（{len(list_scripts())} 个脚本）")
        return

    CATALOG_PATH.write_text(updated, encoding="utf-8")
    print(f"✅ 刷新 {len(list_scripts())} 个脚本目录 -> {CATALOG_PATH.relative_to(PKG_ROOT)}")


if __name__ == "__main__":
    main()

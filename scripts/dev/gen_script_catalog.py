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

# 常用参数列最多展示的 flag 数（完整列表见各脚本 -h）
_MAX_FLAGS = 5


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


def _extract_argparse_hint(filepath: Path) -> str:
    """提取脚本声明的参数（短选项在前，最多 _MAX_FLAGS 个）。

    使用 `common.cli_base.create_parser` 的脚本自带 -j/--sources/--no-cache/--debug，
    其中 -j 最常用，故显式补在最前。
    """
    try:
        source = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

    declared = re.findall(r'add_argument\(\s*["\'](-{1,2}[A-Za-z][\w-]*)["\']', source)
    if "create_parser(" in source:
        declared.insert(0, "-j")

    short = [f for f in declared if not f.startswith("--")]
    long = [f for f in declared if f.startswith("--")]

    unique: list[str] = []
    for flag in short + long:
        if flag not in unique:
            unique.append(flag)
    return "、".join(unique[:_MAX_FLAGS])


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
            }
        )
    return scripts


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


def main():
    parser = argparse.ArgumentParser(description="维护脚本目录的受管清单区域")
    parser.add_argument("--check", action="store_true", help="校验受管区域是否最新（CI 用）")
    parser.add_argument("--stdout", action="store_true", help="输出刷新后的全文到 stdout，不写文件")
    args = parser.parse_args()

    existing = CATALOG_PATH.read_text(encoding="utf-8") if CATALOG_PATH.exists() else ""
    region = build_region()
    updated = splice(existing, region)

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

#!/usr/bin/env python3
"""自动生成脚本目录 markdown（skills/_shared/references/script-catalog.md）。

扫描 scripts/*.py 的模块 docstring 第一行作为用途描述，
生成 markdown 表格。CI 测试验证 catalog 与 scripts/ 目录双向一致。

用法：
  python3 scripts/dev/gen_script_catalog.py              # 生成到 skills/_shared/references/
  python3 scripts/dev/gen_script_catalog.py --check       # 校验 catalog 是否最新（CI 用）
  python3 scripts/dev/gen_script_catalog.py --stdout       # 输出到 stdout
"""

import argparse
import ast
import re
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PKG_ROOT / "scripts"
CATALOG_PATH = PKG_ROOT / "skills" / "_shared" / "references" / "script-catalog.md"

# 不纳入 catalog 的脚本（辅助/内部脚本）
_EXCLUDED = {
    "__init__",
    "conftest",
}


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
    """提取 argparse 用法提示（从 add_argument 的 help 或 usage 字符串）。"""
    try:
        source = filepath.read_text(encoding="utf-8")
        # 找 description="..." 或 add_argument(..., help="...")
        # 简化：找 add_argument 中的 -j/-h 等 flag
        flags = re.findall(r'add_argument\(\s*["\'](-\w+)["\']', source)
        if flags:
            unique = sorted(set(flags))
            return "、".join(unique[:4])
    except (SyntaxError, UnicodeDecodeError):
        pass
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
            }
        )
    return scripts


def generate_catalog() -> str:
    """生成 catalog markdown 内容。"""
    scripts = list_scripts()
    lines = [
        "# 脚本目录",
        "",
        f"> {len(scripts)} 个脚本，自动生成（`scripts/dev/gen_script_catalog.py`）。",
        "> Claude Code 运行时工作目录即为项目根目录。",
        "",
        "| 脚本 | 用途 | 常用参数 |",
        "|------|------|----------|",
    ]
    for s in scripts:
        cmd = f"`python3 {s['path']}`"
        flags = s["flags"] or "—"
        # 转义 markdown 管道符
        desc = s["description"].replace("|", "\\|")
        flags = flags.replace("|", "\\|")
        lines.append(f"| {cmd} | {desc} | {flags} |")

    lines.append("")
    lines.append("## JSON 输出")
    lines.append("")
    lines.append("所有数据获取脚本支持 `-j` 输出 JSON，便于二次计算（排序、过滤、聚合）。")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成脚本目录 markdown")
    parser.add_argument("--check", action="store_true", help="校验 catalog 是否最新（CI 用）")
    parser.add_argument("--stdout", action="store_true", help="输出到 stdout 而非文件")
    args = parser.parse_args()

    content = generate_catalog()

    if args.stdout:
        print(content)
        return

    if args.check:
        existing = CATALOG_PATH.read_text(encoding="utf-8") if CATALOG_PATH.exists() else ""
        if existing.strip() != content.strip():
            print("❌ script-catalog.md 不是最新，请运行:")
            print("   python3 scripts/dev/gen_script_catalog.py")
            # 显示差异
            import difflib

            diff = difflib.unified_diff(
                existing.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile="当前",
                tofile="期望",
                n=1,
            )
            print("".join(diff), end="")
            raise SystemExit(1)
        print(f"✅ script-catalog.md 已最新（{len(list_scripts())} 个脚本）")
        return

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(content, encoding="utf-8")
    print(f"✅ 生成 {len(list_scripts())} 个脚本目录 -> {CATALOG_PATH.relative_to(PKG_ROOT)}")


if __name__ == "__main__":
    main()

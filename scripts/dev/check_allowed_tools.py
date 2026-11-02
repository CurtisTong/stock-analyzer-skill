#!/usr/bin/env python3
"""
自审计脚本：校验 SKILL.md 声明的命令 vs .claude/settings.json allowed-tools。

用途：
  - CI 接入后自动阻断 PR 引入 allowed-tools 不一致
  - 本地开发时快速检查路径/命令是否对齐

校验项：
  1. SKILL.md 中 `python3 scripts/xxx.py` 命令是否在 settings.json allow 列表
  2. SKILL.md 中 Read(...) 引用的路径是否实际存在
  3. settings.json allow 列表中无重复条目

用法：
  python3 scripts/dev/check_allowed_tools.py          # 打印报告
  python3 scripts/dev/check_allowed_tools.py --ci      # CI 模式：有遗漏时 exit 1
"""

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = PKG_ROOT / "skills"
SETTINGS_FILE = PKG_ROOT / ".claude" / "settings.json"

# 匹配 `python3 scripts/xxx.py [args...]` 内联命令（v1.31 修复：旧正则
# `[^\s`]+` 不允许反引号内出现空格，所有带参命令全部漏检——假阳性"全部通过"）
_CMD_INLINE_RE = re.compile(r"`(python3\s+scripts/[^`\n]+)`")
# 内联 python3 -c 命令（portfolio CRUD 的文档化执行路径）
_CMD_PYC_INLINE_RE = re.compile(r"`(python3\s+-c\s+[^`\n]+)`")
# 匹配代码块内的 python3 scripts/ 命令（去掉行首 $ 或 # 提示符）
_CMD_BLOCK_RE = re.compile(r"^\s*[$#]?\s*(python3\s+scripts/\S+)", re.MULTILINE)
# 代码块内的 python3 -c 命令（单行）
_CMD_PYC_BLOCK_RE = re.compile(r"^\s*[$#]?\s*(python3\s+-c\s+\S[^\n]*)$", re.MULTILINE)
# 匹配 Read(...) 路径
_READ_RE = re.compile(r"Read\(([^)]+)\)")
# 匹配 fenced code blocks
_CODE_BLOCK_RE = re.compile(r"```(?:bash|shell|text)?\n(.*?)```", re.DOTALL)
# frontmatter 块与 allowed-tools 行
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_ALLOWED_TOOLS_RE = re.compile(r"^allowed-tools:\s*(.+)$", re.MULTILINE)


def load_settings():
    """加载 .claude/settings.json，返回 allow 列表。"""
    if not SETTINGS_FILE.exists():
        print(f"⚠️  settings.json 不存在: {SETTINGS_FILE}")
        return []
    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return data.get("permissions", {}).get("allow", [])


def parse_skill_commands(skill_md_path):
    """从 SKILL.md 提取所有 python3 scripts/ 与 python3 -c 命令和 Read(...) 路径。"""
    text = skill_md_path.read_text(encoding="utf-8")

    # 1. 内联反引号命令（含参数）
    cmds = set(_CMD_INLINE_RE.findall(text))
    cmds.update(_CMD_PYC_INLINE_RE.findall(text))

    # 2. 代码块内的命令（fenced code blocks）
    for block_match in _CODE_BLOCK_RE.finditer(text):
        block = block_match.group(1)
        for cmd_match in _CMD_BLOCK_RE.finditer(block):
            cmds.add(cmd_match.group(1).strip())
        for cmd_match in _CMD_PYC_BLOCK_RE.finditer(block):
            cmds.add(cmd_match.group(1).strip())

    # 提取 Read(...) 路径（去重）
    reads = sorted(set(_READ_RE.findall(text)))

    return sorted(cmds), reads


def parse_frontmatter_patterns(skill_md_path):
    """提取 SKILL.md frontmatter allowed-tools 中的 Bash(...) 模式列表。

    skill 激活时工具层按 frontmatter 拦截——settings.json 全局放行但
    frontmatter 缺失的命令，在 skill 会话内依然会被拒（闭环校验用）。
    """
    text = skill_md_path.read_text(encoding="utf-8")
    fm = _FRONTMATTER_RE.search(text)
    if not fm:
        return []
    at = _ALLOWED_TOOLS_RE.search(fm.group(1))
    if not at:
        return []
    # 返回与 load_settings 相同契约（Bash(...) 包裹），match_command_to_allow 依赖它
    return [f"Bash({p})" for p in re.findall(r"Bash\(([^)]*)\)", at.group(1))]


def match_command_to_allow(cmd, allow_patterns):
    """检查命令是否匹配 allow 列表中的任何模式。

    allow 模式格式: 'Bash(python3 scripts/quote.py *)'
    命令格式:       'python3 scripts/quote.py sh600989'
    """
    for pattern in allow_patterns:
        # 提取 Bash(...) 内容
        bash_match = re.match(r"^Bash\((.+)\)$", pattern)
        if not bash_match:
            continue
        inner = bash_match.group(1)
        # 使用 fnmatch 做 glob 匹配（处理 * 和 ? 通配符）
        if fnmatch.fnmatch(cmd, inner):
            return True
        # 兼容：去掉尾部 * 和空格做前缀匹配
        if inner.endswith("*"):
            prefix = inner.rstrip(" *")
            if cmd.startswith(prefix):
                return True
    return False


def check_path_exists(path_str, skill_dir):
    """检查 Read(...) 路径是否实际存在。

    路径格式可能是：
      //<user>/...  (绝对路径)
      ../_shared/...     (相对路径)
    """
    if path_str.startswith("//"):
        # 双斜杠开头的绝对路径，去掉一个 /
        p = Path(path_str[1:])
    elif path_str.startswith("/"):
        p = Path(path_str)
    else:
        # ./ 开头的路径是项目根目录相对路径，不是 skill 目录相对路径
        p = PKG_ROOT / path_str

    # 通配符路径（如 skills/**）不做检查
    if "*" in str(p) or "**" in str(p):
        return True
    return p.exists()


def main():
    parser = argparse.ArgumentParser(description="SKILL.md vs settings.json 自审计")
    parser.add_argument("--ci", action="store_true", help="CI 模式：有遗漏时 exit 1")
    parser.add_argument(
        "--strict-frontmatter",
        action="store_true",
        help="frontmatter 缺授权也视为错误（默认仅警告）",
    )
    args = parser.parse_args()

    allow_patterns = load_settings()
    if not allow_patterns:
        print("❌ 无法加载 settings.json 或 allow 列表为空")
        if args.ci:
            sys.exit(1)
        return

    errors = []
    warnings = []
    ok_count = 0

    # 遍历所有 SKILL.md
    skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if not skill_files:
        print("⚠️  未找到任何 SKILL.md")
        return

    for skill_md in skill_files:
        skill_name = skill_md.parent.name
        cmds, reads = parse_skill_commands(skill_md)
        fm_patterns = parse_frontmatter_patterns(skill_md)

        for cmd in cmds:
            if not match_command_to_allow(cmd, allow_patterns):
                errors.append(f"  ❌ [{skill_name}] {cmd}")
                continue
            # settings 已授权：再查 skill 自身 frontmatter（skill 激活时按其拦截）
            if fm_patterns and not match_command_to_allow(cmd, fm_patterns):
                msg = f"  ⚠️  [{skill_name}] settings 已授权但 frontmatter 缺失: {cmd}"
                if args.strict_frontmatter:
                    errors.append(msg)
                else:
                    warnings.append(msg)
                continue
            ok_count += 1

        for path_str in reads:
            if not check_path_exists(path_str, skill_md.parent):
                # 只报 Read() 中的非通配符路径
                errors.append(f"  ❌ [{skill_name}] Read({path_str}) 路径不存在")

    # 检查 allow 列表重复
    seen = set()
    for p in allow_patterns:
        if p in seen:
            warnings.append(f"  ⚠️  重复条目: {p}")
        seen.add(p)

    # 输出报告
    print("=" * 60)
    print("SKILL.md vs settings.json 自审计报告")
    print("=" * 60)
    print(f"✅ 匹配通过: {ok_count} 条命令")
    print(f"❌ 发现问题: {len(errors)} 条")
    if warnings:
        print(f"⚠️  警告: {len(warnings)} 条")

    if errors:
        print("\n--- 缺失的 allowed-tools ---")
        for e in errors:
            print(e)

    if warnings:
        print("\n--- 警告 ---")
        for w in warnings:
            print(w)

    if errors:
        print("\n💡 修复方法: 在 .claude/settings.json 的 permissions.allow 中添加以上条目")
        if args.ci:
            sys.exit(1)
    else:
        print("\n✅ 全部通过，无遗漏。")


if __name__ == "__main__":
    main()

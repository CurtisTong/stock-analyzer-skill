#!/usr/bin/env python3
"""从 git commits 自动生成 CHANGELOG 片段。

基于 Conventional Commits 规范解析 commit messages，
输出 markdown 格式的 CHANGELOG 条目。

用法：
  python3 scripts/dev/gen_changelog.py              # 从上个 tag 到 HEAD
  python3 scripts/dev/gen_changelog.py --all         # 全部 commits
  python3 scripts/dev/gen_changelog.py --since 2026-06-01  # 指定起始日期
  python3 scripts/dev/gen_changelog.py --append      # 追加到 CHANGELOG.md

输出格式：
  ## [Unreleased]
  ### Added
  - feat(xxx): 描述
  ### Fixed
  - fix(xxx): 描述
"""

import argparse
import re
import subprocess
from datetime import datetime
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent

# Conventional Commits 类型 → CHANGELOG 分类
TYPE_MAP = {
    "feat": "Added",
    "fix": "Fixed",
    "docs": "Documentation",
    "refactor": "Changed",
    "perf": "Changed",
    "test": "Testing",
    "ci": "CI/CD",
    "chore": "Maintenance",
    "style": "Maintenance",
    "build": "Maintenance",
}

# 忽略的类型
IGNORE_TYPES = {"merge", "revert"}

# 噪声 commit 模式（subject 命中任一即跳过）
# 1. auto-update 自引用——CHANGELOG 自己产生的 commit 不应再次进入
# 2. data: 持仓操作流水——散户交易不应混入 CHANGELOG
NOISE_PATTERNS = [
    re.compile(r"auto-update\s+CHANGELOG\.md", re.IGNORECASE),
    re.compile(
        r"^data\s*:", re.IGNORECASE
    ),  # e.g. "data: 记录 2026-06-29 持仓交易操作"
]


def get_commits(since: str | None = None, all_commits: bool = False) -> list[dict]:
    """获取 git commits。"""
    cmd = ["git", "log", "--oneline", "--format=%H|%s|%an|%ad", "--date=short"]
    if not all_commits:
        # 获取上个 tag
        tag_result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            cwd=PKG_ROOT,
        )
        if tag_result.returncode == 0:
            last_tag = tag_result.stdout.strip()
            cmd.append(f"{last_tag}..HEAD")
        elif since:
            cmd.append(f"--since={since}")
    elif since:
        cmd.append(f"--since={since}")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PKG_ROOT)
    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append(
                {
                    "hash": parts[0],
                    "subject": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                }
            )
    return commits


def parse_commit(subject: str) -> dict | None:
    """解析 Conventional Commit 格式。

    格式: type(scope): description
    返回: {"type": "feat", "scope": "stock", "description": "描述"} 或 None
    """
    # 匹配 type(scope): description 或 type: description
    match = re.match(r"^(\w+)(?:\(([^)]+)\))?!?:\s*(.+)$", subject)
    if not match:
        return None

    commit_type = match.group(1).lower()
    scope = match.group(2) or ""
    description = match.group(3)

    if commit_type in IGNORE_TYPES:
        return None

    return {
        "type": commit_type,
        "scope": scope,
        "description": description,
    }


def generate_changelog(commits: list[dict]) -> str:
    """生成 CHANGELOG markdown。"""
    categories: dict[str, list[str]] = {}

    for commit in commits:
        # 过滤噪声 commit（auto-update 自引用 / data: 持仓流水）
        if any(p.search(commit["subject"]) for p in NOISE_PATTERNS):
            continue
        parsed = parse_commit(commit["subject"])
        if not parsed:
            # 非 Conventional Commit，归入 "Other"
            category = "Other"
            entry = f"- {commit['subject']}"
        else:
            category = TYPE_MAP.get(parsed["type"], "Other")
            scope = f"**{parsed['scope']}**: " if parsed["scope"] else ""
            entry = f"- {scope}{parsed['description']}"

        if category not in categories:
            categories[category] = []
        categories[category].append(entry)

    if not categories:
        return ""

    # 按固定顺序输出
    order = [
        "Added",
        "Fixed",
        "Changed",
        "Documentation",
        "Testing",
        "CI/CD",
        "Maintenance",
        "Other",
    ]
    lines = []
    for cat in order:
        if cat in categories:
            lines.append(f"### {cat}")
            lines.extend(categories[cat])
            lines.append("")

    return "\n".join(lines)


def append_to_changelog(content: str) -> None:
    """追加到 CHANGELOG.md。"""
    changelog_path = PKG_ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        print("❌ CHANGELOG.md 不存在")
        return

    existing = changelog_path.read_text(encoding="utf-8")
    date_str = datetime.now().strftime("%Y-%m-%d")
    header = f"\n## [Unreleased] - {date_str}\n\n"

    # 找到第一个 ## [xxx] 行，在其前面插入
    insert_pos = existing.find("\n## [")
    if insert_pos == -1:
        # 没有找到，在文件末尾追加
        new_content = existing + header + content
    else:
        new_content = existing[:insert_pos] + header + content + existing[insert_pos:]

    changelog_path.write_text(new_content, encoding="utf-8")
    print("✅ 已追加到 CHANGELOG.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="从 git commits 生成 CHANGELOG")
    parser.add_argument("--all", action="store_true", help="包含全部 commits")
    parser.add_argument("--since", help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--append", action="store_true", help="追加到 CHANGELOG.md")
    args = parser.parse_args()

    commits = get_commits(since=args.since, all_commits=args.all)
    if not commits:
        print("⚠️  无新 commits")
        return

    changelog = generate_changelog(commits)
    if not changelog:
        print("⚠️  无可解析的 Conventional Commits")
        return

    if args.append:
        append_to_changelog(changelog)
    else:
        print(changelog)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""CI 启动时校验 skill 数量在 CLAUDE.md / README.md / skills/ 实际目录数一致。

解决问题：skill 数量数字漂移问题——文档宣称的 skill 数量与
skills/ 实际目录数、README badge、CLAUDE.md 描述三者不一致，
外部读者无法判断项目当前真实状态。

校验目标（实际 skill 数 = 12）：

1. skills/ 实际目录数（排除 _shared 这种共享资源目录）
2. CLAUDE.md 第 9/96 行附近的"12 个 skill"声称
3. README.md 顶部 badge "skills-N" 与 #-N-个-skill-速查 锚点
4. README.md 内部"12 个 skill"声称一致性

设计原则（与 sync_skill_test_versions.py 对齐）：
- 单一来源：skills/ 目录扫描（事实）
- 自动校验：--check 模式仅做一致性检查，CI 中作为门禁
- 安全：仅修改 README badge（如果与实际不符）一处单行文本

用法：
  python3 scripts/dev/sync_skill_count.py              # 同步并写回（仅 README badge）
  python3 scripts/dev/sync_skill_count.py --check      # 仅检查（CI 用）
  python3 scripts/dev/sync_skill_count.py --dry-run    # 预览变更
"""

import argparse
import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = PKG_ROOT / "skills"
CLAUDE_MD = PKG_ROOT / "CLAUDE.md"
README_MD = PKG_ROOT / "README.md"


# 排除共享资源目录（不是独立 skill）
_NON_SKILL_DIRS = {"_shared"}


def actual_skill_count() -> int:
    """扫描 skills/ 下实际 skill 目录数（排除 _shared）。"""
    if not SKILLS_DIR.exists():
        return 0
    return sum(
        1 for d in SKILLS_DIR.iterdir() if d.is_dir() and d.name not in _NON_SKILL_DIRS
    )


def actual_skill_names() -> list[str]:
    """列出实际 skill 名（按字母排序）。"""
    if not SKILLS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name not in _NON_SKILL_DIRS
    )


def extract_skill_count_from_text(text: str, pattern: str) -> int | None:
    """从文本里提取 N 个 skill 的数字（找不到返回 None）。"""
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def check() -> int:
    """检查 skill 数量一致性。CI 中使用：失败时 exit 1。"""
    actual = actual_skill_count()
    names = actual_skill_names()
    errors = []

    claude_text = CLAUDE_MD.read_text(encoding="utf-8")
    readme_text = README_MD.read_text(encoding="utf-8")

    # 1. CLAUDE.md:9 "提供 12 个 skill" + CLAUDE.md:96 "Skill 索引表（12 个）"
    claude_claims = []
    for pattern, label in [
        (r"提供\s*(\d+)\s*个\s*skill", "CLAUDE.md:9 '提供 N 个 skill'"),
        (r"Skill\s*索引表[（(]\s*(\d+)\s*个", "CLAUDE.md:96 'Skill 索引表（N 个）'"),
    ]:
        n = extract_skill_count_from_text(claude_text, pattern)
        claude_claims.append((label, n))
        if n is None:
            errors.append(f"✗ CLAUDE.md 找不到声称: {label}")
        elif n != actual:
            errors.append(f"✗ {label} 声称 {n}，实际 {actual}（{', '.join(names)}）")

    # 2. README.md: "12 个 skill" 多处
    readme_claims = []
    for pattern, label in [
        (r"等\s*(\d+)\s*个斜杠命令", "README.md 主标语 '等 N 个斜杠命令'"),
        (r"(\d+)\s*个\s*[Ss]kill\s*速查", "README.md TOC 'N 个 Skill 速查'"),
        (r"(\d+)\s*个\s*skill\s*自动生效", "README.md 'N 个 skill 自动生效'"),
        (r"(\d+)\s*个\s*skill\s*完整衔接", "README.md 'N 个 skill 完整衔接'"),
        (r"##\s*📋\s*(\d+)\s*个\s*[Ss]kill", "README.md '## N 个 Skill 速查'"),
        (r"看到\s*(\d+)\s*个\s*skill", "README.md '看到 N 个 skill 即成功'"),
    ]:
        n = extract_skill_count_from_text(readme_text, pattern)
        readme_claims.append((label, n))
        if n is None:
            errors.append(f"✗ README.md 找不到声称: {label}")
        elif n != actual:
            errors.append(f"✗ {label} 声称 {n}，实际 {actual}")

    # 3. README.md 顶部 badge "skills-13" 必须等于实际 N
    badge_pattern = r"badge/skills-(\d+)-"
    m_badge = re.search(badge_pattern, readme_text)
    if not m_badge:
        errors.append("✗ README.md 顶部 badge 找不到 'badge/skills-N-N'")
    elif int(m_badge.group(1)) != actual:
        errors.append(
            f"✗ README.md 顶部 badge 写 skills-{m_badge.group(1)}，"
            f"应为 skills-{actual}"
        )

    # 4. README.md 锚点 #N-个-skill-速查 必须等于实际 N
    anchor_pattern = r"\(#-(\d+)-个-skill-速查\)"
    m_anchor = re.search(anchor_pattern, readme_text)
    if not m_anchor:
        errors.append("✗ README.md 锚点找不到 '(#-N-个-skill-速查)'")
    elif int(m_anchor.group(1)) != actual:
        errors.append(
            f"✗ README.md 锚点写 #-{m_anchor.group(1)}-个-skill-速查，"
            f"应为 #-{actual}-个-skill-速查"
        )

    # 输出
    print(f"实际 skill 数: {actual}（{', '.join(names)}）")
    for label, n in claude_claims + readme_claims:
        marker = "✓" if n == actual else "✗"
        print(f"  {marker} {label}: {n}")

    if errors:
        print("\n修复方法:", file=sys.stderr)
        print("  python3 scripts/dev/sync_skill_count.py", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("\n✓ skill 数量在所有声称位置一致")
    return 0


def sync() -> int:
    """同步：仅修复 README badge 与锚点（CLAUDE.md 与 README 段内文字按 --check 暴露人工处理）。"""
    actual = actual_skill_count()
    readme_text = README_MD.read_text(encoding="utf-8")
    new_text = readme_text

    new_text = re.sub(
        r"badge/skills-\d+-",
        f"badge/skills-{actual}-",
        new_text,
    )
    new_text = re.sub(
        r"\(#-\d+-个-skill-速查\)",
        f"(#-{actual}-个-skill-速查)",
        new_text,
    )

    if new_text == readme_text:
        print("README.md badge 与锚点已与实际一致，无需修改")
        return 0

    README_MD.write_text(new_text, encoding="utf-8")
    print(f"已更新 README.md: badge skills-{actual}, 锚点 #-{actual}-个-skill-速查")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="仅检查，不修改")
    ap.add_argument("--dry-run", action="store_true", help="预览变更")
    args = ap.parse_args()

    if args.check:
        return check()
    if args.dry_run:
        actual = actual_skill_count()
        readme_text = README_MD.read_text(encoding="utf-8")
        m_badge = re.search(r"badge/skills-(\d+)-", readme_text)
        m_anchor = re.search(r"\(#-(\d+)-个-skill-速查\)", readme_text)
        print("DRY-RUN: 将做以下变更（不写文件）")
        print(
            f"  README badge: skills-{m_badge.group(1) if m_badge else '?'} → skills-{actual}"
        )
        print(
            f"  README 锚点:  #-{m_anchor.group(1) if m_anchor else '?'}-个-skill-速查 → #-{actual}-个-skill-速查"
        )
        return 0
    return sync()


if __name__ == "__main__":
    sys.exit(main())

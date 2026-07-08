#!/usr/bin/env python3
"""列出所有可用 skill（动态发现）。

替代 help SKILL.md 中硬编码的 skill 列表。
"""

import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


def main() -> int:
    if not SKILLS_DIR.exists():
        print(f"❌ skills 目录不存在: {SKILLS_DIR}")
        return 1

    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        text = skill_md.read_text(encoding="utf-8")
        # 简易 frontmatter 解析
        name = skill_dir.name
        desc = ""
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                for line in text[3:end].splitlines():
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                        break

        skills.append((name, desc))

    print(f"==> 共 {len(skills)} 个 skill：\n")
    for name, desc in skills:
        marker = "🔧" if "已合并" in desc else "📦"
        print(f"  {marker} {name:20s} {desc[:60]}{'...' if len(desc) > 60 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

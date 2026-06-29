#!/usr/bin/env python3
"""CI 启动时同步 SKILL.md 版本到测试文件。

解决问题：开发者 bump 版本后忘记同步 test_skill_metadata.py 的
DEFAULT_VERSION / VERSION_OVERRIDES，导致 release workflow 的 test job 失败、
publish job 被阻塞。

设计原则：
- 单一来源：package.json 的 version 字段
- 自动派生：扫描所有 skills/*/SKILL.md 的 version 字段，构建 VERSION_OVERRIDES
- 安全：仅修改 test_skill_metadata.py 顶部两行常量，不改其他逻辑
- 可检：--check 模式仅做一致性检查，CI 中作为门禁

用法：
  python3 scripts/dev/sync_skill_test_versions.py              # 同步并写回
  python3 scripts/dev/sync_skill_test_versions.py --check      # 仅检查（CI 用）
  python3 scripts/dev/sync_skill_test_versions.py --dry-run    # 预览变更
"""

import argparse
import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_FILE = PKG_ROOT / "tests" / "test_skill_metadata.py"
SKILLS_DIR = PKG_ROOT / "skills"


def get_package_version() -> str:
    """从 package.json 读取主版本号。"""
    import json

    with open(PKG_ROOT / "package.json", encoding="utf-8") as f:
        return json.load(f)["version"]


def parse_skill_version(skill_md: Path) -> str | None:
    """从 SKILL.md frontmatter 提取 version 字段。"""
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    fm = m.group(1)
    m_ver = re.search(r"^version:\s*[\"']?([^\"'\s]+)[\"']?\s*$", fm, re.MULTILINE)
    return m_ver.group(1) if m_ver else None


def collect_overrides() -> dict[str, str]:
    """扫描所有 skills/*/SKILL.md，收集非主版本的 skill。"""
    overrides = {}
    pkg_ver = get_package_version()
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        ver = parse_skill_version(skill_md)
        if ver and ver != pkg_ver:
            overrides[skill_dir.name] = ver
    return overrides


def parse_existing_constants(test_text: str) -> tuple[str, dict[str, str]]:
    """提取 test_skill_metadata.py 中现有的 DEFAULT_VERSION 和 VERSION_OVERRIDES。"""
    m_default = re.search(
        r'^(DEFAULT_VERSION\s*=\s*[\'"])([^\'"]+)([\'"])',
        test_text,
        re.MULTILINE,
    )
    if not m_default:
        raise ValueError("找不到 DEFAULT_VERSION 常量")
    default = m_default.group(2)

    m_overrides = re.search(
        r"^VERSION_OVERRIDES\s*=\s*\{(.*?)\n\}",
        test_text,
        re.MULTILINE | re.DOTALL,
    )
    overrides: dict[str, str] = {}
    if m_overrides:
        for line in m_overrides.group(1).splitlines():
            m_item = re.match(
                r'\s*[\'"]?([\w-]+)[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', line
            )
            if m_item:
                overrides[m_item.group(1)] = m_item.group(2)
    return default, overrides


def build_new_constants(default: str, overrides: dict[str, str]) -> str:
    """生成新的常量块。"""
    if not overrides:
        return f'VERSION_OVERRIDES = {{\n    # 当前所有 skill 与主版本一致\n}}\nDEFAULT_VERSION = "{default}"\n'

    lines = ["VERSION_OVERRIDES = {"]
    for name in sorted(overrides):
        lines.append(f'    "{name}": "{overrides[name]}",')
    lines.append("}")
    lines.append(f'DEFAULT_VERSION = "{default}"')
    lines.append("")
    return "\n".join(lines)


def sync() -> int:
    """执行同步：读 package.json + SKILL.md → 写回 test_skill_metadata.py。"""
    pkg_ver = get_package_version()
    overrides = collect_overrides()
    test_text = TEST_FILE.read_text(encoding="utf-8")
    old_default, old_overrides = parse_existing_constants(test_text)

    new_block = build_new_constants(pkg_ver, overrides)
    pattern = re.compile(
        r"^VERSION_OVERRIDES\s*=\s*\{.*?^\}\nDEFAULT_VERSION\s*=\s*[\"'][^\"']+[\"']\n",
        re.MULTILINE | re.DOTALL,
    )
    if not pattern.search(test_text):
        print("ERROR: 在 test_skill_metadata.py 找不到完整的常量块", file=sys.stderr)
        return 1

    new_text = pattern.sub(new_block, test_text, count=1)
    if new_text == test_text:
        return 0

    TEST_FILE.write_text(new_text, encoding="utf-8")
    print(f"已更新 {TEST_FILE.relative_to(PKG_ROOT)}:")
    print(f"  DEFAULT_VERSION: {old_default} → {pkg_ver}")
    if old_overrides != overrides:
        print(f"  VERSION_OVERRIDES: {old_overrides} → {overrides}")
    return 0


def check() -> int:
    """检查一致性。CI 中使用：失败时 exit 1，阻塞后续 job。"""
    pkg_ver = get_package_version()
    overrides = collect_overrides()
    test_text = TEST_FILE.read_text(encoding="utf-8")
    cur_default, cur_overrides = parse_existing_constants(test_text)

    errors = []
    if cur_default != pkg_ver:
        errors.append(
            f"DEFAULT_VERSION 不一致: 测试文件={cur_default}, package.json={pkg_ver}"
        )
    if cur_overrides != overrides:
        errors.append(
            f"VERSION_OVERRIDES 不一致: 测试文件={cur_overrides}, 实际={overrides}"
        )

    if errors:
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print(
            "\n修复方法: python3 scripts/dev/sync_skill_test_versions.py",
            file=sys.stderr,
        )
        return 1
    print(f"✓ 一致（DEFAULT_VERSION={cur_default}，{len(cur_overrides)} 个 override）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="仅检查，不修改")
    ap.add_argument("--dry-run", action="store_true", help="预览变更")
    args = ap.parse_args()

    if args.check:
        return check()
    if args.dry_run:
        pkg_ver = get_package_version()
        overrides = collect_overrides()
        test_text = TEST_FILE.read_text(encoding="utf-8")
        cur_default, cur_overrides = parse_existing_constants(test_text)
        print("DRY-RUN: 将做以下变更（不写文件）")
        print(f"  DEFAULT_VERSION: {cur_default} → {pkg_ver}")
        print(f"  VERSION_OVERRIDES: {cur_overrides} → {overrides}")
        return 0
    return sync()


if __name__ == "__main__":
    sys.exit(main())

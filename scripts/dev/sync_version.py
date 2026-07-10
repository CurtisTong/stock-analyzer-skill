#!/usr/bin/env python3
"""版本同步工具 - 从 package.json 同步版本到所有相关文件。

单一版本源：package.json 的 version 字段
自动更新：SKILL.md、plugin.json、marketplace.json、README.md、测试文件、
  methodology.md、pyproject.toml、docs/product-architecture.md

P2-30: 重构为声明式结构--update 和 check 共享同一 VERSION_TARGETS 列表，
  每个条目定义 (label, file_spec, patterns)。
  file_spec 为单文件路径或 glob 模式（"skills/**/SKILL.md"）。
  patterns 为 [(regex, replacement_group_indices)] 列表，支持单文件多模式（如 README badge+footer）。

用法：
  python3 scripts/dev/sync_version.py              # 同步到 package.json 版本
  python3 scripts/dev/sync_version.py --version 1.10.0  # 同步到指定版本
  python3 scripts/dev/sync_version.py --check      # 仅检查，不修改
  python3 scripts/dev/sync_version.py --dry-run    # 预览变更
"""

import argparse
import json
import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent


def get_package_version() -> str:
    """从 package.json 获取版本号。"""
    pkg_path = PKG_ROOT / "package.json"
    with open(pkg_path, encoding="utf-8") as f:
        return json.load(f)["version"]


# ═══════════════════════════════════════════════════════════════
# P2-30: 声明式版本同步目标
# 每个条目: (label, file_spec, patterns)
#   - label: 显示名
#   - file_spec: 相对路径（单文件）或 glob 模式（多文件）
#   - patterns: [(regex, replacement)] 列表，replacement 用 {version} 占位符
# ═══════════════════════════════════════════════════════════════

# 版本号正则片段（复用）
_VER = r"\d+\.\d+\.\d+"

VERSION_TARGETS: list[tuple[str, str, list[tuple[str, str]]]] = [
    # JSON 文件（plugin.json + marketplace.json）
    (
        "plugin.json",
        ".claude-plugin/plugin.json",
        [
            (
                r'(?m)^(?P<prefix>\s*"version"\s*:\s*")[^"]+(?P<suffix>")',
                r"{prefix}{version}{suffix}",
            )
        ],
    ),
    (
        "marketplace.json",
        ".claude-plugin/marketplace.json",
        [
            (
                r'(?m)^(?P<prefix>\s*"version"\s*:\s*")[^"]+(?P<suffix>")',
                r"{prefix}{version}{suffix}",
            )
        ],
    ),
    # SKILL.md frontmatter（glob 多文件）
    (
        "skills/*/SKILL.md",
        "skills/**/SKILL.md",
        [(r"(?m)^(?P<prefix>version:\s*)" + _VER, r"{prefix}{version}")],
    ),
    # methodology.md frontmatter
    (
        "methodology.md",
        "methodology.md",
        [(r"(?m)^(?P<prefix>version:\s*)" + _VER, r"{prefix}{version}")],
    ),
    # pyproject.toml
    (
        "pyproject.toml",
        "pyproject.toml",
        [
            (
                r'(?m)^(?P<prefix>version\s*=\s*")[^"]+(?P<suffix>")',
                r"{prefix}{version}{suffix}",
            )
        ],
    ),
    # docs/product-architecture.md header
    (
        "docs/product-architecture.md",
        "docs/product-architecture.md",
        [
            (
                r"(?P<prefix>版本：v)"
                + _VER
                + r"(?P<suffix>\s*\|\s*更新日期：\s*\d{4}-\d{2}-\d{2})",
                r"{prefix}{version}{suffix}",
            )
        ],
    ),
    # README.md（badge + footer 双模式）
    (
        "README.md",
        "README.md",
        [
            (
                r"(?P<prefix>version-)" + _VER + r"(?P<suffix>-)",
                r"{prefix}{version}{suffix}",
            ),
            (
                r"(?P<prefix>\*\*v)" + _VER + r"(?P<suffix>\*\*)",
                r"{prefix}{version}{suffix}",
            ),
        ],
    ),
    # 测试文件
    (
        "tests/test_skill_metadata.py",
        "tests/test_skill_metadata.py",
        [
            (
                r'(?P<prefix>DEFAULT_VERSION\s*=\s*")[^"]+(?P<suffix>")',
                r"{prefix}{version}{suffix}",
            )
        ],
    ),
]


def _resolve_files(file_spec: str) -> list[Path]:
    """解析 file_spec 为文件列表（支持 glob）。"""
    path = PKG_ROOT / file_spec
    if "**" in file_spec or "*" in file_spec:
        return sorted(PKG_ROOT.glob(file_spec))
    return [path] if path.exists() else []


def _apply_patterns(
    content: str, patterns: list[tuple[str, str]], version: str
) -> tuple[str, list[str]]:
    """对内容应用所有 patterns，返回 (新内容, 匹配到的版本列表)。"""
    found_versions = []
    for regex, replacement in patterns:
        # 先提取当前版本（用于 check）
        for m in re.finditer(regex, content):
            # 从 match 中提取版本号（取第一个非 named-group 的数字段）
            matched_text = m.group(0)
            ver_match = re.search(_VER, matched_text)
            if ver_match:
                found_versions.append(ver_match.group(0))
        # 替换
        repl = replacement.replace("{version}", version)
        content = re.sub(regex, repl, content)
    return content, found_versions


def update_version(
    label: str, file_spec: str, patterns: list[tuple[str, str]], version: str
) -> list[Path]:
    """更新单个目标的版本号，返回被修改的文件列表。"""
    updated = []
    for path in _resolve_files(file_spec):
        content = path.read_text(encoding="utf-8")
        new_content, _ = _apply_patterns(content, patterns, version)
        if new_content != content:
            path.write_text(new_content, encoding="utf-8")
            updated.append(path)
    return updated


def check_version(
    label: str, file_spec: str, patterns: list[tuple[str, str]], version: str
) -> tuple[list[str], list[str], list[str]]:
    """检查单个目标的版本一致性，返回 (match, mismatch, missing) 列表。"""
    match, mismatch, missing = [], [], []
    files = _resolve_files(file_spec)
    if not files:
        missing.append(label)
        return match, mismatch, missing
    for path in files:
        content = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(PKG_ROOT))
        _, found_versions = _apply_patterns(content, patterns, version)
        if not found_versions:
            missing.append(rel)
        else:
            for v in found_versions:
                if v == version:
                    match.append(rel if len(files) > 1 else label)
                else:
                    mismatch.append(
                        f"{rel}: {v}" if len(files) > 1 else f"{label}: {v}"
                    )
    return match, mismatch, missing


def update_all(version: str, dry_run: bool = False) -> list[str]:
    """更新所有目标版本，返回变更摘要列表。"""
    summaries = []
    for label, file_spec, patterns in VERSION_TARGETS:
        if dry_run:
            # dry-run 模式：检查是否需要更新
            match, mismatch, missing = check_version(
                label, file_spec, patterns, version
            )
            if mismatch:
                summaries.append(f"   📝 {label} (需更新)")
            elif missing:
                summaries.append(f"   ⚠️  {label} (版本字段缺失)")
            else:
                summaries.append(f"   ⏭️  {label} (已是最新)")
        else:
            updated = update_version(label, file_spec, patterns, version)
            if updated:
                for p in updated:
                    summaries.append(f"   ✅ {p.relative_to(PKG_ROOT)}")
            else:
                summaries.append(f"   ⏭️  {label} (已是最新)")
    return summaries


def check_versions(target_version: str) -> dict[str, list[str]]:
    """检查所有文件的版本一致性。"""
    result: dict[str, list[str]] = {"match": [], "mismatch": [], "missing": []}

    # 检查 package.json（源）
    pkg_version = get_package_version()
    if pkg_version == target_version:
        result["match"].append("package.json")
    else:
        result["mismatch"].append(f"package.json: {pkg_version}")

    # 检查所有声明式目标
    for label, file_spec, patterns in VERSION_TARGETS:
        match, mismatch, missing = check_version(
            label, file_spec, patterns, target_version
        )
        result["match"].extend(match)
        result["mismatch"].extend(mismatch)
        result["missing"].extend(missing)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="版本同步工具")
    parser.add_argument("--version", help="指定目标版本（默认从 package.json 读取）")
    parser.add_argument("--check", action="store_true", help="仅检查，不修改")
    parser.add_argument("--dry-run", action="store_true", help="预览变更")
    args = parser.parse_args()

    target_version = args.version or get_package_version()
    print(f"📦 目标版本: {target_version}")

    if args.check:
        print("\n🔍 版本一致性检查:")
        result = check_versions(target_version)

        if result["match"]:
            print(f"\n✅ 一致 ({len(result['match'])} 个):")
            for f in result["match"]:
                print(f"   {f}")

        if result["mismatch"]:
            print(f"\n❌ 不一致 ({len(result['mismatch'])} 个):")
            for f in result["mismatch"]:
                print(f"   {f}")

        if result["missing"]:
            print(f"\n⚠️  缺失 ({len(result['missing'])} 个):")
            for f in result["missing"]:
                print(f"   {f}")

        sys.exit(1 if result["mismatch"] else 0)

    if args.dry_run:
        print("\n🔍 预览变更:")
    else:
        print("\n🔄 同步版本:")

    summaries = update_all(target_version, dry_run=args.dry_run)
    for s in summaries:
        print(s)

    print(f"\n✅ 版本同步完成: {target_version}")


if __name__ == "__main__":
    main()

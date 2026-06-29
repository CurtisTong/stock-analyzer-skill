#!/usr/bin/env python3
"""版本同步工具 - 从 package.json 同步版本到所有相关文件。

单一版本源：package.json 的 version 字段
自动更新：SKILL.md、plugin.json、marketplace.json、README.md、测试文件、
  methodology.md、pyproject.toml、docs/product-architecture.md

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


def update_json_version(file_path: Path, version: str) -> bool:
    """更新 JSON 文件中的 version 字段。"""
    if not file_path.exists():
        return False

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # 使用正则替换，保持格式
    new_content = re.sub(
        r'("version"\s*:\s*")[^"]+(")',
        rf"\g<1>{version}\2",
        content,
    )

    if new_content != content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False


def update_skill_versions(version: str) -> list[Path]:
    """更新所有 SKILL.md 的 version 字段。"""
    updated = []
    skills_dir = PKG_ROOT / "skills"

    for skill_md in skills_dir.rglob("SKILL.md"):
        content = skill_md.read_text(encoding="utf-8")
        # 匹配 YAML frontmatter 中的 version: x.x.x
        new_content = re.sub(
            r"^(version:\s*)\d+\.\d+\.\d+",
            rf"\g<1>{version}",
            content,
            flags=re.MULTILINE,
        )
        if new_content != content:
            skill_md.write_text(new_content, encoding="utf-8")
            updated.append(skill_md)
    return updated


def update_methodology_version(version: str) -> bool:
    """更新 methodology.md frontmatter 中的 version 字段。"""
    path = PKG_ROOT / "methodology.md"
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(version:\s*)\d+\.\d+\.\d+",
        rf"\g<1>{version}",
        content,
        flags=re.MULTILINE,
    )
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return True
    return False


def update_pyproject_version(version: str) -> bool:
    """更新 pyproject.toml [project] 段中的 version 字段。"""
    path = PKG_ROOT / "pyproject.toml"
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    new_content = re.sub(
        r'^(version\s*=\s*")[^"]+(")',
        rf"\g<1>{version}\2",
        content,
        flags=re.MULTILINE,
    )
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return True
    return False


def update_doc_header_version(version: str) -> bool:
    """更新 docs/product-architecture.md 顶部的版本声明行。"""
    path = PKG_ROOT / "docs" / "product-architecture.md"
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"(版本：v)\d+\.\d+\.\d+(\s*\|\s*更新日期：\s*\d{4}-\d{2}-\d{2})",
        rf"\g<1>{version}\2",
        content,
    )
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        return True
    return False


def update_readme_version(version: str) -> bool:
    """更新 README.md 中的版本号。"""
    readme_path = PKG_ROOT / "README.md"
    if not readme_path.exists():
        return False

    content = readme_path.read_text(encoding="utf-8")
    original = content

    # 更新 badge: version-X.Y.Z
    content = re.sub(
        r"(version-)\d+\.\d+\.\d+(-)",
        rf"\g<1>{version}\2",
        content,
    )

    # 更新 footer: **vX.Y.Z**
    content = re.sub(
        r"(\*\*v)\d+\.\d+\.\d+(\*\*)",
        rf"\g<1>{version}\2",
        content,
    )

    if content != original:
        readme_path.write_text(content, encoding="utf-8")
        return True
    return False


def update_test_version(version: str) -> bool:
    """更新测试文件中的版本号。"""
    test_path = PKG_ROOT / "tests" / "test_skill_metadata.py"
    if not test_path.exists():
        return False

    content = test_path.read_text(encoding="utf-8")
    # 匹配 DEFAULT_VERSION = "x.x.x"
    new_content = re.sub(
        r'(DEFAULT_VERSION\s*=\s*")[^"]+(")',
        rf"\g<1>{version}\2",
        content,
    )

    if new_content != content:
        test_path.write_text(new_content, encoding="utf-8")
        return True
    return False


def check_versions(target_version: str) -> dict[str, list[str]]:
    """检查所有文件的版本一致性。"""
    result = {"match": [], "mismatch": [], "missing": []}

    # 检查 package.json
    pkg_version = get_package_version()
    if pkg_version == target_version:
        result["match"].append("package.json")
    else:
        result["mismatch"].append(f"package.json: {pkg_version}")

    # 检查 JSON 文件
    for json_file in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"]:
        path = PKG_ROOT / json_file
        if path.exists():
            content = path.read_text(encoding="utf-8")
            versions = re.findall(r'"version"\s*:\s*"([^"]+)"', content)
            for v in versions:
                if v == target_version:
                    result["match"].append(f"{json_file}")
                else:
                    result["mismatch"].append(f"{json_file}: {v}")

    # 检查 SKILL.md
    skills_dir = PKG_ROOT / "skills"
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        rel_path = skill_md.relative_to(PKG_ROOT)
        content = skill_md.read_text(encoding="utf-8")
        match = re.search(r"^version:\s*(\d+\.\d+\.\d+)", content, re.MULTILINE)
        if match:
            v = match.group(1)
            if v == target_version:
                result["match"].append(str(rel_path))
            else:
                result["mismatch"].append(f"{rel_path}: {v}")
        else:
            result["missing"].append(str(rel_path))

    # 检查 README.md
    readme_path = PKG_ROOT / "README.md"
    if readme_path.exists():
        content = readme_path.read_text(encoding="utf-8")
        badge_match = re.search(r"version-(\d+\.\d+\.\d+)", content)
        footer_match = re.search(r"\*\*v(\d+\.\d+\.\d+)\*\*", content)
        for match, label in [(badge_match, "badge"), (footer_match, "footer")]:
            if match:
                v = match.group(1)
                if v == target_version:
                    result["match"].append(f"README.md ({label})")
                else:
                    result["mismatch"].append(f"README.md ({label}): {v}")

    # 检查测试文件
    test_path = PKG_ROOT / "tests" / "test_skill_metadata.py"
    if test_path.exists():
        content = test_path.read_text(encoding="utf-8")
        match = re.search(r'DEFAULT_VERSION\s*=\s*"([^"]+)"', content)
        if match:
            v = match.group(1)
            if v == target_version:
                result["match"].append("tests/test_skill_metadata.py")
            else:
                result["mismatch"].append(f"tests/test_skill_metadata.py: {v}")

    # 检查 methodology.md
    methodology_path = PKG_ROOT / "methodology.md"
    if methodology_path.exists():
        content = methodology_path.read_text(encoding="utf-8")
        match = re.search(r"^version:\s*(\d+\.\d+\.\d+)", content, re.MULTILINE)
        if match:
            v = match.group(1)
            label = "methodology.md"
            if v == target_version:
                result["match"].append(label)
            else:
                result["mismatch"].append(f"{label}: {v}")
        else:
            result["missing"].append("methodology.md")

    # 检查 pyproject.toml
    pyproject_path = PKG_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        content = pyproject_path.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            v = match.group(1)
            label = "pyproject.toml"
            if v == target_version:
                result["match"].append(label)
            else:
                result["mismatch"].append(f"{label}: {v}")
        else:
            result["missing"].append("pyproject.toml")

    # 检查 docs/product-architecture.md
    doc_path = PKG_ROOT / "docs" / "product-architecture.md"
    if doc_path.exists():
        content = doc_path.read_text(encoding="utf-8")
        match = re.search(r"版本：v(\d+\.\d+\.\d+)", content)
        if match:
            v = match.group(1)
            label = "docs/product-architecture.md"
            if v == target_version:
                result["match"].append(label)
            else:
                result["mismatch"].append(f"{label}: {v}")
        else:
            result["missing"].append(label)

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

    # 更新 JSON 文件
    for json_file in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"]:
        path = PKG_ROOT / json_file
        if update_json_version(path, target_version):
            print(f"   ✅ {json_file}")
        else:
            print(f"   ⏭️  {json_file} (已是最新)")

    # 更新 SKILL.md
    updated_skills = update_skill_versions(target_version)
    if updated_skills:
        for skill in updated_skills:
            print(f"   ✅ {skill.relative_to(PKG_ROOT)}")
    else:
        print("   ⏭️  skills/*/SKILL.md (已是最新)")

    # 更新 README.md
    if update_readme_version(target_version):
        print("   ✅ README.md")
    else:
        print("   ⏭️  README.md (已是最新)")

    # 更新测试文件
    if update_test_version(target_version):
        print("   ✅ tests/test_skill_metadata.py")
    else:
        print("   ⏭️  tests/test_skill_metadata.py (已是最新)")

    # 更新 methodology.md
    if update_methodology_version(target_version):
        print("   ✅ methodology.md")
    else:
        print("   ⏭️  methodology.md (已是最新)")

    # 更新 pyproject.toml
    if update_pyproject_version(target_version):
        print("   ✅ pyproject.toml")
    else:
        print("   ⏭️  pyproject.toml (已是最新)")

    # 更新 docs/product-architecture.md
    if update_doc_header_version(target_version):
        print("   ✅ docs/product-architecture.md")
    else:
        print("   ⏭️  docs/product-architecture.md (已是最新)")

    print(f"\n✅ 版本同步完成: {target_version}")


if __name__ == "__main__":
    main()

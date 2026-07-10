"""测试 scripts/dev/sync_version.py：版本号同步工具。

策略：直接调用函数，验证 VERSION_TARGETS 声明式语法、_apply_patterns
正反向、check_versions 一致性。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dev import sync_version

# ═══════════════════════════════════════════════════════════════
# get_package_version：package.json 读取
# ═══════════════════════════════════════════════════════════════


class TestGetPackageVersion:
    def test_returns_semver(self):
        """返回字符串且符合 X.Y.Z 格式。"""
        v = sync_version.get_package_version()
        assert isinstance(v, str)
        parts = v.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ═══════════════════════════════════════════════════════════════
# _apply_patterns：单个文件的正则替换
# ═══════════════════════════════════════════════════════════════


class TestApplyPatterns:
    def test_replaces_version(self):
        """单 pattern 替换：replacement 中的 {version} 被填充。"""
        content = "version: 1.0.0\n"
        # 使用 \g<prefix> 反向引用（re.sub 原生支持）+ {version} 占位符
        patterns = [
            (r"(?m)^(?P<prefix>version:\s*)\d+\.\d+\.\d+", r"\g<prefix>{version}")
        ]
        new, found = sync_version._apply_patterns(content, patterns, "2.0.0")
        assert "version: 2.0.0" in new
        assert "{version}" not in new
        assert found == ["1.0.0"]

    def test_multi_patterns(self):
        """README 双 pattern（badge + footer）同时替换。

        使用 \\g<name> 反向引用 + {version} 混合占位符。
        """
        content = "version-1.0.0-blue\n\n**v1.0.0**\n"
        patterns = [
            (
                r"(?P<prefix>version-)\d+\.\d+\.\d+(?P<suffix>-)",
                r"\g<prefix>{version}\g<suffix>",
            ),
            (
                r"(?P<prefix>\*\*v)\d+\.\d+\.\d+(?P<suffix>\*\*)",
                r"\g<prefix>{version}\g<suffix>",
            ),
        ]
        new, found = sync_version._apply_patterns(content, patterns, "9.9.9")
        assert "version-9.9.9-blue" in new
        assert "**v9.9.9**" in new
        assert "{version}" not in new
        assert "\\g" not in new
        # 找到的版本列表中含 1.0.0（出现 2 次）
        assert "1.0.0" in found
        assert len(found) == 2

    def test_no_match_returns_original(self):
        """无匹配时返回原内容且 found 为空。"""
        content = "no version here\n"
        patterns = [(r"(?P<prefix>v)\d+(?P<suffix>$)", r"{prefix}{version}{suffix}")]
        new, found = sync_version._apply_patterns(content, patterns, "1.0.0")
        assert new == content
        assert found == []


# ═══════════════════════════════════════════════════════════════
# _resolve_files：glob 与单文件
# ═══════════════════════════════════════════════════════════════


class TestResolveFiles:
    def test_single_file(self):
        """单文件路径返回单元素列表。"""
        files = sync_version._resolve_files("pyproject.toml")
        assert len(files) == 1
        assert files[0].name == "pyproject.toml"

    def test_glob_multi_files(self):
        """glob 模式返回多个 SKILL.md。"""
        files = sync_version._resolve_files("skills/**/SKILL.md")
        assert len(files) > 1
        assert all(f.suffix == ".md" for f in files)

    def test_missing_single_returns_empty(self):
        """不存在的单文件返回空列表（不抛异常）。"""
        files = sync_version._resolve_files("nonexistent_xyz.toml")
        assert files == []


# ═══════════════════════════════════════════════════════════════
# check_versions：一致性检查
# ═══════════════════════════════════════════════════════════════


class TestCheckVersions:
    def test_consistent_returns_match_only(self):
        """所有文件一致时无 mismatch。"""
        result = sync_version.check_versions("1.15.0")
        # match 必有 package.json + 多数目标
        assert "package.json" in result["match"]
        assert len(result["mismatch"]) == 0


# ═══════════════════════════════════════════════════════════════
# update_version + update_all：dry_run 模式
# ═══════════════════════════════════════════════════════════════


class TestUpdateAll:
    def test_dry_run_no_changes(self):
        """dry_run 模式不修改任何文件（只生成摘要）。"""
        before = (PROJECT_ROOT / "pyproject.toml").read_text()
        summaries = sync_version.update_all("1.15.0", dry_run=True)
        after = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert before == after
        # dry_run 应当产生每条 target 的摘要
        assert len(summaries) >= len(sync_version.VERSION_TARGETS)


# ═══════════════════════════════════════════════════════════════
# main：CLI 入口（不实际写文件）
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_check_mode_exits_clean(self, capsys, monkeypatch):
        """--check 模式下当前版本一致应当 exit 0。"""
        monkeypatch.setattr(sys, "argv", ["sync_version.py", "--check"])
        with pytest.raises(SystemExit) as exc_info:
            sync_version.main()
        # 一致时退出码 0
        assert exc_info.value.code == 0

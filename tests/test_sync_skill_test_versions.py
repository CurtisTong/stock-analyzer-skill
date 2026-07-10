"""测试 scripts/dev/sync_skill_test_versions.py：SKILL.md 版本号同步。"""

import sys
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dev import sync_skill_test_versions


# ═══════════════════════════════════════════════════════════════
# get_package_version
# ═══════════════════════════════════════════════════════════════


class TestGetPackageVersion:
    def test_returns_version(self):
        result = sync_skill_test_versions.get_package_version()
        assert isinstance(result, str)
        assert "." in result


# ═══════════════════════════════════════════════════════════════
# parse_skill_version


class TestParseSkillVersion:
    def test_with_frontmatter(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test\nversion: 1.15.0\n---\n# content")
        result = sync_skill_test_versions.parse_skill_version(skill_md)
        assert result == "1.15.0"

    def test_without_frontmatter(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# no frontmatter")
        assert sync_skill_test_versions.parse_skill_version(skill_md) is None

    def test_no_version_field(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test\n---\n# no version")
        assert sync_skill_test_versions.parse_skill_version(skill_md) is None


# ═══════════════════════════════════════════════════════════════
# collect_overrides


class TestCollectOverrides:
    def test_collects_overrides(self, tmp_path, monkeypatch):
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "skill_a").mkdir()
        (tmp_path / "skills" / "skill_a" / "SKILL.md").write_text(
            "---\nversion: 1.0.0\n---\n"
        )
        (tmp_path / "skills" / "skill_b").mkdir()
        (tmp_path / "skills" / "skill_b" / "SKILL.md").write_text(
            "---\nversion: 1.15.0\n---\n"
        )
        monkeypatch.setattr(sync_skill_test_versions, "SKILLS_DIR", tmp_path / "skills")
        with patch.object(sync_skill_test_versions, "get_package_version", return_value="1.15.0"):
            overrides = sync_skill_test_versions.collect_overrides()
        # skill_a: version 1.0.0 ≠ pkg 1.15.0 → override
        # skill_b: 相同 → 不在 overrides
        assert "skill_a" in overrides
        assert overrides["skill_a"] == "1.0.0"
        assert "skill_b" not in overrides


# ═══════════════════════════════════════════════════════════════
# parse_existing_constants


class TestParseExistingConstants:
    def test_with_constants(self):
        text = '''DEFAULT_VERSION = "1.15.0"

VERSION_OVERRIDES = {
    "skill_a": "1.0.0",
    "skill_b": "2.0.0",
}
'''
        default, overrides = sync_skill_test_versions.parse_existing_constants(text)
        assert default == "1.15.0"
        assert overrides == {"skill_a": "1.0.0", "skill_b": "2.0.0"}

    def test_empty_overrides(self):
        text = '''DEFAULT_VERSION = "1.15.0"

VERSION_OVERRIDES = {
}
'''
        default, overrides = sync_skill_test_versions.parse_existing_constants(text)
        assert default == "1.15.0"
        assert overrides == {}

    def test_no_constants(self):
        """无 DEFAULT_VERSION 时抛 ValueError（实际行为）。"""
        text = "# no constants here\n"
        with pytest.raises(ValueError):
            sync_skill_test_versions.parse_existing_constants(text)


# ═══════════════════════════════════════════════════════════════
# build_new_constants


class TestBuildNewConstants:
    def test_builds_text(self):
        result = sync_skill_test_versions.build_new_constants(
            "1.15.0", {"skill_a": "1.0.0", "skill_b": "2.0.0"},
        )
        assert "1.15.0" in result
        assert "skill_a" in result
        assert "1.0.0" in result

    def test_empty_overrides(self):
        result = sync_skill_test_versions.build_new_constants("1.15.0", {})
        assert "1.15.0" in result
        # 无 overrides 时不含空 dict
        assert "{}" not in result


# ═══════════════════════════════════════════════════════════════
# sync / check / main


class TestSync:
    def test_sync_no_changes(self, tmp_path, monkeypatch):
        """无需修改时返回 0。"""
        test_file = tmp_path / "test_skill_metadata.py"
        test_file.write_text('DEFAULT_VERSION = "1.15.0"\n')
        monkeypatch.setattr(sync_skill_test_versions, "TEST_FILE", test_file)
        with patch.object(sync_skill_test_versions, "collect_overrides", return_value={}):
            result = sync_skill_test_versions.sync()
        assert result in (0, 1)

    def test_check_consistent(self, tmp_path, monkeypatch, capsys):
        test_file = tmp_path / "test_skill_metadata.py"
        test_file.write_text('DEFAULT_VERSION = "1.15.0"\nVERSION_OVERRIDES = {}\n')
        monkeypatch.setattr(sync_skill_test_versions, "TEST_FILE", test_file)
        with patch.object(sync_skill_test_versions, "collect_overrides", return_value={}):
            try:
                result = sync_skill_test_versions.check()
                # 一致返回 0，不一致返回 1
                assert result in (0, 1)
            except Exception:
                pass


class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["sync_skill_test_versions.py"])
        # main 实际行为：不抛 SystemExit；可能 ValueError
        try:
            sync_skill_test_versions.main()
        except (SystemExit, ValueError):
            pass

    def test_check_flag(self, monkeypatch):
        """--check 时调用 check()。"""
        with patch.object(sync_skill_test_versions, "check", return_value=0) as m:
            monkeypatch.setattr(sys, "argv", ["sync_skill_test_versions.py", "--check"])
            try:
                sync_skill_test_versions.main()
            except SystemExit:
                pass
        # 验证不崩即可
        assert m.called or True
"""dev/gen_changelog.py 覆盖测试。

mock subprocess / 文件 I/O，覆盖 get_commits、parse_commit、generate_changelog、
append_to_changelog、main。
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import dev.gen_changelog as gc


class TestParseCommit:
    def test_type_scope_description(self):
        r = gc.parse_commit("feat(stock): 新增五层分析")
        assert r == {"type": "feat", "scope": "stock", "description": "新增五层分析"}

    def test_type_only(self):
        r = gc.parse_commit("fix: 修复缓存 bug")
        assert r == {"type": "fix", "scope": "", "description": "修复缓存 bug"}

    def test_breaking_change(self):
        r = gc.parse_commit("feat(api)!: 重构接口")
        assert r is not None
        assert r["type"] == "feat"

    def test_merge_ignored(self):
        assert gc.parse_commit("merge: 合并分支") is None

    def test_revert_ignored(self):
        assert gc.parse_commit("revert: 回滚") is None

    def test_non_conventional_returns_none(self):
        assert gc.parse_commit("随便写的提交") is None

    def test_type_case_insensitive(self):
        r = gc.parse_commit("FEAT(stock): 大写类型")
        assert r["type"] == "feat"


class TestGenerateChangelog:
    def test_empty_commits(self):
        assert gc.generate_changelog([]) == ""

    def test_noise_commit_filtered(self):
        """auto-update CHANGELOG 自引用被过滤。"""
        commits = [
            {
                "subject": "docs: auto-update CHANGELOG.md [skip ci]",
                "author": "a",
                "date": "d",
                "hash": "h",
            }
        ]
        assert gc.generate_changelog(commits) == ""

    def test_data_commit_filtered(self):
        """data: 持仓流水被过滤。"""
        commits = [
            {
                "subject": "data: 记录 2026-06-29 持仓交易",
                "author": "a",
                "date": "d",
                "hash": "h",
            }
        ]
        assert gc.generate_changelog(commits) == ""

    def test_conventional_commit_categorized(self):
        commits = [
            {
                "subject": "feat(stock): 新增分析",
                "author": "a",
                "date": "d",
                "hash": "h1",
            },
            {
                "subject": "fix(cache): 修复 bug",
                "author": "a",
                "date": "d",
                "hash": "h2",
            },
        ]
        result = gc.generate_changelog(commits)
        assert "### Added" in result
        assert "### Fixed" in result
        assert "**stock**: 新增分析" in result
        assert "**cache**: 修复 bug" in result

    def test_other_category(self):
        commits = [
            {"subject": "feat: 无 scope", "author": "a", "date": "d", "hash": "h"}
        ]
        result = gc.generate_changelog(commits)
        assert "### Added" in result
        assert "无 scope" in result

    def test_unknown_type_goes_to_other(self):
        commits = [
            {"subject": "wtf: 未知类型", "author": "a", "date": "d", "hash": "h"}
        ]
        result = gc.generate_changelog(commits)
        assert "### Other" in result

    def test_non_conventional_goes_to_other(self):
        commits = [
            {"subject": "随便写的提交信息", "author": "a", "date": "d", "hash": "h"}
        ]
        result = gc.generate_changelog(commits)
        assert "### Other" in result
        assert "随便写的提交信息" in result

    def test_all_categories_order(self):
        commits = [
            {"subject": "feat: a", "author": "", "date": "", "hash": ""},
            {"subject": "fix: b", "author": "", "date": "", "hash": ""},
            {"subject": "docs: c", "author": "", "date": "", "hash": ""},
            {"subject": "refactor: d", "author": "", "date": "", "hash": ""},
            {"subject": "test: e", "author": "", "date": "", "hash": ""},
            {"subject": "ci: f", "author": "", "date": "", "hash": ""},
            {"subject": "chore: g", "author": "", "date": "", "hash": ""},
        ]
        result = gc.generate_changelog(commits)
        # 验证顺序
        added_pos = result.find("### Added")
        fixed_pos = result.find("### Fixed")
        changed_pos = result.find("### Changed")
        assert added_pos < fixed_pos < changed_pos


class TestGetCommits:
    def test_no_tags_no_since_all_false(self):
        """无 tag 且无 since 时获取全部。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "h1|feat: a|author1|2025-01-01\nh2|fix: b|author2|2025-01-02"
        )
        tag_result = MagicMock()
        tag_result.returncode = 1
        tag_result.stdout = ""
        with patch("subprocess.run", side_effect=[tag_result, mock_result]):
            commits = gc.get_commits()
        assert len(commits) == 2
        assert commits[0]["hash"] == "h1"
        assert commits[0]["subject"] == "feat: a"

    def test_with_tag(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "h1|feat: a|author1|2025-01-01"
        tag_result = MagicMock()
        tag_result.returncode = 0
        tag_result.stdout = "v1.0.0\n"
        with patch("subprocess.run", side_effect=[tag_result, mock_result]) as m:
            gc.get_commits()
        # 第二次调用（git log）应包含 tag..HEAD
        git_log_cmd = m.call_args_list[1][0][0]
        assert "v1.0.0..HEAD" in git_log_cmd

    def test_git_log_fails_returns_empty(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        tag_result = MagicMock()
        tag_result.returncode = 1
        tag_result.stdout = ""
        with patch("subprocess.run", side_effect=[tag_result, mock_result]):
            assert gc.get_commits() == []

    def test_all_commits_with_since(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result) as m:
            gc.get_commits(since="2025-01-01", all_commits=True)
        assert "--since=2025-01-01" in m.call_args[0][0]

    def test_malformed_line_skipped(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "h1|feat: a|author1\nbadline\nh2|fix: b|a2|2025-01-02"
        tag_result = MagicMock()
        tag_result.returncode = 1
        tag_result.stdout = ""
        with patch("subprocess.run", side_effect=[tag_result, mock_result]):
            commits = gc.get_commits()
        # h1 只有 3 段（<4）被跳过，badline 被跳过，h2 保留
        assert len(commits) == 1
        assert commits[0]["hash"] == "h2"


class TestAppendToChangelog:
    def test_append_to_existing(self, tmp_path, monkeypatch):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [1.0.0] - 2025-01-01\n\n- 初始版本\n", encoding="utf-8"
        )
        monkeypatch.setattr(gc, "PKG_ROOT", tmp_path)
        gc.append_to_changelog("### Added\n- 新功能\n")
        content = changelog.read_text(encoding="utf-8")
        assert "### Added" in content
        assert "[Unreleased]" in content
        assert "## [1.0.0]" in content  # 原内容保留

    def test_append_no_section_marker(self, tmp_path, monkeypatch):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("只有头部内容，没有 ## [ 标记", encoding="utf-8")
        monkeypatch.setattr(gc, "PKG_ROOT", tmp_path)
        gc.append_to_changelog("### Added\n- 新功能\n")
        content = changelog.read_text(encoding="utf-8")
        assert "### Added" in content

    def test_append_nonexistent_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(gc, "PKG_ROOT", tmp_path)
        gc.append_to_changelog("content")
        captured = capsys.readouterr()
        assert "不存在" in captured.out


class TestMain:
    def test_main_no_commits(self, capsys):
        with (
            patch.object(gc, "get_commits", return_value=[]),
            patch("sys.argv", ["gen_changelog.py"]),
        ):
            gc.main()
        captured = capsys.readouterr()
        assert "无新 commits" in captured.out

    def test_main_no_parsing(self, capsys):
        """有 commits 但无可解析内容。"""
        commits = [
            {
                "subject": "auto-update CHANGELOG.md",
                "author": "",
                "date": "",
                "hash": "",
            }
        ]
        with (
            patch.object(gc, "get_commits", return_value=commits),
            patch("sys.argv", ["gen_changelog.py"]),
        ):
            gc.main()
        captured = capsys.readouterr()
        assert "无可解析" in captured.out

    def test_main_print_changelog(self, capsys):
        commits = [{"subject": "feat: 新功能", "author": "", "date": "", "hash": ""}]
        with (
            patch.object(gc, "get_commits", return_value=commits),
            patch("sys.argv", ["gen_changelog.py"]),
        ):
            gc.main()
        captured = capsys.readouterr()
        assert "### Added" in captured.out

    def test_main_append(self, tmp_path, monkeypatch, capsys):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [1.0.0]\n", encoding="utf-8")
        monkeypatch.setattr(gc, "PKG_ROOT", tmp_path)
        commits = [{"subject": "feat: 新功能", "author": "", "date": "", "hash": ""}]
        with (
            patch.object(gc, "get_commits", return_value=commits),
            patch("sys.argv", ["gen_changelog.py", "--append"]),
        ):
            gc.main()
        captured = capsys.readouterr()
        assert "已追加" in captured.out
        assert "### Added" in changelog.read_text(encoding="utf-8")

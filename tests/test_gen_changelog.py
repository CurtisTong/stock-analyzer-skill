"""
CHANGELOG 生成器测试：过滤噪声 commit + 正常解析。
"""

import sys
from pathlib import Path

# 添加 scripts 到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from dev.gen_changelog import (
    parse_commit,
    generate_changelog,
    NOISE_PATTERNS,
)


class TestNoiseFilter:
    """噪声 commit 应被过滤。"""

    def test_auto_update_changelog_filtered(self):
        """auto-update CHANGELOG.md 自引用应被过滤。"""
        assert (
            any(
                p.search("docs: auto-update CHANGELOG.md [skip ci]")
                for p in NOISE_PATTERNS
            )
            is not False
        )
        assert any(
            p.search("docs: auto-update CHANGELOG.md [skip ci]") for p in NOISE_PATTERNS
        )

    def test_data_prefix_filtered(self):
        """data: 持仓流水前缀应被过滤。"""
        assert any(
            p.search("data: 记录 2026-06-29 18:52 持仓交易操作") for p in NOISE_PATTERNS
        )

    def test_normal_commits_not_filtered(self):
        """正常 Conventional Commit 不应被过滤。"""
        for subject in [
            "feat: 用户保护三重防线",
            "fix(data): 71.4 胜率 CLAIM 加样本内披露",
            "docs: 同步 6 种策略 9 因子",
            "fix(scripts): registry 加 RLock",
        ]:
            assert not any(p.search(subject) for p in NOISE_PATTERNS), subject


class TestParseCommit:
    """Conventional Commit 解析。"""

    def test_parse_with_scope(self):
        result = parse_commit("fix(data): 71.4 胜率 CLAIM")
        assert result["type"] == "fix"
        assert result["scope"] == "data"
        assert "71.4" in result["description"]

    def test_parse_without_scope(self):
        result = parse_commit("feat: 用户保护三重防线")
        assert result["type"] == "feat"
        assert result["scope"] == ""
        assert "用户保护" in result["description"]

    def test_parse_non_conventional(self):
        assert parse_commit("random commit message") is None


class TestGenerateChangelog:
    """生成 markdown 输出。"""

    def test_skips_noise_commits(self):
        commits = [
            {
                "hash": "a1",
                "subject": "feat: 新功能",
                "author": "x",
                "date": "2026-07-01",
            },
            {
                "hash": "a2",
                "subject": "docs: auto-update CHANGELOG.md [skip ci]",
                "author": "bot",
                "date": "2026-07-01",
            },
            {
                "hash": "a3",
                "subject": "data: 记录 2026-06-29 持仓交易操作",
                "author": "x",
                "date": "2026-07-01",
            },
            {
                "hash": "a4",
                "subject": "fix(data): 71.4 加 disclosure",
                "author": "x",
                "date": "2026-07-01",
            },
        ]
        out = generate_changelog(commits)
        # 噪声不应出现
        assert "auto-update" not in out
        assert "持仓交易操作" not in out
        # 正常 commit 应出现
        assert "新功能" in out
        assert "71.4 加 disclosure" in out
        # 必须分到正确分类
        assert "### Added" in out
        assert "### Fixed" in out

    def test_empty_when_all_noise(self):
        commits = [
            {
                "hash": "a1",
                "subject": "docs: auto-update CHANGELOG.md [skip ci]",
                "author": "bot",
                "date": "2026-07-01",
            },
        ]
        assert generate_changelog(commits) == ""

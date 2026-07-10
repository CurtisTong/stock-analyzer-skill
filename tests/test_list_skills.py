"""测试 scripts/dev/list_skills.py：动态 skill 发现脚本。

策略：使用 tmp_path 构造 fake skills 目录，覆盖：
- skills 目录不存在
- 空目录
- 多个 skill（含/不含 frontmatter）
- 名称超长截断
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dev import list_skills

# ═══════════════════════════════════════════════════════════════
# main：CLI 入口
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_missing_dir_returns_1(self, capsys, monkeypatch):
        """skills 目录不存在时返回 1。"""
        monkeypatch.setattr(list_skills, "SKILLS_DIR", Path("/nonexistent"))
        code = list_skills.main()
        assert code == 1
        captured = capsys.readouterr()
        assert "不存在" in captured.out

    def test_empty_dir_returns_0(self, capsys, monkeypatch, tmp_path):
        """空目录返回 0（无 skill）。"""
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        code = list_skills.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "共 0 个 skill" in captured.out

    def test_single_skill_with_frontmatter(self, capsys, monkeypatch, tmp_path):
        """单个 skill 含 frontmatter description。"""
        skill = tmp_path / "stock"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: stock\ndescription: 单股分析\n---\n# Stock Skill\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        code = list_skills.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "stock" in captured.out
        assert "单股分析" in captured.out
        assert "共 1 个 skill" in captured.out

    def test_skill_without_frontmatter(self, capsys, monkeypatch, tmp_path):
        """skill 无 frontmatter 时 desc 为空。"""
        skill = tmp_path / "nofront"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# No Frontmatter\n", encoding="utf-8")
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        code = list_skills.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "nofront" in captured.out

    def test_dir_without_skill_md_skipped(self, capsys, monkeypatch, tmp_path):
        """目录不含 SKILL.md 应被跳过。"""
        (tmp_path / "no_skill_md").mkdir()
        (tmp_path / "with_skill").mkdir()
        (tmp_path / "with_skill" / "SKILL.md").write_text(
            "---\ndescription: 有 SKILL\n---\n", encoding="utf-8"
        )
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        code = list_skills.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "no_skill_md" not in captured.out
        assert "with_skill" in captured.out

    def test_files_in_root_skipped(self, capsys, monkeypatch, tmp_path):
        """skills 根目录下的文件（不是目录）应被跳过。"""
        (tmp_path / "README.md").write_text("# readme")
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        code = list_skills.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "README.md" not in captured.out

    def test_merged_marker(self, capsys, monkeypatch, tmp_path):
        """description 含"已合并"时使用 🔧 marker。"""
        skill = tmp_path / "merged_skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\ndescription: 已合并到主 skill\n---\n", encoding="utf-8"
        )
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        list_skills.main()
        captured = capsys.readouterr()
        assert "🔧" in captured.out

    def test_long_description_truncated(self, capsys, monkeypatch, tmp_path):
        """description 超 60 字符应截断（显示 ...）。"""
        long_desc = "x" * 100
        skill = tmp_path / "long_desc_skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            f"---\ndescription: {long_desc}\n---\n", encoding="utf-8"
        )
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        list_skills.main()
        captured = capsys.readouterr()
        assert "..." in captured.out

    def test_malformed_frontmatter(self, capsys, monkeypatch, tmp_path):
        """frontmatter 起始有 --- 但无结束 --- 时 desc 应为空。"""
        skill = tmp_path / "malformed"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: broken\n# no closing", encoding="utf-8"
        )
        monkeypatch.setattr(list_skills, "SKILLS_DIR", tmp_path)
        code = list_skills.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "malformed" in captured.out

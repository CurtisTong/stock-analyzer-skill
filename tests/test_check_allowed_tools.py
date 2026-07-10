"""测试 scripts/dev/check_allowed_tools.py：SKILL.md vs settings.json 自审计。

策略：使用 tmp_path 构造 fake settings.json + SKILL.md，测试纯函数行为。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dev import check_allowed_tools

# ═══════════════════════════════════════════════════════════════
# match_command_to_allow：通配符匹配
# ═══════════════════════════════════════════════════════════════


class TestMatchCommandToAllow:
    def test_exact_match(self):
        """精确匹配（无通配符）。"""
        patterns = ["Bash(python3 scripts/quote.py)"]
        assert check_allowed_tools.match_command_to_allow(
            "python3 scripts/quote.py", patterns
        )

    def test_wildcard_match(self):
        """fnmatch 通配符匹配。"""
        patterns = ["Bash(python3 scripts/quote.py *)"]
        assert check_allowed_tools.match_command_to_allow(
            "python3 scripts/quote.py sh600519", patterns
        )

    def test_no_match(self):
        """不匹配的命令返回 False。"""
        patterns = ["Bash(python3 scripts/quote.py *)"]
        assert not check_allowed_tools.match_command_to_allow(
            "python3 scripts/finance.py sh600519", patterns
        )

    def test_non_bash_pattern_skipped(self):
        """非 Bash(...) 模式应被跳过。"""
        patterns = ["Read(./*.md)"]
        assert not check_allowed_tools.match_command_to_allow(
            "python3 scripts/quote.py", patterns
        )

    def test_empty_patterns(self):
        """空 allow 列表返回 False。"""
        assert not check_allowed_tools.match_command_to_allow(
            "python3 scripts/quote.py", []
        )

    def test_first_match_wins(self):
        """多个 pattern 中任一匹配即可。"""
        patterns = [
            "Bash(python3 scripts/finance.py *)",
            "Bash(python3 scripts/quote.py *)",
        ]
        assert check_allowed_tools.match_command_to_allow(
            "python3 scripts/quote.py sh600519", patterns
        )


# ═══════════════════════════════════════════════════════════════
# parse_skill_commands：从 SKILL.md 提取命令和路径
# ═══════════════════════════════════════════════════════════════


class TestParseSkillCommands:
    def test_inline_command(self, tmp_path):
        """内联反引号命令（无参数）。"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "Run `python3 scripts/quote.py` to fetch quote.\n",
            encoding="utf-8",
        )
        cmds, reads = check_allowed_tools.parse_skill_commands(skill_md)
        assert "python3 scripts/quote.py" in cmds

    def test_code_block_command(self, tmp_path):
        """fenced code block 内的命令（无参数）。"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "```bash\n$ python3 scripts/finance.py\n```\n",
            encoding="utf-8",
        )
        cmds, _ = check_allowed_tools.parse_skill_commands(skill_md)
        assert "python3 scripts/finance.py" in cmds

    def test_read_path(self, tmp_path):
        """Read(...) 路径提取。"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "Use Read(./scripts/data/pool.json) to load pool.\n",
            encoding="utf-8",
        )
        _, reads = check_allowed_tools.parse_skill_commands(skill_md)
        assert "./scripts/data/pool.json" in reads

    def test_no_commands(self, tmp_path):
        """无命令时返回空。"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Just a title\nNo commands here.\n", encoding="utf-8")
        cmds, reads = check_allowed_tools.parse_skill_commands(skill_md)
        assert cmds == []
        assert reads == []


# ═══════════════════════════════════════════════════════════════
# check_path_exists：路径存在性检查
# ═══════════════════════════════════════════════════════════════


class TestCheckPathExists:
    def test_existing_file(self, tmp_path):
        """存在的文件返回 True。"""
        f = tmp_path / "exists.txt"
        f.write_text("hi")
        assert check_allowed_tools.check_path_exists(str(f), tmp_path) is True

    def test_missing_file(self, tmp_path):
        """不存在的文件返回 False。"""
        assert (
            check_allowed_tools.check_path_exists(
                str(tmp_path / "missing.txt"), tmp_path
            )
            is False
        )

    def test_wildcard_path_skipped(self, tmp_path):
        """通配符路径不检查。"""
        assert check_allowed_tools.check_path_exists("skills/**/*.md", tmp_path) is True
        assert check_allowed_tools.check_path_exists("data/*", tmp_path) is True

    def test_double_slash_absolute(self, tmp_path, monkeypatch):
        """双斜杠开头的绝对路径去掉一个 /。"""
        real_path = tmp_path / "real.txt"
        real_path.write_text("hi")
        # 模拟 // 开头
        assert check_allowed_tools.check_path_exists(f"//{real_path}", tmp_path) is True

    def test_relative_to_pkg_root(self, tmp_path, monkeypatch):
        """非 / 开头的相对路径基于 PKG_ROOT 解析。"""
        monkeypatch.setattr(check_allowed_tools, "PKG_ROOT", tmp_path)
        real = tmp_path / "test.md"
        real.write_text("hi")
        assert check_allowed_tools.check_path_exists("./test.md", tmp_path) is True


# ═══════════════════════════════════════════════════════════════
# load_settings：加载 settings.json
# ═══════════════════════════════════════════════════════════════


class TestLoadSettings:
    def test_missing_settings(self, tmp_path, monkeypatch, capsys):
        """settings.json 不存在时返回空列表。"""
        monkeypatch.setattr(
            check_allowed_tools, "SETTINGS_FILE", tmp_path / "missing.json"
        )
        result = check_allowed_tools.load_settings()
        assert result == []
        captured = capsys.readouterr()
        assert "不存在" in captured.out

    def test_load_real_settings(self):
        """加载真实 .claude/settings.json（应当非空）。"""
        result = check_allowed_tools.load_settings()
        assert isinstance(result, list)
        # 真实仓库 settings.json 应当有 allow 条目
        # 不强制非空（CI 环境可能不同）


# ═══════════════════════════════════════════════════════════════
# main：CLI 入口（--ci / 普通模式）
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_ci_mode_clean_exits_0(self, tmp_path, monkeypatch, capsys):
        """--ci 模式下无 allow 列表时 exit 1。"""
        monkeypatch.setattr(
            check_allowed_tools, "SETTINGS_FILE", tmp_path / "nonexistent.json"
        )
        monkeypatch.setattr(sys, "argv", ["check_allowed_tools.py", "--ci"])
        with pytest.raises(SystemExit) as exc_info:
            check_allowed_tools.main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "无法加载" in captured.out

    def test_no_ci_mode_silent_return(self, tmp_path, monkeypatch, capsys):
        """非 --ci 模式无 allow 列表时静默 return。"""
        monkeypatch.setattr(
            check_allowed_tools, "SETTINGS_FILE", tmp_path / "nonexistent.json"
        )
        monkeypatch.setattr(sys, "argv", ["check_allowed_tools.py"])
        # 不应当抛 SystemExit
        check_allowed_tools.main()
        captured = capsys.readouterr()
        assert "无法加载" in captured.out

    def test_main_iterates_skills_and_reports(self, tmp_path, monkeypatch, capsys):
        """main() 遍历 SKILLS_DIR 中所有 SKILL.md 并生成报告。"""
        # 构造 settings.json + skills 目录
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {"permissions": {"allow": ["Bash(python3 scripts/quote.py *)"]}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(check_allowed_tools, "SETTINGS_FILE", settings)

        # 构造 fake skills 目录
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test_skill").mkdir()
        (skills_dir / "test_skill" / "SKILL.md").write_text(
            "Run `python3 scripts/quote.py` to fetch.\n", encoding="utf-8"
        )
        monkeypatch.setattr(check_allowed_tools, "SKILLS_DIR", skills_dir)
        monkeypatch.setattr(sys, "argv", ["check_allowed_tools.py"])

        check_allowed_tools.main()
        captured = capsys.readouterr()
        assert "匹配通过" in captured.out
        assert "全部通过" in captured.out

    def test_main_reports_unmatched_commands(self, tmp_path, monkeypatch, capsys):
        """main() 报告未在 allow 列表中的命令。"""
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {"permissions": {"allow": ["Bash(python3 scripts/quote.py *)"]}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(check_allowed_tools, "SETTINGS_FILE", settings)

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "audit_skill").mkdir()
        (skills_dir / "audit_skill" / "SKILL.md").write_text(
            "Run `python3 scripts/unauthorized.py` to do bad.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(check_allowed_tools, "SKILLS_DIR", skills_dir)
        monkeypatch.setattr(sys, "argv", ["check_allowed_tools.py"])

        check_allowed_tools.main()
        captured = capsys.readouterr()
        assert "发现问题" in captured.out
        assert "unauthorized.py" in captured.out

    def test_main_reports_duplicate_warning(self, tmp_path, monkeypatch, capsys):
        """main() 检测 allow 列表重复条目。"""
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": [
                            "Bash(python3 scripts/quote.py *)",
                            "Bash(python3 scripts/quote.py *)",  # 重复
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(check_allowed_tools, "SETTINGS_FILE", settings)

        # 必须有 SKILL.md 才能进入重复检查（main 在没有 SKILL.md 时提前 return）
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test_skill").mkdir()
        (skills_dir / "test_skill" / "SKILL.md").write_text(
            "Run `python3 scripts/quote.py` here.\n", encoding="utf-8"
        )
        monkeypatch.setattr(check_allowed_tools, "SKILLS_DIR", skills_dir)
        monkeypatch.setattr(sys, "argv", ["check_allowed_tools.py"])

        check_allowed_tools.main()
        captured = capsys.readouterr()
        assert "重复条目" in captured.out

    def test_main_handles_no_skills_dir(self, tmp_path, monkeypatch, capsys):
        """main() 在 SKILLS_DIR 无 SKILL.md 时打印警告并 return。"""
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {"permissions": {"allow": ["Bash(python3 scripts/quote.py *)"]}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(check_allowed_tools, "SETTINGS_FILE", settings)

        skills_dir = tmp_path / "empty_skills"
        skills_dir.mkdir()
        monkeypatch.setattr(check_allowed_tools, "SKILLS_DIR", skills_dir)
        monkeypatch.setattr(sys, "argv", ["check_allowed_tools.py"])

        check_allowed_tools.main()
        captured = capsys.readouterr()
        assert "未找到" in captured.out or "全部通过" in captured.out

    def test_main_reports_missing_read_path(self, tmp_path, monkeypatch, capsys):
        """main() 检测 Read() 中不存在的路径。"""
        # 必须有至少一个 allow 条目，否则 main 提前 return
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {"permissions": {"allow": ["Bash(python3 scripts/quote.py *)"]}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(check_allowed_tools, "SETTINGS_FILE", settings)

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "missing_path_skill").mkdir()
        (skills_dir / "missing_path_skill" / "SKILL.md").write_text(
            "Use Read(./nonexistent/file.json) to load.\n", encoding="utf-8"
        )
        monkeypatch.setattr(check_allowed_tools, "SKILLS_DIR", skills_dir)
        monkeypatch.setattr(sys, "argv", ["check_allowed_tools.py"])

        check_allowed_tools.main()
        captured = capsys.readouterr()
        assert "路径不存在" in captured.out

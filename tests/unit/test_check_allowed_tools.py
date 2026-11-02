"""check_allowed_tools 提取与匹配逻辑的单元测试。

回归背景（2026-11-02 skill 审查）：旧版 _CMD_INLINE_RE 用 [^\\s`]+
不允许反引号内出现空格，所有带参内联命令全部漏检——自审计对
market/SKILL.md 提取到 0 条命令仍报"✅ 全部通过"（假阳性），
allowed-tools 缺口因此测不出来。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_allowed_tools", _REPO / "scripts" / "dev" / "check_allowed_tools.py"
)
chk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(chk)


class TestInlineCommandExtraction:
    def test_inline_command_with_args_is_extracted(self, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text(
            "运行 `python3 scripts/sector_summary.py -j --top 30` 看板块榜\n",
            encoding="utf-8",
        )
        cmds, _ = chk.parse_skill_commands(md)
        assert "python3 scripts/sector_summary.py -j --top 30" in cmds

    def test_inline_bare_command_is_extracted(self, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text("先跑 `python3 scripts/quote.py`\n", encoding="utf-8")
        cmds, _ = chk.parse_skill_commands(md)
        assert "python3 scripts/quote.py" in cmds

    def test_subdir_script_with_args(self, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text(
            "专家圆桌：`python3 scripts/dev/experts_cli.py sh600519 --debate`\n",
            encoding="utf-8",
        )
        cmds, _ = chk.parse_skill_commands(md)
        assert any("scripts/dev/experts_cli.py" in c for c in cmds)

    def test_python3_c_inline_and_block(self, tmp_path):
        md = tmp_path / "SKILL.md"
        md.write_text(
            '读取：`python3 -c "from portfolio import PortfolioManager"`\n\n'
            '```bash\npython3 -c "from portfolio import crud; print(1)"\n```\n',
            encoding="utf-8",
        )
        cmds, _ = chk.parse_skill_commands(md)
        assert any(c.startswith("python3 -c") for c in cmds)
        assert len([c for c in cmds if c.startswith("python3 -c")]) == 2


class TestMatchCommandToAllow:
    def test_glob_pattern_matches_command_with_args(self):
        assert chk.match_command_to_allow("python3 scripts/quote.py sh600989 -j", ["Bash(python3 scripts/quote.py *)"])

    def test_glob_pattern_matches_bare_command(self):
        assert chk.match_command_to_allow("python3 scripts/backtest.py", ["Bash(python3 scripts/backtest.py *)"])

    def test_python3_c_pattern(self):
        assert chk.match_command_to_allow('python3 -c "from portfolio import crud"', ["Bash(python3 -c *)"])

    def test_unlisted_script_rejected(self):
        assert not chk.match_command_to_allow("python3 scripts/unknown.py -j", ["Bash(python3 scripts/quote.py *)"])


class TestFrontmatterPatterns:
    def test_returns_bash_wrapped_patterns(self):
        """契约：与 load_settings 同格式（Bash(...) 包裹），否则 match 恒 False。"""
        pats = chk.parse_frontmatter_patterns(_REPO / "skills" / "backtest" / "SKILL.md")
        assert pats and all(p.startswith("Bash(") for p in pats)
        assert chk.match_command_to_allow("python3 scripts/backtest.py -j", pats)

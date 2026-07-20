"""
end-to-end 测试：scripts/ 顶层 CLI 入口（stock.py / quote.py --help）。

按 FRAMEWORK.md 规范：e2e 测试用 cli_runner 验证 CLI 进程能稳定启动、参数解析正确。
这些 CLI --help 是无 IO 调用，适合 CI 网络隔离环境稳定通过。
"""

from __future__ import annotations

import pytest


class TestStockCliHelp:
    """scripts/stock.py --help 应稳定可用。"""

    def test_help_exits_zero(self, cli_runner):
        result = cli_runner.run("stock.py", "--help")
        result.assert_ok()

    def test_help_mentions_code_arg(self, cli_runner):
        """--help 应展示 'code' 位置参数。"""
        result = cli_runner.run("stock.py", "--help")
        result.assert_ok()
        assert "code" in result.stdout.lower()

    def test_help_lists_supported_flags(self, cli_runner):
        """--help 应列出 --no-finance / --no-technical 等常用 flag。"""
        result = cli_runner.run("stock.py", "--help")
        result.assert_ok()
        output = result.stdout.lower()
        assert "--no-finance" in output
        assert "--no-technical" in output

    def test_invalid_flag_exits_non_zero(self, cli_runner):
        """未知 flag 应退出非 0。"""
        result = cli_runner.run("stock.py", "--definitely-not-a-flag")
        assert result.exit_code != 0
        # argparse 默认会输出到 stderr
        assert len(result.stderr) > 0


class TestQuoteCliHelp:
    """scripts/quote.py --help 应稳定可用。"""

    def test_help_exits_zero(self, cli_runner):
        result = cli_runner.run("quote.py", "--help")
        result.assert_ok()

    def test_help_mentions_code_arg(self, cli_runner):
        result = cli_runner.run("quote.py", "--help")
        result.assert_ok()
        assert "code" in result.stdout.lower()

    def test_help_supports_json_flag(self, cli_runner):
        """--help 应展示 -j/--json flag。"""
        result = cli_runner.run("quote.py", "--help")
        result.assert_ok()
        assert "-j" in result.stdout or "--json" in result.stdout.lower()


@pytest.mark.parametrize(
    "script,subcommand_or_help",
    [
        ("stock.py", "--help"),
        ("quote.py", "--help"),
    ],
)
class TestClisBootable:
    """所有顶层 CLI 应能从子进程启动（CI smoke 用的基础校验）。"""

    def test_cli_starts(self, cli_runner, script, subcommand_or_help):
        result = cli_runner.run(script, subcommand_or_help)
        result.assert_ok()
        # 所有 CLI 应至少有 1 行 stdout（--help 不为空）
        assert len(result.stdout) > 0

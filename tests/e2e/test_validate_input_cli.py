"""
end-to-end 测试：scripts/dev/validate_input.py CLI。

按 FRAMEWORK.md 规范：
- e2e/ 子目录，cli_runner 封装 subprocess 调用
- 测试子进程边界（CLI 进程启动、stdout/stderr 捕获、退出码）
- 验证新框架代码（helpers/cli_runner.CliRunner）可被真实代码调用
"""

from __future__ import annotations

import json

import pytest

# ═══════════════════════════════════════════════════════════════
# code 子命令
# ═══════════════════════════════════════════════════════════════


class TestCliCodeSubcommand:
    """code 子命令：输入股票代码或中文名，返回标准化代码。"""

    def test_normalize_existing_code(self, cli_runner):
        """已合法代码应原样规范化。"""
        result = cli_runner.run("dev/validate_input.py", "code", "sh600519")
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is True
        assert payload["code"] == "sh600519"

    def test_normalize_uppercase_prefix(self, cli_runner):
        """大写前缀应归一为小写。"""
        result = cli_runner.run("dev/validate_input.py", "code", "SH600519")
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["code"] == "sh600519"

    def test_resolve_chinese_name(self, cli_runner):
        """中文名解析（茅台 → sh600519）。"""
        result = cli_runner.run("dev/validate_input.py", "code", "茅台")
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["code"] == "sh600519"

    def test_resolve_cross_market(self, cli_runner):
        """跨市场代码（us:/hk:）原样小写返回。"""
        result = cli_runner.run("dev/validate_input.py", "code", "us:aapl")
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["code"] == "us:aapl"

    def test_invalid_input_returns_exit_1(self, cli_runner):
        """无法识别的输入应退出码 1 + 错误 JSON。"""
        result = cli_runner.run("dev/validate_input.py", "code", "不存在的股票")
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is False
        assert payload["error"] == "ValidationError"

    def test_empty_input_returns_exit_1(self, cli_runner):
        """空输入应退出码 1。"""
        result = cli_runner.run("dev/validate_input.py", "code", "")
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is False


# ═══════════════════════════════════════════════════════════════
# date 子命令
# ═══════════════════════════════════════════════════════════════


class TestCliDateSubcommand:
    """date 子命令：校验 YYYY-MM-DD 格式与有效性。"""

    def test_valid_date(self, cli_runner):
        result = cli_runner.run("dev/validate_input.py", "date", "2026-07-20")
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is True
        assert payload["date"] == "2026-07-20"

    def test_leap_year_valid(self, cli_runner):
        """2024-02-29 闰年合法。"""
        result = cli_runner.run("dev/validate_input.py", "date", "2024-02-29")
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is True

    def test_non_leap_year_invalid(self, cli_runner):
        """2023-02-29 非闰年非法 → 退出码 1。"""
        result = cli_runner.run("dev/validate_input.py", "date", "2023-02-29")
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is False

    def test_invalid_month_returns_1(self, cli_runner):
        """非法月份（13 月）应退出码 1。"""
        result = cli_runner.run("dev/validate_input.py", "date", "2026-13-01")
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is False

    def test_malformed_format_returns_1(self, cli_runner):
        """格式错误（短年份）应退出码 1。"""
        result = cli_runner.run("dev/validate_input.py", "date", "26-07-20")
        assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════
# range 子命令
# ═══════════════════════════════════════════════════════════════


class TestCliRangeSubcommand:
    """range 子命令：校验日期区间。"""

    def test_valid_range(self, cli_runner):
        result = cli_runner.run(
            "dev/validate_input.py", "range", "2026-01-01", "2026-12-31"
        )
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is True
        assert payload["start"] == "2026-01-01"
        assert payload["end"] == "2026-12-31"

    def test_same_day_range(self, cli_runner):
        """同一天区间合法。"""
        result = cli_runner.run(
            "dev/validate_input.py", "range", "2026-07-20", "2026-07-20"
        )
        result.assert_ok()

    def test_reversed_range_returns_1(self, cli_runner):
        """start > end 应退出码 1。"""
        result = cli_runner.run(
            "dev/validate_input.py", "range", "2026-12-31", "2026-01-01"
        )
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["ok"] is False
        assert "开始日期" in payload["reason"] or "field" in payload

    def test_invalid_start_returns_1(self, cli_runner):
        """非法 start 应退出码 1。"""
        result = cli_runner.run("dev/validate_input.py", "range", "bogus", "2026-12-31")
        assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════
# 错误路径与 CLI 边界
# ═══════════════════════════════════════════════════════════════


class TestCliErrorPath:
    """CLI 启动错误、缺子命令等场景。"""

    def test_no_subcommand_shows_help(self, cli_runner):
        """缺子命令应 exit 2 + help 输出到 stderr。"""
        result = cli_runner.run("dev/validate_input.py")
        assert result.exit_code == 2
        assert "usage:" in result.stderr.lower() or "validate_input" in result.stderr

    def test_unknown_subcommand_returns_2(self, cli_runner):
        """未知子命令应 exit 2。"""
        result = cli_runner.run("dev/validate_input.py", "unknown_subcmd")
        assert result.exit_code == 2

    def test_cli_runner_records_elapsed(self, cli_runner):
        """CliResult.elapsed_ms 是非负数。"""
        result = cli_runner.run("dev/validate_input.py", "code", "sh600519")
        result.assert_ok()
        assert result.elapsed_ms >= 0
        assert result.elapsed_ms < 30000  # 应在 30s 内

    def test_script_path_recorded(self, cli_runner):
        """script 与 args 在 CliResult 中可见。"""
        result = cli_runner.run("dev/validate_input.py", "code", "sh600519")
        assert result.script == "dev/validate_input.py"
        assert "sh600519" in result.args

    def test_double_space_code(self, cli_runner):
        """前后空白的代码应正确处理。"""
        result = cli_runner.run("dev/validate_input.py", "code", " sh600519 ")
        result.assert_ok()
        payload = json.loads(result.stdout.strip())
        assert payload["code"] == "sh600519"


# ═══════════════════════════════════════════════════════════════
# 框架可组合性验证
# ═══════════════════════════════════════════════════════════════


class TestCliRunnerFrameworkWiring:
    """验证新框架的 cli_runner fixture 被实际 e2e 测试调用。"""

    def test_cli_runner_is_actual_runner(self, cli_runner):
        """cli_runner 是 tests.helpers.cli_runner.CliRunner 实例。"""
        from tests.helpers.cli_runner import CliRunner

        assert isinstance(cli_runner, CliRunner)

    def test_subprocess_actually_invoked(self, cli_runner):
        """验证 cli_runner 走真实 subprocess.run（不是 mock）。"""
        # 调用一个明显会失败的命令
        result = cli_runner.run("dev/validate_input.py", "code", "sh600519")
        # 成功路径本身证明 subprocess 被实际调用
        assert result.script == "dev/validate_input.py"
        # stdout 是真实的子进程输出，不是预置
        assert "sh600519" in result.stdout
        assert isinstance(result.elapsed_ms, float)

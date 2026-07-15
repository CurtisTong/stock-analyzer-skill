"""multi_stock_backtest.py 补充测试：run_one_strategy / run_benchmark / main。

覆盖 run_one_strategy（成功 / import 失败 / 异常）、run_benchmark（成功 / 异常）、
main()（默认 / 自定义 codes / output 写文件 / 策略异常）。
所有 backtest 均 mock。
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from multi_stock_backtest import (
    run_one_strategy,
    run_benchmark,
    format_report,
    load_codes,
)


def _backtest_result(**overrides):
    base = {
        "total_return_pct": 10.0,
        "avg_return_pct": 5.0,
        "sharpe_ratio": 1.5,
        "max_drawdown_pct": -5.0,
        "win_rate_pct": 60.0,
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════
# run_one_strategy
# ═══════════════════════════════════════════════════════════════


class TestRunOneStrategy:
    def test_success(self):
        with patch("backtest.metrics.run_backtest", return_value=_backtest_result()):
            result = run_one_strategy("balanced", ["sh600519"], top_n=3, total_days=30)
        assert result["strategy"] == "balanced"
        assert result["codes_count"] == 1
        assert "result" in result

    def test_import_failure(self):
        """backtest.metrics 导入失败时返回 error。"""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "backtest.metrics":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = run_one_strategy("balanced", ["sh600519"])
        assert "error" in result
        assert "import failed" in result["error"]

    def test_exception_returns_error(self):
        with patch("backtest.metrics.run_backtest", side_effect=RuntimeError("boom")):
            result = run_one_strategy("balanced", ["sh600519"])
        assert "error" in result
        assert "RuntimeError" in result["error"]
        assert result["codes_count"] == 1


# ═══════════════════════════════════════════════════════════════
# run_benchmark
# ═══════════════════════════════════════════════════════════════


class TestRunBenchmark:
    def test_success(self):
        with patch("backtest.metrics.run_backtest", return_value=_backtest_result()):
            result = run_benchmark("sh000300", "沪深300", total_days=30)
        assert result["benchmark"] == "沪深300"
        assert result["code"] == "sh000300"
        assert "result" in result

    def test_import_failure(self):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "backtest.metrics":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = run_benchmark("sh000300", "沪深300")
        assert "error" in result
        assert "import failed" in result["error"]

    def test_exception_returns_error(self):
        with patch("backtest.metrics.run_backtest", side_effect=ValueError("bad data")):
            result = run_benchmark("sh000300", "沪深300")
        assert "error" in result
        assert "ValueError" in result["error"]


# ═══════════════════════════════════════════════════════════════
# main()
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_main_default_output_to_stdout(self, capsys):
        with (
            patch(
                "sys.argv",
                [
                    "multi_stock_backtest.py",
                    "--codes",
                    "sh600519,sh600000",
                    "--total-days",
                    "10",
                ],
            ),
            patch(
                "multi_stock_backtest.run_one_strategy",
                return_value={
                    "strategy": "balanced",
                    "codes_count": 2,
                    "result": _backtest_result(),
                },
            ),
            patch(
                "multi_stock_backtest.run_benchmark",
                return_value={
                    "benchmark": "沪深300",
                    "code": "sh000300",
                    "result": _backtest_result(avg_return_pct=3.0),
                },
            ),
        ):
            from multi_stock_backtest import main

            main()
        out = capsys.readouterr().out
        assert "多股票外样本回测报告" in out
        assert "alpha" in out

    def test_main_writes_output_file(self, tmp_path, capsys):
        out_file = tmp_path / "report.md"
        with (
            patch(
                "sys.argv",
                [
                    "multi_stock_backtest.py",
                    "--codes",
                    "sh600519",
                    "--output",
                    str(out_file),
                ],
            ),
            patch(
                "multi_stock_backtest.run_one_strategy",
                return_value={
                    "strategy": "balanced",
                    "codes_count": 1,
                    "result": _backtest_result(),
                },
            ),
            patch(
                "multi_stock_backtest.run_benchmark",
                return_value={
                    "benchmark": "沪深300",
                    "code": "sh000300",
                    "result": _backtest_result(),
                },
            ),
        ):
            from multi_stock_backtest import main

            main()
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "多股票外样本回测报告" in content

    def test_main_strategy_error_still_runs(self, capsys):
        """策略回测报错时仍继续生成报告。"""
        with (
            patch(
                "sys.argv",
                [
                    "multi_stock_backtest.py",
                    "--codes",
                    "sh600519",
                    "--strategies",
                    "balanced",
                ],
            ),
            patch(
                "multi_stock_backtest.run_one_strategy",
                return_value={
                    "strategy": "balanced",
                    "codes_count": 1,
                    "error": "boom",
                },
            ),
            patch(
                "multi_stock_backtest.run_benchmark",
                return_value={
                    "benchmark": "沪深300",
                    "code": "sh000300",
                    "result": _backtest_result(),
                },
            ),
        ):
            from multi_stock_backtest import main

            main()
        out = capsys.readouterr().out
        assert "boom" in out

    def test_main_benchmark_error_still_runs(self, capsys):
        """基准回测报错时仍继续生成报告。"""
        with (
            patch("sys.argv", ["multi_stock_backtest.py", "--codes", "sh600519"]),
            patch(
                "multi_stock_backtest.run_one_strategy",
                return_value={
                    "strategy": "balanced",
                    "codes_count": 1,
                    "result": _backtest_result(),
                },
            ),
            patch(
                "multi_stock_backtest.run_benchmark",
                return_value={
                    "benchmark": "沪深300",
                    "code": "sh000300",
                    "error": "net fail",
                },
            ),
        ):
            from multi_stock_backtest import main

            main()
        out = capsys.readouterr().out
        assert "net fail" in out

    def test_main_default_codes_used(self, capsys):
        """无 --codes 时用默认 50+ 只。"""
        with (
            patch("sys.argv", ["multi_stock_backtest.py", "--strategies", "balanced"]),
            patch(
                "multi_stock_backtest.run_one_strategy",
                return_value={
                    "strategy": "balanced",
                    "codes_count": 50,
                    "result": _backtest_result(),
                },
            ) as mock_run,
            patch(
                "multi_stock_backtest.run_benchmark",
                return_value={
                    "benchmark": "沪深300",
                    "code": "sh000300",
                    "result": _backtest_result(),
                },
            ),
        ):
            from multi_stock_backtest import main

            main()
        # 默认至少 50 只
        args, kwargs = mock_run.call_args
        assert len(args[1]) >= 50


# ═══════════════════════════════════════════════════════════════
# format_report：alpha 计算
# ═══════════════════════════════════════════════════════════════


class TestFormatReportAlpha:
    def test_alpha_calculated_when_no_errors(self):
        strategy_results = [
            {
                "strategy": "balanced",
                "codes_count": 5,
                "result": _backtest_result(avg_return_pct=8.0),
            }
        ]
        benchmark_results = [
            {
                "benchmark": "沪深300",
                "code": "sh000300",
                "result": _backtest_result(avg_return_pct=3.0),
            }
        ]
        report = format_report(strategy_results, benchmark_results, ["sh600519"])
        # alpha = 8.0 - 3.0 = 5.0
        assert "alpha = +5.00%" in report

    def test_no_alpha_when_strategy_error(self):
        strategy_results = [{"strategy": "balanced", "codes_count": 5, "error": "fail"}]
        benchmark_results = [
            {"benchmark": "沪深300", "code": "sh000300", "result": _backtest_result()}
        ]
        report = format_report(strategy_results, benchmark_results, ["sh600519"])
        assert "alpha" not in report

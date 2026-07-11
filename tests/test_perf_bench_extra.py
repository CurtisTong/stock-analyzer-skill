"""perf_bench.py 补充测试：bench_screener / bench_backtest / main。

覆盖 bench_screener（正常 / stdev 计算）、bench_backtest（正常 / error）、
main()（screener / backtest / all / save 子命令）。
所有 screener/backtest 均 mock。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ═══════════════════════════════════════════════════════════════
# bench_screener
# ═══════════════════════════════════════════════════════════════


class TestBenchScreener:
    def test_returns_metrics_dict(self):
        from perf_bench import bench_screener

        with patch("screener.analyze_code", return_value={"score": 75.0}):
            result = bench_screener(["sh600519"], rounds=2)
        assert result["module"] == "screener.analyze_code"
        assert result["codes"] == 1
        assert result["rounds"] == 2
        assert "total_seconds" in result
        assert "avg_per_round" in result
        assert "per_stock_ms" in result

    def test_stdev_with_multiple_rounds(self):
        from perf_bench import bench_screener

        with patch("screener.analyze_code", return_value={}):
            result = bench_screener(["sh600519", "sh600000"], rounds=3)
        assert result["stdev"] >= 0
        assert result["codes"] == 2

    def test_single_round_stdev_zero(self):
        from perf_bench import bench_screener

        with patch("screener.analyze_code", return_value={}):
            result = bench_screener(["sh600519"], rounds=1)
        assert result["stdev"] == 0


# ═══════════════════════════════════════════════════════════════
# bench_backtest
# ═══════════════════════════════════════════════════════════════


class TestBenchBacktest:
    def test_returns_metrics_dict(self):
        from perf_bench import bench_backtest

        mock_report = {
            "total_return_pct": 10.0,
            "sharpe_ratio": 1.5,
            "win_rate_pct": 60.0,
        }
        with patch("backtest.run_backtest", return_value=mock_report):
            result = bench_backtest(["sh600519"], rounds=2)
        assert result["module"] == "backtest.run_backtest"
        assert result["codes"] == 1
        assert result["rounds"] == 2
        assert "total_seconds" in result

    def test_error_returns_early(self):
        """run_backtest 返回 error 时提前返回。"""
        from perf_bench import bench_backtest

        with patch("backtest.run_backtest", return_value={"error": "no data"}):
            result = bench_backtest(["sh600519"], rounds=3)
        assert "error" in result
        assert result["error"] == "no data"
        assert "durations" in result


# ═══════════════════════════════════════════════════════════════
# main()
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_command_prints_help(self, capsys):
        """无子命令时 print_help（mock parse_args 避免 args.codes 崩溃）。"""
        from perf_bench import main

        mock_args = MagicMock()
        mock_args.command = None
        mock_args.codes = "sh600519"
        mock_args.rounds = 1
        with patch("perf_bench.argparse.ArgumentParser.parse_args", return_value=mock_args):
            main()
        out = capsys.readouterr().out
        assert "screener" in out or "backtest" in out or "usage" in out.lower()

    def test_screener_command(self, capsys):
        from perf_bench import main

        with patch("sys.argv", ["perf_bench.py", "screener", "--codes", "sh600519", "--rounds", "1"]), \
             patch("screener.analyze_code", return_value={}):
            main()
        out = capsys.readouterr().out
        assert "[screener]" in out

    def test_backtest_command(self, capsys):
        from perf_bench import main

        mock_report = {"total_return_pct": 5.0, "sharpe_ratio": 1.0, "win_rate_pct": 50.0}
        with patch("sys.argv", ["perf_bench.py", "backtest", "--codes", "sh600519", "--rounds", "1"]), \
             patch("backtest.run_backtest", return_value=mock_report):
            main()
        out = capsys.readouterr().out
        assert "[backtest]" in out

    def test_all_command(self, capsys):
        from perf_bench import main

        mock_report = {"total_return_pct": 5.0, "sharpe_ratio": 1.0, "win_rate_pct": 50.0}
        with patch("sys.argv", ["perf_bench.py", "all", "--codes", "sh600519", "--rounds", "1"]), \
             patch("screener.analyze_code", return_value={}), \
             patch("backtest.run_backtest", return_value=mock_report):
            main()
        out = capsys.readouterr().out
        assert "[screener]" in out
        assert "[backtest]" in out

    def test_save_command_writes_file(self, tmp_path, capsys):
        """save 子命令写入 perf_benchmarks.json。"""
        from perf_bench import main

        out_path = tmp_path / "perf_benchmarks.json"
        mock_report = {"total_return_pct": 5.0, "sharpe_ratio": 1.0, "win_rate_pct": 50.0}
        with patch("sys.argv", ["perf_bench.py", "save", "--codes", "sh600519", "--rounds", "1"]), \
             patch("screener.analyze_code", return_value={}), \
             patch("backtest.run_backtest", return_value=mock_report), \
             patch("common.DATA_DIR", str(tmp_path)):
            main()
        assert out_path.exists()
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert "version" in data
        assert "results" in data
        assert "screener" in data["results"]
        assert "backtest" in data["results"]

    def test_backtest_command_error_output(self, capsys):
        """backtest 返回 error 时打印 ERROR。"""
        from perf_bench import main

        with patch("sys.argv", ["perf_bench.py", "backtest", "--codes", "sh600519", "--rounds", "1"]), \
             patch("backtest.run_backtest", return_value={"error": "fail"}):
            main()
        out = capsys.readouterr().out
        assert "ERROR" in out
        assert "fail" in out

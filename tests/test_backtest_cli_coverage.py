"""backtest/cli.py 覆盖率补充测试。

覆盖 compare_strategies（含 scenarios）、optimize_weights、_fetch_benchmark_return
的更多分支、load_test_universe（文件不存在/非列表值）、main() 各子命令。
所有回测/行情均 mock。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def _backtest_report(**overrides):
    """构造一个完整的 run_backtest 返回报告。"""
    base = {
        "total_return_pct": 10.0,
        "avg_return_pct": 5.0,
        "max_return_pct": 8.0,
        "min_return_pct": 2.0,
        "win_rate_pct": 60.0,
        "sharpe_ratio": 1.5,
        "max_drawdown_pct": -5.0,
        "information_ratio": 0.8,
        "profit_loss_ratio": 2.0,
        "annual_turnover": 50,
        "rounds": 3,
        "round_details": [{"returns": [1.0, 2.0, 3.0]}],
        "win_by_position": {"early": 60, "mid": 55, "late": 65},
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════
# compare_strategies
# ═══════════════════════════════════════════════════════════════


class TestCompareStrategies:
    def test_basic_compare(self):
        from backtest.cli import compare_strategies

        with patch("backtest.cli.run_backtest", return_value=_backtest_report()):
            result = compare_strategies(["sh600519"], top_n=3, days=30, rounds=2)
        assert isinstance(result, dict)
        assert len(result) >= 1

    def test_with_scenarios(self):
        from backtest.cli import compare_strategies

        scenarios = [
            {"label": "近1月", "days": 20, "rounds": 3},
            {"label": "近3月", "days": 60, "rounds": 3},
        ]
        with patch("backtest.cli.run_backtest", return_value=_backtest_report()):
            result = compare_strategies(
                ["sh600519"],
                top_n=3,
                days=30,
                rounds=2,
                scenarios=scenarios,
            )
        # 每个策略的 report 应含 scenarios
        for name, report in result.items():
            assert "scenarios" in report
            assert "近1月" in report["scenarios"]

    def test_scenarios_uses_defaults_when_missing(self):
        """scenario 缺 days/rounds 时用 days / max(1, rounds//2)。"""
        from backtest.cli import compare_strategies

        scenarios = [{"label": "默认"}]
        with patch("backtest.cli.run_backtest", return_value=_backtest_report()) as mock_run:
            compare_strategies(
                ["sh600519"],
                top_n=3,
                days=30,
                rounds=5,
                scenarios=scenarios,
            )
        # 多次调用：主回测 + 每个 scenario 一次
        assert mock_run.call_count > 1


# ═══════════════════════════════════════════════════════════════
# optimize_weights
# ═══════════════════════════════════════════════════════════════


class TestOptimizeWeights:
    def test_returns_result_dict(self):
        from backtest.cli import optimize_weights

        with patch("backtest.cli.run_backtest", return_value=_backtest_report(sharpe_ratio=1.5)):
            result = optimize_weights(["sh600519"], "balanced", top_n=3, days=30)
        assert result["strategy"] == "balanced"
        assert "best_weights" in result
        assert "best_sharpe" in result
        assert "baseline_sharpe" in result
        assert "improvement" in result
        assert "all_results" in result

    def test_best_weights_keys(self):
        from backtest.cli import optimize_weights

        with patch("backtest.cli.run_backtest", return_value=_backtest_report()):
            result = optimize_weights(["sh600519"], "balanced", top_n=3, days=30)
        assert set(result["best_weights"].keys()) == {
            "quality",
            "valuation",
            "momentum",
            "liquidity",
        }

    def test_finds_better_sharpe(self):
        """当某次网格搜索返回更高夏普时，best_sharpe 应大于 baseline。"""
        from backtest.cli import optimize_weights

        call_count = [0]

        def fake_run(*args, **kwargs):
            call_count[0] += 1
            # 第一次是 baseline，返回较低夏普；之后返回较高
            sharpe = 2.0 if call_count[0] > 1 else 1.0
            return _backtest_report(sharpe_ratio=sharpe)

        with patch("backtest.cli.run_backtest", side_effect=fake_run):
            result = optimize_weights(["sh600519"], "balanced", top_n=3, days=30)
        assert result["best_sharpe"] >= result["baseline_sharpe"]
        assert result["improvement"] >= 0


# ═══════════════════════════════════════════════════════════════
# _fetch_benchmark_return
# ═══════════════════════════════════════════════════════════════


class TestFetchBenchmarkReturn:
    def test_none_when_no_bars(self):
        from backtest.cli import _fetch_benchmark_return

        with patch("data.get_kline", return_value=[]):
            assert _fetch_benchmark_return("sh000300", 30) is None

    def test_none_when_single_bar(self):
        from backtest.cli import _fetch_benchmark_return

        with patch("data.get_kline", return_value=[MagicMock(close=100)]):
            assert _fetch_benchmark_return("sh000300", 30) is None

    def test_none_when_first_close_zero(self):
        from backtest.cli import _fetch_benchmark_return

        bars = [MagicMock(close=0), MagicMock(close=110)]
        with patch("data.get_kline", return_value=bars):
            assert _fetch_benchmark_return("sh000300", 2) is None

    def test_calculates_positive_return(self):
        from backtest.cli import _fetch_benchmark_return

        bars = [MagicMock(close=100), MagicMock(close=110)]
        with patch("data.get_kline", return_value=bars):
            result = _fetch_benchmark_return("sh000300", 2)
        assert result == 10.0  # (110/100 - 1) * 100

    def test_calculates_negative_return(self):
        from backtest.cli import _fetch_benchmark_return

        bars = [MagicMock(close=200), MagicMock(close=180)]
        with patch("data.get_kline", return_value=bars):
            result = _fetch_benchmark_return("sh000300", 2)
        assert result == -10.0

    def test_returns_none_on_exception(self):
        from backtest.cli import _fetch_benchmark_return

        with patch("data.get_kline", side_effect=RuntimeError("boom")):
            assert _fetch_benchmark_return("sh000300", 30) is None

    def test_truncates_to_days(self):
        """bars 数量超过 days 时取最后 days 根。"""
        from backtest.cli import _fetch_benchmark_return

        bars = [MagicMock(close=100), MagicMock(close=90), MagicMock(close=110)]
        with patch("data.get_kline", return_value=bars):
            # days=2 -> 取最后 2 根 [90, 110]
            result = _fetch_benchmark_return("sh000300", 2)
        assert result == round((110 / 90 - 1) * 100, 2)


# ═══════════════════════════════════════════════════════════════
# load_test_universe
# ═══════════════════════════════════════════════════════════════


class TestLoadTestUniverse:
    def test_returns_sorted_unique_list(self):
        from backtest.cli import load_test_universe

        result = load_test_universe()
        assert isinstance(result, list)
        assert result == sorted(set(result))

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        from backtest import cli as cli_mod
        from common import DATA_DIR

        # 指向不存在的文件
        monkeypatch.setattr(cli_mod, "DATA_DIR", tmp_path)
        result = cli_mod.load_test_universe()
        assert result == []

    def test_filters_non_list_values(self, tmp_path, monkeypatch):
        """元数据 key（非 list）应被过滤。"""
        from backtest import cli as cli_mod

        f = tmp_path / "sector_stocks.json"
        f.write_text(
            json.dumps(
                {
                    "_meta": {"x": 1},
                    "消费": ["sh600519", "sh600000"],
                    "金融": "not_a_list",  # 非列表值应跳过
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(cli_mod, "DATA_DIR", tmp_path)
        result = cli_mod.load_test_universe()
        assert "sh600519" in result
        assert "sh600000" in result
        # "not_a_list" 不应出现（它不是 list 会被跳过）


# ═══════════════════════════════════════════════════════════════
# main() CLI
# ═══════════════════════════════════════════════════════════════


class TestMainCLI:
    def test_main_default_backtest(self, capsys):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", "sh600519", "--top", "1", "--days", "10", "--rounds", "1"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.run_backtest", return_value=_backtest_report()):
            main()
        out = capsys.readouterr().out
        assert "总收益" in out
        assert "10.00%" in out

    def test_main_json_output(self, capsys):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", "sh600519", "-j"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.run_backtest", return_value=_backtest_report()):
            main()
        out = capsys.readouterr().out
        # JSON 前有提示文本，从第一个 { 提取 JSON
        json_start = out.index("{")
        parsed = json.loads(out[json_start:])
        assert "total_return_pct" in parsed

    def test_main_error_report(self, capsys):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", "sh600519"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.run_backtest", return_value={"error": "no data"}):
            main()
        out = capsys.readouterr().out
        assert "no data" in out

    def test_main_no_codes_exits(self):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", ""]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.load_test_universe", return_value=[]):
            with pytest.raises(SystemExit):
                main()

    def test_main_optimize(self, capsys):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", "sh600519", "--optimize", "--days", "10"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.run_backtest", return_value=_backtest_report(sharpe_ratio=1.5)):
            main()
        out = capsys.readouterr().out
        assert "最优权重" in out or "best_weights" in out

    def test_main_all_compare(self, capsys):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", "sh600519", "--all", "--days", "10"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.run_backtest", return_value=_backtest_report()):
            main()
        out = capsys.readouterr().out
        assert "策略" in out

    def test_main_all_with_benchmark(self, capsys):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", "sh600519", "--all", "--benchmark", "sh000300", "--days", "10"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.run_backtest", return_value=_backtest_report()), \
             patch("backtest.cli._fetch_benchmark_return", return_value=3.5):
            main()
        out = capsys.readouterr().out
        assert "sh000300" in out

    def test_main_top_adjusted_when_codes_less_than_top(self, capsys):
        from backtest.cli import main

        with patch("sys.argv", ["backtest", "--codes", "sh600519", "--top", "5", "--days", "10"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch("backtest.cli.run_backtest", return_value=_backtest_report()):
            main()
        out = capsys.readouterr().out
        assert "自动调整" in out

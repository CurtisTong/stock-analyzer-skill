"""strategy_performance.py 补充测试：record_all / _load / _save / main。

覆盖 record_all（成功 / 无股票池 / 单策略 error）、_load（文件不存在 / 存在）、
_save（原子写）、main() 的 record / report / compare 子命令。
所有 run_backtest / 文件 I/O 均 mock。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategy_performance import (
    record_all,
    report,
    compare,
    _load,
    _save,
    PERFORMANCE_FILE,
)


def _backtest_result(**overrides):
    base = {
        "total_return_pct": 10.0,
        "sharpe_ratio": 1.5,
        "max_drawdown_pct": -5.0,
        "win_rate_pct": 60.0,
        "annual_turnover": 50,
        "profit_loss_ratio": 2.0,
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════
# record_all
# ═══════════════════════════════════════════════════════════════


class TestRecordAll:
    def test_no_codes_returns_error(self):
        """无股票池时返回 error。"""
        with patch("strategy_performance.load_test_universe", return_value=[]):
            result = record_all()
        assert "error" in result

    def test_records_all_strategies(self, tmp_path):
        """正常记录所有策略。"""
        with (
            patch("strategy_performance.load_test_universe", return_value=["sh600519"]),
            patch("strategy_performance.run_backtest", return_value=_backtest_result()),
            patch("strategy_performance._load", return_value={"records": []}),
            patch("strategy_performance._save") as mock_save,
        ):
            result = record_all(days=30, top=3)
        assert "strategies" in result
        assert "timestamp" in result
        assert "date" in result
        assert "month" in result
        assert result["pool_size"] == 1
        mock_save.assert_called_once()

    def test_strategy_error_recorded(self):
        """单策略 error 时记录到 strategies。"""

        def fake_run(name, *args, **kwargs):
            if name == "balanced":
                return {"error": "no data"}
            return _backtest_result()

        with (
            patch("strategy_performance.load_test_universe", return_value=["sh600519"]),
            patch("strategy_performance.run_backtest", side_effect=fake_run),
            patch("strategy_performance._load", return_value={"records": []}),
            patch("strategy_performance._save"),
        ):
            result = record_all(days=30, top=3)
        assert "error" in result["strategies"]["balanced"]

    def test_custom_codes_used(self):
        """传入 codes 时不调用 load_test_universe。"""
        with (
            patch("strategy_performance.load_test_universe") as mock_load,
            patch("strategy_performance.run_backtest", return_value=_backtest_result()),
            patch("strategy_performance._load", return_value={"records": []}),
            patch("strategy_performance._save"),
        ):
            result = record_all(codes=["sh600519", "sh600000"])
        mock_load.assert_not_called()
        assert result["pool_size"] == 2

    def test_record_appended_to_existing(self):
        """新记录追加到已有 records。"""
        existing = {"records": [{"month": "2026-06", "strategies": {}}]}
        with (
            patch("strategy_performance.load_test_universe", return_value=["sh600519"]),
            patch("strategy_performance.run_backtest", return_value=_backtest_result()),
            patch("strategy_performance._load", return_value=existing),
            patch("strategy_performance._save") as mock_save,
        ):
            record_all(days=30, top=3)
        saved_data = mock_save.call_args[0][0]
        assert len(saved_data["records"]) == 2  # 原有 1 + 新增 1


# ═══════════════════════════════════════════════════════════════
# _load / _save
# ═══════════════════════════════════════════════════════════════


class TestLoadSave:
    def test_load_missing_file(self, tmp_path, monkeypatch):
        """文件不存在时返回空 records。"""
        monkeypatch.setattr(
            "strategy_performance.PERFORMANCE_FILE", tmp_path / "nope.json"
        )
        result = _load()
        assert result == {"records": []}

    def test_load_existing_file(self, tmp_path, monkeypatch):
        f = tmp_path / "perf.json"
        f.write_text(json.dumps({"records": [{"month": "2026-06"}]}), encoding="utf-8")
        monkeypatch.setattr("strategy_performance.PERFORMANCE_FILE", f)
        result = _load()
        assert len(result["records"]) == 1

    def test_save_writes_file(self, tmp_path, monkeypatch):
        f = tmp_path / "perf.json"
        monkeypatch.setattr("strategy_performance.PERFORMANCE_FILE", f)
        with patch("strategy_performance.atomic_write_json") as mock_write:
            _save({"records": [{"month": "2026-07"}]})
        mock_write.assert_called_once()
        args = mock_write.call_args[0]
        assert args[0] == f


# ═══════════════════════════════════════════════════════════════
# compare：补充分支
# ═══════════════════════════════════════════════════════════════


class TestCompareExtra:
    def test_empty_ranking_returns_none_best_worst(self):
        """无有效数据时 best/worst 为 None。"""
        with patch("strategy_performance._load", return_value={"records": []}):
            result = compare(metric="sharpe_ratio")
        assert result["best"] is None
        assert result["worst"] is None
        assert result["spread"] == 0

    def test_ranking_with_data(self):
        """有数据时生成排名。"""
        records = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {"sharpe_ratio": 1.5},
                        "quality_value": {"sharpe_ratio": 2.0},
                    },
                }
            ]
        }
        with patch("strategy_performance._load", return_value=records):
            result = compare(metric="sharpe_ratio")
        assert result["best"] == "quality_value"
        assert result["worst"] == "balanced"
        assert result["spread"] == 0.5

    def test_skip_strategy_with_error(self):
        """含 error 的策略被跳过。"""
        records = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {"sharpe_ratio": 1.5},
                        "quality_value": {"error": "fail"},
                    },
                }
            ]
        }
        with patch("strategy_performance._load", return_value=records):
            result = compare(metric="sharpe_ratio")
        names = [r["strategy"] for r in result["ranking"]]
        assert "balanced" in names
        assert "quality_value" not in names

    def test_ranking_includes_label_and_runs(self):
        records = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {"balanced": {"sharpe_ratio": 1.5}},
                }
            ]
        }
        with patch("strategy_performance._load", return_value=records):
            result = compare(metric="sharpe_ratio")
        for r in result["ranking"]:
            assert "label" in r
            assert "runs" in r


# ═══════════════════════════════════════════════════════════════
# report：补充分支
# ═══════════════════════════════════════════════════════════════


class TestReportExtra:
    def test_latest_record_returned(self):
        records = {
            "records": [
                {
                    "month": "2026-05",
                    "strategies": {"balanced": {"total_return_pct": 5.0}},
                },
                {
                    "month": "2026-06",
                    "strategies": {"balanced": {"total_return_pct": 10.0}},
                },
            ]
        }
        with patch("strategy_performance._load", return_value=records):
            result = report()
        assert result["latest"]["month"] == "2026-06"

    def test_skip_records_with_none_values(self):
        """total_return_pct 为 None 的记录不参与聚合（不追加到 runs）。"""
        records = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {"total_return_pct": None, "sharpe_ratio": 1.0}
                    },
                }
            ]
        }
        with patch("strategy_performance._load", return_value=records):
            result = report(month="2026-06")
        agg = result["by_month"]["2026-06"]
        # balanced 的 runs 为空（total_return_pct=None 不追加），不参与聚合
        assert "balanced" not in agg


# ═══════════════════════════════════════════════════════════════
# main()
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_main_record(self, capsys):
        with (
            patch(
                "sys.argv",
                [
                    "strategy_performance.py",
                    "record",
                    "--codes",
                    "sh600519",
                    "--days",
                    "30",
                ],
            ),
            patch(
                "strategy_performance.record_all",
                return_value={
                    "strategies": {
                        "balanced": {
                            "total_return_pct": 10.0,
                            "sharpe_ratio": 1.5,
                            "win_rate_pct": 60.0,
                        }
                    }
                },
            ),
        ):
            from strategy_performance import main

            main()
        out = capsys.readouterr().out
        assert "已记录" in out

    def test_main_record_error(self, capsys):
        with (
            patch("sys.argv", ["strategy_performance.py", "record"]),
            patch("strategy_performance.record_all", return_value={"error": "no pool"}),
        ):
            from strategy_performance import main

            main()
        out = capsys.readouterr().out
        assert "no pool" in out

    def test_main_report(self, capsys):
        report_result = {
            "by_month": {
                "2026-06": {
                    "balanced": {
                        "runs": 2,
                        "total_return_pct": 10.0,
                        "sharpe_ratio": 1.5,
                        "win_rate_pct": 60.0,
                    }
                }
            },
            "latest": {"month": "2026-06"},
        }
        with (
            patch("sys.argv", ["strategy_performance.py", "report"]),
            patch("strategy_performance.report", return_value=report_result),
        ):
            from strategy_performance import main

            main()
        out = capsys.readouterr().out
        assert "2026-06" in out

    def test_main_report_json(self, capsys):
        report_result = {"by_month": {}, "latest": None}
        with (
            patch("sys.argv", ["strategy_performance.py", "report", "-j"]),
            patch("strategy_performance.report", return_value=report_result),
        ):
            from strategy_performance import main

            main()
        out = capsys.readouterr().out
        json_start = out.index("{")
        parsed = json.loads(out[json_start:])
        assert "by_month" in parsed

    def test_main_compare(self, capsys):
        compare_result = {
            "metric": "sharpe_ratio",
            "ranking": [
                {"strategy": "balanced", "label": "均衡", "value": 1.5, "runs": 2}
            ],
            "best": "balanced",
            "worst": "balanced",
            "spread": 0,
        }
        with (
            patch("sys.argv", ["strategy_performance.py", "compare"]),
            patch("strategy_performance.compare", return_value=compare_result),
        ):
            from strategy_performance import main

            main()
        out = capsys.readouterr().out
        assert "最佳" in out
        assert "balanced" in out

    def test_main_compare_json(self, capsys):
        compare_result = {
            "metric": "sharpe_ratio",
            "ranking": [],
            "best": None,
            "worst": None,
            "spread": 0,
        }
        with (
            patch("sys.argv", ["strategy_performance.py", "compare", "-j"]),
            patch("strategy_performance.compare", return_value=compare_result),
        ):
            from strategy_performance import main

            main()
        out = capsys.readouterr().out
        json_start = out.index("{")
        parsed = json.loads(out[json_start:])
        assert parsed["metric"] == "sharpe_ratio"

    def test_main_no_command_prints_help(self, capsys):
        with patch("sys.argv", ["strategy_performance.py"]):
            from strategy_performance import main

            main()
        out = capsys.readouterr().out
        assert "record" in out or "compare" in out

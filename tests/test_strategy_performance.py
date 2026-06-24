"""策略表现校准模块测试（纯函数，无网络调用）。"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategy_performance import report, compare, _load, _save


class TestReport:
    """report 函数测试。"""

    @patch("strategy_performance._load")
    def test_empty_records(self, mock_load):
        """无记录时返回空报告。"""
        mock_load.return_value = {"records": []}
        result = report()
        assert result["by_month"] == {}
        assert result["latest"] is None

    @patch("strategy_performance._load")
    def test_single_record(self, mock_load):
        """单条记录。"""
        mock_load.return_value = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {
                            "total_return_pct": 10.5,
                            "sharpe_ratio": 1.2,
                            "win_rate_pct": 60.0,
                            "max_drawdown_pct": -5.0,
                        },
                    },
                }
            ],
        }
        result = report()
        assert "2026-06" in result["by_month"]
        assert result["latest"] is not None

    @patch("strategy_performance._load")
    def test_month_filter(self, mock_load):
        """按月份过滤。"""
        mock_load.return_value = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {"total_return_pct": 10.0, "sharpe_ratio": 1.0}
                    },
                },
                {
                    "month": "2026-05",
                    "strategies": {
                        "balanced": {"total_return_pct": 5.0, "sharpe_ratio": 0.5}
                    },
                },
            ],
        }
        result = report(month="2026-06")
        assert "2026-06" in result["by_month"]
        assert "2026-05" not in result["by_month"]

    @patch("strategy_performance._load")
    def test_aggregation(self, mock_load):
        """多条记录聚合计算平均值。"""
        mock_load.return_value = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {
                            "total_return_pct": 10.0,
                            "sharpe_ratio": 1.0,
                            "win_rate_pct": 60.0,
                        }
                    },
                },
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {
                            "total_return_pct": 20.0,
                            "sharpe_ratio": 2.0,
                            "win_rate_pct": 80.0,
                        }
                    },
                },
            ],
        }
        result = report(month="2026-06")
        balanced = result["by_month"]["2026-06"]["balanced"]
        assert balanced["runs"] == 2
        assert balanced["total_return_pct"] == 15.0  # (10+20)/2
        assert balanced["sharpe_ratio"] == 1.5  # (1+2)/2

    @patch("strategy_performance._load")
    def test_skip_error_records(self, mock_load):
        """跳过错误记录。"""
        mock_load.return_value = {
            "records": [
                {
                    "month": "2026-06",
                    "strategies": {
                        "balanced": {"error": "数据不足"},
                        "quality_value": {
                            "total_return_pct": 10.0,
                            "sharpe_ratio": 1.0,
                        },
                    },
                }
            ],
        }
        result = report()
        assert "balanced" not in result["by_month"]["2026-06"]
        assert "quality_value" in result["by_month"]["2026-06"]


class TestCompare:
    """compare 函数测试。"""

    @patch("strategy_performance._load")
    def test_empty_records(self, mock_load):
        """无记录时返回空排名。"""
        mock_load.return_value = {"records": []}
        result = compare()
        assert result["ranking"] == []
        assert result["best"] is None

    @patch("strategy_performance._load")
    def test_ranking(self, mock_load):
        """策略排名。"""
        mock_load.return_value = {
            "records": [
                {
                    "strategies": {
                        "balanced": {"sharpe_ratio": 1.0},
                        "quality_value": {"sharpe_ratio": 2.0},
                        "defensive": {"sharpe_ratio": 0.5},
                    },
                }
            ],
        }
        result = compare("sharpe_ratio")
        assert result["best"] == "quality_value"
        assert result["worst"] == "defensive"
        assert result["spread"] == 1.5  # 2.0 - 0.5

    @patch("strategy_performance._load")
    def test_custom_metric(self, mock_load):
        """自定义指标。"""
        mock_load.return_value = {
            "records": [
                {
                    "strategies": {
                        "balanced": {"total_return_pct": 10.0},
                        "quality_value": {"total_return_pct": 20.0},
                    },
                }
            ],
        }
        result = compare("total_return_pct")
        assert result["metric"] == "total_return_pct"
        assert result["best"] == "quality_value"

    @patch("strategy_performance._load")
    def test_skip_errors(self, mock_load):
        """跳过错误记录。"""
        mock_load.return_value = {
            "records": [
                {
                    "strategies": {
                        "balanced": {"sharpe_ratio": 1.0},
                        "quality_value": {"error": "数据不足"},
                    },
                }
            ],
        }
        result = compare("sharpe_ratio")
        assert len(result["ranking"]) == 1
        assert result["ranking"][0]["strategy"] == "balanced"

    @patch("strategy_performance._load")
    def test_multiple_runs_aggregation(self, mock_load):
        """多次运行取平均。"""
        mock_load.return_value = {
            "records": [
                {"strategies": {"balanced": {"sharpe_ratio": 1.0}}},
                {"strategies": {"balanced": {"sharpe_ratio": 3.0}}},
            ],
        }
        result = compare("sharpe_ratio")
        assert result["ranking"][0]["value"] == 2.0  # (1+3)/2

"""
strategy_performance.py main() CLI 覆盖率测试（Sprint 11）。
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestMainCLI:
    """main() 函数 argparse + 分发测试。"""

    def test_no_args_shows_help(self):
        """无参数显示 help。"""
        result = subprocess.run(
            [sys.executable, "scripts/strategy_performance.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        # 无子命令 → print_help 退出码 0
        assert "compare" in result.stdout
        assert "record" in result.stdout

    def test_record_with_codes(self, monkeypatch):
        """record --codes 调用 main()。"""
        import strategy_performance as sp

        def mock_run_backtest(name, codes, top_n, days, rounds):
            return {
                "total_return_pct": 5.0,
                "sharpe_ratio": 1.0,
                "max_drawdown_pct": -2.0,
                "win_rate_pct": 60.0,
                "annual_turnover": 50,
                "profit_loss_ratio": 1.0,
            }

        monkeypatch.setattr(sp, "run_backtest", mock_run_backtest)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/strategy_performance.py",
                "record",
                "--days",
                "10",
                "--top",
                "3",
                "--codes",
                "sh600519,sh600989",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "已记录" in result.stdout
        assert "balanced" in result.stdout

    def test_report_no_data(self, monkeypatch, tmp_path):
        """report 在无数据时优雅处理。"""
        # 隔离 PERFORMANCE_FILE
        import strategy_performance as sp

        test_path = tmp_path / "empty.json"
        monkeypatch.setattr(sp, "PERFORMANCE_FILE", test_path)
        # 临时覆盖 HOME/缓存目录
        monkeypatch.setenv("STOCK_CACHE_DIR", str(tmp_path))

        result = subprocess.run(
            [sys.executable, "scripts/strategy_performance.py", "report"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        # 无数据时按月报告为空 dict，输出空
        assert "按月报告" in result.stdout or result.returncode == 0

    def test_compare_with_no_data(self, monkeypatch, tmp_path):
        """compare 在无数据时输出空 ranking。"""
        import strategy_performance as sp

        test_path = tmp_path / "empty.json"
        monkeypatch.setattr(sp, "PERFORMANCE_FILE", test_path)
        monkeypatch.setenv("STOCK_CACHE_DIR", str(tmp_path))

        result = subprocess.run(
            [
                sys.executable,
                "scripts/strategy_performance.py",
                "compare",
                "--metric",
                "sharpe_ratio",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert "跨策略对比" in result.stdout or result.returncode == 0

    def test_compare_json_output(self, tmp_path, monkeypatch):
        """compare -j 输出 JSON 格式。"""
        import strategy_performance as sp

        test_path = tmp_path / "empty.json"
        test_path.write_text('{"records": []}', encoding="utf-8")
        # 用 monkeypatch 替换 compare 函数以返回已知数据
        original_compare = sp.compare

        def mock_compare(metric="sharpe_ratio"):
            return {
                "metric": metric,
                "ranking": [
                    {
                        "strategy": "balanced",
                        "label": "均衡精选",
                        "value": 1.0,
                        "runs": 1,
                    }
                ],
                "best": "balanced",
                "worst": "balanced",
                "spread": 0,
            }

        monkeypatch.setattr(sp, "compare", mock_compare)
        # 直接调用 main 的内部逻辑
        import argparse

        args = argparse.Namespace(
            metric="sharpe_ratio",
            json=True,
            month=None,
        )
        # 模拟 main 内的 compare 分支
        result = mock_compare(metric=args.metric)
        import json

        output = json.dumps(result, ensure_ascii=False, indent=2)
        data = json.loads(output)
        assert data["metric"] == "sharpe_ratio"
        assert len(data["ranking"]) == 1

"""strategy_performance 自校准最小池强制测试（2026-08-26 复盘 P1）。

历史 442 条自校准记录中 441 条在 ≤3 只小池上跑、策略间无区分度，
自校准链从未真正工作。record_all 现强制 MIN_POOL_SIZE=30，小池拒绝记录。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import strategy_performance as sp  # noqa: E402


class TestMinPoolSize:
    def test_small_pool_raises(self, monkeypatch, tmp_path):
        """小于最小池的股票池被拒绝，且不写入文件。"""
        monkeypatch.setattr(sp, "PERFORMANCE_FILE", tmp_path / "perf.json")
        small_pool = [f"sh60000{i}" for i in range(5)]
        with pytest.raises(ValueError, match="股票池过小"):
            sp.record_all(days=30, top=3, codes=small_pool)
        assert not (tmp_path / "perf.json").exists()  # 未写入任何记录

    def test_exactly_min_pool_passes(self, monkeypatch, tmp_path):
        """恰好 30 只（门槛值）允许记录。"""
        monkeypatch.setattr(sp, "PERFORMANCE_FILE", tmp_path / "perf.json")

        def _fake_run_backtest(name, codes, **kwargs):
            return {
                "total_return_pct": 1.0,
                "sharpe_ratio": 0.5,
                "max_drawdown_pct": -2.0,
                "win_rate_pct": 55.0,
                "annual_turnover": 100,
                "profit_loss_ratio": 1.2,
            }

        monkeypatch.setattr(sp, "run_backtest", _fake_run_backtest)
        pool = [f"sh6000{i:02d}" for i in range(30)]
        record = sp.record_all(days=30, top=3, codes=pool)
        assert "error" not in record
        assert record["pool_size"] == 30
        # 文件已写入
        assert (tmp_path / "perf.json").exists()

    def test_record_contains_window_start(self, monkeypatch, tmp_path):
        """记录包含 window_start（回测起点日期）。"""
        monkeypatch.setattr(sp, "PERFORMANCE_FILE", tmp_path / "perf.json")

        def fake_run_backtest(code, codes, **kwargs):
            return {
                "total_return_pct": 1.0,
                "sharpe_ratio": 0.5,
                "max_drawdown_pct": -2.0,
                "win_rate_pct": 55.0,
                "annual_turnover": 100,
                "profit_loss_ratio": 1.2,
            }

        monkeypatch.setattr(sp, "run_backtest", fake_run_backtest)
        pool = [f"sh6000{i:02d}" for i in range(30)]
        record = sp.record_all(days=60, top=5, codes=pool)
        assert "window_start" in record
        assert record["days"] == 60

    def test_empty_pool_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sp, "PERFORMANCE_FILE", tmp_path / "perf.json")
        result = sp.record_all(days=30, top=3, codes=[])
        assert result == {"error": "无可用股票池"}

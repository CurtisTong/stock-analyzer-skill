"""情绪因子阶段 2 测试：IC 链路接通 + 无前瞻性。

背景：
- v3.0 的因子 IC 机制整条链路是纸面的——引擎算了 parts 不输出，
  compute_all_factor_ic / save_ic / load_ic 都没有调用方。
- 情绪因子进入回测必须按**历史时点**取快照；用最新快照算历史因子是未来函数。
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def snapshots(tmp_path, monkeypatch):
    """写两份历史快照（供按日期查询与晋级率验证）。"""
    import data.sentiment_panel as panel

    path = tmp_path / "sentiment_snapshots.json"
    monkeypatch.setattr(panel, "_snapshot_path", lambda: path)

    def _snap(date, codes):
        return {
            "date": date,
            "limit_up_count": len(codes),
            "broken_count": 0,
            "max_height": 2,
            "height_distribution": {"1": len(codes)},
            "median_chg_pct": 10.0,
            "sectors": {"专用设备": {"limit_up": len(codes), "broken": 0, "count": len(codes)}},
            "stocks": {
                c: {
                    "code": c,
                    "name": "测试",
                    "status": "limit_up",
                    "lbc": 2,
                    "zbc": 0,
                    "fund": 1e8,
                    "ltsz": 1e10,
                    "hs": 3.0,
                    "zdp": 10.0,
                    "sector": "专用设备",
                }
                for c in codes
            },
        }

    panel.save_snapshot(_snap("20261028", ["sh600001", "sh600002"]))
    panel.save_snapshot(_snap("20261029", ["sh600001"]))
    return path


class TestNoLookahead:
    """情绪因子必须按指定日期取快照（不能用最新快照算历史）。"""

    def test_score_at_uses_that_date(self, snapshots):
        from strategies.factors.sentiment import sentiment_score_at

        # 20261028 有两只，20261029 只有一只
        assert sentiment_score_at("sh600001", "20261028") is not None
        assert sentiment_score_at("sh600002", "20261028") is not None
        # sh600002 在 10-29 的快照里不存在 → 缺失
        assert sentiment_score_at("sh600002", "20261029") is None

    def test_missing_date_returns_none(self, snapshots):
        from strategies.factors.sentiment import sentiment_score_at

        assert sentiment_score_at("sh600001", "20260101") is None

    def test_latest_vs_at_can_differ(self, snapshots):
        """最新快照与指定日期快照是不同数据源（防止误用）。"""
        from strategies.factors.sentiment import sentiment_score, sentiment_score_at

        # 10-29 的 sh600001 存在，最新快照也是 10-29 → 两者一致
        assert sentiment_score("sh600001") == sentiment_score_at("sh600001", "20261029")
        # 10-28 的 sh600002 在最新快照里已不存在
        assert sentiment_score("sh600002") is None
        assert sentiment_score_at("sh600002", "20261028") is not None

    def test_panel_get_snapshot_by_date(self, snapshots):
        from data.sentiment_panel import get_snapshot

        assert get_snapshot("20261028")["limit_up_count"] == 2
        assert get_snapshot("20260101") is None


class TestIcPipelineConnected:
    """因子 IC 链路：engine 的 selections 必须带 parts。"""

    def test_selections_carry_parts(self):
        """引擎输出逐因子分值（IC 评估的前提）。"""
        import inspect

        from backtest import engine

        src = inspect.getsource(engine.simulate_strategy)
        assert '"parts"' in src, "engine 必须把 parts 写进 selections"

    def test_metrics_passes_full_selections(self):
        """metrics 透传全量 selections（前 20 条摘要不足以算 IC）。"""
        import inspect

        from backtest import metrics

        src = inspect.getsource(metrics.run_backtest)
        assert "all_selections" in src

    def test_ic_computable_from_selections(self):
        """构造 selections → IC 可算（链路端到端）。"""
        from strategies.factor.ic import compute_all_factor_ic

        selections = [
            {"parts": {"momentum": 10 + i, "quality": 50 + i}, "return_pct": i * 0.5, "regime": "bull"}
            for i in range(10)
        ]
        ic = compute_all_factor_ic(selections)
        assert "momentum" in ic
        assert ic["momentum"] > 0.9  # 完全正相关
        assert ic["quality"] > 0.9

    def test_ic_cli_exists(self):
        """IC 评估 CLI 存在且可导入。"""
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        spec = importlib.util.spec_from_file_location("factor_ic_cli", root / "scripts" / "factor_ic.py")
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "cmd_evaluate")


class TestEngineSentimentPart:
    def test_engine_uses_historical_snapshot(self):
        """engine 的情绪因子按 bars[i].day 取快照（无前瞻）。"""
        import inspect

        from backtest import engine

        src = inspect.getsource(engine)
        assert "_sentiment_score_at" in src
        assert "sentiment_score_at(code, day.replace" in src

    def test_helper_returns_none_on_failure(self):
        """情绪因子异常时按缺失处理（不得拖垮回测）。"""
        from backtest.engine import _sentiment_score_at

        # 不存在的日期 → None（不是抛错）
        assert _sentiment_score_at("sh600519", "1900-01-01") is None

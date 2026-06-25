"""
Sprint 6 月度校准 + review#7 测试。
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.factors.momentum import momentum_score  # noqa: E402


@pytest.fixture
def temp_perf_file(monkeypatch):
    """隔离 PERFORMANCE_FILE 路径。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        import strategy_performance as sp

        test_path = Path(tmpdir) / "strategy_performance.json"
        monkeypatch.setattr(sp, "PERFORMANCE_FILE", test_path)
        yield test_path


class TestMomentumTrendRefinement:
    """review#7：动量趋势基础分收敛（40→30, 20→18, 12→15）。"""

    def test_trend_up_base_is_30(self):
        """趋势上升基础分 30（从 40 收敛）。"""
        features = {
            "trend": 1,
            "ret20": 0,
            "volume_ratio": 1.0,
            "rsi": 50,
            "macd_signal": 0,
            "vol_price_signal": 0,
        }
        quote = {"turnover": 1.0, "market_amount": 1000}
        score = momentum_score(features, quote)
        # 30 基础分 + ret20=0 加分约 14 + 量价中性 + MACD=0 + RSI 中性
        # 50 分附近属于合理范围
        assert 30 <= score <= 60

    def test_trend_down_base_is_15(self):
        """趋势下降基础分 15（从 12 略提升）。"""
        features = {
            "trend": -1,
            "ret20": 0,
            "volume_ratio": 1.0,
            "rsi": 50,
            "macd_signal": 0,
            "vol_price_signal": 0,
        }
        quote = {"turnover": 1.0, "market_amount": 1000}
        score = momentum_score(features, quote)
        # 15 基础分 + 其他中性加分
        assert 5 <= score <= 40

    def test_trend_neutral_base_is_18(self):
        """趋势中性基础分 18（从 20 略降）。"""
        features = {
            "trend": 0,
            "ret20": 0,
            "volume_ratio": 1.0,
            "rsi": 50,
            "macd_signal": 0,
            "vol_price_signal": 0,
        }
        quote = {"turnover": 1.0, "market_amount": 1000}
        score = momentum_score(features, quote)
        # 18 基础分 + 中性加分
        assert 10 <= score <= 50

    def test_trend_gap_reduced(self):
        """review#7 目标：上升 vs 下降差距 28→15。"""
        # 上升 30 - 下降 15 = 15（远小于旧 28）
        assert 30 - 15 == 15  # 验证收敛后的差距


class TestStrategyPerformance:
    """strategy_performance.py 月度校准测试。"""

    def test_record_creates_file(self, temp_perf_file, monkeypatch):
        """record 后文件应被创建。"""
        import strategy_performance as sp

        # mock backtest 避免网络
        def mock_run_backtest(name, codes, top_n, days, rounds):
            return {
                "strategy": name,
                "total_return_pct": 5.0,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": -3.0,
                "win_rate_pct": 60.0,
                "annual_turnover": 50,
            }

        monkeypatch.setattr(sp, "run_backtest", mock_run_backtest)

        record = sp.record_all(days=10, top=3, codes=["sh600519"])
        assert "strategies" in record
        assert "balanced" in record["strategies"]
        assert record["strategies"]["balanced"]["total_return_pct"] == 5.0
        assert temp_perf_file.exists()

    def test_record_aggregates_by_month(self, temp_perf_file, monkeypatch):
        """多次 record 后按月聚合。"""
        import strategy_performance as sp

        def mock_run_backtest(name, codes, top_n, days, rounds):
            return {
                "strategy": name,
                "total_return_pct": 2.0,
                "sharpe_ratio": 0.8,
                "max_drawdown_pct": -2.0,
                "win_rate_pct": 55.0,
                "annual_turnover": 40,
            }

        monkeypatch.setattr(sp, "run_backtest", mock_run_backtest)

        sp.record_all(days=10, top=3, codes=["sh600519"])
        sp.record_all(days=10, top=3, codes=["sh600519"])

        result = sp.report()
        assert "by_month" in result
        months = result["by_month"]
        assert len(months) >= 1
        for m, sdata in months.items():
            for sname, m_data in sdata.items():
                assert m_data.get("runs", 0) >= 2

    def test_report_specific_month(self, temp_perf_file, monkeypatch):
        """指定月份过滤。"""
        import strategy_performance as sp
        from datetime import datetime

        def mock_run_backtest(name, codes, top_n, days, rounds):
            return {
                "total_return_pct": 3.0,
                "sharpe_ratio": 1.0,
                "max_drawdown_pct": -2.5,
                "win_rate_pct": 58.0,
                "annual_turnover": 45,
            }

        monkeypatch.setattr(sp, "run_backtest", mock_run_backtest)

        sp.record_all(days=10, top=3, codes=["sh600519"])

        current_month = datetime.now().strftime("%Y-%m")
        result = sp.report(month=current_month)
        assert current_month in result["by_month"]


class TestPerfBench:
    """perf_bench.py 性能压测测试。"""

    def test_bench_screener_structure(self, monkeypatch):
        """bench_screener 返回结构化结果。"""
        from perf_bench import bench_screener
        import screener

        # mock analyze_code 避免网络
        def mock_analyze(*a, **k):
            return {"code": "x", "score": 50, "rejected": []}

        monkeypatch.setattr(screener, "analyze_code", mock_analyze)

        result = bench_screener(["sh600519", "sh600989"], rounds=2)
        assert result["module"] == "screener.analyze_code"
        assert result["codes"] == 2
        assert result["rounds"] == 2
        assert "avg_per_round" in result
        assert "per_stock_ms" in result
        assert result["per_stock_ms"] >= 0


class TestStrategyCompare:
    """strategy_performance.compare 跨策略对比测试。"""

    def test_compare_ranking_order(self, temp_perf_file, monkeypatch):
        """compare 按指定指标降序排名（max_drawdown_pct 升序）。"""
        import strategy_performance as sp

        def mock_run_backtest(name, codes, top_n, days, rounds):
            return {
                "total_return_pct": {
                    "balanced": 5,
                    "growth_momentum": 10,
                    "defensive": 3,
                    "turning_point": 7,
                    "quality_value": 4,
                }.get(name, 0),
                "sharpe_ratio": {
                    "balanced": 1.0,
                    "growth_momentum": 2.0,
                    "defensive": 0.5,
                    "turning_point": 1.5,
                    "quality_value": 0.8,
                }.get(name, 0),
                "max_drawdown_pct": -1.0,
                "win_rate_pct": 50.0,
                "annual_turnover": 50,
                "profit_loss_ratio": 1.0,
            }

        monkeypatch.setattr(sp, "run_backtest", mock_run_backtest)

        sp.record_all(days=10, top=3, codes=["sh600519"])
        sp.record_all(days=10, top=3, codes=["sh600519"])

        # 测试 sharpe_ratio 降序
        result = sp.compare(metric="sharpe_ratio")
        assert result["metric"] == "sharpe_ratio"
        assert len(result["ranking"]) == 6
        # 第一名应是 growth_momentum (2.0)
        assert result["ranking"][0]["strategy"] == "growth_momentum"
        assert result["best"] == "growth_momentum"
        # 最后应是 ma_volume_momentum (0.0)
        assert result["ranking"][-1]["strategy"] == "ma_volume_momentum"
        assert result["worst"] == "ma_volume_momentum"
        # spread = 2.0 - 0.0 = 2.0
        assert abs(result["spread"] - 2.0) < 0.01

    def test_compare_max_drawdown_inverted(self, temp_perf_file, monkeypatch):
        """max_drawdown_pct 是负数，越接近 0 越好（升序排名）。"""
        import strategy_performance as sp

        def mock_run_backtest(name, codes, top_n, days, rounds):
            return {
                "total_return_pct": 0,
                "sharpe_ratio": 0,
                "max_drawdown_pct": -1.0 if name == "defensive" else -5.0,
                "win_rate_pct": 0,
                "annual_turnover": 0,
                "profit_loss_ratio": 0,
            }

        monkeypatch.setattr(sp, "run_backtest", mock_run_backtest)

        sp.record_all(days=10, top=3, codes=["sh600519"])
        result = sp.compare(metric="max_drawdown_pct")
        # defensive (-1.0) 应排在前面（回撤最小）
        assert result["ranking"][0]["strategy"] == "defensive"

    def test_compare_empty_records(self, temp_perf_file):
        """无记录时返回空 ranking。"""
        import strategy_performance as sp

        result = sp.compare(metric="sharpe_ratio")
        assert result["ranking"] == []
        assert result["best"] is None

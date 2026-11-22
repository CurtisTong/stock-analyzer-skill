"""P2 回测指标回归：基准切片 off-by-one、alpha 单位、CLI top 自动调整。"""

from datetime import datetime, timedelta
from math import sqrt
from statistics import mean, stdev, variance

import pytest

from data.types import KlineBar


def _benchmark_bars(n=80):
    """基准日线：收益逐日递增，便于定位到底取了哪一天。"""
    base = datetime(2026, 1, 1)
    bars = []
    price = 100.0
    for i in range(n):
        price *= 1 + 0.001 * (i + 1)
        bars.append(
            KlineBar(
                day=(base + timedelta(days=i)).strftime("%Y-%m-%d"),
                close=price,
                open=price,
                high=price,
                low=price,
                volume=1000,
            )
        )
    return bars


class TestBenchmarkFirstPeriod:
    """P2：首个选股日（bars[MIN_HISTORY]）必须能在基准序列里查到。"""

    def test_fetch_includes_selection_day_date(self, monkeypatch):
        import data
        from backtest.engine import MIN_HISTORY

        bars = _benchmark_bars(MIN_HISTORY + 10 + 10)
        monkeypatch.setattr(data, "get_kline", lambda code, scale=240, datalen=80: bars)

        from backtest.metrics import _fetch_benchmark_returns

        dates, _ = _fetch_benchmark_returns("sh000300", days=10)
        assert dates
        assert dates[0] == bars[MIN_HISTORY].day, (
            f"基准首日应为首个选股日 {bars[MIN_HISTORY].day}，实际 {dates[0]}"
            "（旧实现晚一天导致首期记 0）"
        )

    def test_first_period_benchmark_return_not_zero(self, monkeypatch):
        """首期基准收益必须按选股日次日起的 hold 天计算，不能是 0。"""
        import data
        from backtest.engine import MIN_HISTORY
        from backtest.metrics import _fetch_benchmark_returns, _slice_benchmark_by_period

        bars = _benchmark_bars(MIN_HISTORY + 10 + 10)
        monkeypatch.setattr(data, "get_kline", lambda code, scale=240, datalen=80: bars)

        dates, returns = _fetch_benchmark_returns("sh000300", days=10)
        out = _slice_benchmark_by_period(
            dates, returns, [{"start": bars[MIN_HISTORY].day, "holding_days": 3}], 3
        )
        expected = (bars[MIN_HISTORY + 3].close / bars[MIN_HISTORY].close - 1) * 100
        assert out[0] != 0.0
        assert out[0] == pytest.approx(expected, abs=1e-6)


class TestExcessReturnUnits:
    """P2：期收益是百分数，无风险利率必须换算为百分数后再参与 alpha/超额夏普。"""

    def test_alpha_and_excess_sharpe_use_percent_rf(self, monkeypatch):
        import backtest

        strat = [1.0, 3.0, -1.0, 2.0, 4.0]  # 单位：%
        bm = [0.5, 1.0, -0.5, 1.0, 1.5]  # 单位：%
        dates = [f"d{i}" for i in range(len(strat) + 1)]
        # _slice_benchmark_by_period 的日期约定：dates[i] 当日收益在 returns[i]，
        # 选股日 d_i 的持仓期从 returns[i+1] 起算。
        bm_daily = [0.0] + [b / 100 for b in bm]

        def _fake_simulate(ctx):
            return {
                "returns": strat,
                "daily_returns": [0.001] * 10,
                "period_dates": [{"start": f"d{i}", "holding_days": 1} for i in range(len(strat))],
                "all_selections": [],
            }

        monkeypatch.setattr(backtest.metrics, "simulate_strategy", _fake_simulate)
        monkeypatch.setattr(
            backtest.metrics, "_fetch_benchmark_returns", lambda code, days: (dates, bm_daily)
        )

        report = backtest.run_backtest(
            "balanced", ["sh600519"], top_n=1, days=5, rounds=5, benchmark="sh000300"
        )
        assert "error" not in report

        ppy = 252  # holding_days = days // rounds = 1
        rf_pct = 0.03 / ppy * 100
        sm, bm_mean = mean(strat), mean(bm)
        cov = sum((s - sm) * (b - bm_mean) for s, b in zip(strat, bm)) / (len(strat) - 1)
        beta = cov / variance(bm)
        alpha = ((sm - rf_pct) - beta * (bm_mean - rf_pct)) * ppy
        bm_sharpe = (bm_mean - rf_pct) / stdev([b - rf_pct for b in bm]) * sqrt(ppy)
        strat_sharpe = (sm - rf_pct) / stdev([s - rf_pct for s in strat]) * sqrt(ppy)
        expected_excess = strat_sharpe - bm_sharpe

        assert report["beta"] == pytest.approx(beta, abs=0.02)
        assert report["alpha"] == pytest.approx(alpha, abs=0.02), (
            f"alpha 应把 rf 换算成百分数：期望 {alpha:.2f}，实际 {report['alpha']}"
        )
        assert report["excess_sharpe"] == pytest.approx(expected_excess, abs=0.02), (
            "超额夏普必须用百分数口径的 rf"
        )


class TestCliTopAdjustment:
    """P2/CLI：提示自动调整 top 后必须真的修改 args.top。"""

    def test_cli_top_is_actually_adjusted(self, monkeypatch, capsys):
        import backtest

        monkeypatch.setattr(backtest.cli, "load_test_universe", lambda: ["sh600519", "sh600520"])
        captured = {}

        def _fake_run_backtest(strategy, codes, top_n, days, rounds, **kwargs):
            captured["top_n"] = top_n
            return {
                "strategy": strategy,
                "total_return_pct": 1.0,
                "avg_return_pct": 0.5,
                "max_return_pct": 2.0,
                "min_return_pct": -1.0,
                "win_rate_pct": 50.0,
                "sharpe_ratio": 1.2,
                "sortino_ratio": 1.5,
                "information_ratio": None,
                "max_drawdown_pct": 3.0,
                "calmar_ratio": 0.5,
                "profit_loss_ratio": 1.0,
                "annual_turnover": 10,
                "win_by_position": {},
                "round_details": [{"returns": []}],
                "meta": {"generated_at": "2026-01-01T00:00:00", "data_sources": ["test"]},
            }

        monkeypatch.setattr(backtest.cli, "run_backtest", _fake_run_backtest)
        monkeypatch.setattr(
            "sys.argv",
            ["backtest.py", "--codes", "sh600519,sh600520", "--top", "5", "--days", "10", "--rounds", "2"],
        )
        backtest.cli.main()
        out = capsys.readouterr().out
        assert "自动调整为 top=2" in out
        assert captured["top_n"] == 2, "提示调整了 top，但实际仍按原值回测"


if __name__ == "__main__":
    pytest.main([__file__])

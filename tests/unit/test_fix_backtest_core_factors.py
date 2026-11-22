"""P1-13 / P1-14 / P1-17 / P2 幸存者偏差回归：回测因子的口径与可披露性。"""

from datetime import datetime, timedelta

import pytest

from data.types import KlineBar


def _bars(prices, last_day=None, volume=1000):
    """构造带 amount/volume 的 K 线；last_day 可指定以模拟陈旧股票。"""
    if last_day is None:
        last_day = datetime.now() - timedelta(days=1)
    out = []
    for i, price in enumerate(prices):
        day = (last_day - timedelta(days=len(prices) - 1 - i)).strftime("%Y-%m-%d")
        out.append(
            KlineBar(
                day=day,
                close=price,
                open=price,
                high=price,
                low=price,
                volume=volume,
                amount=price * volume,
            )
        )
    return out


def _offline_engine(monkeypatch, fin_records, code_bars):
    """替换回测所有网络依赖，返回 code_bars（{code: bars}）。"""
    import backtest

    monkeypatch.setattr(
        backtest.engine,
        "get_kline",
        lambda code, scale=240, datalen=140: code_bars.get(code, code_bars.get("default", []))[-datalen:],
    )
    monkeypatch.setattr(backtest.engine, "get_finance", lambda code: (list(fin_records), None))
    monkeypatch.setattr(backtest.engine, "_detect_st_codes", lambda codes: set())
    monkeypatch.setattr(backtest.engine, "_chip_score", lambda code, trade_day=None: 50.0)
    monkeypatch.setattr(backtest.engine, "_sentiment_score_at", lambda code, day: None)


class TestPePeriodType:
    """P1-13：PE 必须按 data.helpers.compute_pe 的报告期口径计算。"""

    def test_annual_eps_uses_direct_division(self):
        from backtest.engine import _build_hist_quote

        bars = _bars([13.0])
        result = _build_hist_quote(bars, 0, {"eps": 2.0, "period_type": "annual"}, "sh600989")
        assert result["pe"] == pytest.approx(6.5)

    def test_quarterly_eps_is_annualized(self):
        """单季 EPS 需 ×4 年化（老实现直接 price/eps，PE 高估约 4 倍）。"""
        from backtest.engine import _build_hist_quote

        bars = _bars([13.0])
        result = _build_hist_quote(bars, 0, {"eps": 2.0, "period_type": "quarterly"}, "sh600989")
        # compute_pe 内部 round 到 2 位：13 / (2*4) = 1.625 → 1.62
        assert result["pe"] == pytest.approx(1.62)

    @pytest.mark.parametrize("period_type", ["cumulative", "", "unknown"])
    def test_cumulative_or_unknown_pe_is_neutral_zero(self, period_type):
        """累计期/口径未知时 compute_pe 返回 None → 中性 0（禁止自行除）。"""
        from backtest.engine import _build_hist_quote

        bars = _bars([13.0])
        result = _build_hist_quote(bars, 0, {"eps": 2.0, "period_type": period_type}, "sh600989")
        assert result["pe"] == 0


class TestQuoteCapTurnover:
    """P1-14：市值/换手优先从可用字段推导，无法推导时显式披露降维。"""

    def test_cap_and_turnover_derived_from_finance_and_kline(self):
        """net_assets(亿)/bps 推股本 → 历史市值；volume/股本 → 换手率。"""
        from backtest.engine import _build_hist_quote

        # 净资产 100 亿、每股净资产 10 元 → 总股本 10 亿股
        fin = {"net_assets": 100.0, "bps": 10.0}
        bars = _bars([20.0], volume=100_000_000)  # 当日成交 1 亿股 → 换手 10%
        result = _build_hist_quote(bars, 0, fin, "sh600989")
        assert result["total_cap"] == pytest.approx(200.0)  # 10 亿股 × 20 元 = 200 亿
        assert result["turnover"] == pytest.approx(10.0)

    def test_legacy_finance_total_cap_still_honored(self):
        """老 dict 的 total_cap 字段仍优先使用，保持向后兼容。"""
        from backtest.engine import _build_hist_quote

        bars = _bars([13.0])
        result = _build_hist_quote(bars, 0, {"total_cap": 500}, "sh600989")
        assert result["total_cap"] == 500

    def test_result_discloses_degraded_factors(self, monkeypatch):
        """缺股本信息时不得伪造数字，simulate_strategy 要标注 factor_degradation。"""
        import backtest
        from data.types import FinanceRecord

        fin = FinanceRecord(eps=2.0, period_type="annual", roe=15.0)  # 无 net_assets/bps
        bars = _bars([10.0 + i * 0.01 for i in range(140)])
        _offline_engine(monkeypatch, [fin], {"default": bars})

        result = backtest.simulate_strategy(
            backtest.SimContext(strategy_name="balanced", codes=["sh600519"], top_n=1, holding_days=5)
        )
        assert "error" not in result
        degraded = result.get("factor_degradation")
        assert degraded is not None, "必须在结果中披露因子降维"
        assert "total_cap" in degraded and "turnover" in degraded

    def test_report_propagates_factor_degradation(self, monkeypatch):
        """run_backtest 报告必须透传降维说明，供 JSON/文本披露。"""
        import backtest

        captured = {"factor_degradation": ["total_cap", "turnover"]}

        def _fake_simulate(ctx):
            return {
                "returns": [1.0, 2.0, -1.0],
                "daily_returns": [0.01, 0.02, -0.01],
                "period_dates": [{"start": "2026-01-01", "holding_days": 1}] * 3,
                "all_selections": [],
                "factor_degradation": captured["factor_degradation"],
            }

        monkeypatch.setattr(backtest.metrics, "simulate_strategy", _fake_simulate)
        report = backtest.run_backtest("balanced", ["sh600519"], top_n=1, days=3, rounds=3)
        assert report.get("factor_degradation") == ["total_cap", "turnover"]
        assert report["meta"].get("factor_degradation") == ["total_cap", "turnover"]


class TestEventExcluded:
    """P1-17：回测禁用 event，必须剔除其权重并重新归一化，原 weights 不变。"""

    def _run_with_spy(self, monkeypatch, weights=None):
        import backtest

        fin = None
        from data.types import FinanceRecord

        fin = FinanceRecord(eps=2.0, period_type="annual", roe=15.0)
        bars = _bars([10.0 + i * 0.01 for i in range(140)])
        _offline_engine(monkeypatch, [fin], {"default": bars})

        seen_input, seen_output = [], []
        orig = backtest.engine.compute_overlay_weights

        def _spy(w, regime, **kwargs):
            seen_input.append(dict(w))
            out = orig(w, regime, **kwargs)
            seen_output.append(dict(out))
            return out

        monkeypatch.setattr(backtest.engine, "compute_overlay_weights", _spy)
        ctx = backtest.SimContext(
            strategy_name="balanced", codes=["sh600519"], top_n=1, holding_days=5, weights=weights
        )
        return backtest.simulate_strategy(ctx), seen_input, seen_output

    def test_result_marks_event_excluded(self, monkeypatch):
        result, _, _ = self._run_with_spy(monkeypatch)
        assert result.get("event_excluded_from_scoring") is True

    def test_event_removed_and_weights_renormalized(self, monkeypatch):
        result, seen_input, seen_output = self._run_with_spy(monkeypatch)
        assert "error" not in result
        assert seen_input and seen_output
        for w in seen_input + seen_output:
            assert "event" not in w, f"event 权重不得进入打分：{w}"
            numeric = [v for v in w.values() if isinstance(v, (int, float))]
            assert numeric and abs(sum(numeric) - 1.0) < 1e-6, f"剩余权重必须归一化：{w}"

    def test_original_weights_not_mutated(self, monkeypatch):
        from strategies import get_strategy

        custom = dict(get_strategy("balanced"))  # 含 event=0.05
        original = dict(custom)
        self._run_with_spy(monkeypatch, weights=custom)
        assert custom == original, "不得修改调用方传入的 weights"
        assert get_strategy("balanced")["event"] == 0.05, "不得修改策略注册表"


class TestSurvivorshipDisclosure:
    """P2：末根陈旧过滤会引入幸存者偏差，选池逻辑不变但必须披露。"""

    def test_stale_universe_filter_is_disclosed(self, monkeypatch):
        import backtest
        from data.types import FinanceRecord

        fin = FinanceRecord(eps=2.0, period_type="annual")
        fresh = _bars([10.0 + i * 0.01 for i in range(140)])
        stale = _bars([10.0 + i * 0.01 for i in range(140)], last_day=datetime.now() - timedelta(days=90))
        _offline_engine(monkeypatch, [fin], {"sh600519": fresh, "sh600520": stale})

        result = backtest.simulate_strategy(
            backtest.SimContext(strategy_name="balanced", codes=["sh600519", "sh600520"], top_n=1, holding_days=5)
        )
        assert "error" not in result
        disc = result.get("survivorship_bias_disclosure")
        assert disc is not None, "必须在结果中披露幸存者偏差"
        assert disc["excluded_count"] == 1
        assert "幸存者偏差" in disc["note"]
        assert result["effective_universe_size"] == 1  # P1-15 联动：真实入池数
        # 选池逻辑不得擅自改变：陈旧股票仍被排除
        assert {s["code"] for s in result["selections"]} <= {"sh600519"}


if __name__ == "__main__":
    pytest.main([__file__])

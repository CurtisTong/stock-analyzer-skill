"""P0-1 回归：walk-forward 各窗口 OOS 必须映射到互不重叠、按时间递进的真实日期。

复现原理：get_kline 取最近 datalen 根（bars 右对齐"今天"），引擎把 datalen 设为
MIN_HISTORY + total_days + 10，并把 eval_start/eval_end 当 bars 下标。旧实现每个
窗口同时递增 total_days 和下标，两者相消，5 个 OOS 全部落在同一段真实日期。

本测试严格按 datalen 返回 bars（不垫高长度），因此能在旧实现上复现并失败。
"""

from datetime import datetime, timedelta

import pytest

from data.types import KlineBar


def _finance_obj():
    """构造带年报口径的 FinanceRecord（PE 修复后仍需可评分）。"""
    from data.types import FinanceRecord

    return FinanceRecord(eps=2.0, period_type="annual", roe=15.0, net_profit_yoy=10.0, gross_margin=50.0)


def _install_offline_mocks(monkeypatch):
    """替换所有可能的网络依赖，并记录每次 get_kline 的 datalen。"""
    import backtest

    lengths = []
    today = datetime.now()

    def _mock_kline(code, scale=240, datalen=140):
        # 关键：严格按 datalen 返回，复现 bars 右对齐"今天"的数据层语义。
        lengths.append(datalen)
        bars = []
        for i in range(datalen):
            d = today - timedelta(days=datalen - i)
            price = 10.0 + i * 0.01  # 平滑上涨，避免涨跌停跳过打乱下标映射
            bars.append(
                KlineBar(
                    day=d.strftime("%Y-%m-%d"),
                    close=price,
                    open=price,
                    high=price,
                    low=price,
                    volume=1000,
                    amount=price * 1000,
                )
            )
        return bars

    monkeypatch.setattr(backtest.engine, "get_kline", _mock_kline)
    monkeypatch.setattr(backtest.engine, "get_finance", lambda code: ([_finance_obj()], None))
    monkeypatch.setattr(backtest.engine, "_detect_st_codes", lambda codes: set())
    monkeypatch.setattr(backtest.engine, "_chip_score", lambda code, trade_day=None: 50.0)
    monkeypatch.setattr(backtest.engine, "_sentiment_score_at", lambda code, day: None)
    return lengths


def _capture_windows(monkeypatch):
    """spy walk_forward.simulate_strategy，记录每次调用的 ctx 与结果。"""
    import backtest

    seen = []
    orig = backtest.walk_forward.simulate_strategy

    def _spy(ctx):
        result = orig(ctx)
        seen.append((ctx, result))
        return result

    monkeypatch.setattr(backtest.walk_forward, "simulate_strategy", _spy)
    return seen


def _starts(result: dict) -> list[str]:
    """从引擎结果里取实际评估用的选股日（bar.day）。"""
    return [p["start"] for p in result.get("period_dates", [])]


class TestWalkForwardOosCalendar:
    """P0-1：所有窗口共用同一数据深度，eval 下标才映射到不同日历区间。"""

    def test_oos_intervals_distinct_and_chronological(self, monkeypatch):
        """5 个 OOS 的 bar.day 区间互不相同且按时间递进（旧实现全部相同）。"""
        from backtest.walk_forward import run_walk_forward, WalkForwardConfig

        _install_offline_mocks(monkeypatch)
        seen = _capture_windows(monkeypatch)

        cfg = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            top_n=2,
            holding_days=5,
            train_days=120,
            test_days=30,
            step_days=30,
            n_windows=5,
        )
        result = run_walk_forward(cfg)
        assert result.n_valid_windows == 5, result.errors

        # 每个窗口两次调用：IS、OOS
        assert len(seen) == 10
        is_pair = [(seen[2 * w][0], seen[2 * w][1]) for w in range(cfg.n_windows)]
        oos_pair = [(seen[2 * w + 1][0], seen[2 * w + 1][1]) for w in range(cfg.n_windows)]

        oos_starts = [_starts(res) for _, res in oos_pair]
        for dates in oos_starts:
            assert dates, "每个 OOS 窗口都应产出实际评估日"

        # 核心断言：窗口之间 OOS 日期互不相同（旧实现 5 段完全重合）
        for w in range(cfg.n_windows):
            for v in range(w + 1, cfg.n_windows):
                assert set(oos_starts[w]).isdisjoint(oos_starts[v]), (
                    f"窗口 {w} 与 {v} 的 OOS 日期重叠：{oos_starts[w][:2]} / {oos_starts[v][:2]}"
                )

        # 按时间递进：后一窗口的首个 OOS 日必须晚于前一窗口的末个 OOS 日
        for w in range(cfg.n_windows - 1):
            assert max(oos_starts[w]) < min(oos_starts[w + 1]), (
                f"窗口 {w+1} 的 OOS 应严格晚于窗口 {w}：{max(oos_starts[w])} >= {min(oos_starts[w+1])}"
            )

        # 同一窗口内：IS 末根日期 < OOS 首根日期（IS 不含自己的 OOS）
        for w in range(cfg.n_windows):
            is_dates = _starts(is_pair[w][1])
            assert is_dates and oos_starts[w]
            assert max(is_dates) < min(oos_starts[w]), (
                f"窗口 {w} 的 IS 覆盖了 OOS：IS末={max(is_dates)} OOS首={min(oos_starts[w])}"
            )

    def test_all_windows_use_same_total_days(self, monkeypatch):
        """所有窗口的 IS/OOS 都传 max_total_days → datalen 恒定（旧实现 10 次调用 5 种深度）。"""
        from backtest.walk_forward import run_walk_forward, WalkForwardConfig

        lengths = _install_offline_mocks(monkeypatch)
        seen = _capture_windows(monkeypatch)

        cfg = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            top_n=2,
            holding_days=5,
            train_days=120,
            test_days=30,
            step_days=30,
            n_windows=5,
        )
        expected_total_days = (cfg.n_windows - 1) * cfg.step_days + cfg.train_days + cfg.test_days
        run_walk_forward(cfg)

        assert {ctx.total_days for ctx, _ in seen} == {expected_total_days}
        expected_datalen = 60 + expected_total_days + 10  # MIN_HISTORY + total_days + 10
        assert set(lengths) == {expected_datalen}, f"每次取数深度必须一致：{set(lengths)}"
        # test_end 必须显著小于 datalen，保证下标不越界
        assert expected_datalen > expected_total_days + 10

    def test_eval_start_end_still_window_relative(self, monkeypatch):
        """修复不得把 eval_start/eval_end 也固定：它们仍随窗口推进。"""
        from backtest.walk_forward import run_walk_forward, WalkForwardConfig

        _install_offline_mocks(monkeypatch)
        seen = _capture_windows(monkeypatch)

        cfg = WalkForwardConfig(
            strategy_name="balanced",
            codes=["sh600519"],
            top_n=2,
            holding_days=5,
            train_days=120,
            test_days=30,
            step_days=30,
            n_windows=3,
        )
        run_walk_forward(cfg)
        oos_ends = [seen[2 * w + 1][0].eval_end for w in range(cfg.n_windows)]
        assert oos_ends == [150, 180, 210]
        oos_starts = [seen[2 * w + 1][0].eval_start for w in range(cfg.n_windows)]
        assert oos_starts == [120, 150, 180]


if __name__ == "__main__":
    pytest.main([__file__])

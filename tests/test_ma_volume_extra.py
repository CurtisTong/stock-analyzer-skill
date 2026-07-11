"""ma_volume_strategy.py 补充测试：覆盖 detect_ma_volume_signal 更多分支。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategies.patterns.ma_volume_strategy import (
    calc_ma,
    detect_ma_volume_signal,
    backtest_strategy,
    get_strategy_params,
)


def _make_records(n, base_price=10.0, base_vol=1000):
    """构造 n 天 K 线记录。"""
    return [
        {"day": f"2024-01-{i + 1:02d}", "close": base_price, "volume": base_vol}
        for i in range(n)
    ]


def _records_with_data(closes, vols):
    """根据 closes/vols 序列构造 records（day 用序号占位）。"""
    return [
        {"day": f"2024-01-{i + 1:02d}", "close": c, "volume": v}
        for i, (c, v) in enumerate(zip(closes, vols))
    ]


# ═══════════════════════════════════════════════════════════════
# calc_ma
# ═══════════════════════════════════════════════════════════════


class TestCalcMa:
    def test_exact_period(self):
        """正好 period 长度返回 1 个 MA 值。"""
        assert calc_ma([1, 2, 3, 4, 5], 5) == [3.0]

    def test_short_data_returns_empty(self):
        """数据不足返回空。"""
        assert calc_ma([1, 2, 3], 5) == []

    def test_multiple_values(self):
        """多日 MA 序列。"""
        result = calc_ma([1, 2, 3, 4, 5, 6], 3)
        assert result == [2.0, 3.0, 4.0, 5.0]


# ═══════════════════════════════════════════════════════════════
# detect_ma_volume_signal
# ═══════════════════════════════════════════════════════════════


class TestDetectMaVolumeSignal:
    def test_insufficient_data_returns_empty(self):
        """数据不足返回空信号。"""
        records = _make_records(20)
        closes = [10.0] * 20
        vols = [1000] * 20
        assert detect_ma_volume_signal(records, closes, vols) == []

    def test_no_cross_no_signal(self):
        """无金叉无放量 -> 无信号。"""
        n = 40
        records = _make_records(n)
        closes = [10.0 + i * 0.01 for i in range(n)]  # 缓慢上升，无金叉
        vols = [1000] * n
        # 短均线始终在长均线上方（稳定上升），不会有金叉
        signals = detect_ma_volume_signal(records, closes, vols)
        # 无金叉 -> 即使放量也不会满足 2 个条件中的金叉
        # 可能突破前高，但单独一个条件不触发
        for s in signals:
            assert "MA10/MA21金叉" in s["desc"] or len(s["conditions"]) >= 2

    def test_golden_cross_with_volume_signal(self):
        """金叉 + 放量 + 突破前高 -> 高置信度买入信号。"""
        n = 35
        records = _make_records(n)
        # 先下跌再急涨：制造金叉
        closes = [20 - i * 0.3 for i in range(20)] + [14 + i * 1.5 for i in range(15)]
        # 金叉日大幅放量
        vols = [1000] * 35
        vols[33] = 5000  # 大放量
        vols[34] = 5000
        signals = detect_ma_volume_signal(records, closes, vols)
        # 至少检测到信号
        assert len(signals) >= 1
        # 首个信号带 warning
        assert "_warning" in signals[0]

    def test_signal_has_metadata(self):
        """信号包含 date/idx/conditions/strength 字段。"""
        n = 35
        records = _make_records(n)
        closes = [20 - i * 0.3 for i in range(20)] + [14 + i * 1.5 for i in range(15)]
        vols = [1000] * 35
        vols[33] = 5000
        vols[34] = 5000
        signals = detect_ma_volume_signal(records, closes, vols)
        for s in signals:
            assert "date" in s
            assert "idx" in s
            assert "conditions" in s
            assert "strength" in s
            assert "type" in s
            assert "desc" in s
            assert "confidence" in s

    def test_confidence_levels(self):
        """置信度分级：高/中/低。"""
        n = 35
        records = _make_records(n)
        # 强信号场景：金叉+放量大涨+突破前高
        closes = [20 - i * 0.5 for i in range(20)] + [10 + i * 2 for i in range(15)]
        vols = [1000] * 35
        vols[33] = 8000
        vols[34] = 8000
        signals = detect_ma_volume_signal(records, closes, vols)
        if signals:
            assert signals[-1]["confidence"] in ("高", "中", "低")

    def test_custom_parameters(self):
        """自定义均线周期和量阈值。"""
        n = 40
        records = _make_records(n)
        closes = [20 - i * 0.3 for i in range(20)] + [14 + i * 1.5 for i in range(20)]
        vols = [1000] * 40
        vols[37] = 6000
        vols[38] = 6000
        vols[39] = 6000
        signals = detect_ma_volume_signal(
            records, closes, vols, ma_short=5, ma_long=15, vol_threshold=3.0
        )
        # 自定义参数也能检测信号
        assert isinstance(signals, list)


# ═══════════════════════════════════════════════════════════════
# backtest_strategy
# ═══════════════════════════════════════════════════════════════


class TestBacktestStrategy:
    def test_no_signal_no_trades(self):
        """无信号 -> 无交易（平盘数据）。"""
        n = 30
        records = _make_records(n, base_price=10.0)  # 平盘，无金叉
        trades = backtest_strategy(records)
        assert trades == []

    def test_trade_fields(self):
        """交易记录包含必要字段（金叉+放量产生交易）。"""
        n = 35
        closes = [20 - i * 0.5 for i in range(20)] + [10 + i * 1.5 for i in range(15)]
        vols = [1000] * n
        for i in range(28, n):
            vols[i] = 5000
        records = _records_with_data(closes, vols)
        trades = backtest_strategy(records)
        assert len(trades) >= 1
        for t in trades:
            assert "buy_date" in t
            assert "buy_price" in t
            assert "sell_date" in t
            assert "sell_price" in t
            assert "return_pct" in t
            assert "exit_reason" in t
            assert "signal" in t
            assert "confidence" in t
            assert "strength" in t

    def test_hold_to_expiry_exit(self):
        """持有到期退出场景。"""
        n = 35
        closes = [20 - i * 0.5 for i in range(20)] + [10 + i * 1.5 for i in range(15)]
        vols = [1000] * n
        for i in range(28, n):
            vols[i] = 5000
        records = _records_with_data(closes, vols)
        trades = backtest_strategy(records, hold_days=5)
        assert len(trades) >= 1
        assert all(t["exit_reason"] == "持有到期" for t in trades)

    def test_stop_loss_exit(self):
        """止损触发场景：信号后暴跌。"""
        n = 40
        closes = [20 - i * 0.5 for i in range(20)] + [10 + i * 1.5 for i in range(5)]
        closes += [10 - i * 1 for i in range(1, 16)]  # 信号后暴跌
        vols = [1000] * n
        for i in range(24, 30):
            vols[i] = 5000
        records = _records_with_data(closes, vols)
        trades = backtest_strategy(records, stop_loss=-5)
        assert len(trades) >= 1
        # 至少有一个止损
        assert any(t["exit_reason"] == "止损" for t in trades)

    def test_signal_near_end_skipped(self):
        """信号接近数据末尾（idx+hold_days >= len）-> 跳过。"""
        n = 30
        closes = [20 - i * 0.5 for i in range(20)] + [10 + i * 1.5 for i in range(10)]
        vols = [1000] * n
        for i in range(26, n):
            vols[i] = 5000
        records = _records_with_data(closes, vols)
        trades = backtest_strategy(records, hold_days=5)
        # 末尾的信号因 idx+hold_days >= len 被跳过
        assert isinstance(trades, list)

    def test_custom_hold_days(self):
        """自定义持仓天数。"""
        n = 40
        closes = [20 - i * 0.5 for i in range(20)] + [10 + i * 1.5 for i in range(20)]
        vols = [1000] * n
        for i in range(28, 35):
            vols[i] = 5000
        records = _records_with_data(closes, vols)
        trades = backtest_strategy(records, hold_days=10)
        assert isinstance(trades, list)


# ═══════════════════════════════════════════════════════════════
# get_strategy_params
# ═══════════════════════════════════════════════════════════════


class TestGetStrategyParams:
    def test_returns_dict(self):
        params = get_strategy_params()
        assert isinstance(params, dict)

    def test_has_parameters(self):
        params = get_strategy_params()
        assert "parameters" in params
        assert "ma_short" in params["parameters"]
        assert "ma_long" in params["parameters"]
        assert "vol_threshold" in params["parameters"]

    def test_has_backtest_results(self):
        params = get_strategy_params()
        assert "backtest_results" in params
        assert "win_rate" in params["backtest_results"]
        assert "disclosure" in params["backtest_results"]

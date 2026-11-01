"""技术指标模块审查修复的回归测试（v1.28.0）。

覆盖：
1. **前低支撑坐标系错位**（P0）：`_find_swing_points` 只对 highs 调用一次，
   返回的 pl（highs 序列的极小值索引）被拿去索引 lows —— 两个坐标系无关，
   取到的是随机位。前低支撑标 strength="强" 并直接进入报告的"关键支撑"。
2. **aligned_macd 契约**（P0）：26≤n<34 时 DEA 不足以起算，原实现
   `dif_series[-0:]` 不截断而 dea_offset=n，声称的 closes 索引越界。
3. **连板阈值二次打折**（P1）：阈值表已是打折值（主板 9.5），判定处又乘
   0.95 → 9.025%，+9.1% 的非涨停被计板。
4. **ma_stop「不再新低」方向反转**（P1）：原实现要求最低点在窗口左半段，
   上涨趋势中恒成立（93% 触发），V 型反转反而漏报。
5. **KDJ 超买超卖阈值施加在 J 值**（P1）：J=3K−2D 波动远大于 K，命中率
   53.7%；且"金叉+超买"时超买标记被完全丢弃。
6. **ATR 数据不足返回部分窗口**（P1）：与 backtest/engine._calc_atr 的
   "不足则返回 0"口径不一致，且使 atr_tolerance 的 2% 回退永不触发。
7. **MACD n=34 时 prev_dea 错位**（P1）：DEA 只有 1 个元素时回退到当前 DEA，
   与 prev_dif 差一根，随机序列 33/400 报出无意义金叉/死叉。
"""

from __future__ import annotations

import random

import pytest


class TestSwingLowCoordinate:
    """前低支撑必须来自 lows 序列自身的摆动低点。"""

    def test_swing_low_from_lows_series(self):
        from technical.trend import support_resistance

        highs = [20.0] * 40
        lows = [19.0] * 40
        highs[30] = 15.0  # highs 序列的凹陷
        lows[8] = 10.0  # lows 序列真正的摆动低点
        closes = [18.0] * 40
        out = support_resistance(closes, highs, lows, {"ma_supports": [], "ma_resistances": []})
        front_lows = [s["level"] for s in out["supports"] if s["source"] == "前低"]
        assert 10.0 in front_lows

    def test_short_series_returns_all_keys(self):
        """早退分支必须含全部键（report.py 用 sr["nearest_support"] 直接下标）。"""
        from technical.trend import support_resistance

        out = support_resistance([1.0] * 5, [1.0] * 5, [1.0] * 5, {})
        for key in (
            "supports",
            "resistances",
            "nearest_support",
            "nearest_resistance",
            "recent_swing_highs",
            "breakout_target",
        ):
            assert key in out


class TestAlignedMacdContract:
    """aligned_macd 的索引契约。"""

    @pytest.mark.parametrize("n", [26, 30, 33])
    def test_no_dea_returns_empty_series(self, n):
        """DEA 不足以起算时两条序列都为空（无 DEA 就没有可比 MACD）。"""
        from technical.core import aligned_macd

        m = aligned_macd([100.0] * n)
        assert m["dif_series"] == []
        assert m["dea_series"] == []
        assert m["dea_offset"] == 0

    def test_offset_points_to_actual_close_index(self):
        """dea_offset 必须真的指向 dif_series[0] 对应的 closes 索引。"""
        from technical.core import aligned_macd

        closes = [100.0 + i for i in range(60)]
        m = aligned_macd(closes)
        n = len(closes)
        # dif_series[0] 与 dea_series[0] 指向同一根 K 线
        assert m["dea_offset"] == n - len(m["dea_series"])
        assert len(m["dif_series"]) == len(m["dea_series"])

    def test_dif_and_dea_share_starting_bar(self):
        """dif_series 与 dea_series 起点必须对齐（同一根 K 线）。"""
        from technical.core import aligned_macd

        closes = [100.0 + (i % 7) for i in range(80)]
        m = aligned_macd(closes)
        assert len(m["dif_series"]) == len(m["dea_series"])


class TestLimitStreakThreshold:
    """连板判定阈值不得二次打折。"""

    def test_non_limit_up_not_counted_as_streak(self):
        """+9.1% 的非涨停（主板）不得计板。"""
        from technical.astock import _LIMIT_THRESHOLDS, _count_limit_streak

        recs = []
        px = 10.0
        for _ in range(12):
            px = px * 1.091
            recs.append({"day": "d", "open": px, "close": px, "high": px, "low": px})
        assert _count_limit_streak(recs, _LIMIT_THRESHOLDS["主板"]) == 0

    def test_real_limit_up_counted(self):
        """+10% 的真涨停应计板。"""
        from technical.astock import _LIMIT_THRESHOLDS, _count_limit_streak

        recs = []
        px = 10.0
        for _ in range(12):
            px = px * 1.10
            recs.append({"day": "d", "open": px, "close": px, "high": px, "low": px})
        assert _count_limit_streak(recs, _LIMIT_THRESHOLDS["主板"]) >= 10

    def test_st_main_board_threshold(self):
        """ST 主板 ±5%：+5% 应计板。"""
        from technical.astock import _ST_MAIN_THRESHOLD, _count_limit_streak

        recs = []
        px = 10.0
        for _ in range(6):
            px = px * 1.05
            recs.append({"day": "d", "open": px, "close": px, "high": px, "low": px})
        assert _count_limit_streak(recs, _ST_MAIN_THRESHOLD) >= 5


class TestMaStopNotAlwaysTrue:
    """ma_stop 的「不再新低」判定方向。"""

    def test_steady_uptrend_does_not_trigger(self):
        """稳态上涨中不应恒发止跌买点（修复前 93% 触发）。"""
        from technical.ma_stop import ma_stop_buy
        from technical.moving_average import ma_system

        closes = [100.0 + i * 0.3 for i in range(110)]
        lows = [c - 0.2 for c in closes]
        highs = [c + 0.2 for c in closes]
        hits = 0
        for i in range(30, 110):
            res = ma_stop_buy(closes[: i + 1], highs[: i + 1], lows[: i + 1], ma_system(closes[: i + 1]))
            if res and res.get("signal") == 1:
                hits += 1
        assert hits == 0

    def test_decline_then_rebound_triggers(self):
        """下跌创低后回升应触发止跌买点。"""
        from technical.ma_stop import ma_stop_buy
        from technical.moving_average import ma_system

        closes = []
        px = 10.0
        for i in range(20):
            closes.append(round(px + (i % 3 - 1) * 0.05, 2))
        px = closes[-1]
        for _ in range(6):
            px = round(px - 0.3, 2)
            closes.append(px)
        for _ in range(5):
            px = round(px + 0.3, 2)
            closes.append(px)
        lows = [c - 0.2 for c in closes]
        highs = [c + 0.4 for c in closes]
        res = ma_stop_buy(closes, highs, lows, ma_system(closes))
        assert res is not None and res["signal"] == 1


class TestKdjZone:
    """KDJ 超买超卖的判定口径与信号组合完整性。"""

    def test_zone_rate_not_extreme(self):
        """超买/超卖命中率不应过半（修复前基于 J 值达 53.7%）。"""
        from technical.kdj import kdj_full

        random.seed(7)
        closes = [100.0]
        for _ in range(300):
            closes.append(closes[-1] * (1 + random.gauss(0, 0.02)))
        highs = [c * 1.01 for c in closes]
        lows = [c * 0.99 for c in closes]
        hits = 0
        total = 0
        for i in range(10, 300):
            s = kdj_full(closes[: i + 1], highs[: i + 1], lows[: i + 1])
            if not s:
                continue
            total += 1
            if "超买" in s["signal"] or "超卖" in s["signal"]:
                hits += 1
        assert total > 0
        assert hits / total < 0.45

    def test_cross_keeps_zone_marker(self):
        """金叉/死叉时若处于超买/超卖区，标记不得丢失。

        原实现三个分支（��叉+超卖 / 死叉+超买 / 正常→zone）都判不中时，
        超买标记被完全丢弃——"金叉且 K>80"（高位金叉）三分支全不命中，
        信号文本只剩"金叉"，评分侧按正面信号给 *0.8（带超买的只给 *0.3）。
        """
        from technical.kdj import kdj_full

        random.seed(11)
        closes = [100.0]
        for _ in range(200):
            closes.append(closes[-1] * (1 + random.gauss(0, 0.025)))
        highs = [c * 1.012 for c in closes]
        lows = [c * 0.988 for c in closes]
        checked = 0
        for i in range(12, 200):
            s = kdj_full(closes[: i + 1], highs[: i + 1], lows[: i + 1])
            if not s:
                continue
            sig = s["signal"]
            if "金叉" in sig and s["k"] >= 80:
                assert "超买" in sig, sig
                checked += 1
            elif "死叉" in sig and s["k"] <= 20:
                assert "超卖" in sig, sig
                checked += 1
        assert checked > 0, "未找到可用于验证的交叉样本"


class TestAtrConsistency:
    """ATR 与回测引擎口径一致。"""

    def test_matches_engine_for_insufficient_data(self):
        from technical.volatility import compute_atr
        from backtest.engine import _calc_atr

        class _B:
            def __init__(self, hi, lo, cl):
                self.high, self.low, self.close = hi, lo, cl

        closes = [100.0 + i * 0.5 for i in range(10)]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        bars = [_B(highs[i], lows[i], closes[i]) for i in range(10)]
        assert compute_atr(highs, lows, closes, 14) == _calc_atr(bars, 14) == 0.0

    def test_atr_tolerance_fallback_reachable(self):
        """数据不足时 atr_tolerance 回退到收盘价 2%（修复前永不触发）。"""
        from technical.volatility import atr_tolerance

        closes = [10.0] * 5
        highs = [11.0] * 5
        lows = [9.0] * 5
        assert atr_tolerance(closes, highs, lows) == pytest.approx(0.2, abs=1e-6)


class TestMacdSignalAlignment:
    """MACD 金叉死叉的坐标一致性。"""

    def test_no_signal_when_dea_has_single_point(self):
        """n=34 时 DEA 只有一个点 → 无前值可比 → 不报金叉/死叉。"""
        from technical.macd import macd_full

        random.seed(3)
        signals = 0
        for _ in range(200):
            closes = [100.0]
            for _ in range(33):
                closes.append(closes[-1] * (1 + random.gauss(0, 0.02)))
            out = macd_full(closes)
            if out and out.get("signal") != 0:
                signals += 1
        assert signals == 0


class TestHoldersMemoCache:
    """股东户数进程内记忆化（v1.30.0）。

    data/chip 无缓存层，chip_score_static 在回测中按 (代码 × 每根 K 线) 调用
    → 一次网格寻优实测发出 660 次 HTTP 请求（25 秒里的 20 秒），CI 上触发
    60s 超时。股东户数与 trade_day 无关（时点过滤在上层做），按
    (code, periods) 记忆化在语义上安全。
    """

    def test_repeated_calls_hit_cache(self, monkeypatch):
        from strategies.factors import chip as chip_factor

        calls = {"n": 0}

        def _fake_get_holders(code, periods=4):
            calls["n"] += 1
            return [{"holder_num_change": -1.0, "end_date": "2026-01-01"}]

        import data.chip as data_chip

        monkeypatch.setattr(data_chip, "get_holders", _fake_get_holders)
        chip_factor._HOLDERS_MEMO.clear()
        try:
            for _ in range(10):
                chip_factor._get_cached_holders("sh600519", periods=12)
            assert calls["n"] == 1, "重复调用未命中记忆化缓存"
        finally:
            chip_factor._HOLDERS_MEMO.clear()

    def test_different_periods_are_separate_keys(self, monkeypatch):
        from strategies.factors import chip as chip_factor

        calls = []

        def _fake_get_holders(code, periods=4):
            calls.append(periods)
            return []

        import data.chip as data_chip

        monkeypatch.setattr(data_chip, "get_holders", _fake_get_holders)
        chip_factor._HOLDERS_MEMO.clear()
        try:
            chip_factor._get_cached_holders("sh600519", periods=4)
            chip_factor._get_cached_holders("sh600519", periods=12)
            assert sorted(calls) == [4, 12]
        finally:
            chip_factor._HOLDERS_MEMO.clear()

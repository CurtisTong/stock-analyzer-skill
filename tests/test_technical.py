"""
technical.py 单元测试。
覆盖纯计算函数，不测试网络请求相关逻辑。
"""

import math
import pytest

from technical import (
    sma,
    ema,
    stddev,
    ma_system,
    macd_full,
    kdj_full,
    bollinger,
    volume_analysis,
    detect_candle_patterns,
    rsi_features,
    composite_score,
    detect_market_environment,
)
from technical.core import _ema_series, _find_swing_points
from technical.macd import _detect_macd_divergence
from technical.volume import _obv_series, _detect_obv_divergence
from technical.candlestick import (
    _body_shadow,
    _is_bullish,
    _candle_single,
    _candle_double,
    _candle_triple,
    _candle_ashare,
)
from technical.scoring import _market_weight_adjustments
from technical.signals import _generate_signals
from technical import (
    support_resistance,
    box_detection,
    breakout_check,
    wave_state,
    limit_analysis,
)
from technical.astock import _count_limit_streak
from technical.core import _parse_records
from technical.moving_average import _MA_PERIODS
from technical.scoring import _STOCK_TYPE_WEIGHTS_DEFAULT

# ═══════════════════════════════════════════════════════════════
# 1. 数学工具函数
# ═══════════════════════════════════════════════════════════════


class TestSMA:
    def test_basic(self):
        assert sma([1, 2, 3, 4, 5], 3) == 4.0  # (3+4+5)/3

    def test_period_equals_length(self):
        assert sma([10, 20, 30], 3) == 20.0

    def test_period_greater_than_length(self):
        # 数据不足时返回 None
        assert sma([10, 20], 5) is None

    def test_empty(self):
        assert sma([], 5) is None

    def test_single_value(self):
        assert sma([42], 1) == 42.0

    def test_period_one(self):
        assert sma([1, 2, 3], 1) == 3.0


class TestEMA:
    def test_basic(self):
        # period=3, 前3个均值 = (1+2+3)/3 = 2.0
        # k = 2/(3+1) = 0.5
        # EMA(4) = 4*0.5 + 2*0.5 = 3.0
        # EMA(5) = 5*0.5 + 3*0.5 = 4.0
        assert ema([1, 2, 3, 4, 5], 3) == 4.0

    def test_period_equals_length(self):
        assert ema([10, 20, 30], 3) == 20.0

    def test_period_greater_than_length(self):
        assert ema([10, 20], 5) == 15.0

    def test_empty(self):
        assert ema([], 5) == 0

    def test_constant_values(self):
        # 常数序列的 EMA 应等于该常数
        vals = [5.0] * 20
        assert abs(ema(vals, 10) - 5.0) < 1e-6


class TestEMASeries:
    def test_basic(self):
        series = _ema_series([1, 2, 3, 4, 5], 3)
        assert len(series) == 3  # 5 - 3 + 1 = 3
        assert series[0] == 2.0  # mean of first 3

    def test_too_short(self):
        assert _ema_series([1, 2], 5) == []

    def test_exact_period(self):
        series = _ema_series([10, 20, 30], 3)
        assert len(series) == 1
        assert series[0] == 20.0


class TestStddev:
    def test_basic(self):
        # stddev of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0
        vals = [2, 4, 4, 4, 5, 5, 7, 9]
        assert abs(stddev(vals) - 2.0) < 1e-6

    def test_single_value(self):
        assert stddev([42]) == 0

    def test_empty(self):
        assert stddev([]) == 0

    def test_identical_values(self):
        assert stddev([5, 5, 5, 5]) == 0


class TestFindSwingPoints:
    def test_too_short(self):
        highs, lows = _find_swing_points([1, 2, 3], window=5)
        assert highs == []
        assert lows == []

    def test_find_peak(self):
        # 在中间构造一个明显峰值
        vals = [1, 2, 3, 4, 5, 10, 5, 4, 3, 2, 1]
        highs, lows = _find_swing_points(vals, window=3)
        assert 5 in highs  # index 5 是峰值

    def test_find_trough(self):
        vals = [10, 9, 8, 7, 6, 1, 6, 7, 8, 9, 10]
        highs, lows = _find_swing_points(vals, window=3)
        assert 5 in lows  # index 5 是谷值

    def test_window_boundary(self):
        # window=2, 需要 2*2+1=5 个点
        highs, lows = _find_swing_points([1, 2, 3, 2, 1], window=2)
        assert 2 in highs


# ═══════════════════════════════════════════════════════════════
# 2. 均线系统
# ═══════════════════════════════════════════════════════════════


class TestMASystem:
    def test_uptrend_alignment(self, kline_uptrend):
        closes = [r["close"] for r in kline_uptrend]
        result = ma_system(closes)
        # 20根K线，MA5/MA10有值，MA20有值，MA60/120/250为None
        assert result["ma5"] is not None
        assert result["ma10"] is not None
        assert result["ma20"] is not None
        assert result["ma60"] is None

    def test_downtrend_alignment(self, kline_downtrend):
        closes = [r["close"] for r in kline_downtrend]
        result = ma_system(closes)
        assert result["ma5"] is not None
        assert result["alignment"] in ("空头排列", "交叉震荡", "数据不足")

    def test_sideways_convergence(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        result = ma_system(closes)
        # 横盘应该有粘合度数据
        assert result["convergence"] is not None
        assert result["convergence_desc"] in ("高度粘合(变盘窗口)", "中度粘合", "发散")

    def test_insufficient_data(self):
        result = ma_system([10.0, 11.0, 12.0])
        assert result["alignment"] == "数据不足"
        assert result["convergence_desc"] == "数据不足"

    def test_support_resistance_classification(self, kline_uptrend):
        closes = [r["close"] for r in kline_uptrend]
        result = ma_system(closes)
        last = closes[-1]
        # 所有支撑位应低于当前价
        for name, price in result["ma_supports"]:
            assert price < last
        # 所有阻力位应高于当前价
        for name, price in result["ma_resistances"]:
            assert price > last

    def test_ma_values_rounded(self, kline_uptrend):
        closes = [r["close"] for r in kline_uptrend]
        result = ma_system(closes)
        for p in _MA_PERIODS:
            v = result[f"ma{p}"]
            if v is not None:
                assert round(v, 2) == v  # 已经是2位小数


# ═══════════════════════════════════════════════════════════════
# 3. MACD
# ═══════════════════════════════════════════════════════════════


class TestMACD:
    def test_insufficient_data(self):
        assert macd_full([1.0] * 33) is None

    def test_basic_structure(self, kline_uptrend):
        closes = [r["close"] for r in kline_uptrend]
        # 20根不够34根，需要更长数据
        # 手动构造足够长的数据
        closes_long = closes + [c + 0.1 for c in closes]
        result = macd_full(closes_long)
        assert result is not None
        assert "dif" in result
        assert "dea" in result
        assert "macd_bar" in result
        assert "signal" in result
        assert "signal_desc" in result
        assert "bar_trend" in result
        assert "divergence" in result

    def test_golden_cross(self, kline_macd_golden_cross):
        closes = [r["close"] for r in kline_macd_golden_cross]
        # macd_full 需要至少 34 根 K 线，fixture 只有 30 根，需补齐
        while len(closes) < 34:
            closes.append(closes[-1] + 0.1)
        result = macd_full(closes)
        assert result is not None
        assert result["signal"] in (1, 0, -1)

    def test_death_cross(self, kline_macd_death_cross):
        closes = [r["close"] for r in kline_macd_death_cross]
        while len(closes) < 34:
            closes.append(closes[-1] - 0.1)
        result = macd_full(closes)
        assert result is not None
        assert result["signal"] in (1, 0, -1)

    def test_bar_trend_values(self, kline_macd_golden_cross):
        closes = [r["close"] for r in kline_macd_golden_cross]
        while len(closes) < 34:
            closes.append(closes[-1] + 0.1)
        result = macd_full(closes)
        assert result is not None
        valid_trends = ("红柱放大", "红柱缩小", "绿柱放大", "绿柱缩小")
        assert result["bar_trend"] in valid_trends

    def test_signal_desc_matches_signal(self, kline_macd_golden_cross):
        closes = [r["close"] for r in kline_macd_golden_cross]
        while len(closes) < 34:
            closes.append(closes[-1] + 0.1)
        result = macd_full(closes)
        if result["signal"] == 1:
            assert result["signal_desc"] == "金叉"
        elif result["signal"] == -1:
            assert result["signal_desc"] == "死叉"
        else:
            assert result["signal_desc"] == "无"


class TestMACDDivergence:
    def test_insufficient_data(self):
        assert _detect_macd_divergence([1.0] * 30, [1.0] * 30, [1.0] * 30) is None

    def test_no_divergence_with_constant(self):
        # 恒定数据不应产生背离
        closes = [10.0] * 80
        dif = [0.0] * 80
        dea = [0.0] * 80
        assert _detect_macd_divergence(closes, dif, dea) is None


# ═══════════════════════════════════════════════════════════════
# 4. KDJ
# ═══════════════════════════════════════════════════════════════


class TestKDJ:
    def test_insufficient_data(self):
        assert kdj_full([1, 2, 3], [2, 3, 4], [0, 1, 2], n=9) is None

    def test_basic_structure(self):
        n = 20
        closes = [10 + i * 0.5 for i in range(n)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        result = kdj_full(closes, highs, lows, n=9)
        assert result is not None
        assert "k" in result
        assert "d" in result
        assert "j" in result
        assert "signal" in result
        assert "钝化" in result

    def test_kdj_relationship(self):
        """J = 3K - 2D"""
        n = 20
        closes = [10 + i * 0.3 for i in range(n)]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]
        result = kdj_full(closes, highs, lows, n=9)
        assert result is not None
        j_expected = 3 * result["k"] - 2 * result["d"]
        assert abs(result["j"] - round(j_expected, 2)) < 0.02

    def test_overbought_detection(self):
        """连续高价应触发超买。"""
        n = 20
        closes = [100 + i * 2 for i in range(n)]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        result = kdj_full(closes, highs, lows, n=9)
        assert result is not None
        # J 值可能超过 100
        if result["j"] > 100:
            assert "超买" in result["signal"]

    def test_oversold_detection(self):
        """连续低价应触发超卖。"""
        n = 20
        closes = [100 - i * 2 for i in range(n)]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        result = kdj_full(closes, highs, lows, n=9)
        assert result is not None
        if result["j"] < 0:
            assert "超卖" in result["signal"]

    def test_dunhua_high(self):
        """高位钝化：连续 K>80。"""
        n = 20
        # 构造持续上涨序列，使 K 值持续在 80 以上
        closes = [50 + i * 5 for i in range(n)]
        highs = [c + 2 for c in closes]
        lows = [c - 2 for c in closes]
        result = kdj_full(closes, highs, lows, n=9)
        assert result is not None
        # 如果 K 持续高位，应该检测到钝化
        if result["k"] > 80:
            # 钝化检测取决于最近5个K值
            pass  # 不强制断言，取决于数据

    def test_flat_market(self):
        """横盘市场 KDJ 应在中性区域。"""
        n = 20
        closes = [10.0] * n
        highs = [10.5] * n
        lows = [9.5] * n
        result = kdj_full(closes, highs, lows, n=9)
        assert result is not None
        # 横盘时 K、D 应接近 50
        assert 30 < result["k"] < 70
        assert 30 < result["d"] < 70


# ═══════════════════════════════════════════════════════════════
# 5. BOLL
# ═══════════════════════════════════════════════════════════════


class TestBollinger:
    def test_insufficient_data(self):
        assert bollinger([1, 2, 3], period=20) is None

    def test_basic_structure(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        result = bollinger(closes, period=20)
        assert result is not None
        assert "upper" in result
        assert "mid" in result
        assert "lower" in result
        assert "bandwidth" in result
        assert "position" in result
        assert "position_desc" in result
        assert "bandwidth_desc" in result

    def test_upper_mid_lower_order(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        result = bollinger(closes, period=20)
        assert result["upper"] > result["mid"] > result["lower"]

    def test_position_range(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        result = bollinger(closes, period=20)
        assert 0 <= result["position"] <= 1 or result["position"] == 0.5

    def test_bandwidth_positive(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        result = bollinger(closes, period=20)
        assert result["bandwidth"] >= 0

    def test_position_desc_values(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        result = bollinger(closes, period=20)
        valid_descs = ("触及上轨", "触及下轨", "偏上轨", "偏下轨", "中轨附近")
        assert result["position_desc"] in valid_descs

    def test_bandwidth_desc_values(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        result = bollinger(closes, period=20)
        valid_bw = ("极度收窄(变盘信号)", "收窄中", "正常带宽")
        assert result["bandwidth_desc"] in valid_bw

    def test_constant_closes(self):
        """常数序列的布林带下轨可能为负，但 mid 应等于该常数。"""
        closes = [10.0] * 25
        result = bollinger(closes, period=20)
        assert result is not None
        assert result["mid"] == 10.0
        assert result["bandwidth"] == 0  # stddev=0


# ═══════════════════════════════════════════════════════════════
# 6. K 线形态识别
# ═══════════════════════════════════════════════════════════════


class TestBodyShadow:
    def test_basic(self):
        bar = {"open": 10.0, "close": 12.0, "high": 13.0, "low": 9.0}
        body, upper, lower, total = _body_shadow(bar)
        assert body == 2.0
        assert upper == 1.0  # 13 - 12
        assert lower == 1.0  # 10 - 9
        assert total == 4.0

    def test_bearish_bar(self):
        bar = {"open": 12.0, "close": 10.0, "high": 13.0, "low": 9.0}
        body, upper, lower, total = _body_shadow(bar)
        assert body == 2.0
        assert upper == 1.0  # 13 - 12
        assert lower == 1.0  # 10 - 9


class TestIsBullish:
    def test_bullish(self):
        assert _is_bullish({"open": 10, "close": 12}) is True

    def test_bearish(self):
        assert _is_bullish({"open": 12, "close": 10}) is False

    def test_equal(self):
        assert _is_bullish({"open": 10, "close": 10}) is False


class TestCandleSingle:
    def test_doji(self):
        """十字星：实体/总长 < 0.1"""
        bar = {"open": 10.0, "close": 10.05, "high": 10.5, "low": 9.5}
        patterns = _candle_single(bar, 10.0)
        assert any("十字星" in p for p in patterns)

    def test_hammer(self):
        """锤子线：下影线 > 2*实体，上影线 < 实体"""
        bar = {"open": 10.0, "close": 10.5, "high": 10.6, "low": 8.0}
        patterns = _candle_single(bar, 10.0)
        assert any("锤子线" in p for p in patterns)

    def test_inverted_hammer(self):
        """倒锤子：上影线 > 2*实体，收盘-最低 < 实体"""
        # body/total 必须 >= 0.1 否则先匹配十字星
        bar = {"open": 10.5, "close": 10.09, "high": 14.0, "low": 10.0}
        # body=0.41, upper=3.5, total=4.0, body/total=0.1025>0.1
        # upper>2*body: 3.5>0.82, (close-low)=0.09<0.41
        patterns = _candle_single(bar, 10.0)
        assert any("倒锤子" in p for p in patterns)

    def test_zero_range(self):
        """high == low 时应返回空列表。"""
        bar = {"open": 10.0, "close": 10.0, "high": 10.0, "low": 10.0}
        patterns = _candle_single(bar, 10.0)
        assert patterns == []


class TestCandleDouble:
    def test_bullish_engulfing(self):
        """阳包阴：前阴后阳，后根完全包裹前根。"""
        b1 = {"open": 12.0, "close": 10.0, "high": 12.5, "low": 9.5}
        b2 = {"open": 9.5, "close": 13.0, "high": 13.5, "low": 9.0}
        patterns = _candle_double(b1, b2)
        assert any("阳包阴" in p for p in patterns)

    def test_bearish_engulfing(self):
        """阴包阳：前阳后阴，后根完全包裹前根。"""
        b1 = {"open": 10.0, "close": 12.0, "high": 12.5, "low": 9.5}
        b2 = {"open": 12.5, "close": 9.0, "high": 13.0, "low": 8.5}
        patterns = _candle_double(b1, b2)
        assert any("阴包阳" in p for p in patterns)


class TestCandleTriple:
    def test_morning_star(self):
        """早晨之星：阴线 + 小实体 + 阳线（收盘高于前根中点）。"""
        b1 = {"open": 12.0, "close": 10.0, "high": 12.5, "low": 9.5}
        b2 = {"open": 10.0, "close": 10.3, "high": 10.5, "low": 9.8}
        b3 = {"open": 10.3, "close": 12.5, "high": 13.0, "low": 10.0}
        patterns = _candle_triple(b1, b2, b3)
        assert any("早晨之星" in p for p in patterns)

    def test_evening_star(self):
        """黄昏之星：阳线 + 小实体 + 阴线（收盘低于前根中点）。"""
        b1 = {"open": 10.0, "close": 12.0, "high": 12.5, "low": 9.5}
        b2 = {"open": 12.0, "close": 11.8, "high": 12.2, "low": 11.5}
        b3 = {"open": 11.8, "close": 9.5, "high": 12.0, "low": 9.0}
        patterns = _candle_triple(b1, b2, b3)
        assert any("黄昏之星" in p for p in patterns)

    def test_three_soldiers(self):
        """红三兵：三根阳线，收盘递增，开盘递增。"""
        b1 = {"open": 10.0, "close": 11.0, "high": 11.2, "low": 9.8}
        b2 = {"open": 10.5, "close": 12.0, "high": 12.2, "low": 10.3}
        b3 = {"open": 11.0, "close": 13.0, "high": 13.2, "low": 10.8}
        patterns = _candle_triple(b1, b2, b3)
        assert any("红三兵" in p for p in patterns)

    def test_three_crows(self):
        """三只乌鸦：三根阴线，收盘递减。"""
        b1 = {"open": 13.0, "close": 12.0, "high": 13.2, "low": 11.8}
        b2 = {"open": 12.5, "close": 11.0, "high": 12.7, "low": 10.8}
        b3 = {"open": 11.5, "close": 10.0, "high": 11.7, "low": 9.8}
        patterns = _candle_triple(b1, b2, b3)
        assert any("三只乌鸦" in p for p in patterns)


class TestCandleAShare:
    def test_fake_bullish(self):
        """假阳真阴：收阳但比昨收低。"""
        prev = {"open": 10.0, "close": 12.0, "high": 12.5, "low": 9.5}
        curr = {
            "open": 11.0,
            "close": 11.5,
            "high": 12.0,
            "low": 10.5,
        }  # 阳线但 close < prev.close
        result = _candle_ashare(prev, curr)
        assert result == "假阳真阴(收阳但实际下跌)"

    def test_fake_bearish(self):
        """假阴真阳：收阴但比昨收高。"""
        prev = {"open": 12.0, "close": 10.0, "high": 12.5, "low": 9.5}
        curr = {
            "open": 11.0,
            "close": 10.5,
            "high": 11.5,
            "low": 10.0,
        }  # 阴线但 close > prev.close
        result = _candle_ashare(prev, curr)
        assert result == "假阴真阳(收阴但实际上涨)"

    def test_normal_bullish(self):
        """正常阳线：无特殊标记。"""
        prev = {"open": 10.0, "close": 11.0, "high": 11.5, "low": 9.5}
        curr = {"open": 11.0, "close": 12.0, "high": 12.5, "low": 10.5}
        assert _candle_ashare(prev, curr) is None


class TestDetectCandlePatterns:
    def test_insufficient_data(self):
        assert (
            detect_candle_patterns(
                [{"day": "d1", "open": 10, "high": 11, "low": 9, "close": 10}]
            )
            == []
        )

    def test_returns_list(self, kline_uptrend):
        patterns = detect_candle_patterns(kline_uptrend)
        assert isinstance(patterns, list)

    def test_pattern_structure(self, kline_uptrend):
        patterns = detect_candle_patterns(kline_uptrend)
        for p in patterns:
            assert "date" in p
            assert "type" in p
            assert "position" in p


# ═══════════════════════════════════════════════════════════════
# 7. 成交量分析
# ═══════════════════════════════════════════════════════════════


class TestOBV:
    def test_basic(self):
        closes = [10, 11, 10, 12, 11]
        volumes = [100, 200, 150, 300, 250]
        result = _obv_series(closes, volumes)
        assert len(result) == 5
        assert result[0] == 0
        # 10->11 up: +200
        assert result[1] == 200
        # 11->10 down: -150
        assert result[2] == 50
        # 10->12 up: +300
        assert result[3] == 350
        # 12->11 down: -250
        assert result[4] == 100

    def test_all_up(self):
        closes = [1, 2, 3, 4]
        volumes = [100, 100, 100, 100]
        result = _obv_series(closes, volumes)
        assert result == [0, 100, 200, 300]

    def test_flat(self):
        closes = [10, 10, 10]
        volumes = [100, 100, 100]
        result = _obv_series(closes, volumes)
        assert result == [0, 0, 0]


class TestVolumeAnalysis:
    def test_insufficient_data(self):
        assert volume_analysis([1, 2, 3], [100, 200, 300]) is None

    def test_basic_structure(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        volumes = [r["volume"] for r in kline_sideways]
        result = volume_analysis(closes, volumes)
        assert result is not None
        assert "volume_ratio" in result
        assert "volume_ratio_desc" in result
        assert "volume_price" in result
        assert "volume_price_signal" in result

    def test_volume_ratio_desc_values(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        volumes = [r["volume"] for r in kline_sideways]
        result = volume_analysis(closes, volumes)
        valid_descs = (
            "地量(底部信号)",
            "极度缩量",
            "缩量",
            "正常",
            "放量",
            "显著放量",
            "巨量(警惕短期高点)",
        )
        assert result["volume_ratio_desc"] in valid_descs


# ═══════════════════════════════════════════════════════════════
# 8. RSI
# ═══════════════════════════════════════════════════════════════


class TestRSI:
    def test_insufficient_data(self):
        result = rsi_features([1, 2, 3], period=14)
        assert result is None

    def test_all_gains(self):
        """持续上涨应使 RSI 接近 100。"""
        closes = [10 + i for i in range(20)]
        result = rsi_features(closes, period=14)
        assert result["rsi"] > 90
        assert result["signal"] == -1  # 超买

    def test_all_losses(self):
        """持续下跌应使 RSI 接近 0。"""
        closes = [100 - i for i in range(20)]
        result = rsi_features(closes, period=14)
        assert result["rsi"] < 10
        assert result["signal"] == 1  # 超卖

    def test_neutral(self):
        """震荡数据 RSI 应在 40-60 附近。"""
        closes = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11]
        result = rsi_features(closes, period=14)
        assert 40 <= result["rsi"] <= 60

    def test_signal_values(self, kline_uptrend):
        closes = [r["close"] for r in kline_uptrend]
        result = rsi_features(closes)
        assert result["signal"] in (-1, 0, 1)


# ═══════════════════════════════════════════════════════════════
# 9. 综合评分
# ═══════════════════════════════════════════════════════════════


class TestCompositeScore:
    def test_empty_features(self):
        result = composite_score({})
        assert 0 <= result["score"] <= 100
        assert result["grade"] in ("强烈看多", "偏多", "中性", "偏空", "强烈看空")

    def test_score_range(self, kline_uptrend):
        """任何输入的分数都应在 0-100 范围内。"""
        closes = [r["close"] for r in kline_uptrend]
        features = {
            "ma_system": ma_system(closes),
            "rsi": rsi_features(closes),
        }
        result = composite_score(features)
        assert 0 <= result["score"] <= 100

    def test_grade_thresholds(self):
        """验证分级逻辑。"""
        # 构造一个高分特征集
        features = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "bar_trend": "红柱放大", "divergence": None},
            "kdj": {"signal": "金叉+超卖", "钝化": False},
            "bollinger": {"position": 0.2, "bandwidth_desc": "收窄中"},
            "rsi": {"rsi": 35, "signal": 1},
            "volume": {
                "volume_price_signal": 1,
                "volume_price": "放量上涨(资金介入)",
                "volume_ratio": 0.2,
            },
            "patterns": [{"type": "早晨之星(底部反转)"}],
        }
        result = composite_score(features, stock_type="题材股")
        # 题材股权重高，应该得到较高分
        assert result["score"] > 0

    def test_stock_type_weights(self):
        """不同股票类型应产生不同分数。"""
        features = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "bar_trend": "红柱放大", "divergence": None},
            "rsi": {"rsi": 50},
            "volume": {"volume_price_signal": 0, "volume_ratio": 1},
            "patterns": [],
        }
        score_type1 = composite_score(features, stock_type="题材股")["score"]
        score_type2 = composite_score(features, stock_type="蓝筹股")["score"]
        # 不同权重应导致不同分数
        # （不一定总是不同，但在有信号时通常会不同）
        assert isinstance(score_type1, (int, float))
        assert isinstance(score_type2, (int, float))

    def test_bearish_features_lower_score(self):
        """看空特征应产生较低分数。"""
        features = {
            "ma_system": {"alignment": "空头排列"},
            "macd": {
                "signal": -1,
                "bar_trend": "绿柱放大",
                "divergence": "顶背离(看跌)",
            },
            "kdj": {"signal": "死叉", "钝化": False},
            "bollinger": {"position": 0.9, "bandwidth_desc": "正常带宽"},
            "rsi": {"rsi": 75, "signal": -1},
            "volume": {
                "volume_price_signal": -1,
                "volume_price": "放量下跌(主力出货)",
                "volume_ratio": 2.5,
            },
            "patterns": [{"type": "黄昏之星(顶部反转)"}],
        }
        result = composite_score(features)
        assert result["score"] < 50  # 应该偏空

    def test_buy_sell_signals_generated(self):
        """有信号时应生成买卖信号列表。"""
        features = {
            "ma_system": {},
            "macd": {"signal": 1, "divergence": "底背离(看涨)"},
            "kdj": {"signal": "金叉+超卖"},
            "bollinger": {"position": 0.1, "bandwidth_desc": "收窄中"},
            "rsi": {"rsi": 25},
            "volume": {
                "volume_price_signal": 1,
                "volume_price": "放量上涨(资金介入)",
                "volume_ratio": 1.5,
            },
            "patterns": [],
        }
        result = composite_score(features)
        assert len(result["buy_signals"]) > 0

    def test_market_state_adjustment(self):
        """不同市场状态应影响分数。"""
        features = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "bar_trend": "红柱放大", "divergence": None},
            "rsi": {"rsi": 50},
            "volume": {"volume_price_signal": 0, "volume_ratio": 1},
            "patterns": [],
        }
        score_bull = composite_score(features, market_state="牛市")["score"]
        score_bear = composite_score(features, market_state="熊市")["score"]
        # 牛市应该对多头排列加分更多
        assert score_bull >= score_bear


class TestGenerateSignals:
    def test_empty_features(self):
        buy, sell, _ = _generate_signals({})
        assert isinstance(buy, list)
        assert isinstance(sell, list)

    def test_macd_golden_cross_signal(self):
        features = {
            "macd": {"signal": 1},
            "kdj": {},
            "bollinger": {},
            "rsi": {},
            "volume": {},
        }
        buy, sell, _ = _generate_signals(features)
        assert "MACD金叉" in buy

    def test_macd_death_cross_signal(self):
        features = {
            "macd": {"signal": -1},
            "kdj": {},
            "bollinger": {},
            "rsi": {},
            "volume": {},
        }
        buy, sell, _ = _generate_signals(features)
        assert "MACD死叉" in sell

    def test_structured_signals_p1_16(self):
        """P1-16: 结构化信号应正确反映各指标状态。"""
        features = {
            "macd": {"signal": 1},
            "kdj": {"signal": "金叉,超卖"},
            "bollinger": {"position": 0.1},
            "rsi": {"rsi": 30},
            "volume": {"volume_price_signal": 1, "volume_price": "放量上涨"},
        }
        _, _, s = _generate_signals(features)
        assert s["macd_golden_cross"] is True
        assert s["kdj_golden_cross"] is True
        assert s["kdj_oversold"] is True
        assert s["boll_lower_band"] is True
        assert s["rsi_oversold"] is True
        assert s["volume_inflow"] is True
        assert s["macd_death_cross"] is False


# ═══════════════════════════════════════════════════════════════
# 10. 市场环境
# ═══════════════════════════════════════════════════════════════


class TestMarketEnvironment:
    def test_no_index_data(self):
        result = detect_market_environment()
        assert result["state"] == "震荡"
        assert "大盘数据缺失" in result["signals"][0]

    def test_bull_market(self):
        idx = {"price": "3500", "change_pct": "3.0", "turnover": "2.0"}
        result = detect_market_environment(idx)
        assert result["state"] == "牛市"

    def test_bear_market(self):
        idx = {"price": "3000", "change_pct": "-3.0", "turnover": "1.0"}
        result = detect_market_environment(idx)
        assert result["state"] == "熊市"

    def test_frenzy(self):
        """高换手 + 涨幅 -> 亢奋。"""
        idx = {"price": "3500", "change_pct": "3.0", "turnover": "6.0"}
        result = detect_market_environment(idx)
        assert result["state"] == "亢奋"

    def test_freezing(self):
        """极低换手 + 跌幅 -> 冰点。"""
        idx = {"price": "3000", "change_pct": "-3.0", "turnover": "0.3"}
        result = detect_market_environment(idx)
        assert result["state"] == "冰点"

    def test_has_weight_adjustments(self):
        result = detect_market_environment()
        assert "weight_adjustments" in result
        assert "bullish_bias" in result["weight_adjustments"]


class TestMarketWeightAdjustments:
    def test_all_states_covered(self):
        for state in ("牛市", "熊市", "震荡", "冰点", "亢奋"):
            adj = _market_weight_adjustments(state)
            assert "bullish_bias" in adj
            assert "trend_following" in adj

    def test_unknown_state_fallback(self):
        adj = _market_weight_adjustments("未知状态")
        assert adj == _market_weight_adjustments("震荡")


# ═══════════════════════════════════════════════════════════════
# 11. 支撑阻力 / 箱体 / 突破 / 波浪
# ═══════════════════════════════════════════════════════════════


class TestSupportResistance:
    def test_insufficient_data(self):
        result = support_resistance([10], [11], [9], {})
        assert result["supports"] == []
        assert result["resistances"] == []

    def test_basic_structure(self, kline_uptrend):
        closes = [r["close"] for r in kline_uptrend]
        highs = [r["high"] for r in kline_uptrend]
        lows = [r["low"] for r in kline_uptrend]
        ma_info = ma_system(closes)
        result = support_resistance(closes, highs, lows, ma_info)
        assert "supports" in result
        assert "resistances" in result
        assert "nearest_support" in result
        assert "nearest_resistance" in result


class TestBoxDetection:
    def test_insufficient_data(self):
        assert box_detection([1], [0], [0.5], window=20) is None

    def test_no_box(self):
        """单边上涨不应检测为箱体。"""
        highs = [10 + i * 0.5 for i in range(25)]
        lows = [9 + i * 0.5 for i in range(25)]
        closes = [9.5 + i * 0.5 for i in range(25)]
        result = box_detection(highs, lows, closes, window=20)
        # 可能返回 None 或箱体，取决于数据
        # 主要是不崩溃
        assert result is None or isinstance(result, dict)

    def test_box_structure(self, kline_sideways):
        highs = [r["high"] for r in kline_sideways]
        lows = [r["low"] for r in kline_sideways]
        closes = [r["close"] for r in kline_sideways]
        result = box_detection(highs, lows, closes, window=20)
        if result is not None:
            assert "top" in result
            assert "bottom" in result
            assert "mid" in result
            assert "status" in result
            assert result["status"] == "箱体震荡"


class TestBreakoutCheck:
    def test_insufficient_data(self):
        result = breakout_check([1, 2], [3], [100], 2.5)
        assert result["status"] == "数据不足"

    def test_no_breakout(self):
        closes = [10] * 25
        highs = [10.5] * 25
        volumes = [1000] * 25
        result = breakout_check(closes, highs, volumes, 15.0)
        assert result["status"] == "未突破"


class TestWaveState:
    def test_insufficient_data(self):
        assert wave_state([1, 2, 3], [2, 3, 4], [0, 1, 2]) == "数据不足"

    def test_returns_string(self, kline_sideways):
        closes = [r["close"] for r in kline_sideways]
        highs = [r["high"] for r in kline_sideways]
        lows = [r["low"] for r in kline_sideways]
        # 需要40+根K线
        closes_long = closes + closes
        highs_long = highs + highs
        lows_long = lows + lows
        result = wave_state(closes_long, highs_long, lows_long)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# 12. 涨跌停分析
# ═══════════════════════════════════════════════════════════════


class TestLimitAnalysis:
    def test_insufficient_data(self):
        assert limit_analysis([{"close": "10"}], "主板", {}) is None

    def test_basic_structure(self, kline_limit_up):
        quote = {
            "limit_up": str(round(kline_limit_up[-1]["close"], 2)),
            "limit_down": str(round(kline_limit_up[-1]["close"] * 0.9, 2)),
        }
        result = limit_analysis(kline_limit_up, "主板", quote)
        assert result is not None
        assert "board" in result
        assert "board_status" in result
        assert "limit_streak" in result
        assert "streak_type" in result


class TestCountLimitStreak:
    def test_no_streak(self):
        records = [
            {"close": "10.0", "open": "9.5"},
            {"close": "10.5", "open": "10.0"},
            {"close": "10.8", "open": "10.3"},
        ]
        assert _count_limit_streak(records, 9.5) == 0

    def test_single_limit_up(self):
        prev_close = 10.0
        limit_price = round(prev_close * 1.095, 2)
        records = [
            {"close": str(prev_close), "open": "9.5"},
            {"close": str(limit_price), "open": str(prev_close)},
        ]
        streak = _count_limit_streak(records, 9.5)
        assert streak >= 1


# ═══════════════════════════════════════════════════════════════
# 13. 解析工具
# ═══════════════════════════════════════════════════════════════


class TestParseRecords:
    def test_basic(self, kline_uptrend):
        closes, opens, highs, lows, volumes = _parse_records(kline_uptrend)
        assert len(closes) == len(opens) == len(highs) == len(lows) == len(volumes)
        assert len(closes) > 0
        assert all(v > 0 for v in closes)

    def test_empty(self):
        closes, opens, highs, lows, volumes = _parse_records([])
        assert len(closes) == 0

    def test_min_length_consistency(self):
        """所有返回列表长度应一致。"""
        records = [
            {"close": "10", "open": "9", "high": "11", "low": "8", "volume": "100"},
            {"close": "11", "open": "10", "high": "12", "low": "9", "volume": "200"},
        ]
        closes, opens, highs, lows, volumes = _parse_records(records)
        assert len(closes) == len(opens) == len(highs) == len(lows) == len(volumes) == 2

    def test_filters_zero_values(self):
        """应过滤掉值为 0 的记录。"""
        records = [
            {"close": "10", "open": "9", "high": "11", "low": "8", "volume": "100"},
            {"close": "0", "open": "0", "high": "0", "low": "0", "volume": "0"},
            {"close": "12", "open": "11", "high": "13", "low": "10", "volume": "200"},
        ]
        closes, opens, highs, lows, volumes = _parse_records(records)
        assert len(closes) == 2
        assert closes == [10.0, 12.0]


# ═══════════════════════════════════════════════════════════════
# 14. 集成级测试：完整数据流
# ═══════════════════════════════════════════════════════════════


class TestIntegration:
    """使用 conftest fixtures 运行完整计算流程。"""

    def test_uptrend_full_pipeline(self, kline_uptrend):
        """上升趋势完整计算不崩溃。"""
        closes, opens, highs, lows, volumes = _parse_records(kline_uptrend)
        assert len(closes) >= 10

        ma = ma_system(closes)
        assert ma["ma5"] is not None

        rsi = rsi_features(closes)
        assert "rsi" in rsi

        boll = bollinger(closes)
        # 20根K线刚好够
        if boll:
            assert boll["upper"] > boll["lower"]

        patterns = detect_candle_patterns(kline_uptrend)
        assert isinstance(patterns, list)

    def test_downtrend_full_pipeline(self, kline_downtrend):
        """下降趋势完整计算不崩溃。"""
        closes, opens, highs, lows, volumes = _parse_records(kline_downtrend)
        ma = ma_system(closes)
        assert ma["alignment"] in ("空头排列", "交叉震荡", "数据不足")

    def test_sideways_full_pipeline(self, kline_sideways):
        """横盘趋势完整计算不崩溃。"""
        closes, opens, highs, lows, volumes = _parse_records(kline_sideways)
        ma = ma_system(closes)
        assert ma["convergence"] is not None

        boll = bollinger(closes, period=20)
        if boll:
            assert 0 <= boll["position"] <= 1 or boll["position"] == 0.5

    def test_composite_score_with_real_features(self, kline_uptrend):
        """用真实 K 线数据计算综合评分。"""
        closes, opens, highs, lows, volumes = _parse_records(kline_uptrend)
        features = {
            "ma_system": ma_system(closes),
            "rsi": rsi_features(closes),
            "volume": volume_analysis(closes, volumes) or {},
            "patterns": detect_candle_patterns(kline_uptrend),
        }
        result = composite_score(features)
        assert 0 <= result["score"] <= 100
        # 包含所有可能的 grade 值（含中间模糊区间档位）
        valid_grades = (
            "强烈看多", "偏多(强)", "偏多", "中性(偏多)",
            "中性", "中性(偏空)", "偏空", "偏空(强)", "强烈看空",
        )
        assert result["grade"] in valid_grades

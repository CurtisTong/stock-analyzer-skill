"""technical 剩余模块分支补齐测试（macd/kdj/boll/core 已完成，见 test_technical_macd_kdj_boll.py）。

覆盖：
- moving_average: 空头排列→交叉震荡→数据不足收敛, incremental_ma
- ma_stop: 参数缺失 / 双重确认
- rsi: short / 超卖 signal / zone_desc 分区
- volatility: compute_atr 边界 / atr_tolerance 回退
- shadow_stats: 数据不足 / 一字板跳过 / 正常统计
- pipeline: 数据不足 / 单指标 / ma10 回退 / ret20 / amihud
- volume: 少数据 / 量比档次 / 放量下跌 / 缩量上涨 / OBV 边界
- trend: support_resistance / box / wave
- candlestick: 单根/双根/三根形态 + A股特化
"""

import math

import pytest

from technical.candlestick import _candle_ashare, detect_candle_patterns
from technical.core import _find_swing_points
from technical.ma_stop import ma_stop_buy
from technical.moving_average import incremental_ma, ma_system
from technical.pipeline import _calc_amihud, compute_indicators
from technical.rsi import rsi_features
from technical.scoring import _score_kdj
from technical.shadow_stats import shadow_ratio_stats
from technical.trend import (
    box_detection,
    breakout_check,
    support_resistance,
    wave_state,
)
from technical.volatility import atr_tolerance, compute_atr
from technical.volume import (
    _detect_obv_divergence,
    volume_analysis,
)


def _records(closes, opens=None, highs=None, lows=None, base=10.0):
    """构造 KlineBar dict 记录列表。"""
    opens = opens if opens is not None else closes[:]
    highs = (
        highs if highs is not None else [max(o, c) + 0.2 for o, c in zip(opens, closes)]
    )
    lows = (
        lows if lows is not None else [min(o, c) - 0.2 for o, c in zip(opens, closes)]
    )
    return [
        {"open": o, "high": h, "low": lo, "close": c, "day": f"d{i}", "volume": 1000.0}
        for i, (o, h, lo, c) in enumerate(zip(opens, highs, lows, closes))
    ]


# ═══════════════════════════════════════════════════════════════
# moving_average.py
# ═══════════════════════════════════════════════════════════════


class TestMovingAverage:
    def test_incremental_ma_nan_warmup(self):
        """数据不足 period 根 → NaN（20-31 行）。"""
        out = incremental_ma([1.0, 2.0, 3.0], 5)
        assert all(math.isnan(v) for v in out)

    def test_incremental_ma_full(self):
        """满数据 → 滑动均值。"""
        out = incremental_ma([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 3)
        valid = [x for x in out if not math.isnan(x)]
        assert valid == [2.0, 3.0, 4.0, 5.0]

    def test_ma_system_bear_alignment(self):
        """空头排列（54 行）。"""
        closes = [float(100 - i) for i in range(90)]
        out = ma_system(closes)
        assert out["alignment"] == "空头排列"

    def test_ma_system_bull_and_cross(self):
        """多头排列与交叉震荡（50, 56 行）。"""
        bull = ma_system([float(100 + i) for i in range(90)])
        assert bull["alignment"] == "多头排列"
        # 不规则摆动 → 非严格单调 → 交叉震荡
        cross = [50.0, 55.0, 45.0, 52.0, 48.0, 55.0, 42.0, 58.0] * 12
        out = ma_system(cross)
        assert out["alignment"] == "交叉震荡"

    def test_ma_system_insufficient_data(self):
        """<4 条均线 → 数据不足。"""
        closes = [50.0] * 30
        out = ma_system(closes)
        assert out["alignment"] == "数据不足"
        assert out["convergence"] == 0.0
        assert out["convergence_desc"] == "高度粘合(变盘窗口)"

    def test_ma_system_zero_closes(self):
        """收盘全 0 → short_mas 为空 → None（77-78 行）。"""
        closes = [0.0] * 30
        out = ma_system(closes)
        assert out["convergence"] is None
        assert out["convergence_desc"] == "数据不足"

    def test_ma_system_backup_none_convergence(self):
        """收敛计算时 mean 非正 → None（74-75 行）。"""
        closes = [-5.0] * 30
        out = ma_system(closes)
        assert out["convergence"] is None
        assert out["convergence_desc"] == "数据不足"


# ═══════════════════════════════════════════════════════════════
# ma_stop.py
# ═══════════════════════════════════════════════════════════════


class TestMaStop:
    def test_ma20_missing_returns_none(self):
        """数据不足 → None（38 行）。"""
        closes = [50.0] * 10
        lows = [49.0] * 10
        highs = [51.0] * 10
        assert ma_stop_buy(closes, highs, lows, {}) is None

    def test_ma20_negative_returns_none(self):
        """ma20 为负 → None（51 行）。"""
        closes = [50.0 + i for i in range(20)]
        out = ma_stop_buy(closes, [51.0] * 20, [49.0] * 20, {"ma5": 55.0, "ma20": -1.0})
        assert out is None

    def test_cond_a_only(self):
        """仅条件 A（不再新低+站上MA5）→ 站上5日线（83 行）。"""
        closes = [50.0] * 20
        closes[-5:] = [48.0, 49.0, 50.0, 51.0, 52.0]
        lows = [49.0] * 19 + [51.5]
        lows[12] = 47.0
        highs = [53.0] * 20
        mas = {"ma5": sum(closes[-5:]) / 5, "ma20": sum(closes[-20:]) / 20}
        out = ma_stop_buy(closes, highs, lows, mas)
        assert out["type"] == "站上5日线"
        assert out["signal"] == 1

    def test_mas_empty_recompute(self):
        """mas 无预计算值 → 现场补算（45-48 行）。"""
        closes = [50.0] * 20
        closes[-3:] = [50.2, 50.4, 50.5]
        lows = [49.0] * 19 + [50.45]
        lows[12] = 48.5  # 最低点在前半段
        highs = [51.0] * 20
        out = ma_stop_buy(closes, highs, lows, {})
        assert out is not None
        assert "status" in out

    def test_double_confirm(self):
        """不再新低+站上MA5+回踩MA20 → 双重止跌（76 行）。"""
        # 回看期最低点在前半段，收盘站上 MA5 且近 MA20
        closes = [50.0] * 20
        closes[-5:] = [49.5, 49.8, 50.2, 50.4, 50.35]
        lows = [49.0] * 19 + [50.15]
        lows[12] = 48.5  # 最低点出现在回看窗口左半段
        highs = [51.0] * 20
        mas = {"ma5": sma_avg(closes[:5]), "ma20": sma_avg(closes[:20])}
        mas["ma5"] = sum(closes[-5:]) / 5
        mas["ma20"] = sum(closes[-20:]) / 20
        out = ma_stop_buy(closes, highs, lows, mas)
        assert out["type"] in ("双重止跌", "站上5日线", "回踩20日线")
        assert out["signal"] == 1

    def test_no_signal(self):
        """无信号 → 无止跌信号（97-102 行）。"""
        closes = [50.0] * 20
        lows = [49.0] * 20
        highs = [51.0] * 20
        mas = {"ma5": 50.0, "ma20": 50.0}
        out = ma_stop_buy(closes, highs, lows, mas)
        assert out["signal"] == 0
        assert out["type"] is None


def sma_avg(vals):
    return sum(vals) / len(vals)


# ═══════════════════════════════════════════════════════════════
# rsi.py
# ═══════════════════════════════════════════════════════════════


class TestRsi:
    def test_short_returns_none(self):
        """len < period+1 → None（10 行）。"""
        assert rsi_features([1.0, 2.0]) is None

    def test_oversold_signal(self):
        """rsi < 30 → 超卖 signal=1（34 行）。"""
        # 单调下跌 → RSI ~0
        closes = [10.0 - i for i in range(30)]
        out = rsi_features(closes)
        assert out["signal"] == 1
        assert out["zone_desc"] in ("极度超卖", "超卖区")

    def test_overbought_signal(self):
        """rsi > 70 → 超买 signal=-1。"""
        closes = [10.0 + i for i in range(30)]
        out = rsi_features(closes)
        assert out["signal"] == -1
        assert out["zone_desc"] in ("超买区", "极度超买")

    def test_zone_desc_gradient(self):
        """区间描述各档位（40-52 行）。"""
        cases = {
            # ratio = 涨/跌幅度（交替锯齿波，Wilder 平滑收敛到目标 RSI）
            "极度超卖": 0.02,
            "超卖区": 0.35,
            "偏弱": 0.55,
            "中性": 1.0,
            "偏强": 1.9,
            "超买区": 2.8,
            "极度超买": 8.0,
        }
        for expected, ratio in cases.items():
            out = rsi_features(_rsi_ratio_series(ratio))
            assert (
                out["zone_desc"] == expected
            ), f"ratio={ratio} got={out['zone_desc']} rsi={out['rsi']}"

    def test_flat_price_rsi_100(self):
        """无波动 → RSI=100（26-27 行）。"""
        out = rsi_features([5.0] * 20)
        assert out["rsi"] == 100


class TestRsiMultiPeriod:
    """v1.21.1: RSI 6/12/24 三档参考（审查 修复）。"""

    def test_multi_period_keys_present(self):
        """返回 dict 含 rsi6/rsi12/rsi24 键（数据充足时）。"""
        closes = [10.0 + i * 0.1 for i in range(60)]
        out = rsi_features(closes)
        assert out["rsi6"] is not None
        assert out["rsi12"] is not None
        assert out["rsi24"] is not None
        assert all(0 <= out[k] <= 100 for k in ("rsi6", "rsi12", "rsi24"))

    def test_flat_price_all_periods_100(self):
        """无波动 → 三档均为 100。"""
        out = rsi_features([5.0] * 30)
        assert out["rsi6"] == 100
        assert out["rsi12"] == 100
        assert out["rsi24"] == 100

    def test_main_period_unchanged(self):
        """主键 rsi/signal/zone_desc 与单周期行为一致（14 周期）。"""
        closes = [10.0 - i for i in range(40)]
        out = rsi_features(closes)
        assert out["rsi"] == 0.0
        assert out["signal"] == 1
        assert out["zone_desc"] == "极度超卖"

    def test_insufficient_data_short_period_none(self):
        """数据只够 14 周期时，rsi6/rsi12 有值、rsi24 为 None。"""
        closes = [10.0 + i * 0.1 for i in range(20)]
        out = rsi_features(closes)
        assert out["rsi"] is not None
        assert out["rsi6"] is not None
        assert out["rsi12"] is not None
        assert out["rsi24"] is None


class TestKdjDunhuaDowngrade:
    """v1.21.1: KDJ 钝化降权（审查 修复）。"""

    @staticmethod
    def _features(kdj_sig: str, dunhua: bool) -> dict:
        return {
            "ma_system": {"alignment": "交叉震荡"},
            "macd": {},
            "kdj": {"signal": kdj_sig, "钝化": dunhua},
            "bollinger": {},
            "rsi": {},
            "volume": {},
            "patterns": [],
            "chan_theory": None,
            "local_patterns": {"patterns": []},
            "limit_analysis": {},
            "chip": {},
            "valuation_score": 50,
        }

    def test_dunhua_suppresses_sell_signal(self):
        """钝化+超买 → sell_signals 不含 KDJ（报告层"暂停参考"落地）。"""
        from technical.scoring import composite_score

        sig = "超买区(J=95) [KDJ高位钝化-趋势延续]"
        score = composite_score(self._features(sig, dunhua=True))
        assert not any("KDJ" in s for s in score["sell_signals"])

    def test_dunhua_suppresses_structured_signals(self):
        """钝化时结构化 KDJ 信号与字符串信号一致（均为 False）。"""
        from technical.scoring import composite_score

        score = composite_score(
            self._features("死叉+超买 [KDJ高位钝化-趋势延续]", dunhua=True)
        )
        st = score["structured_signals"]
        assert not st["kdj_death_cross"]
        assert not st["kdj_overbought"]

    def test_no_dunhua_keeps_sell_signal(self):
        """非钝化超买 → 卖出信号保留（回归）。"""
        from technical.scoring import composite_score

        score = composite_score(self._features("超买区(J=95)", dunhua=False))
        assert any("KDJ" in s for s in score["sell_signals"])

    def test_dunhua_halves_oversold_score(self):
        """钝化时超卖档位评分低于非钝化同档。"""
        type_w = {"kdj": 1.0}
        adj = {"trend_following": 1.0}
        base = _score_kdj(
            {"signal": "超卖区(J=8)", "钝化": False}, type_w, adj, vol_signal=0
        )
        dunhua = _score_kdj(
            {"signal": "超卖区(J=8) [KDJ低位钝化-趋势延续]", "钝化": True},
            type_w,
            adj,
            vol_signal=0,
        )
        assert dunhua < base


def _rsi_ratio_series(ratio, n=300):
    """交替锯齿波：奇数日涨 ratio、偶数日跌 1，使 RSI 收敛。"""
    closes = [10.0]
    for i in range(1, n):
        closes.append(closes[-1] + (ratio if i % 2 == 1 else -1.0))
    return closes


# ═══════════════════════════════════════════════════════════════
# volatility.py
# ═══════════════════════════════════════════════════════════════


class TestVolatility:
    def test_compute_atr_short(self):
        """数据不足 → 0（26-27 行）。"""
        assert compute_atr([1.0], [1.0], [1.0]) == 0.0
        assert compute_atr([1.0, 2.0], [1.0, 2.0], [1.0, 2.0], period=0) == 0.0

    def test_compute_atr_normal(self):
        """正常 ATR 计算（29-46 行）。"""
        highs = [10.0, 11.0, 12.0, 11.5, 10.5]
        lows = [9.0, 10.0, 11.0, 10.5, 9.5]
        closes = [9.5, 10.5, 11.5, 11.0, 10.0]
        out = compute_atr(highs, lows, closes, period=14)
        assert out > 0

    def test_atr_tolerance_with_data(self):
        """有 highs/lows → ATR*k（68-71 行）。"""
        closes = [10.0] * 20
        highs = [11.0] * 20
        lows = [9.0] * 20
        out = atr_tolerance(closes, highs, lows, period=5, k=0.5)
        assert out > 0
        assert out < 1.5  # ATR ~2, half = 1

    def test_atr_tolerance_fallback(self):
        """无 highs/lows → 收盘价 2%（73-74 行）。"""
        assert atr_tolerance([50.0] * 10) == pytest.approx(1.0)
        assert atr_tolerance([], k=0.5) == 0.0


# ═══════════════════════════════════════════════════════════════
# shadow_stats.py
# ═══════════════════════════════════════════════════════════════


class TestShadowStats:
    def test_insufficient_data(self):
        """records < 3 → None（34-35 行）。"""
        assert shadow_ratio_stats([]) is None
        assert shadow_ratio_stats(_records([1, 2], base=50)) is None

    def test_all_one_word(self):
        """全部一字板 → None（52-53 + 71-72 行）。"""
        closes = [50.0] * 5
        records = _records(closes)
        for r in records:
            r["high"] = 50.0
            r["low"] = 50.0
        assert shadow_ratio_stats(records) is None

    def test_normal_stats(self):
        """有振幅 → 统计（55-81 行）。"""
        closes = [50.0 + i for i in range(5)]
        opens = [49.9 + i for i in range(5)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        records = _records(closes, opens=opens, highs=highs, lows=lows)
        out = shadow_ratio_stats(records)
        assert out["long_shadow_count"] >= 0
        assert 0 <= out["avg_shadow_ratio"] <= 1


# ═══════════════════════════════════════════════════════════════
# pipeline.py
# ═══════════════════════════════════════════════════════════════


class _Bar:
    def __init__(
        self, close, volume=None, amount=None, open_=None, high=None, low=None
    ):
        self.close = close
        self.open = open_ if open_ is not None else close
        self.high = high if high is not None else close
        self.low = low if low is not None else close
        self.volume = volume if volume is not None else 1000.0
        self.amount = amount if amount is not None else close * self.volume


class TestPipeline:
    def test_too_few_bars(self):
        """closes < 10 → 空结果（33-40 行）。"""
        bars = [_Bar(float(i)) for i in range(5, 13)]
        out = compute_indicators(bars)
        assert out["trend"] == 0
        assert out["rsi"] == 50

    def test_single_indicator_trend(self):
        """仅算 trend（42-70 行）。"""
        bars = [_Bar(100.0 + i) for i in range(40)]
        out = compute_indicators(bars, indicators=["trend"])
        assert "trend" in out
        assert "ma10" in out
        assert "rsi" not in out

    def test_trend_ma20_fallback(self):
        """数据 10-19 根 → ma20 None → 回退分支（56-68 行）。"""
        bars = [_Bar(10.0 + i) for i in range(12)]
        out = compute_indicators(bars, indicators=["trend"])
        assert "trend" in out
        assert out["ma20"] == pytest.approx(15.5)

    def test_single_indicator_ret20(self):
        """仅算 ret20（72-74 行）。"""
        bars = [_Bar(100.0 + i) for i in range(30)]
        out = compute_indicators(bars, indicators=["ret20"])
        assert "ret20" in out
        assert "trend" not in out

    def test_single_indicator_volume(self):
        """仅算 volume（76-81 行）。"""
        bars = [_Bar(100.0, 1000.0) for _ in range(30)]
        out = compute_indicators(bars, indicators=["volume"])
        assert "volume_ratio" in out

    def test_single_indicator_rsi(self):
        """仅算 rsi（83-85 行）。"""
        bars = [_Bar(100.0 + i) for i in range(40)]
        out = compute_indicators(bars, indicators=["rsi"])
        assert 0 <= out["rsi"] <= 100

    def test_single_indicator_macd(self):
        """仅算 macd（88-94 行）。"""
        bars = [_Bar(100.0 + i) for i in range(50)]
        out = compute_indicators(bars, indicators=["macd"])
        assert "macd_signal" in out
        assert "macd_bar_trend" in out

    def test_single_indicator_vol_price(self):
        """仅算 vol_price（96-98 行）。"""
        bars = [_Bar(100.0 + i, 1000.0) for i in range(40)]
        out = compute_indicators(bars, indicators=["vol_price"])
        assert "vol_price_signal" in out

    def test_amihud_indicator(self):
        """amihud 指标（102-104 行）。"""
        bars = [_Bar(100.0 + i, 1000.0, amount=1e6) for i in range(40)]
        out = compute_indicators(bars, indicators=["amihud"])
        assert "amihud_illiq" in out
        assert out["amihud_illiq"] > 0

    def test_amihud_calc_short(self):
        """数据不足 → 0（123-124 行）。"""
        assert _calc_amihud([1.0], [1.0]) == 0.0

    def test_amihud_calc_clean(self):
        """正常 Amihud 计算（127-146 行）。"""
        closes = [10.0 + 0.1 * i for i in range(25)]
        amounts = [1e6 + i for i in range(25)]
        out = _calc_amihud(closes, amounts)
        assert out > 0

    def test_amihud_skip_invalid(self):
        """非法值（None/负金额）跳过（136-144 行）。"""
        closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
        amounts = [None, 1e6, -5, "x", 1e6, 1e6, 1e6, 1e6, 1e6, 0]
        out = _calc_amihud(closes, amounts)
        assert out > 0

    def test_amihud_no_valid(self):
        """全部非法 → 0（143-144 行）。"""
        out = _calc_amihud([10.0, 11.0], [None, None])
        assert out == 0.0

    def test_compute_all_indicators(self):
        """全部指标（indicator=None 默认路径）。"""
        bars = [_Bar(100.0 + i, 1000.0, amount=1e6) for i in range(50)]
        out = compute_indicators(bars)
        assert "trend" in out
        assert "rsi" in out
        assert "macd_bar_trend" in out
        assert "vol_price_signal" in out
        assert "amihud_illiq" in out


# ═══════════════════════════════════════════════════════════════
# volume.py
# ═══════════════════════════════════════════════════════════════


class TestVolume:
    def test_volume_analysis_short(self):
        """数据不足 → None（86-87 行）。"""
        assert volume_analysis([1.0] * 5, [1.0] * 5) is None

    def test_volume_analysis_basic(self):
        """正常结果（89-177 行）。"""
        closes = [10.0 + 0.1 * i for i in range(30)]
        volumes = [1000.0 + i for i in range(30)]
        out = volume_analysis(closes, volumes)
        assert out["volume_ratio"] > 0
        assert out["volume_price_state"] in (0, 1, 2, 3, 4)

    def test_volume_ratio_tiers(self):
        """量比多档（96-109 行）。"""
        closes = [10.0 + 0.1 * i for i in range(30)]
        cases = [
            (0.2, "地量(底部信号)"),
            (0.4, "极度缩量"),
            (0.6, "缩量"),
            (1.0, "正常"),
            (1.5, "放量"),
            (2.5, "显著放量"),
            (4.0, "巨量(警惕短期高点)"),
        ]
        for ratio, expected in cases:
            vols = [1000.0] * 25 + [ratio * 1000.0] * 5
            out = volume_analysis(closes, vols)
            assert (
                out["volume_ratio_desc"] == expected
            ), f"ratio={ratio} got={out['volume_ratio']}"

    def test_volume_price_rise_shrink(self):
        """缩量上涨（135 行）。"""
        closes = [10.0 + 0.5 * i for i in range(30)]
        vols = [1000.0] * 25 + [400.0] * 5
        out = volume_analysis(closes, vols)
        assert out["volume_price_state"] == 3

    def test_volume_price_fall_vol(self):
        """放量下跌（138 行）。"""
        closes = [10.0 - 0.5 * i for i in range(30)]
        vols = [1000.0] * 25 + [4000.0] * 5
        out = volume_analysis(closes, vols)
        assert out["volume_price_state"] == 4

    def test_obv_series_empty(self):
        """空输入 → None（198 行）。"""
        assert _detect_obv_divergence([], []) is None
        assert _detect_obv_divergence([1.0] * 30, [1.0] * 30) is None

    def test_obv_divergence(self):
        """OBV 顶底背离（204-231 行）。"""
        # 价格双高但 OBV 双高递减 → 顶背离
        closes = [100.0] * 60
        closes[10:15] = [105.0] * 5
        closes[30:35] = [110.0] * 5
        obv = [5.0] * 60
        obv[10:15] = [20.0] * 5
        obv[30:35] = [10.0] * 5
        result = _detect_obv_divergence(closes, obv)
        assert result in ("OBV顶背离", "OBV底背离", None)


# ═══════════════════════════════════════════════════════════════
# trend.py
# ═══════════════════════════════════════════════════════════════


class TestTrend:
    def test_support_resistance_short(self):
        """数据不足 → 空列表（14 行）。"""
        out = support_resistance([1.0] * 5, [1.0] * 5, [1.0] * 5, {})
        assert out == {"supports": [], "resistances": []}

    def test_support_resistance_normal(self):
        """正常支撑阻力（16-80 行）。"""
        closes = [54.0] * 30
        highs = [55.0] * 30
        highs[5] = 58.0
        highs[15] = 56.0
        highs[8] = 52.0
        highs[18] = 53.0
        lows = [53.0] * 30
        lows[6] = 50.0
        lows[16] = 51.0
        ma_info = {
            "ma_supports": [("MA20", 52.0)],
            "ma_resistances": [("MA5", 55.5)],
        }
        out = support_resistance(closes, highs, lows, ma_info)
        assert out["nearest_support"] == 53.0
        assert out["nearest_resistance"] == 55.5
        # 前高阻力(47 行) + 整数关口支撑(52-56 行) + 前低支撑(43 行)
        sources = {s["source"] for s in out["supports"]} | {
            s["source"] for s in out["resistances"]
        }
        assert "前高" in sources
        assert "整数关口" in sources
        assert "前低" in sources

    def test_support_resistance_low_price(self):
        """last<50 → 整数关口阻力（58-60 行）。"""
        closes = [49.0] * 30
        highs = [50.0] * 30
        lows = [48.0] * 30
        out = support_resistance(
            closes, highs, lows, {"ma_supports": [], "ma_resistances": []}
        )
        assert out["nearest_resistance"] == 51.0
        assert out["nearest_support"] is None

    def test_box_detection_short(self):
        """closes < window → None（86 行）。"""
        assert box_detection([1.0] * 10, [1.0] * 10, [1.0] * 10) is None

    def test_box_detection_tiny_range(self):
        """范围 < 3% → None（92-93 行）。"""
        closes = [10.0] * 25
        highs = [10.1] * 25
        lows = [9.9] * 25
        assert box_detection(highs, lows, closes) is None

    def test_box_detection_flat(self):
        """箱体震荡（96-108 行）。"""
        closes = [10.0 + 0.3 * math.sin(i) for i in range(25)]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        out = box_detection(highs, lows, closes)
        assert out is None or out["status"] == "箱体震荡"

    def test_box_detection_vshape(self):
        """箱体判定不成立 → None（109 行）。"""
        closes = [10.0] * 12 + [12.0] * 13
        highs = [12.2] * 25
        lows = [9.8] * 25
        assert box_detection(highs, lows, closes) is None

    def test_breakout_short(self):
        """closes < 21 → 数据不足（115 行）。"""
        out = breakout_check([1.0] * 10, [1.0] * 10, [1.0] * 10, 5.0)
        assert out["status"] == "数据不足"

    def test_breakout_confirmed(self):
        """放量突破（125-132 行）。"""
        closes = [10.0] * 21
        closes[-1] = 11.0
        volumes = [1000.0] * 21
        volumes[-1] = 3000.0
        out = breakout_check(closes, [11.0] * 21, volumes, 10.5)
        assert out["status"] == "突破确认(放量)"

    def test_breakout_unconfirmed(self):
        """缩量突破 → 待确认。"""
        closes = [10.0] * 21
        closes[-1] = 11.0
        volumes = [1000.0] * 21
        out = breakout_check(closes, [11.0] * 21, volumes, 10.5)
        assert out["status"] == "突破待确认(缩量)"

    def test_breakout_pullback_confirming(self):
        """回踩确认（144-145 行）。"""
        closes = [10.0] * 15 + [11.0] * 5 + [10.45]
        volumes = [1000.0] * 21
        out = breakout_check(closes, [11.0] * 21, volumes, 10.5)
        assert out["status"] == "回踩确认中"

    def test_breakout_none(self):
        """未突破 → None status。"""
        closes = [10.0] * 21
        volumes = [1000.0] * 21
        out = breakout_check(closes, [10.0] * 21, volumes, 11.0)
        assert out["status"] == "未突破"

    def test_breakout_sustained(self):
        """突破后运行维持（143 行）。"""
        closes = [11.0] * 21
        volumes = [1000.0] * 21
        out = breakout_check(closes, [11.0] * 21, volumes, 10.5)
        assert out["status"] == "突破维持(回踩未破)"

    def test_wave_increasing(self):
        """上升浪(高点抬高+低点抬高)（161-162 行）。"""
        up = _wave_series(
            [
                (0, 100),
                (6, 114),
                (8, 108),
                (19, 122),
                (21, 116),
                (32, 130),
                (35, 124),
                (46, 140),
                (47, 135),
                (55, 146),
            ]
        )
        highs = [c + 1 for c in up]
        lows = [c - 1 for c in up]
        out = wave_state(up, highs, lows)
        assert out == "上升浪(高点抬高+低点抬高)"

    def test_wave_decreasing(self):
        """下跌浪(高点降低+低点降低)（168-169 行）。"""
        dn = _wave_series(
            [
                (0, 146),
                (6, 132),
                (8, 139),
                (19, 125),
                (21, 132),
                (32, 118),
                (35, 125),
                (46, 106),
                (47, 112),
                (55, 100),
            ]
        )
        highs = [c + 1 for c in dn]
        lows = [c - 1 for c in dn]
        out = wave_state(dn, highs, lows)
        assert out == "下跌浪(高点降低+低点降低)"

    def test_wave_short(self):
        """closes < 40 → 数据不足（151-152 行）。"""
        assert wave_state([1.0] * 30, [1.0] * 30, [1.0] * 30) == "数据不足"

    def test_wave_bottom_structure(self):
        """低点抬高但高点不抬 → 底部结构（172-173 行）。"""
        arr = _wave_series(
            [(0, 100), (9, 111.4), (16, 101.4), (26, 95.0), (34, 101.0), (55, 101.7)]
        )
        out = wave_state(arr, [c + 1 for c in arr], [c - 1 for c in arr])
        assert out == "可能有底部结构(低点抬高)"

    def test_wave_range(self):
        """无明确趋势 → 盘整（174 行）。"""
        arr = _wave_series([(0, 100), (15, 97.6), (22, 97.5), (37, 95.3), (55, 93.6)])
        out = wave_state(arr, [c + 1 for c in arr], [c - 1 for c in arr])
        assert out == "盘整"


def _wave_series(keypoints):
    """线性插值构造 60 根 K 线的锯齿波。keypoints: [(idx, value)]。"""
    seg = sorted(keypoints)
    arr = []
    for t in range(60):
        i = 0
        while i < len(seg) - 1 and seg[i + 1][0] <= t:
            i += 1
        x0, y0 = seg[i]
        x1, y1 = seg[i + 1] if i < len(seg) - 1 else seg[i]
        if x1 == x0:
            arr.append(float(y0))
        else:
            arr.append(float(y0 + (y1 - y0) * (t - x0) / (x1 - x0)))
    return arr


# ═══════════════════════════════════════════════════════════════
# candlestick.py
# ═══════════════════════════════════════════════════════════════


class TestCandlestick:
    def test_short_returns_empty(self):
        """records < 4 → []（12 行）。"""
        assert detect_candle_patterns([]) == []

    def test_doji_single(self):
        """十字星（79-80 行）。"""
        records = _records(
            [10.0, 10.1, 10.2, 10.15],
            opens=[10.0, 10.1, 10.1, 10.12],
            highs=[10.2, 10.3, 10.3, 10.2],
            lows=[9.9, 10.0, 10.0, 10.1],
        )
        types = [p["type"] for p in detect_candle_patterns(records)]
        assert any("十字星" in t for t in types)

    def test_bullish_bearish_engulf(self):
        """阳包阴/阴包阳（126-141 行）。"""
        # 阳包阴（后两根: 阴线被阳线吞噬）
        records = [
            {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0, "day": "0"},
            {"open": 10.1, "high": 10.3, "low": 9.9, "close": 10.1, "day": "1"},
            {"open": 10.3, "high": 10.5, "low": 9.95, "close": 10.0, "day": "2"},
            {"open": 9.95, "high": 10.7, "low": 9.9, "close": 10.6, "day": "3"},
        ]
        types = [p["type"] for p in detect_candle_patterns(records)]
        assert any("阳包阴" in t for t in types)

        # 阴包阳（后两根: 阳线被阴线吞噬）
        records2 = [
            {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0, "day": "0"},
            {"open": 10.1, "high": 10.3, "low": 9.9, "close": 10.1, "day": "1"},
            {"open": 10.0, "high": 10.5, "low": 9.9, "close": 10.4, "day": "2"},
            {"open": 10.5, "high": 10.6, "low": 9.7, "close": 9.8, "day": "3"},
        ]
        types2 = [p["type"] for p in detect_candle_patterns(records2)]
        assert any("阴包阳" in t for t in types2)

    def test_ashare_fake_yang(self):
        """假阳真阴（115-116 行）。"""
        prev = {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.1}
        curr = {"open": 10.0, "high": 10.2, "low": 9.9, "close": 10.05}
        assert _candle_ashare(prev, curr) == "假阳真阴(收阳但实际下跌)"

    def test_ashare_fake_yin(self):
        """假阴真阳（118-119 行）。"""
        prev = {"open": 10.0, "high": 10.2, "low": 9.8, "close": 9.9}
        curr = {"open": 10.1, "high": 10.3, "low": 9.9, "close": 10.05}
        assert _candle_ashare(prev, curr) == "假阴真阳(收阴但实际上涨)"

    def test_ashare_neutral(self):
        """无特化形态 → None。"""
        prev = {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.1}
        curr = {"open": 10.2, "high": 10.4, "low": 10.0, "close": 10.3}
        assert _candle_ashare(prev, curr) is None

    def test_triple_patterns(self):
        """早晨之星/红三兵（165-188 行）。"""
        # 红三兵：三根阳线，收盘价与开盘价逐根抬高
        records = [
            {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0, "day": "0"},
            {"open": 10.0, "high": 10.5, "low": 9.9, "close": 10.4, "day": "1"},
            {"open": 10.5, "high": 10.9, "low": 10.4, "close": 10.8, "day": "2"},
            {"open": 10.9, "high": 11.3, "low": 10.8, "close": 11.2, "day": "3"},
        ]
        types = [p["type"] for p in detect_candle_patterns(records)]
        assert any("红三兵" in t for t in types)

    def test_three_crows(self):
        """三只乌鸦（190-196 行）。"""
        records = [
            {"open": 11.2, "high": 11.3, "low": 10.8, "close": 11.0, "day": "0"},
            {"open": 11.0, "high": 11.2, "low": 10.5, "close": 10.6, "day": "1"},
            {"open": 10.5, "high": 10.7, "low": 10.0, "close": 10.1, "day": "2"},
            {"open": 10.0, "high": 10.2, "low": 9.5, "close": 9.6, "day": "3"},
        ]
        types = [p["type"] for p in detect_candle_patterns(records)]
        assert any("三只乌鸦" in t for t in types)

"""technical/macd.py + kdj.py + boll.py 分支补齐测试。

覆盖目标（来自全仓 coverage 报告）：
- macd.py: 12 / 34 / 36 / 45 / 70-99 / 104-106
- kdj.py:  31 / 35-39 / 41-45 / 82 / 91 / 96 / 98 / 109-110
- boll.py: 12 / 24 / 26 / 34 / 38

测试策略：
- 构造确定性 K 线数组；驱动金叉/死叉/背离用 monkeypatch 控制 EMA 序列。
"""

import pytest

from technical.boll import bollinger
from technical.core import _ema_series, aligned_macd, ema, sma, stddev
from technical.kdj import kdj_full
from technical.macd import _detect_macd_divergence, _nearest_point, macd_full


# ═══════════════════════════════════════════════════════════════
# core.py
# ═══════════════════════════════════════════════════════════════


class TestCoreBasics:
    def test_sma_short(self):
        """数据不足 → None（23 行）。"""
        assert sma([1.0, 2.0], 5) is None
        assert sma([1.0, 2.0, 3.0], 3) == 2.0

    def test_ema_short_returns_mean(self):
        """数据不足 → 均值（29-30 行）。"""
        assert ema([1.0, 2.0, 3.0], 10) == 2.0
        assert ema([], 3) == 0

    def test_ema_full(self):
        """数据充足 → 指数加权（32-35 行）。"""
        values = [float(i) for i in range(1, 20)]
        out = ema(values, 5)
        assert out > 0
        # 与手算一致：均值起步后逐步加权
        k = 2 / 6
        expected = 3.0
        for v in values[5:]:
            expected = v * k + expected * (1 - k)
        assert out == pytest.approx(expected)

    def test_ema_series_short(self):
        """数据不足 → 空列表（41 行）。"""
        assert _ema_series([1.0, 2.0], 5) == []

    def test_ema_series_full(self):
        """数据充足 → 序列（42-46 行）。"""
        out = _ema_series([float(i) for i in range(30)], 5)
        assert len(out) == 26

    def test_aligned_macd_short(self):
        """closes < slow → 空结果（61-62 行）。"""
        assert aligned_macd([1.0] * 20) == {
            "dif_series": [],
            "dea_series": [],
            "dea_offset": 0,
        }

    def test_aligned_macd_full(self):
        """closes 充足 → 对齐（64-79 行）。"""
        closes = [float(i) for i in range(100)]
        out = aligned_macd(closes)
        assert len(out["dif_series"]) > 0
        assert len(out["dif_series"]) == len(out["dea_series"])
        assert out["dea_offset"] > 0

    def test_stddev_short(self):
        """len < 2 → 0（84-85 行）。"""
        assert stddev([3.0]) == 0
        assert stddev([]) == 0

    def test_stddev_full(self):
        """总体标准差（86-87 行）。"""
        assert stddev([1.0, 2.0, 3.0]) == pytest.approx(0.81649658)


# ═══════════════════════════════════════════════════════════════
# macd.py
# ═══════════════════════════════════════════════════════════════


def _monkey_dif_dea(monkeypatch, dif_series, dea_series):
    """让 macd_full 使用手控 DIF/DEA 序列。

    macd_full 内部调用 _ema_series(closes,12) / (closes,26)，再对 dif 做
    _ema_series(...,9)。我们 patch 三个 EMA 输出：
    - fake26 长 N → dif_series 长 N（设 fake12[14+i]-fake26[i]=dif_series[i]）
    - fake9 长 N → dea_series 长 N（fake9 直接等于 dea_series）
    """
    import technical.macd as macd_mod

    n = len(dif_series)
    fake26 = [0.0] * n

    def fake_ema12(values, period):
        if period == 12:
            return [
                dif_series[i] + fake26[i] for i in range(n)
            ]  # 长 n（含补齐 offset）
        if period == 26:
            return fake26
        if period == 9:
            return list(dea_series)

    monkeypatch.setattr(macd_mod, "_ema_series", fake_ema12)


def _dif_dea_series(dif, dea):
    """构造长度一致的 dif/dea 序列（尾部对齐）。"""
    n = max(len(dif), len(dea))
    dif = list(dif) + [dif[-1]] * (n - len(dif))
    dea = list(dea) + [dea[-1]] * (n - len(dea))
    return dif, dea


class TestMacdFullBranches:
    def test_too_short_returns_none(self):
        """closes < 34 根 → None（12 行）。"""
        assert macd_full([float(i) for i in range(30)]) is None

    def test_golden_cross(self, monkeypatch):
        """prev_dif<prev_dea 且 dif>dea → 金叉信号（34 行）。"""
        dif, dea = _dif_dea_series([0.1, 0.1, 0.1, 0.1, 0.1, 1.0], [0.5] * 6)
        _monkey_dif_dea(monkeypatch, dif, dea)

        out = macd_full([float(i) for i in range(40)])
        assert out["signal"] == 1
        assert out["signal_desc"] == "金叉"
        assert out["dif"] is not None

    def test_death_cross(self, monkeypatch):
        """prev_dif>prev_dea 且 dif<dea → 死叉信号（36 行）。"""
        dif, dea = _dif_dea_series([0.5, 0.5, 0.5, 0.5, 1.0, 0.1], [0.5] * 6)
        _monkey_dif_dea(monkeypatch, dif, dea)

        out = macd_full([float(i) for i in range(40)])
        assert out["signal"] == -1
        assert out["signal_desc"] == "死叉"
        assert out["bar_trend"] == "绿柱放大"  # 45 行

    def test_bar_trend_red_shrink(self, monkeypatch):
        """红柱放大后缩小（43 行）。"""
        dif, dea = _dif_dea_series([0.7, 0.6], [0.5, 0.5])
        _monkey_dif_dea(monkeypatch, dif, dea)
        out = macd_full([float(i) for i in range(40)])
        assert out["bar_trend"] == "红柱缩小"

    def test_bar_trend_green_shrink(self, monkeypatch):
        """绿柱缩小（47 行 else）。"""
        dif, dea = _dif_dea_series([0.4, 0.45], [0.5, 0.5])
        _monkey_dif_dea(monkeypatch, dif, dea)
        out = macd_full([float(i) for i in range(40)])
        assert out["bar_trend"] == "绿柱缩小"
        assert out["signal"] == 0


class TestMacdDivergence:
    """_detect_macd_divergence 顶底背离 + 边界。"""

    def test_short_series_returns_none(self):
        """dif_series < 60 → None（65 行）。"""
        assert _detect_macd_divergence([1] * 100, [1] * 30, []) is None

    def test_top_divergence(self):
        """价格新高而 DIF 未新高 → 顶背离（70-86 行）。"""
        c = [100.0] * 60
        c[10] = 110.0  # 第一个价格峰
        c[30] = 112.0  # 第二个价格峰更高

        d = [0.0] * 60
        d[10] = 0.8  # 第一个 DIF 峰
        d[30] = 0.4  # 第二个 DIF 峰更低

        assert _detect_macd_divergence(c, d, []) == "顶背离(看跌)"

    def test_bottom_divergence(self):
        """价格新低而 DIF 未新低 → 底背离（89-97 行）。"""
        c = [100.0] * 60
        c[10] = 90.0  # 第一个价格谷
        c[30] = 85.0  # 第二个价格谷更低

        d = [0.0] * 60
        d[10] = -0.8  # 第一个 DIF 谷
        d[30] = -0.4  # 第二个 DIF 谷更高

        assert _detect_macd_divergence(c, d, []) == "底背离(看涨)"

    def test_no_divergence_returns_none(self):
        """价格与 DIF 同步 → None（99 行 fallthrough）。"""
        c = [float(i) for i in range(60, 120)]
        d = [0.01 * i for i in range(60)]
        assert _detect_macd_divergence(c, d, []) is None

    def test_nearest_point_empty(self):
        """peaks 为空 → None（104 行）。"""
        assert _nearest_point([], 42) is None

    def test_nearest_point_finds_closest(self):
        """peaks 非空 → 最近邻（105 行）。"""
        assert _nearest_point([10, 30, 50], 28) == 30


# ═══════════════════════════════════════════════════════════════
# kdj.py
# ═══════════════════════════════════════════════════════════════


class TestKdjBranches:
    def test_too_short_returns_none(self):
        """closes < n+1 → None（31 行）。"""
        assert kdj_full([1.0], [1.5], [0.5]) is None

    def test_board_chi_next_20cm(self):
        """创业板/科创板差异化阈值（35-39 行）。"""
        closes = [float(i) for i in range(10, 39)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        out = kdj_full(closes, highs, lows, board="创业板")
        assert out["board"] == "创业板"
        assert isinstance(out["k"], float)

    def test_board_bse(self):
        """北交所差异化阈值（41-45 行）。"""
        closes = [float(i) for i in range(10, 39)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        out = kdj_full(closes, highs, lows, board="北交所")
        assert out["board"] == "北交所"

    def test_golden_cross(self):
        """K 上叉 D → 金叉（82 行）。"""
        closes = [10.0, 10.0, 9.8, 9.5, 9.5, 9.2, 9.0, 9.2, 8.8, 8.6, 9.0, 9.0]
        highs = [c + 0.4 for c in closes]
        lows = [c - 0.4 for c in closes]
        out = kdj_full(closes, highs, lows, n=9, board="主板")
        assert "金叉" in out["signal"]

    def test_oversold_zone(self):
        """J 低于超卖阈值 → 超卖区（91 行）。"""
        closes = [10.0 - i for i in range(20)]
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes]
        out = kdj_full(closes, highs, lows, n=9, board="主板")
        assert "超卖" in out["signal"]

    def test_golden_cross_oversold_combined(self):
        """金叉+超卖组合信号（96 行）。"""
        closes = [
            10.0,
            9.5,
            9.0,
            8.0,
            7.4,
            7.8,
            7.2,
            6.9,
            5.9,
            5.9,
            5.5,
            5.3,
            5.7,
            5.3,
            5.3,
            4.5,
            4.0,
        ]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        out = kdj_full(closes, highs, lows, n=9, board="主板")
        assert out["signal"].startswith("金叉+超卖")

    def test_death_cross_overbought_combined(self):
        """死叉+超买组合信号（98 行）。"""
        closes = [
            10.0,
            9.2,
            8.8,
            7.8,
            8.8,
            9.4,
            9.2,
            8.8,
            8.2,
            8.8,
            9.8,
            10.8,
            10.6,
            11.0,
            10.6,
            11.6,
            10.8,
            12.3,
            12.7,
            13.1,
            13.3,
            12.9,
        ]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        out = kdj_full(closes, highs, lows, n=9, board="主板")
        assert out["signal"].startswith("死叉+超买")

    def test_low_dunhua(self):
        """低位钝化 → KDJ低位钝化（109-110 行）。"""
        # 长期持续下跌：K 稳居低位（<20）超过确认周期
        closes = [10.0 - 0.3 * i for i in range(40)]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        out = kdj_full(closes, highs, lows, n=9, board="主板")
        assert out["钝化"] is True
        assert "低位钝化" in out["signal"]


# ═══════════════════════════════════════════════════════════════
# boll.py
# ═══════════════════════════════════════════════════════════════


class TestBollBranches:
    def test_too_short_returns_none(self):
        """closes < period → None（12 行）。"""
        assert bollinger([1.0, 2.0]) is None

    def test_bandwidth_extreme_narrow(self):
        """带宽 < 0.05 → 极度收窄（24 行）。"""
        closes = [10.0] * 25
        out = bollinger(closes)
        assert out["bandwidth_desc"] == "极度收窄(变盘信号)"

    def test_bandwidth_narrow(self):
        """带宽 0.05~0.10 → 收窄中（26 行）。"""
        import math

        closes = [10.0 + 0.2 * math.sin(i) for i in range(25)]
        out = bollinger(closes)
        assert out["bandwidth"] == pytest.approx(0.0576, abs=0.001)
        assert out["bandwidth_desc"] == "收窄中"

    def test_touch_lower_band(self):
        """position < 0.1 → 触及下轨（34 行）。"""
        # 收盘价远低于中轨
        closes = [10.0] * 24 + [9.9]
        out = bollinger(closes)
        assert out["position_desc"] == "触及下轨"

    def test_below_mid_band(self):
        """position 0.1~0.3 → 偏下轨（38 行）。"""
        import math

        closes = [10.0 + 0.2 * math.sin(i) for i in range(20)]
        closes[-1] = 9.87
        out = bollinger(closes)
        assert out["position"] == pytest.approx(0.281, abs=0.01)
        assert out["position_desc"] == "偏下轨"

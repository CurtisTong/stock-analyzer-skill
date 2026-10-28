"""本土战法 6 检测器专项单测（补 2026-10-19 审查遗留：仅 duanban 有单测）。

覆盖：sanying / shuangzhen / meirenjian / laoyatou / dibu_shouban / zhangting。
每个检测器：标准形态触发 + 关键过滤条件反例 + 数据不足边界。
mas 用 technical.moving_average.incremental_ma 生成（等长序列 + NaN 填充，
与实盘 analyzer 传入 detect_all_local_patterns 的构造一致）。
"""

from technical.moving_average import incremental_ma
from strategies.patterns.sanying import detect_sanying_yiyang
from strategies.patterns.shuangzhen import detect_shuangzhen
from strategies.patterns.meirenjian import detect_meirenjian
from strategies.patterns.laoyatou import detect_laoyatou
from strategies.patterns.dibu_shouban import detect_dibu_shouban
from strategies.patterns.zhangting import detect_zhangting


def _pack(seq, code="sh600000"):
    """(open, close, high, low, volume) 序列 → 检测器参数包。"""
    records = [
        {"day": f"2026-07-{i + 1:02d}", "open": o, "close": c, "high": h, "low": lo, "volume": v}
        for i, (o, c, h, lo, v) in enumerate(seq)
    ]
    closes = [r["close"] for r in records]
    highs = [r["high"] for r in records]
    lows = [r["low"] for r in records]
    volumes = [r["volume"] for r in records]
    mas = {
        "ma5": incremental_ma(closes, 5),
        "ma10": incremental_ma(closes, 10),
        "ma20": incremental_ma(closes, 20),
        "ma60": incremental_ma(closes, 60),
    }
    return records, closes, highs, lows, volumes, mas


def _needle(o, c, low, vol):
    """长下影线 K 线：下影 > 实体×2 且 > 上影×3。"""
    return (o, c, max(o, c) + 0.02, low, vol)


class TestSanyingYiyang:
    """三阴一阳（洗盘反弹）/ 三阳一阴（诱多出货）。"""

    def test_three_yin_one_yang_bullish(self):
        seq = [
            (10.5, 10.2, 10.6, 10.15, 5000),
            (10.2, 10.0, 10.3, 9.95, 5000),
            (10.0, 9.8, 10.1, 9.75, 5000),
            (9.8, 10.0, 10.05, 9.75, 6000),
        ]
        records, _, _, _, volumes, _ = _pack(seq)
        results = detect_sanying_yiyang(records, volumes)
        assert any(r["name"] == "三阴一阳" and r["type"] == "看涨" for r in results)
        r = results[0]
        assert r["metrics"]["total_decline"] < -1.0
        assert r["metrics"]["vol_ratio"] >= 1.0

    def test_three_yang_one_yin_bearish(self):
        seq = [
            (10.0, 10.3, 10.35, 9.95, 5000),
            (10.3, 10.6, 10.65, 10.25, 5000),
            (10.6, 10.9, 10.95, 10.55, 5000),
            (10.9, 10.4, 10.95, 10.35, 7000),
        ]
        records, _, _, _, volumes, _ = _pack(seq)
        results = detect_sanying_yiyang(records, volumes)
        assert any(r["name"] == "三阳一阴" and r["type"] == "看跌" for r in results)

    def test_rising_three_yin_not_detected(self):
        """三阴整体上涨（未跌超 -1%）不构成洗盘形态。"""
        seq = [
            (10.5, 10.48, 10.55, 10.4, 5000),
            (10.48, 10.46, 10.52, 10.4, 5000),
            (10.46, 10.45, 10.5, 10.4, 5000),
            (10.45, 10.6, 10.65, 10.4, 6000),
        ]
        records, _, _, _, volumes, _ = _pack(seq)
        # 三阴累计 (10.45-10.5)/10.5 ≈ -0.48% > -1% → 跳过
        assert not any(r["name"] == "三阴一阳" for r in detect_sanying_yiyang(records, volumes))

    def test_shrink_volume_yin_not_detected(self):
        """三阳后缩量阴线（量比 < 1.2）不识别三阳一阴。"""
        seq = [
            (10.0, 10.3, 10.35, 9.95, 5000),
            (10.3, 10.6, 10.65, 10.25, 5000),
            (10.6, 10.9, 10.95, 10.55, 5000),
            (10.9, 10.4, 10.95, 10.35, 5500),
        ]
        records, _, _, _, volumes, _ = _pack(seq)
        assert not any(r["name"] == "三阳一阴" for r in detect_sanying_yiyang(records, volumes))

    def test_insufficient_data(self):
        records, _, _, _, volumes, _ = _pack([(10, 10.2, 10.3, 9.9, 5000)] * 3)
        assert detect_sanying_yiyang(records, volumes) == []


class TestShuangzhen:
    """双针探底：6 日窗口内两根长下影低点相近 + 缩量。"""

    def _seq(self, needle_vol=3000, other_vol=10000, low2=9.52):
        return [
            (10.0, 10.05, 10.15, 9.95, other_vol),
            _needle(10.0, 10.05, 9.50, needle_vol),
            (10.05, 10.1, 10.2, 10.0, other_vol),
            _needle(10.1, 10.12, low2, needle_vol),
            (10.1, 10.15, 10.25, 10.05, other_vol),
            (10.15, 10.2, 10.3, 10.1, other_vol),
        ]

    def test_standard_shuangzhen(self):
        records, closes, _, lows, volumes, _ = _pack(self._seq())
        results = detect_shuangzhen(records, closes, lows, volumes)
        assert len(results) >= 1
        r = results[0]
        assert r["name"] == "双针探底"
        assert r["type"] == "看涨"
        assert r["confidence"] == "高"  # 低点差 <1%

    def test_wide_low_gap_not_detected(self):
        """两针低点相差 ≥2% 不识别。"""
        records, closes, _, lows, volumes, _ = _pack(self._seq(low2=9.72))
        assert detect_shuangzhen(records, closes, lows, volumes) == []

    def test_heavy_needle_volume_not_detected(self):
        """双针放量（非缩量触底）不识别。"""
        records, closes, _, lows, volumes, _ = _pack(self._seq(needle_vol=11000))
        assert detect_shuangzhen(records, closes, lows, volumes) == []

    def test_insufficient_data(self):
        records, closes, _, lows, volumes, _ = _pack([(10, 10.05, 10.15, 9.95, 5000)] * 4)
        assert detect_shuangzhen(records, closes, lows, volumes) == []


class TestMeirenjian:
    """美人肩：上升趋势 + 横盘缩量不破 MA10 + 放量突破。"""

    def _seq(self, consol_open=11.85, breakout_vol=13000, consol_vol=5000):
        seq = []
        for i in range(15):  # day0-14: 10.0 -> 11.45 上涨
            o = 10.0 + i * 0.1
            seq.append((o, o + 0.1, o + 0.15, o - 0.05, 12000))
        for _ in range(5):  # day15-19 横盘缩量（consol_open 整体下移可构造破 MA10 反例）
            seq.append((consol_open, consol_open + 0.05, consol_open + 0.2, consol_open - 0.05, consol_vol))
        seq.append((consol_open + 0.2, consol_open + 0.7, consol_open + 0.75, consol_open + 0.15, breakout_vol))
        return seq

    def test_standard_meirenjian(self):
        records, closes, highs, lows, volumes, mas = _pack(self._seq())
        results = detect_meirenjian(records, closes, highs, lows, volumes, mas)
        assert len(results) >= 1
        r = results[0]
        assert r["name"] == "美人肩"
        assert r["type"] == "看涨"
        assert r["confidence"] == "高"  # 突破量 > 横盘均量 ×2

    def test_weak_breakout_volume_not_detected(self):
        records, closes, highs, lows, volumes, mas = _pack(self._seq(breakout_vol=6000))
        assert detect_meirenjian(records, closes, highs, lows, volumes, mas) == []

    def test_consolidation_below_ma10_not_detected(self):
        """横盘价跌破 MA10 不识别。"""
        records, closes, highs, lows, volumes, mas = _pack(self._seq(consol_open=11.2))
        assert detect_meirenjian(records, closes, highs, lows, volumes, mas) == []

    def test_no_volume_shrink_not_detected(self):
        """横盘不缩量（> 前5日均量×0.7）不识别。"""
        records, closes, highs, lows, volumes, mas = _pack(self._seq(consol_vol=10000))
        assert detect_meirenjian(records, closes, highs, lows, volumes, mas) == []


class TestLaoyatou:
    """老鸭头：鸭颈多头排列 → 鸭头回踩（MA5 死叉 MA10）→ 鸭嘴放量突破。"""

    def _seq(self, second_leg_vol=16000, slope=0.65):
        seq = []
        for i in range(60):  # 铺底 + 鸭颈上涨 10 -> 22（多头排列）
            o = 10.0 + i * 0.2
            seq.append((o, o + 0.2, o + 0.3, o - 0.1, 12000))
        for i in range(11):  # day60-70 回调鸭头 22 -> 20.6
            o = 22.0 - i * 0.14
            seq.append((o, o - 0.14, o + 0.05, o - 0.2, 8000))
        for i in range(14):  # day71-84 二次上涨，鸭嘴金叉 + 放量突破前高
            o = 20.6 + i * slope
            vol = second_leg_vol if i >= 1 else 9000
            seq.append((o, o + slope, o + slope + 0.1, o - 0.1, vol))
        return seq

    def test_standard_laoyatou(self):
        records, closes, _, _, volumes, mas = _pack(self._seq())
        results = detect_laoyatou(records, closes, volumes, mas)
        assert len(results) >= 1
        r = results[0]
        assert r["name"] == "老鸭头"
        assert r["type"] == "看涨"
        assert "MA5重上MA10" in r["desc"]

    def test_no_volume_expansion_not_detected(self):
        records, closes, _, _, volumes, mas = _pack(self._seq(second_leg_vol=8500))
        assert detect_laoyatou(records, closes, volumes, mas) == []

    def test_insufficient_data(self):
        records, closes, _, _, volumes, mas = _pack([(10, 10.1, 10.2, 9.9, 5000)] * 30)
        assert detect_laoyatou(records, closes, volumes, mas) == []


class TestDibuShouban:
    """底部首板：下跌趋势后首个涨停 + 2-3 日缩量回踩不破涨停日低点。"""

    def _seq(self, pullback_close=12.1):
        seq = []
        for i in range(10):  # day0-9 上涨段（older high ~14.05）
            o = 13.0 + i * 0.1
            seq.append((o, o + 0.1, o + 0.15, o - 0.05, 10000))
        # day10-19 下跌段（recent high 13.25 < 14.05×0.95，近5日跌 >5%）
        seq.append((13.5, 13.2, 13.25, 13.1, 9000))
        for i in range(9):
            o = 13.1 - i * 0.2
            seq.append((o, o - 0.2, o + 0.05, o - 0.25, 9000))
        # day20 首板 11.4 -> 12.54（主板 10%）
        seq.append((11.4, 12.54, 12.54, 11.4, 20000))
        # day21 缩量回踩（不破涨停日低点 11.4）
        seq.append((12.4, pullback_close, 12.45, 12.0, 8000))
        # day22 阳线确认（量 > 回踩期最低量 ×1.2）
        seq.append((pullback_close, 12.5, 12.6, 12.05, 11000))
        seq.append((12.5, 12.6, 12.7, 12.45, 10000))
        return seq

    def test_standard_dibu_shouban(self):
        records, closes, highs, lows, volumes, _ = _pack(self._seq())
        results = detect_dibu_shouban(records, closes, highs, lows, volumes, "sh600000")
        assert len(results) >= 1
        r = results[0]
        assert r["name"] == "底部首板"
        assert r["type"] == "看涨"
        assert r["confidence"] == "高"  # 2 日内确认

    def test_break_limit_low_not_detected(self):
        """回踩跌破涨停日低点（×0.98）不识别。"""
        records, closes, highs, lows, volumes, _ = _pack(self._seq(pullback_close=11.0))
        assert detect_dibu_shouban(records, closes, highs, lows, volumes, "sh600000") == []

    def test_no_downtrend_not_detected(self):
        """涨停前无下跌趋势（近5日上涨）不识别。"""
        seq = self._seq()
        # 抹平 day15-19 跌幅：改为横盘（pre_change > -5%）
        for i in range(15, 20):
            seq[i] = (13.2, 13.15, 13.25, 13.1, 9000)
        records, closes, highs, lows, volumes, _ = _pack(seq)
        assert detect_dibu_shouban(records, closes, highs, lows, volumes, "sh600000") == []

    def test_insufficient_data(self):
        records, closes, highs, lows, volumes, _ = _pack([(10, 10.1, 10.2, 9.9, 5000)] * 10)
        assert detect_dibu_shouban(records, closes, highs, lows, volumes, "sh600000") == []


class TestZhangting:
    """涨停双响炮：涨停 → 1-3 日缩量整理 → 再板放量。"""

    def _seq(self, gap_days=2, consol_vol=5000, second_vol=18000):
        # 检测循环从 i=4 起，gap=1 场景需 5 根：铺垫×2 + 首板 + 整理×gap + 再板
        seq = [(9.5, 10.0, 10.1, 9.45, 8000), (9.9, 10.0, 10.1, 9.85, 8000), (10.0, 11.0, 11.0, 10.0, 10000)]
        for _ in range(gap_days):  # 整理：缩量 + 收盘 > 首板实体中点 10.5
            seq.append((11.0, 10.9, 11.1, 10.8, consol_vol))
        seq.append((10.95, 12.05, 12.05, 10.9, second_vol))
        return seq

    def test_standard_zhangting_two_day_gap(self):
        records, closes, _, _, volumes, _ = _pack(self._seq(gap_days=2))
        results = detect_zhangting(records, closes, volumes, "sh600000")
        assert len(results) >= 1
        r = results[0]
        assert r["name"] == "涨停双响炮"
        assert r["type"] == "看涨"

    def test_one_day_gap_high_confidence(self):
        """gap=1 且再板量 > 首板量×1.5 → 高置信。"""
        records, closes, _, _, volumes, _ = _pack(self._seq(gap_days=1))
        results = detect_zhangting(records, closes, volumes, "sh600000")
        assert len(results) >= 1
        assert results[0]["confidence"] == "高"

    def test_heavy_consolidation_not_detected(self):
        """整理期放量（> 首板量×0.6）不识别。"""
        records, closes, _, _, volumes, _ = _pack(self._seq(gap_days=2, consol_vol=7000))
        assert detect_zhangting(records, closes, volumes, "sh600000") == []

    def test_weak_second_board_not_detected(self):
        """再板未放量（≤ 首板量×1.2）不识别。"""
        records, closes, _, _, volumes, _ = _pack(self._seq(gap_days=2, second_vol=11000))
        assert detect_zhangting(records, closes, volumes, "sh600000") == []

    def test_insufficient_data(self):
        records, closes, _, _, volumes, _ = _pack([(10, 10.1, 10.2, 9.9, 5000)] * 3)
        assert detect_zhangting(records, closes, volumes, "sh600000") == []

"""T3：trend.py 5 项 P1 逻辑错误回归测试。

每项至少一条用例，断言具体输出值（非仅"不抛异常"）。
运行：PYTHONPATH=scripts python3 -m pytest tests/unit/test_trend_p1_fixes.py -q
"""

from technical.trend import box_detection, breakout_check, support_resistance, wave_state


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


class TestP1IntegerLevelsBothSides:
    """#1 整数关口单侧输出。"""

    def test_last_exactly_on_step_generates_both_sides(self):
        """复现 last=20.0：修复前 supports=[]、resistances=[21,22,23]。"""
        out = support_resistance(
            [20.0] * 30,
            [20.0] * 30,
            [20.0] * 30,
            {"ma_supports": [], "ma_resistances": []},
        )
        assert [s["level"] for s in out["supports"]] == [19, 18, 17, 16]
        assert [r["level"] for r in out["resistances"]] == [21, 22, 23]
        assert out["nearest_support"] == 19
        assert out["nearest_resistance"] == 21

    def test_last_off_step_generates_both_sides(self):
        """非倍数价：下方 floor 与上方 ceil 关口同时存在。"""
        out = support_resistance(
            [20.4] * 30,
            [20.4] * 30,
            [20.4] * 30,
            {"ma_supports": [], "ma_resistances": []},
        )
        assert out["nearest_support"] == 20
        assert out["nearest_resistance"] == 21

    def test_integer_levels_do_not_crowd_out_real_swing_low(self):
        """新增的双侧弱关口不得把真实摆动低点（强）挤出支撑列表。"""
        closes = [18.0] * 40
        highs = [19.0] * 40
        highs[30] = 15.0
        lows = [19.0] * 40
        lows[8] = 10.0
        out = support_resistance(closes, highs, lows, {"ma_supports": [], "ma_resistances": []})
        front_lows = [s["level"] for s in out["supports"] if s["source"] == "前低"]
        assert 10.0 in front_lows

    def test_step_10_alignment(self):
        """last>=50 时 step=10，现价恰在关口也需双侧输出。"""
        out = support_resistance(
            [50.0] * 30,
            [50.0] * 30,
            [50.0] * 30,
            {"ma_supports": [], "ma_resistances": []},
        )
        assert [s["level"] for s in out["supports"]] == [40, 30, 20, 10]
        assert [r["level"] for r in out["resistances"]] == [60, 70, 80]


class TestP1DedupKeepsStrongSource:
    """#2 去重保留弱来源。"""

    def test_strong_swing_low_beats_ma_on_same_level(self):
        """复现：18.0 修复前被标成 MA20/中，应保留 前低/强。"""
        closes = [20.0] * 60
        lows = [20.0] * 30 + [18.0] + [20.0] * 29
        out = support_resistance(
            closes,
            [20.0] * 60,
            lows,
            {"ma_supports": [("MA20", 18.0)], "ma_resistances": []},
        )
        hits = [s for s in out["supports"] if s["level"] == 18.0]
        assert len(hits) == 1
        assert hits[0]["source"] == "前低"
        assert hits[0]["strength"] == "强"


class TestP1BoxRangeBounds:
    """#3 箱体阈值方向反。"""

    def test_narrow_box_1_4pct_accepted(self):
        """1.4% 窄箱体修复前被拒（range_pct<0.03），现应识别为箱体。"""
        out = box_detection([20.14] * 25, [19.86] * 25, [20.0] * 25)
        assert out is not None
        assert out["status"] == "箱体震荡"
        assert out["range_pct"] == 1.4
        assert out["position"] == 50

    def test_wide_range_33_5pct_rejected(self):
        """33.5% 宽幅修复前被收下，现应拒绝。"""
        assert box_detection([23.35] * 25, [16.65] * 25, [20.0] * 25) is None

    def test_noise_and_very_wide_rejected(self):
        """下限 1% 防噪声、上限 20% 防宽幅乱象。"""
        assert box_detection([20.05] * 25, [19.95] * 25, [20.0] * 25) is None
        assert box_detection([22.5] * 25, [17.5] * 25, [20.0] * 25) is None


class TestP1WaveQuadrants:
    """#4 波浪象限误标。"""

    def test_converging_triangle_not_labeled_bottom(self):
        """峰 100->95->90、谷 80->85->88.5：修复前误标"可能有底部结构"。"""
        series = _wave_series(
            [(0, 80), (10, 100), (20, 80), (30, 95), (40, 85), (50, 90), (59, 88.5)]
        )
        out = wave_state(series, [c + 1 for c in series], [c - 1 for c in series])
        assert out == "收敛三角形/中性待突破(高点降低+低点抬高)"

    def test_expansion_labeled_top_risk(self):
        """高点抬高+低点降低 = 扩张/顶部风险。"""
        series = _wave_series(
            [(0, 100), (10, 80), (20, 105), (30, 78), (40, 110), (50, 76), (59, 112)]
        )
        out = wave_state(series, [c + 1 for c in series], [c - 1 for c in series])
        assert out == "扩张形态/顶部风险(高点抬高+低点降低)"

    def test_double_up_and_double_down_unchanged(self):
        """双升/双降两象限保持原有文案，不回归。"""
        up = _wave_series(
            [(0, 100), (6, 114), (8, 108), (19, 122), (21, 116),
             (32, 130), (35, 124), (46, 140), (47, 135), (55, 146)]
        )
        assert wave_state(up, [c + 1 for c in up], [c - 1 for c in up]) == "上升浪(高点抬高+低点抬高)"
        dn = _wave_series(
            [(0, 146), (6, 132), (8, 139), (19, 125), (21, 132),
             (32, 118), (35, 125), (46, 106), (47, 112), (55, 100)]
        )
        assert wave_state(dn, [c + 1 for c in dn], [c - 1 for c in dn]) == "下跌浪(高点降低+低点降低)"


class TestP1BreakoutVolumeGuards:
    """#5 突破检测空量崩溃 / 零量误报。"""

    def test_empty_volumes_returns_insufficient_data(self):
        """复现 breakout_check([1]*21,[1]*21,[],0.5) 原抛 StatisticsError。"""
        assert breakout_check([1.0] * 21, [1.0] * 21, [], 0.5) == {"status": "数据不足"}

    def test_single_volume_returns_insufficient_data(self):
        """仅 1 个量能值无法计算基准。"""
        assert breakout_check([1.0] * 21, [1.0] * 21, [1.0], 0.5) == {"status": "数据不足"}

    def test_zero_baseline_not_reported_as_volume_confirmed(self):
        """复现 volumes=[0]*20+[100]、resistance=24 原误报"突破确认(放量)"。"""
        closes = [10.0] * 21
        closes[-1] = 25.0
        out = breakout_check(closes, [25.0] * 21, [0.0] * 20 + [100.0], 24.0)
        assert out == {
            "status": "突破待确认(量能基准无效)",
            "resistance": 24.0,
            "volume_ratio": 0,
        }

    def test_normal_volume_confirmation_unchanged(self):
        """正常放量突破仍给出放量确认，ratio 与状态口径一致。"""
        closes = [10.0] * 21
        closes[-1] = 11.0
        volumes = [1000.0] * 21
        volumes[-1] = 3000.0
        out = breakout_check(closes, [11.0] * 21, volumes, 10.5)
        assert out == {
            "status": "突破确认(放量)",
            "resistance": 10.5,
            "volume_ratio": 3.0,
        }

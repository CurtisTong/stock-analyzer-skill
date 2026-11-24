"""跳空缺口识别单元测试。

覆盖：向上/向下跳空、回补/未回补、lookback 过滤、边界（数据不足/等值/
零值/浮点噪声）、支撑阻力按 top/bottom 与现价关系判定（不写死方向）。
"""

from technical.gap import detect_gaps, gap_support_resistance


def _series(pairs):
    """由 (high, low) 序列构造对齐的 opens/highs/lows/closes。"""
    highs = [p[0] for p in pairs]
    lows = [p[1] for p in pairs]
    opens = [(h + l) / 2 for h, l in pairs]
    closes = list(opens)
    return opens, highs, lows, closes


def _gap(gap_type, top, bottom, filled=False, date_index=0, fill_index=None):
    """手工构造缺口 dict，便于独立测试支撑阻力逻辑。"""
    return {
        "gap_type": gap_type,
        "top": top,
        "bottom": bottom,
        "width": top - bottom,
        "date_index": date_index,
        "filled": filled,
        "fill_index": fill_index,
    }


class TestDetectGaps:
    def test_detect_up_gap(self):
        """向上跳空：今日 low > 昨日 high，区间 [昨高, 今低]。"""
        gaps = detect_gaps(*_series([(10.0, 9.0), (12.0, 11.0)]))
        assert len(gaps) == 1
        g = gaps[0]
        assert g["gap_type"] == "up"
        assert g["top"] == 11.0
        assert g["bottom"] == 10.0
        assert g["width"] == 1.0
        assert g["date_index"] == 1
        assert g["filled"] is False
        assert g["fill_index"] is None

    def test_detect_down_gap(self):
        """向下跳空：今日 high < 昨日 low，区间 [今高, 昨低]。"""
        gaps = detect_gaps(*_series([(10.0, 9.0), (8.0, 7.0)]))
        assert len(gaps) == 1
        g = gaps[0]
        assert g["gap_type"] == "down"
        assert g["top"] == 9.0
        assert g["bottom"] == 8.0
        assert g["width"] == 1.0
        assert g["date_index"] == 1

    def test_up_gap_filled(self):
        """向上缺口被后续 low 跌回 top 回补，fill_index 指向首根回补 K 线。"""
        gaps = detect_gaps(*_series([(10.0, 9.0), (12.0, 11.0), (11.5, 10.5)]))
        assert len(gaps) == 1
        assert gaps[0]["filled"] is True
        assert gaps[0]["fill_index"] == 2

    def test_down_gap_filled(self):
        """向下缺口被后续 high 反弹到 bottom 回补。"""
        # 回补根 high=8.5 触及 bottom=8，且 low=8.0 不高于昨高 8.0（避免再形成新缺口）
        gaps = detect_gaps(*_series([(10.0, 9.0), (8.0, 7.0), (8.5, 8.0)]))
        assert len(gaps) == 1
        assert gaps[0]["filled"] is True
        assert gaps[0]["fill_index"] == 2

    def test_unfilled_gaps(self):
        """后续价格始终未触及缺口边界 -> 未回补。"""
        up = detect_gaps(*_series([(10.0, 9.0), (12.0, 11.0), (13.0, 12.0)]))
        # 回补根 high=7.5 未达 bottom=8，low=6.5 未高于昨高 8（无新缺口）
        down = detect_gaps(*_series([(10.0, 9.0), (8.0, 7.0), (7.5, 6.5)]))
        assert len(up) == 1 and up[0]["filled"] is False and up[0]["fill_index"] is None
        assert len(down) == 1 and down[0]["filled"] is False and down[0]["fill_index"] is None

    def test_lookback_filter(self):
        """只保留最近 lookback 根内形成的缺口（回补仍用完整历史）。"""
        pairs = [(10.0, 9.0), (12.0, 11.0), (13.0, 12.0), (14.0, 13.0), (16.0, 15.0), (17.0, 16.0)]
        opens, highs, lows, closes = _series(pairs)
        all_gaps = detect_gaps(opens, highs, lows, closes)
        assert [g["date_index"] for g in all_gaps] == [1, 4]
        recent = detect_gaps(opens, highs, lows, closes, lookback=2)
        assert [g["date_index"] for g in recent] == [4]
        assert recent[0]["top"] == 15.0 and recent[0]["bottom"] == 14.0
        assert detect_gaps(opens, highs, lows, closes, lookback=0) == []

    def test_insufficient_data(self):
        """少于 2 根或空数据 -> 空列表。"""
        assert detect_gaps([10.0], [10.0], [10.0], [10.0]) == []
        assert detect_gaps([], [], [], []) == []

    def test_equal_and_zero_series_no_crash(self):
        """全等值序列、零值序列不崩溃且无缺口；浮点噪声不误报。"""
        assert detect_gaps(*_series([(10.0, 10.0)] * 10)) == []
        assert detect_gaps(*_series([(0.0, 0.0)] * 5)) == []
        # 边界恰好相等（10 == 10）不算跳空
        assert detect_gaps(*_series([(10.0, 9.0), (11.0, 10.0)])) == []

    def test_return_structure_fields(self):
        """每条缺口包含全部约定字段。"""
        gaps = detect_gaps(*_series([(10.0, 9.0), (12.0, 11.0)]))
        assert gaps
        for key in ("gap_type", "top", "bottom", "width", "date_index", "filled", "fill_index"):
            assert key in gaps[0], f"缺少字段 {key}"
        assert gaps[0]["top"] >= gaps[0]["bottom"]


class TestGapSupportResistance:
    def test_direction_by_relation_not_gap_type(self):
        """支撑/阻力按区间与现价关系判定：上方即使 up 缺口也算阻力。"""
        gaps = [
            _gap("up", 11.0, 10.0, date_index=1),     # 现价下方
            _gap("down", 3.0, 2.0, date_index=5),     # 现价下方（更低）
            _gap("up", 31.0, 30.0, date_index=9),     # 现价上方
        ]
        res = gap_support_resistance(gaps, price=20.0)
        # 支撑 = 下方缺口中 top 最大者（11.0 的 up 缺口）
        assert res["nearest_gap_support"]["date_index"] == 1
        assert res["nearest_gap_support"]["gap_type"] == "up"
        # 阻力 = 上方缺口中 bottom 最小者（30.0，且是 up 缺口 -> 不写死方向）
        assert res["nearest_gap_resistance"]["date_index"] == 9
        assert res["nearest_gap_resistance"]["gap_type"] == "up"

    def test_down_gap_below_price_can_be_support(self):
        """向下缺口若整体在现价下方，同样可作支撑。"""
        gaps = [_gap("down", 8.0, 7.0, date_index=3)]
        res = gap_support_resistance(gaps, price=10.0)
        assert res["nearest_gap_support"]["date_index"] == 3
        assert res["nearest_gap_resistance"] is None

    def test_ignores_filled_gaps(self):
        """已回补缺口不参与支撑阻力判定。"""
        gaps = [
            _gap("up", 11.0, 10.0, filled=True, date_index=1, fill_index=2),
            _gap("up", 9.0, 8.0, filled=False, date_index=5),
        ]
        res = gap_support_resistance(gaps, price=20.0)
        assert res["nearest_gap_support"]["date_index"] == 5
        assert res["nearest_gap_support"]["top"] == 9.0

    def test_price_inside_gap_is_neither(self):
        """现价落在缺口区间内时既不算支撑也不算阻力。"""
        res = gap_support_resistance([_gap("up", 12.0, 10.0)], price=11.0)
        assert res == {"nearest_gap_support": None, "nearest_gap_resistance": None}

    def test_no_gaps_or_all_filled(self):
        """无缺口 / 全部回补 / 空输入 -> 双 None，不崩溃。"""
        assert gap_support_resistance([], 10.0) == {"nearest_gap_support": None, "nearest_gap_resistance": None}
        assert gap_support_resistance([_gap("up", 11.0, 10.0, filled=True)], 20.0) == {
            "nearest_gap_support": None,
            "nearest_gap_resistance": None,
        }

    def test_integration_with_detect_gaps(self):
        """detect_gaps 输出可直接喂给 gap_support_resistance。"""
        # 下方未回补向上缺口 [10,11]，上方未回补向下缺口 [30,31]
        pairs = [(10.0, 9.0), (12.0, 11.0), (13.0, 12.0), (32.0, 31.0), (30.0, 29.0)]
        gaps = detect_gaps(*_series(pairs))
        assert [g["gap_type"] for g in gaps] == ["up", "up", "down"]
        res = gap_support_resistance(gaps, price=20.0)
        assert res["nearest_gap_support"]["gap_type"] == "up"
        assert res["nearest_gap_support"]["top"] == 11.0
        assert res["nearest_gap_resistance"]["gap_type"] == "down"
        assert res["nearest_gap_resistance"]["bottom"] == 30.0

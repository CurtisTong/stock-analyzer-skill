"""T6：trend.py 剩余 5 项 P2 修复回归测试。

每项至少一条用例，断言具体输出值（非仅"不抛异常"），并覆盖 lead 给出的复现输入。
注意：P2#1 按 lead 裁决为「按设计保留，未消除 50 元处跳变」——本文件对 50 元
附近的输出做固定断言，锁定该设计口径，防止后续被无意改动。

运行：PYTHONPATH=scripts python3 -m pytest tests/unit/test_trend_p2_fixes.py -q
"""

from technical.factions import aggregate_factions
from technical.trend import breakout_check, support_resistance, wave_state

_EMPTY_MA = {"ma_supports": [], "ma_resistances": []}


def _wave_series(keypoints, n=60):
    """线性插值构造锯齿波。keypoints: [(idx, value)]。"""
    seg = sorted(keypoints)
    arr = []
    for t in range(n):
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


class TestP2StepTiers:
    """#1 整数关口步长分档（50 元跳变按设计保留）。"""

    def test_low_price_uses_half_yuan_grid(self):
        """复现：修复前 last=8.0 仍用 1 元网格 → 支撑[7,6,5,4]/阻力[9,10,11]。

        修复后 <10 元档用 0.5 元网格，低价股关口更细。
        """
        px = 8.0
        out = support_resistance([px] * 30, [px] * 30, [px] * 30, _EMPTY_MA)
        assert [s["level"] for s in out["supports"]] == [7.5, 7.0, 6.5, 6.0]
        assert [r["level"] for r in out["resistances"]] == [8.5, 9.0, 9.5]
        assert out["nearest_support"] == 7.5
        assert out["nearest_resistance"] == 8.5

    def test_50_yuan_jump_is_by_design(self):
        """lead 复现输入：49.5→1 元网格，50.0/50.5→10 元网格。

        按 T6 裁决，50/100/200 采用 10 元档属有意设计（非缺陷），此处锁定口径：
        - 49.5: 支撑 [49,48,47,46]、阻力 [50,51,52]
        - 50.0: 支撑 [40,30,20,10]、阻力 [60,70,80]
        - 50.5: 支撑 [50,40,30,20]、阻力 [60,70,80]
        """
        cases = {
            49.5: ([49, 48, 47, 46], [50, 51, 52]),
            50.0: ([40, 30, 20, 10], [60, 70, 80]),
            50.5: ([50, 40, 30, 20], [60, 70, 80]),
        }
        for px, (want_sup, want_res) in cases.items():
            out = support_resistance([px] * 30, [px] * 30, [px] * 30, _EMPTY_MA)
            assert [s["level"] for s in out["supports"]] == want_sup, f"px={px} supports"
            assert [r["level"] for r in out["resistances"]] == want_res, f"px={px} resistances"


class TestP2PullbackWindow:
    """#2 "回踩确认中"窗口必须真实覆盖 5 日（不含今日）。"""

    def test_fifth_previous_day_above_resistance_counts(self):
        """复现：突破发生在倒数第 6 根（idx15=11.0），旧 4 日切片 [-5:-1] 漏掉 → "未突破"。

        closes[-6:-1] = [11.0,10,10,10,10] 含该突破日；今日 10.45 落在阻力 10.5 的
        99% 内 → "回踩确认中"。
        """
        closes = [10.0] * 15 + [11.0] + [10.0] * 4 + [10.45]
        assert len(closes) == 21
        assert any(c > 10.5 for c in closes[-6:-1])  # 新窗口确实覆盖 idx15
        assert not any(c > 10.5 for c in closes[-5:-1])  # 旧窗口确实漏掉
        out = breakout_check(closes, [10.5] * 21, [1000.0] * 21, 10.5)
        assert out == {"status": "回踩确认中", "resistance": 10.5}


class TestP2WaveUsesHighsLows:
    """#3 wave_state 必须真正使用 highs/lows 找摆动点。"""

    def test_constant_highs_lows_change_result(self):
        """复现：传 [999]*60/[0]*60 与传原 high/low 输出相同 → 现应不同。"""
        up = _wave_series(
            [(0, 100), (6, 114), (8, 108), (19, 122), (21, 116),
             (32, 130), (35, 124), (46, 140), (47, 135), (55, 146)]
        )
        real_highs = [c + 1 for c in up]
        real_lows = [c - 1 for c in up]
        real = wave_state(up, real_highs, real_lows)
        const = wave_state(up, [999.0] * 60, [0.0] * 60)
        assert real == "上升浪(高点抬高+低点抬高)"
        assert const == "盘整"
        assert real != const

    def test_factions_keyword_contract_preserved(self):
        """四象限文案仍能被 factions.py 的关键词匹配（多头/空头结构）。"""
        up = _wave_series(
            [(0, 100), (6, 114), (8, 108), (19, 122), (21, 116),
             (32, 130), (35, 124), (46, 140), (47, 135), (55, 146)]
        )
        label_up = wave_state(up, [c + 1 for c in up], [c - 1 for c in up])
        assert aggregate_factions({"wave": label_up}, [], [], [], [], 0.0)["wave_structure"] == "多头结构"

        dn = _wave_series(
            [(0, 146), (6, 132), (8, 139), (19, 125), (21, 132),
             (32, 118), (35, 125), (46, 106), (47, 112), (55, 100)]
        )
        label_dn = wave_state(dn, [c + 1 for c in dn], [c - 1 for c in dn])
        assert label_dn == "下跌浪(高点降低+低点降低)"
        assert aggregate_factions({"wave": label_dn}, [], [], [], [], 0.0)["wave_structure"] == "空头结构"


class TestP2IntradayBreakout:
    """#4 盘中 high 越阻力、收盘回落时不得误报"未突破"。"""

    def test_intraday_high_above_resistance_reported(self):
        """lead 复现：末根 close=23、high=26、resistance=24 → 旧实现返回"未突破"。"""
        closes = [23.0] * 21
        highs = [23.0] * 20 + [26.0]
        out = breakout_check(closes, highs, [1000.0] * 21, 24.0)
        assert out == {"status": "盘中突破待确认(收盘回落)", "resistance": 24.0}

    def test_no_intraday_and_no_close_break_still_none(self):
        """high 与 close 均未越阻力 → 仍为"未突破"（新分支不误报）。"""
        closes = [23.0] * 21
        out = breakout_check(closes, [23.0] * 21, [1000.0] * 21, 24.0)
        assert out == {"status": "未突破"}

    def test_close_breakout_semantics_unchanged(self):
        """收盘越阻力仍走既有放量确认分支（新分支不抢先）。"""
        closes = [10.0] * 21
        closes[-1] = 25.0
        volumes = [1000.0] * 21
        volumes[-1] = 3000.0
        out = breakout_check(closes, [26.0] * 21, volumes, 24.0)
        assert out == {"status": "突破确认(放量)", "resistance": 24.0, "volume_ratio": 3.0}


class TestP2BreakoutTargetFallback:
    """#5 单边上涨无摆动高点时，breakout_target 不得为 None。"""

    def test_strict_uptrend_falls_back_to_21bar_high(self):
        """60 根严格上涨：_find_swing_points(window=3) 的 ph=[] → 旧实现 target=None。"""
        closes = [100.0 + i for i in range(60)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        out = support_resistance(closes, highs, lows, _EMPTY_MA)
        assert out["recent_swing_highs"] == []  # 前置条件：确无摆动高点
        assert out["breakout_target"] == max(highs[-21:-1])
        assert out["breakout_target"] == 158.5  # highs[-2] = 158.5（具体值）

    def test_real_swing_high_takes_priority_over_fallback(self):
        """有摆动高点时仍取最近的下方摆动高点，不被 21 日回退值覆盖。"""
        highs = [14.0] * 30
        highs[5] = 15.0  # 唯一摆动高点：低于现价 16.0，且落在 [-21:-1] 窗口之外
        closes = [16.0] * 30
        out = support_resistance(closes, highs, [16.0] * 30, _EMPTY_MA)
        assert out["recent_swing_highs"] == [15.0]
        assert out["breakout_target"] == 15.0
        assert max(highs[-21:-1]) == 14.0  # 回退值不同，证明走的是摆动高点分支

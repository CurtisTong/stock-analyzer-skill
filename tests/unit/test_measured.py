"""measured_move 形态量度目标位测试（对称派：双顶/双底/auto）。"""

from __future__ import annotations

import pytest

from technical.measured import measured_move

TOL = 1e-6

# 标准双顶：摆动高点 idx10=105 / idx22=104（差 < 3%），其间摆动低点 idx16=90。
H_TOP = [
    90, 91, 92, 93, 94, 95, 96, 98, 101, 104,
    105, 103, 101, 99, 97, 96, 95, 94, 96, 98,
    100, 102, 104, 103, 102, 100, 98, 96, 94, 92,
    90, 88, 86, 84, 82, 80, 78, 76, 74, 72,
]
L_TOP = [
    85, 86, 87, 88, 89, 90, 91, 93, 95, 97,
    99, 96, 94, 93, 92, 91, 90, 91, 92, 93,
    94, 96, 98, 96, 94, 93, 92, 91, 90, 89,
    88, 87, 86, 85, 84, 83, 82, 81, 80, 79,
]
C_TOP = H_TOP[:-1] + [88]  # 末根收盘已跌破颈线 90

# 标准双底：摆动低点 idx10=95 / idx22=96，其间摆动高点 idx16=110。
L_BOTTOM = [
    110, 109, 108, 107, 106, 105, 104, 102, 99, 97,
    95, 97, 99, 101, 103, 105, 106, 104, 102, 100,
    98, 97, 96, 98, 100, 102, 104, 106, 107, 108,
    109, 110, 111, 112, 113, 114, 115, 116, 117, 118,
]
H_BOTTOM = [
    115, 114, 113, 112, 111, 110, 109, 107, 104, 101,
    99, 101, 103, 105, 107, 109, 110, 109, 107, 105,
    103, 101, 100, 102, 104, 106, 108, 110, 111, 112,
    113, 114, 115, 116, 117, 118, 119, 120, 121, 122,
]
C_BOTTOM = H_BOTTOM[:-1] + [120]


class TestDoubleTop:
    def test_standard_double_top(self):
        """双顶量度目标 = 颈线 - (两顶均值 - 颈线)，落在现价下方。"""
        r = measured_move(C_TOP, H_TOP, L_TOP, "double_top")
        assert r["pattern"] == "double_top"
        assert r["direction"] == "down"
        assert r["neckline"] == pytest.approx(90.0, abs=TOL)
        assert r["peak"] == pytest.approx(104.5, abs=TOL)
        assert r["height"] == pytest.approx(14.5, abs=TOL)
        assert r["target"] == pytest.approx(75.5, abs=TOL)
        assert r["target"] < C_TOP[-1]  # 现价下方的具体点位

    def test_equal_peaks_boundary(self):
        """边界等值：两顶高度完全相等仍识别，容差 3% 内。"""
        highs = list(H_TOP)
        highs[22] = 105  # 与 idx10 完全相等
        r = measured_move(C_TOP, highs, L_TOP, "double_top")
        assert r["pattern"] == "double_top"
        assert r["peak"] == pytest.approx(105.0, abs=TOL)
        assert r["target"] == pytest.approx(75.0, abs=TOL)


class TestDoubleBottom:
    def test_standard_double_bottom(self):
        """双底量度目标 = 颈线 + (颈线 - 两底均值)，方向 up。"""
        r = measured_move(C_BOTTOM, H_BOTTOM, L_BOTTOM, "double_bottom")
        assert r["pattern"] == "double_bottom"
        assert r["direction"] == "up"
        assert r["neckline"] == pytest.approx(110.0, abs=TOL)
        assert r["peak"] == pytest.approx(95.5, abs=TOL)  # 两底均值（谷值）
        assert r["height"] == pytest.approx(14.5, abs=TOL)
        assert r["target"] == pytest.approx(124.5, abs=TOL)
        assert r["target"] > C_BOTTOM[-1]


class TestAuto:
    def test_auto_selects_double_top(self):
        r = measured_move(C_TOP, H_TOP, L_TOP, "auto")
        assert r["pattern"] == "double_top"
        assert r["target"] == pytest.approx(75.5, abs=TOL)

    def test_auto_selects_double_bottom(self):
        r = measured_move(C_BOTTOM, H_BOTTOM, L_BOTTOM, "auto")
        assert r["pattern"] == "double_bottom"
        assert r["target"] == pytest.approx(124.5, abs=TOL)


class TestFailurePaths:
    def test_insufficient_data(self):
        """数据不足：返回 target=None + reason，且不崩溃。"""
        r = measured_move([1, 2, 3], [1, 2, 3], [1, 2, 3], "double_top")
        assert r == {
            "pattern": "double_top",
            "target": None,
            "reason": r["reason"],
        }
        assert r["reason"]

    def test_no_pattern_detected(self):
        """单调上涨无摆动点：识别失败。"""
        values = list(range(1, 41))
        r = measured_move(values, values, values, "auto")
        assert r["pattern"] == "auto"
        assert r["target"] is None
        assert r["reason"]

    def test_invalid_pattern(self):
        r = measured_move(C_TOP, H_TOP, L_TOP, "head_shoulders")
        assert r["target"] is None
        assert r["pattern"] == "head_shoulders"


class TestPurity:
    def test_inputs_unchanged(self):
        """纯函数：调用前后输入序列不被修改。"""
        closes, highs, lows = list(C_TOP), list(H_TOP), list(L_TOP)
        measured_move(closes, highs, lows, "auto")
        assert closes == C_TOP
        assert highs == H_TOP
        assert lows == L_TOP

"""T7/T9 二轮修复回归测试。

T7: ma_stop_buy 买点输出新增 stop_price 字段（止损口径 min(MA20*0.98, 近10根最低)）。
T9: ma_system 排列判断不再因某条 MA 为 0 而跳过比较，避免误判多头排列。
"""

import pytest

from technical.ma_stop import ma_stop_buy
from technical.moving_average import ma_system


# ── T7：止损价字段 ────────────────────────────────────────────────────

# 复用 P1「并列最低」样本：近 10 根 lows = [5,5,6,7,8,9,10,11,12,13]，
# 最低价落在窗口内部 → 条件A 成立（同时防止并列最低漏报修复被回退）。
_T7_CLOSES = [10.0] * 9 + [11.0, 13.0]
_T7_LOWS = [1.0] * 9 + [5.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0]
_T7_HIGHS = [c + 1.0 for c in _T7_CLOSES]


class TestMaStopStopPrice:
    """买点信号的 stop_price 字段。"""

    def test_stop_price_when_signal_triggered_recent_low_smaller(self):
        """触发买点：stop_price 取近 10 根最低价（本样本小于 MA20*0.98），desc 有说明。"""
        ma20 = 9.0
        res = ma_stop_buy(_T7_CLOSES, _T7_HIGHS, _T7_LOWS, {"ma5": 10.0, "ma20": ma20})
        assert res is not None
        assert res["signal"] == 1
        expected = min(ma20 * 0.98, min(_T7_LOWS[-10:]))
        assert expected == pytest.approx(5.0)  # 本样本由近 10 根最低价决定
        assert res["stop_price"] == pytest.approx(expected)
        assert "止损价" in res["desc"]
        for key in ("status", "signal", "desc", "type"):
            assert key in res, f"既有字段丢失: {key}"

    def test_stop_price_when_signal_triggered_ma20_breach_smaller(self):
        """触发买点：stop_price 由 MA20*0.98 决定时数值同样正确。"""
        ma20 = 5.0
        res = ma_stop_buy(_T7_CLOSES, _T7_HIGHS, _T7_LOWS, {"ma5": 10.0, "ma20": ma20})
        assert res is not None
        assert res["signal"] == 1
        expected = min(ma20 * 0.98, min(_T7_LOWS[-10:]))
        assert expected == pytest.approx(4.9)
        assert res["stop_price"] == pytest.approx(expected)

    def test_stop_price_none_when_no_signal(self):
        """无信号：signal=0 且 stop_price=None，既有 4 键仍保留。"""
        closes = [10.0]
        for _ in range(24):
            closes.append(round(closes[-1] - 0.2, 2))
        lows = [c - 0.1 for c in closes]
        highs = [c + 0.1 for c in closes]
        res = ma_stop_buy(closes, highs, lows, ma_system(closes))
        assert res is not None
        assert res["signal"] == 0
        assert res["stop_price"] is None
        for key in ("status", "signal", "desc", "type"):
            assert key in res, f"既有字段丢失: {key}"


# ── T9：排列判断真值过滤 ──────────────────────────────────────────────


class TestMaAlignmentZeroMa:
    """MA=0 不得被真值过滤跳过比较。"""

    def test_zero_ma_not_misjudged_as_bullish_alignment(self):
        """ma5..ma250=[10,9,0,8,7,6] 应判为「交叉震荡」，修复前误判「多头排列」。

        构造 250 根使分段和精确命中：MA20=0 打断递减序列；修复前
        `if mas[i] and mas[i+1]` 会跳过 0 相关的两次比较，剩余比较全为真 → 误判多头。
        """
        closes = (
            [5.0] * 120 + [6.0] * 10  # c[0..129] 和=660
            + [6.0] * 60              # c[130..189] 和=360 → MA120 分子=840
            + [12.0] * 40             # c[190..229] 和=480 → MA60 分子=480
            + [-9.0] * 10             # c[230..239] 和=-90 → MA20 分子=0
            + [8.0] * 5               # c[240..244] 和=40  → MA10 分子=90
            + [10.0] * 5              # c[245..249] 和=50  → MA5 分子=50
        )
        assert len(closes) == 250
        res = ma_system(closes)
        assert [res[f"ma{p}"] for p in (5, 10, 20, 60, 120, 250)] == [
            10.0,
            9.0,
            0.0,
            8.0,
            7.0,
            6.0,
        ]
        assert res["alignment"] == "交叉震荡"

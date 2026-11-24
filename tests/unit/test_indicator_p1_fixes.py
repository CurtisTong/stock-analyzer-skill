"""P1 指标修复回归测试：boll 首次触轨 / ma_stop 并列最低 / scoring 高位金叉。

三项修复：
1. boll.bollinger 新增 first_touch_upper / first_touch_lower：本轮首次穿越才为
   True，同一趋势第二次触轨为 False，数据不足无法重算前一根为 False。
2. ma_stop 并列最低：窗口内并列最小值取**最后一个**索引，避免首个落在最老端
   被误判为"一路走高无下探"而漏报；稳态上涨仍不触发。
3. scoring._score_kdj："金叉+超买"按超买口径 0.3 计分，不再落入泛金叉 0.8 分支。
"""

import pytest

from technical.boll import bollinger
from technical.ma_stop import ma_stop_buy
from technical.moving_average import ma_system
from technical.scoring import _score_kdj


class TestBollFirstTouch:
    """布林带首次触轨事件。"""

    def test_first_touch_upper_true(self):
        """前一根未触上轨、当前触上轨 → first_touch_upper=True。"""
        # 前 24 根横盘（前一根 position≈0.5），最后一根跳高使 position>0.9
        out = bollinger([10.0] * 24 + [12.0])
        assert out["position"] > 0.9
        assert out["first_touch_upper"] is True
        assert out["first_touch_lower"] is False

    def test_second_consecutive_upper_touch_false(self):
        """连续两根触上轨：最新一根是同一趋势第二次触轨 → False。"""
        out = bollinger([10.0] * 23 + [12.0, 12.0])
        assert out["position"] > 0.9
        assert out["first_touch_upper"] is False

    def test_first_touch_lower_true(self):
        """前一根未触下轨、当前触下轨 → first_touch_lower=True。"""
        out = bollinger([10.0] * 24 + [8.0])
        assert out["position"] < 0.1
        assert out["first_touch_lower"] is True
        assert out["first_touch_upper"] is False

    def test_second_consecutive_lower_touch_false(self):
        """连续两根触下轨：最新一根是同一趋势第二次触轨 → False。"""
        out = bollinger([10.0] * 23 + [8.0, 8.0])
        assert out["position"] < 0.1
        assert out["first_touch_lower"] is False

    def test_insufficient_history_for_prev_bar_is_false(self):
        """仅有 period 根，无法重算前一根 position → 触轨事件置 False。"""
        out = bollinger([10.0] * 19 + [12.0])  # len == period == 20
        assert out["position"] > 0.9
        assert out["first_touch_upper"] is False
        assert out["first_touch_lower"] is False

    def test_no_touch_and_legacy_keys_preserved(self):
        """未触轨时两字段均 False，且既有返回键不变（向后兼容）。"""
        out = bollinger([10.0] * 25)
        assert out["first_touch_upper"] is False
        assert out["first_touch_lower"] is False
        for key in (
            "upper",
            "mid",
            "lower",
            "bandwidth",
            "bandwidth_desc",
            "position",
            "position_desc",
            "squeeze",
            "low_vol_squeeze",
        ):
            assert key in out, f"既有字段丢失: {key}"


class TestMaStopTiedLow:
    """均线止跌并列最低价漏报。"""

    def test_tied_low_not_missed(self):
        """复现：并列最低使 .index() 取首个（最老端）导致漏报，修复后应触发条件A。"""
        closes = [10.0] * 9 + [11.0, 13.0]
        lows = [1.0] * 9 + [5.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0]
        highs = [c + 1.0 for c in closes]
        res = ma_stop_buy(closes, highs, lows, {"ma5": 10.0, "ma20": 9.0})
        assert res is not None
        assert res["signal"] == 1
        assert res["type"] == "站上5日线"

    def test_steady_uptrend_still_no_signal(self):
        """防回归：稳态上涨（最低点恒在最老端）不得因修复变成恒真买点。"""
        closes = [100.0 + i * 0.3 for i in range(110)]
        lows = [c - 0.2 for c in closes]
        highs = [c + 0.2 for c in closes]
        hits = 0
        for i in range(30, 110):
            res = ma_stop_buy(closes[: i + 1], highs[: i + 1], lows[: i + 1], ma_system(closes[: i + 1]))
            if res and res.get("signal") == 1:
                hits += 1
        assert hits == 0


class TestKdjGoldenCrossOverboughtScore:
    """高位金叉不得按泛金叉正面计分。"""

    _TYPE_W = {"kdj": 1.0}
    _OSC_ADJ = {"trend_following": 0.8}  # 震荡市 → kdj_active → kdj_weight=10

    def test_golden_cross_overbought_scored_as_overbought(self):
        """金叉+超买 = 超买口径 0.3（修复前走泛金叉 0.8 = 8.0）。"""
        score = _score_kdj({"signal": "金叉+超买", "钝化": False}, self._TYPE_W, self._OSC_ADJ, 0)
        assert score == pytest.approx(3.0)  # 10 * 0.3

    def test_golden_cross_overbought_less_than_oversold(self):
        """超买区金叉得分必须低于超卖区金叉。"""
        overbought = _score_kdj({"signal": "金叉+超买", "钝化": False}, self._TYPE_W, self._OSC_ADJ, 0)
        oversold = _score_kdj({"signal": "金叉+超卖", "钝化": False}, self._TYPE_W, self._OSC_ADJ, 0)
        assert overbought < oversold
        assert oversold == pytest.approx(10.0)  # 10 * 1.0 * 1.0 * 1.0

    def test_matches_pure_overbought_score(self):
        """金叉+超买 与 纯超买（K=88 超买区）分值一致，不再多 5 分。"""
        pure = _score_kdj({"signal": "超买区(K=88)", "钝化": False}, self._TYPE_W, self._OSC_ADJ, 0)
        combo = _score_kdj({"signal": "金叉+超买", "钝化": False}, self._TYPE_W, self._OSC_ADJ, 0)
        assert pure == pytest.approx(3.0)
        assert combo == pytest.approx(pure)

    def test_dunhua_penalty_applies_to_golden_cross_overbought(self):
        """钝化时金叉+超买继续按超买口径并乘钝化惩罚。"""
        score = _score_kdj({"signal": "金叉+超买", "钝化": True}, self._TYPE_W, self._OSC_ADJ, 0)
        assert score == pytest.approx(0.75)  # 钝化权重 5 * 0.3 * 0.5

    def test_plain_golden_cross_unchanged(self):
        """防回归：无超买的普通金叉仍走 0.8 分支。"""
        score = _score_kdj({"signal": "金叉", "钝化": False}, self._TYPE_W, self._OSC_ADJ, 0)
        assert score == pytest.approx(8.0)  # 10 * 0.8

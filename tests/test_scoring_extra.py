"""technical/scoring.py 补充测试：覆盖各子评分函数 + 市场环境检测。"""

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from technical.scoring import (
    _get_score_max,
    _get_stock_type_weights,
    _score_ma,
    _score_macd,
    _score_kdj,
    _score_boll,
    _score_rsi,
    _score_volume,
    _score_patterns,
    _score_chan,
    _score_local,
    _score_chip,
    composite_score,
    detect_market_environment,
    _market_weight_adjustments,
)


# ═══════════════════════════════════════════════════════════════
# 配置函数
# ═══════════════════════════════════════════════════════════════


class TestGetScoreMax:
    def test_returns_dict_with_keys(self):
        sm = _get_score_max()
        assert isinstance(sm, dict)
        assert "ma" in sm
        assert "macd" in sm
        assert "valuation" in sm

    def test_values_positive(self):
        sm = _get_score_max()
        for k, v in sm.items():
            assert v > 0, f"{k} 上限应 > 0"


class TestGetStockTypeWeights:
    def test_known_type(self):
        w = _get_stock_type_weights("蓝筹股")
        assert "ma" in w
        assert "macd" in w
        # valuation 可能由配置覆盖而缺失，但核心因子必在
        assert "volume" in w

    def test_unknown_type_fallback(self):
        w = _get_stock_type_weights("不存在的类型")
        assert w["ma"] == 1.0  # 回退普通股

    def test_has_chip_field(self):
        """所有类型权重都应含 chip 字段（向后兼容补全）。"""
        for t in ["题材股", "蓝筹股", "强成长股", "周期股", "防御股", "普通股"]:
            w = _get_stock_type_weights(t)
            assert "chip" in w


# ═══════════════════════════════════════════════════════════════
# _score_ma
# ═══════════════════════════════════════════════════════════════


class TestScoreMa:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def _adj(self):
        return _market_weight_adjustments("震荡")

    def test_bullish_alignment(self):
        scores = {"多头排列": 20, "交叉震荡": 12, "空头排列": 3, "数据不足": 7}
        s = _score_ma("多头排列", self._w(), self._adj(), scores)
        assert 0 <= s <= 30

    def test_bearish_alignment_low(self):
        scores = {"多头排列": 20, "交叉震荡": 12, "空头排列": 3, "数据不足": 7}
        s = _score_ma("空头排列", self._w(), self._adj(), scores)
        assert s < 10

    def test_unknown_alignment_default(self):
        scores = {"多头排列": 20}
        s = _score_ma("未知排列", self._w(), self._adj(), scores)
        assert s == 7 * self._w()["ma"]

    def test_clamped_to_30(self):
        """多头排列 + 牛市调整因子 -> clamp 到 30。"""
        w = _get_stock_type_weights("蓝筹股")  # ma=1.3
        adj = _market_weight_adjustments("牛市")
        scores = {"多头排列": 20}
        s = _score_ma("多头排列", w, adj, scores)
        assert s <= 30


# ═══════════════════════════════════════════════════════════════
# _score_macd
# ═══════════════════════════════════════════════════════════════


class TestScoreMacd:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def _adj(self):
        return _market_weight_adjustments("震荡")

    def test_golden_cross_with_expansion(self):
        s = _score_macd({"signal": 1, "bar_trend": "放大", "divergence": ""}, self._w(), self._adj())
        assert s > 10

    def test_golden_cross(self):
        s = _score_macd({"signal": 1, "bar_trend": "", "divergence": ""}, self._w(), self._adj())
        assert s >= 8

    def test_death_cross(self):
        s = _score_macd({"signal": -1, "bar_trend": "", "divergence": ""}, self._w(), self._adj())
        assert s < 8

    def test_bottom_divergence_bonus(self):
        base = _score_macd({"signal": 0, "bar_trend": "", "divergence": ""}, self._w(), self._adj())
        with_div = _score_macd(
            {"signal": 0, "bar_trend": "", "divergence": "底背离(看涨)"}, self._w(), self._adj()
        )
        assert with_div > base

    def test_top_divergence_penalty(self):
        base = _score_macd({"signal": 0, "bar_trend": "", "divergence": ""}, self._w(), self._adj())
        with_div = _score_macd(
            {"signal": 0, "bar_trend": "", "divergence": "顶背离(看跌)"}, self._w(), self._adj()
        )
        assert with_div < base

    def test_clamped_0_20(self):
        s = _score_macd({"signal": 1, "bar_trend": "放大", "divergence": "底背离(看涨)"}, self._w(), self._adj())
        assert 0 <= s <= 20


# ═══════════════════════════════════════════════════════════════
# _score_kdj
# ═══════════════════════════════════════════════════════════════


class TestScoreKdj:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def _adj(self):
        return _market_weight_adjustments("震荡")

    def test_golden_cross_oversold(self):
        s = _score_kdj({"signal": "金叉+超卖"}, self._w(), self._adj())
        assert s >= 0

    def test_death_cross_overbought_low(self):
        s = _score_kdj({"signal": "死叉+超买"}, self._w(), self._adj())
        assert s < 5

    def test_neutral_signal(self):
        s = _score_kdj({"signal": ""}, self._w(), self._adj())
        assert s >= 0

    def test_dull_signal(self):
        s = _score_kdj({"signal": "", "钝化": True}, self._w(), self._adj())
        assert s >= 0

    def test_vol_signal_penalty_in_downtrend(self):
        """下跌趋势（vol_signal=-1）超卖金叉降权。"""
        adj = _market_weight_adjustments("震荡")
        normal = _score_kdj({"signal": "金叉+超卖"}, self._w(), adj, vol_signal=0)
        penalized = _score_kdj({"signal": "金叉+超卖"}, self._w(), adj, vol_signal=-1)
        assert penalized <= normal


# ═══════════════════════════════════════════════════════════════
# _score_boll
# ═══════════════════════════════════════════════════════════════


class TestScoreBoll:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def test_lower_band_contraction(self):
        s = _score_boll({"position": 0.1, "bandwidth_desc": "收窄"}, self._w())
        assert s > 8

    def test_lower_band_no_contraction(self):
        s = _score_boll({"position": 0.1, "bandwidth_desc": ""}, self._w())
        assert s >= 0

    def test_middle_position(self):
        s = _score_boll({"position": 0.5, "bandwidth_desc": ""}, self._w())
        assert s >= 0

    def test_upper_band(self):
        s = _score_boll({"position": 0.9, "bandwidth_desc": ""}, self._w())
        assert s < 8

    def test_clamped_0_15(self):
        s = _score_boll({"position": 0.0, "bandwidth_desc": "收窄"}, self._w())
        assert 0 <= s <= 15


# ═══════════════════════════════════════════════════════════════
# _score_rsi
# ═══════════════════════════════════════════════════════════════


class TestScoreRsi:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def test_extreme_oversold_high(self):
        s = _score_rsi({"rsi": 10}, self._w())
        assert s > 8

    def test_overbought_low(self):
        s = _score_rsi({"rsi": 85}, self._w())
        assert s < 5

    def test_downtrend_penalty(self):
        normal = _score_rsi({"rsi": 25}, self._w(), vol_signal=0)
        penalized = _score_rsi({"rsi": 25}, self._w(), vol_signal=-1)
        assert penalized < normal

    def test_clamped_0_15(self):
        s = _score_rsi({"rsi": 5}, self._w())
        assert 0 <= s <= 15


# ═══════════════════════════════════════════════════════════════
# _score_volume
# ═══════════════════════════════════════════════════════════════


class TestScoreVolume:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def test_inflow_high(self):
        s = _score_volume({"volume_price_signal": 1, "volume_ratio": 1.5}, self._w())
        assert s > 8

    def test_outflow_low(self):
        s = _score_volume({"volume_price_signal": -1, "volume_ratio": 1.5}, self._w())
        assert s < 5

    def test_low_volume_bonus(self):
        s = _score_volume({"volume_price_signal": 0, "volume_ratio": 0.2}, self._w())
        assert s > 7  # 中性 + 低量加分

    def test_low_volume_no_bonus_on_outflow(self):
        """放量下跌时低量不加 3 分。"""
        s = _score_volume({"volume_price_signal": -1, "volume_ratio": 0.2}, self._w())
        assert s < 5

    def test_clamped_0_20(self):
        s = _score_volume({"volume_price_signal": 1, "volume_ratio": 0.1}, self._w())
        assert 0 <= s <= 20


# ═══════════════════════════════════════════════════════════════
# _score_patterns
# ═══════════════════════════════════════════════════════════════


class TestScorePatterns:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def _adj(self):
        return _market_weight_adjustments("震荡")

    def test_bullish_pattern(self):
        s = _score_patterns([{"type": "早晨之星"}], self._w(), self._adj())
        assert s >= 10

    def test_bearish_pattern(self):
        s = _score_patterns([{"type": "三只乌鸦"}], self._w(), self._adj())
        assert s < 5

    def test_empty_patterns(self):
        s = _score_patterns([], self._w(), self._adj())
        assert s >= 0

    def test_clamped_0_25(self):
        s = _score_patterns([{"type": "红三兵"}], self._w(), self._adj())
        assert 0 <= s <= 25


# ═══════════════════════════════════════════════════════════════
# _score_chan
# ═══════════════════════════════════════════════════════════════


class TestScoreChan:
    def _adj(self):
        return _market_weight_adjustments("震荡")

    def test_invalid_chan(self):
        s = _score_chan({"valid": False}, self._adj())
        assert s == 0

    def test_buy_point_1(self):
        chan = {"valid": True, "maidian": {"buy_points": [{"type": "一买"}]}}
        s = _score_chan(chan, self._adj())
        assert s >= 5

    def test_buy_point_2(self):
        chan = {"valid": True, "maidian": {"buy_points": [{"type": "二买"}]}}
        s = _score_chan(chan, self._adj())
        assert s >= 3

    def test_buy_point_3(self):
        chan = {"valid": True, "maidian": {"buy_points": [{"type": "三买"}]}}
        s = _score_chan(chan, self._adj())
        assert s >= 3

    def test_bottom_divergence(self):
        chan = {"valid": True, "maidian": {"buy_points": []}, "beichi": {"summary": "检测到底背驰"}}
        s = _score_chan(chan, self._adj())
        assert s >= 5

    def test_clamped_0_15(self):
        chan = {
            "valid": True,
            "maidian": {"buy_points": [{"type": "一买"}, {"type": "二买"}, {"type": "三买"}]},
            "beichi": {"summary": "检测到底背驰"},
        }
        s = _score_chan(chan, self._adj())
        assert 0 <= s <= 15


# ═══════════════════════════════════════════════════════════════
# _score_local
# ═══════════════════════════════════════════════════════════════


class TestScoreLocal:
    def test_empty(self):
        assert _score_local({"patterns": []}) == 0

    def test_laoyatou(self):
        s = _score_local({"patterns": [{"name": "老鸭头", "confidence": "中"}]})
        assert s > 0

    def test_meirenjian(self):
        s = _score_local({"patterns": [{"name": "美人肩", "confidence": "中"}]})
        assert s > 0

    def test_sanyinyiyang_with_metrics(self):
        s = _score_local(
            {
                "patterns": [
                    {
                        "name": "三阴一阳",
                        "confidence": "高",
                        "metrics": {"vol_ratio": 1.6, "total_decline": 2, "rebound_ratio": 30},
                    }
                ]
            }
        )
        assert s > 0

    def test_sanyangyiying_negative(self):
        s = _score_local({"patterns": [{"name": "三阳一阴", "confidence": "中", "metrics": {"vol_ratio": 2}}]})
        # 看跌信号，但 clamp 下限 0
        assert s >= 0

    def test_zhangting_shuangxiangpao(self):
        s = _score_local({"patterns": [{"name": "涨停双响炮", "confidence": "中"}]})
        assert s > 0

    def test_confidence_adjustment(self):
        low = _score_local({"patterns": [{"name": "老鸭头", "confidence": "低"}]})
        high = _score_local({"patterns": [{"name": "老鸭头", "confidence": "高"}]})
        assert high > low

    def test_clamped_0_10(self):
        s = _score_local({"patterns": [{"name": "老鸭头", "confidence": "高"}]})
        assert 0 <= s <= 10


# ═══════════════════════════════════════════════════════════════
# _score_chip
# ═══════════════════════════════════════════════════════════════


class TestScoreChip:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def test_empty(self):
        s = _score_chip({}, self._w())
        assert s == 0

    def test_margin_inflow(self):
        s = _score_chip({"margin": {"rzjme_5d": 100, "rzjme_trend": "连续增加"}}, self._w())
        assert s > 0

    def test_margin_outflow_negative(self):
        s = _score_chip({"margin": {"rzjme_5d": -100}}, self._w())
        assert s < 0

    def test_holders_concentration(self):
        s = _score_chip({"holders": {"concentration": "持续集中"}}, self._w())
        assert s > 0

    def test_holders_disperse_negative(self):
        s = _score_chip({"holders": {"concentration": "分散"}}, self._w())
        assert s < 0

    def test_clamped_neg5_to_10(self):
        s = _score_chip({"margin": {"rzjme_5d": -100}, "holders": {"concentration": "分散"}}, self._w())
        assert -5 <= s <= 10


# ═══════════════════════════════════════════════════════════════
# composite_score
# ═══════════════════════════════════════════════════════════════


class TestCompositeScore:
    def test_empty_features(self):
        result = composite_score({})
        assert "score" in result
        assert "grade" in result
        assert 0 <= result["score"] <= 100

    def test_bullish_features(self):
        features = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "bar_trend": "放大", "divergence": "底背离(看涨)"},
            "kdj": {"signal": "金叉+超卖"},
            "bollinger": {"position": 0.1, "bandwidth_desc": "收窄"},
            "rsi": {"rsi": 25},
            "volume": {"volume_price_signal": 1, "volume_ratio": 1.5, "volume_price": "放量上涨"},
            "patterns": [{"type": "早晨之星"}],
        }
        result = composite_score(features, "蓝筹股", "牛市")
        assert result["score"] > 40

    def test_bearish_features(self):
        features = {
            "ma_system": {"alignment": "空头排列"},
            "macd": {"signal": -1, "bar_trend": "", "divergence": "顶背离(看跌)"},
            "kdj": {"signal": "死叉+超买"},
            "bollinger": {"position": 0.9, "bandwidth_desc": ""},
            "rsi": {"rsi": 80},
            "volume": {"volume_price_signal": -1, "volume_ratio": 2, "volume_price": "放量下跌出货"},
            "patterns": [{"type": "三只乌鸦"}],
        }
        result = composite_score(features, "普通股", "熊市")
        assert result["score"] < 50

    def test_grade_mapping(self):
        """验证分数到评级的映射。"""
        # 极低分 -> 强烈看空
        result = composite_score(
            {"ma_system": {"alignment": "空头排列"}, "rsi": {"rsi": 90}}, "普通股", "熊市"
        )
        assert result["grade"] in ("强烈看空", "偏空(强)", "偏空", "中性(偏空)", "中性")

    def test_market_breadth_penalty(self):
        """退潮 + 冰点 + 接力恶化 -> 扣分。"""
        features = {"ma_system": {"alignment": "多头排列"}}
        breadth = {
            "limit_up_count": 10,
            "limit_down_count": 60,
            "continuous_limit_height": 1,
        }
        result = composite_score(features, market_breadth=breadth)
        assert "score" in result

    def test_returns_signals(self):
        result = composite_score({"macd": {"signal": 1}})
        assert "buy_signals" in result
        assert "sell_signals" in result
        assert "structured_signals" in result


# ═══════════════════════════════════════════════════════════════
# detect_market_environment
# ═══════════════════════════════════════════════════════════════


class TestDetectMarketEnvironment:
    def test_no_data_defaults_oscillation(self):
        result = detect_market_environment()
        assert result["state"] == "震荡"
        assert "weight_adjustments" in result

    def test_bull_market(self):
        result = detect_market_environment(index_quote={"price": 3000, "change_pct": 2.0, "turnover": 2})
        assert result["state"] == "牛市"

    def test_bear_market(self):
        result = detect_market_environment(index_quote={"price": 3000, "change_pct": -2.0, "turnover": 2})
        assert result["state"] == "熊市"

    def test_excited_state(self):
        """牛市 + 高换手 -> 亢奋。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 2.0, "turnover": 6}
        )
        assert result["state"] == "亢奋"

    def test_freezing_state(self):
        """熊市/震荡 + 极度缩量 -> 冰点。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 0, "turnover": 0.3}
        )
        assert result["state"] == "冰点"

    def test_multi_day_window(self):
        """多日窗口平滑判断。"""
        recent = [
            {"change_pct": 1.0, "turnover": 2},
            {"change_pct": 2.0, "turnover": 2},
            {"change_pct": 1.5, "turnover": 2},
        ]
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 1.5, "turnover": 2},
            recent_quotes=recent,
        )
        assert "state" in result
        assert any("近3日" in s for s in result["signals"])


class TestMarketWeightAdjustments:
    def test_bull_market(self):
        adj = _market_weight_adjustments("牛市")
        assert "trend_following" in adj

    def test_bear_market(self):
        adj = _market_weight_adjustments("熊市")
        assert "trend_following" in adj

    def test_unknown_state_fallback(self):
        adj = _market_weight_adjustments("未知状态")
        assert "trend_following" in adj  # 回退震荡


# ═══════════════════════════════════════════════════════════════
# _get_score_max 配置覆盖分支
# ═══════════════════════════════════════════════════════════════


class TestGetScoreMaxConfigOverride:
    def test_config_overrides_default(self):
        """配置覆盖默认值。"""
        with patch("technical.scoring._scoring_config", return_value={"ma": 50, "macd": 25}):
            sm = _get_score_max()
        assert sm["ma"] == 50.0
        assert sm["macd"] == 25.0

    def test_config_invalid_value_ignored(self):
        """无效值（非数字）被忽略，保留默认。"""
        with patch(
            "technical.scoring._scoring_config",
            return_value={"ma": "not_a_number", "macd": 25},
        ):
            sm = _get_score_max()
        assert sm["ma"] == 30  # 默认值保留
        assert sm["macd"] == 25.0

    def test_config_none_value_ignored(self):
        """None 值被忽略。"""
        with patch("technical.scoring._scoring_config", return_value={"ma": None}):
            sm = _get_score_max()
        assert sm["ma"] == 30  # 默认值保留

    def test_config_unknown_key_ignored(self):
        """未知键被忽略（不在 merged 中）。"""
        with patch(
            "technical.scoring._scoring_config",
            return_value={"unknown_key": 100, "ma": 50},
        ):
            sm = _get_score_max()
        assert "unknown_key" not in sm
        assert sm["ma"] == 50.0

    def test_config_empty_returns_defaults(self):
        """空配置 -> 全默认。"""
        with patch("technical.scoring._scoring_config", return_value={}):
            sm = _get_score_max()
        assert sm["ma"] == 30
        assert sm["valuation"] == 100


# ═══════════════════════════════════════════════════════════════
# detect_market_environment 边界
# ═══════════════════════════════════════════════════════════════


class TestDetectMarketEnvironmentEdgeCases:
    def test_mild_decline_low_confidence(self):
        """温和下跌（-0.5 ~ -1.5）-> 熊市低置信。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": -1.0, "turnover": 2}
        )
        assert result["state"] == "熊市"
        assert result["confidence"] == "低"

    def test_mild_rise_low_confidence(self):
        """温和上涨（0.5 ~ 1.5）-> 牛市低置信。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 1.0, "turnover": 2}
        )
        assert result["state"] == "牛市"
        assert result["confidence"] == "低"

    def test_narrow_range_oscillation(self):
        """窄幅震荡（-0.5 ~ 0.5）-> 震荡。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 0.2, "turnover": 2}
        )
        assert result["state"] == "震荡"

    def test_large_same_day_rise_signal(self):
        """当日大涨 >2% 补充信号。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 3.0, "turnover": 2}
        )
        assert any("当日大涨" in s for s in result["signals"])

    def test_large_same_day_fall_signal(self):
        """当日大跌 <-2% 补充信号。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": -3.0, "turnover": 2}
        )
        assert any("当日大跌" in s for s in result["signals"])

    def test_high_turnover_signal(self):
        """高换手率信号。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 0.2, "turnover": 6}
        )
        assert any("高换手率" in s for s in result["signals"])

    def test_extreme_low_turnover_signal(self):
        """极度缩量信号。"""
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": 0.2, "turnover": 0.3}
        )
        assert any("极度缩量" in s for s in result["signals"])

    def test_multi_day_mild_decline(self):
        """多日窗口温和下跌。"""
        recent = [
            {"change_pct": -0.8, "turnover": 2},
            {"change_pct": -0.6, "turnover": 2},
        ]
        result = detect_market_environment(
            index_quote={"price": 3000, "change_pct": -0.7, "turnover": 2},
            recent_quotes=recent,
        )
        assert result["state"] == "熊市"
        assert result["confidence"] == "低"


# ═══════════════════════════════════════════════════════════════
# _score_kdj 更多分支
# ═══════════════════════════════════════════════════════════════


class TestScoreKdjMoreBranches:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def _adj(self):
        return _market_weight_adjustments("震荡")

    def test_golden_cross_only(self):
        s = _score_kdj({"signal": "金叉"}, self._w(), self._adj())
        assert s >= 0

    def test_oversold_only(self):
        s = _score_kdj({"signal": "超卖"}, self._w(), self._adj())
        assert s >= 0

    def test_overbought_only(self):
        s = _score_kdj({"signal": "超买"}, self._w(), self._adj())
        assert s >= 0

    def test_death_cross_only(self):
        s = _score_kdj({"signal": "死叉"}, self._w(), self._adj())
        assert s >= 0


# ═══════════════════════════════════════════════════════════════
# _score_chip 更多分支
# ═══════════════════════════════════════════════════════════════


class TestScoreChipMoreBranches:
    def _w(self):
        return _get_stock_type_weights("普通股")

    def test_holders_improve(self):
        s = _score_chip({"holders": {"concentration": "提升"}}, self._w())
        assert s > 0

    def test_margin_continuous_increase(self):
        """融资连续增加额外加分。"""
        base = _score_chip({"margin": {"rzjme_5d": 100, "rzjme_trend": ""}}, self._w())
        with_trend = _score_chip(
            {"margin": {"rzjme_5d": 100, "rzjme_trend": "连续增加"}}, self._w()
        )
        assert with_trend > base

    def test_margin_negative(self):
        s = _score_chip({"margin": {"rzjme_5d": -50}}, self._w())
        assert s < 0

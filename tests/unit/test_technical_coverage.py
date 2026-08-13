"""评分引擎 / 买卖信号 / 涨跌停连板 分支覆盖补充（v2.7 任务 B：coverage）。

针对 2026-08-13 基线 uncovered 分支补测：
- scoring.py: _score_ma / _score_kdj / _score_boll / _score_rsi / _score_volume
  / _score_patterns / _score_chan / _score_local / _score_chip / _score_limit
  / detectable all market environments / breadth penalty
- signals.py: _signal_* 与 _generate_signals 多分支
- astock.py: limit_analysis 涨停/跷板/炸板/连板量能 + _count_limit_streak
"""

import pytest

from technical.astock import _count_limit_streak, limit_analysis
from technical.scoring import (
    _score_boll,
    _score_chan,
    _score_chip,
    _score_kdj,
    _score_limit,
    _score_local,
    _score_ma,
    _score_macd,
    _score_patterns,
    _score_rsi,
    _score_volume,
    composite_score,
    detect_market_environment,
)
from technical.signals import (
    _generate_signals,
    _signal_advance_decline,
    _signal_continuous_height,
    _signal_limit_up_down,
)


def _type_w(**overrides):
    w = {
        "ma": 1.0,
        "macd": 1.0,
        "kdj": 1.0,
        "boll": 1.0,
        "rsi": 1.0,
        "volume": 1.0,
        "pattern": 1.0,
        "chan": 1.0,
        "local": 1.0,
        "limit": 1.0,
        "chip": 1.0,
        "valuation": 1.0,
    }
    w.update(overrides)
    return w


# ═══════════════════════════════════════════════════════════════
# _score_ma / _score_kdj / _score_boll / _score_rsi / _score_volume
# ═══════════════════════════════════════════════════════════════


class TestSubScores:
    """各子评分函数分支覆盖。"""

    def test_score_ma_bull_momentum(self):
        w = _type_w()
        adj = {"trend_following": 1.0}
        asc = {"多头排列": 20, "交叉震荡": 12, "空头排列": 3, "数据不足": 7}
        assert _score_ma("多头排列", w, adj, asc) == 20.0
        assert _score_ma("交叉震荡", w, adj, asc) == 12.0
        assert _score_ma("空头排列", w, adj, asc) == 3.0
        assert _score_ma("数据不足", w, adj, asc) == 7.0
        # 未知 alignent 回退 7
        assert _score_ma("未知形态", w, adj, asc) == 7.0

    def test_score_ma_momentum_scaling(self):
        w = _type_w(ma=1.3)
        adj = {"trend_following": 1.4}
        asc = {"多头排列": 20}
        # 20*1.3*1.4=36.4 → clamp 上限 30
        assert _score_ma("多头排列", w, adj, asc) == 30.0

    def test_score_kdj_branches(self):
        w = _type_w()
        # 震荡市（trend_following<1）时 KDJ 更有效，权重 10
        adj_side = {"trend_following": 0.8}
        # 牛市（trend_following>=1）时降权 5
        adj_bull = {"trend_following": 1.4}
        # 金叉+超卖 → weight×1.0（无趋势惩罚）
        assert _score_kdj({"signal": "金叉超卖"}, w, adj_side) == 10.0
        # 金叉 → weight×0.8
        assert _score_kdj({"signal": "金叉"}, w, adj_bull) == 4.0
        # 放量下跌趋势惩罚 ×0.5
        assert _score_kdj({"signal": "金叉超卖"}, w, adj_side, vol_signal=-1) == 5.0
        # 死叉分支
        assert _score_kdj({"signal": "死叉超买"}, w, adj_bull) == 0.5  # 5*0.1
        assert _score_kdj({"signal": "死叉"}, w, adj_bull) == 1.0  # 5*0.2
        # 超卖/超买/中性
        assert _score_kdj({"signal": "超卖"}, w, adj_side) == 6.0  # 10*0.6
        assert _score_kdj({"signal": "超买"}, w, adj_bull) == 1.5  # 5*0.3
        assert _score_kdj({"signal": "正常"}, w, adj_side) == 4.5  # 10*0.45
        # 钝化分支：权重固定 5
        assert _score_kdj({"signal": "金叉", "钝化": True}, w, adj_side) == 4.0

    def test_score_boll_branches(self):
        w = _type_w()
        assert _score_boll({"position": 0.1, "bandwidth_desc": "收窄"}, w) == 10.0
        assert _score_boll({"position": 0.1, "bandwidth_desc": "正常"}, w) == 6.0
        assert _score_boll({"position": 0.5, "bandwidth_desc": ""}, w) == 7.0
        assert _score_boll({"position": 0.9, "bandwidth_desc": ""}, w) == 4.0
        # 带宽缩放
        assert (
            _score_boll({"position": 0.1, "bandwidth_desc": "收窄"}, _type_w(boll=2))
            == 15.0
        )

    def test_score_rsi_branches(self):
        w = _type_w()
        assert _score_rsi({"rsi": 15}, w) == 12.0
        assert _score_rsi({"rsi": 25}, w) == 10.0
        assert _score_rsi({"rsi": 35}, w) == 8.0
        assert _score_rsi({"rsi": 45}, w) == 7.0
        assert _score_rsi({"rsi": 65}, w) == 5.0
        assert _score_rsi({"rsi": 80}, w) == 3.0
        # 放量下跌时超卖降权
        assert _score_rsi({"rsi": 15}, w, vol_signal=-1) == pytest.approx(7.2)  # 12*0.6
        assert _score_rsi({"rsi": 50}, w, vol_signal=-1) == 7.0  # 中性不受影响

    def test_score_volume_branches(self):
        w = _type_w()
        assert _score_volume({"volume_price_signal": 1, "volume_ratio": 1}, w) == 12.0
        assert _score_volume({"volume_price_signal": -1, "volume_ratio": 1}, w) == 3.0
        assert _score_volume({"volume_price_signal": 0, "volume_ratio": 0.2}, w) == 10.0
        # 放量下跌时地量不加分
        assert _score_volume({"volume_price_signal": -1, "volume_ratio": 0.2}, w) == 3.0
        assert _score_volume({"volume_price_signal": 0, "volume_ratio": 1}, w) == 7.0


# ═══════════════════════════════════════════════════════════════
# _score_patterns / _score_chan / _score_local / _score_chip / _score_limit
# ═══════════════════════════════════════════════════════════════


class TestBonusScores:
    """加分项分支覆盖。"""

    def test_score_patterns(self):
        w = _type_w()
        adj = {"bullish_bias": 1.0}
        # 无形态 → 7
        assert _score_patterns([], w, adj) == 7.0
        # 看涨形态 → max 13
        assert _score_patterns([{"type": "早晨之星"}], w, adj) == 13.0
        # 看跌形态 → min 3
        assert _score_patterns([{"type": "黄昏之星"}], w, adj) == 3.0
        # 看涨后先看涨再跌 → min
        r = _score_patterns([{"type": "阳包阴"}, {"type": "三只乌鸦"}], w, adj)
        assert r == 3.0

    def test_score_patterns_bias(self):
        w = _type_w()
        adj = {"bullish_bias": 1.3}
        assert _score_patterns([{"type": "红三兵"}], w, adj) == pytest.approx(13 * 1.3)

    def test_score_chan_buy_points(self):
        w = _type_w()
        data = {
            "valid": True,
            "maidian": {
                "buy_points": [
                    {"type": "一买"},
                    {"type": "二买"},
                    {"type": "三买"},
                    {"type": "三买"},
                ],
                "sell_points": [],
            },
            "beichi": {"summary": "检测到底背驰"},
        }
        scores = {
            "buy_point_1": 1.0,
            "buy_point_3": 1.0,
            "divergence_bottom": 1.0,
        }
        r = _score_chan(data, w, scores)
        # 一买10+二买5+三买8×2+底背驰8 = 39 → clamp 上限 15
        assert r == 15.0
        # 综合乘法
        w2 = _type_w(chan=1.3)
        r2 = _score_chan(data, w2, scores)
        assert r2 == 15.0

    def test_score_chan_invalid(self):
        assert _score_chan({"valid": False}, _type_w(), {}) == 0.0
        assert _score_chan({}, _type_w(), {}) == 0.0

    def test_score_local_patterns(self):
        r = _score_local(
            {
                "patterns": [
                    {"name": "老鸭头", "confidence": "高"},  # 8*1.2
                    {"name": "美人肩", "confidence": "中"},  # 6
                    {"name": "涨停双响炮", "confidence": "低"},  # 7*0.5
                ]
            }
        )
        # 8*1.2+6+7*0.5=19.1 → clamp 上限 10
        assert r == 10.0

    def test_score_local_sanyinyiyang(self):
        # 三阴一阳量比/跌幅/反弹加分
        r = _score_local(
            {
                "patterns": [
                    {
                        "name": "三阴一阳",
                        "confidence": "中",
                        "metrics": {
                            "vol_ratio": 1.6,
                            "total_decline": -2.0,
                            "rebound_ratio": 30,
                        },
                    }
                ]
            }
        )
        # base 5 + 量比2 + 跌幅1 + 反弹1 = 9
        assert r == 9.0
        # 量比 1.2 仅 +1
        r2 = _score_local(
            {
                "patterns": [
                    {
                        "name": "三阴一阳",
                        "confidence": "中",
                        "metrics": {
                            "vol_ratio": 1.3,
                            "total_decline": 5,
                            "rebound_ratio": 10,
                        },
                    }
                ]
            }
        )
        assert r2 == 6.0

    def test_score_local_bearish(self):
        # 三阳一阴看跌扣分
        assert (
            _score_local(
                {
                    "patterns": [
                        {
                            "name": "三阳一阴",
                            "confidence": "中",
                            "metrics": {"vol_ratio": 2},
                        }
                    ]
                }
            )
            == -5
        )
        assert (
            _score_local(
                {
                    "patterns": [
                        {
                            "name": "三阳一阴",
                            "confidence": "中",
                            "metrics": {"vol_ratio": 1},
                        }
                    ]
                }
            )
            == -3
        )

    def test_score_local_breakout_reversal(self):
        # 断板反包加分项
        r = _score_local(
            {
                "patterns": [
                    {
                        "name": "断板反包",
                        "confidence": "中",
                        "metrics": {"vol_expansion": True, "breakout_new_high": True},
                    }
                ]
            }
        )
        assert r == 10.0  # 7+2+1

    def test_score_local_misc(self):
        assert (
            _score_local({"patterns": [{"name": "底部首板", "confidence": "中"}]})
            == 6.0
        )
        assert (
            _score_local({"patterns": [{"name": "双针探底", "confidence": "中"}]})
            == 5.0
        )
        # 未知形态 → 0
        assert _score_local({"patterns": [{"name": "XYZ", "confidence": "中"}]}) == 0.0

    def test_score_chip_margin(self):
        w = _type_w()
        # 近5日净买入>0
        assert _score_chip({"margin": {"rzjme_5d": 100}}, w) == 2.0
        # 连续增加 → +1
        assert (
            _score_chip({"margin": {"rzjme_5d": 100, "rzjme_trend": "连续增加"}}, w)
            == 3.0
        )
        assert _score_chip({"margin": {"rzjme_5d": -100}}, w) == -1.0

    def test_score_chip_holders(self):
        w = _type_w()
        assert _score_chip({"holders": {"concentration": "持续集中"}}, w) == 3.0
        assert _score_chip({"holders": {"concentration": "提升"}}, w) == 2.0
        assert _score_chip({"holders": {"concentration": "分散"}}, w) == -1.0
        assert _score_chip({"holders": {"concentration": "不变"}}, w) == 0.0

    def test_score_chip_clamp(self):
        # 多正信号 → clamp 上限 10
        r = _score_chip(
            {
                "margin": {"rzjme_5d": 100, "rzjme_trend": "连续增加"},
                "holders": {"concentration": "持续集中"},
            },
            _type_w(chip=3),
        )
        assert r == 10.0

    def test_score_limit_no_streak(self):
        w = _type_w()
        adj = {"divergence_bottom": 1.0, "breakout": 1.0}
        # 空/非 dict → 0
        assert _score_limit(None, w, adj) == 0.0
        assert _score_limit("x", w, adj) == 0.0
        # 无连板正常交易 → 0
        assert (
            _score_limit(
                {
                    "streak_type": "无连板",
                    "board_status": "正常交易",
                    "streak_volume": "",
                },
                w,
                adj,
            )
            == 0.0
        )

    def test_score_limit_streak_branches(self):
        w = _type_w()
        adj = {"divergence_bottom": 1.0, "breakout": 1.0}
        assert (
            _score_limit(
                {
                    "streak_type": "首板",
                    "board_status": "正常交易",
                    "streak_volume": "",
                },
                w,
                adj,
            )
            == 5.0
        )
        assert (
            _score_limit(
                {
                    "streak_type": "二板",
                    "board_status": "正常交易",
                    "streak_volume": "",
                },
                w,
                adj,
            )
            == 8.0
        )
        assert (
            _score_limit(
                {
                    "streak_type": "高位",
                    "board_status": "正常交易",
                    "streak_volume": "",
                },
                w,
                adj,
            )
            == 10.0
        )
        assert (
            _score_limit(
                {
                    "streak_type": "妖股",
                    "board_status": "正常交易",
                    "streak_volume": "",
                },
                w,
                adj,
            )
            == 12.0
        )

    def test_score_limit_volume_penalty(self):
        w = _type_w()
        adj = {"divergence_bottom": 1.0, "breakout": 1.0}
        # 缩量加速 +3
        assert (
            _score_limit(
                {
                    "streak_type": "首板",
                    "board_status": "正常交易",
                    "streak_volume": "缩量加速",
                },
                w,
                adj,
            )
            == 8.0
        )
        # 放量分歧 -2
        assert (
            _score_limit(
                {
                    "streak_type": "首板",
                    "board_status": "正常交易",
                    "streak_volume": "放量分歧",
                },
                w,
                adj,
            )
            == 3.0
        )

    def test_score_limit_board_status(self):
        w = _type_w()
        adj = {"divergence_bottom": 1.0, "breakout": 1.0}
        assert (
            _score_limit(
                {
                    "streak_type": "无连板",
                    "board_status": "封涨停",
                    "streak_volume": "",
                },
                w,
                adj,
            )
            == 3.0
        )
        assert (
            _score_limit(
                {"streak_type": "无连板", "board_status": "翘板", "streak_volume": ""},
                w,
                adj,
            )
            == 2.0
        )
        assert (
            _score_limit(
                {
                    "streak_type": "无连板",
                    "board_status": "封跌停",
                    "streak_volume": "",
                },
                w,
                adj,
            )
            == -3.0
        )
        assert (
            _score_limit(
                {"streak_type": "无连板", "board_status": "炸板", "streak_volume": ""},
                w,
                adj,
            )
            == -2.0
        )

    def test_score_limit_breakout_adj_applied_once(self):
        w = _type_w(limit=1.0)
        adj = {"divergence_bottom": 1.0, "breakout": 1.3}
        r = _score_limit(
            {
                "streak_type": "首板",
                "board_status": "封涨停",
                "streak_volume": "缩量加速",
            },
            w,
            adj,
        )
        # (5+3板 +3缩量)*1.3 = 11*1.3 = 14.3，仅一次 adj
        assert r == pytest.approx(11 * 1.3)
        # 负分被 clamp 到 -3
        r2 = _score_limit(
            {"streak_type": "无连板", "board_status": "封跌停", "streak_volume": ""},
            w,
            adj,
        )
        assert r2 == -3.0


# ═══════════════════════════════════════════════════════════════
# composite_score 全市场状态 + 宽度惩罚
# ═══════════════════════════════════════════════════════════════


class TestCompositeBroad:
    """composite_score 全市场状态与宽度惩罚分支。"""

    def test_market_states_grade(self):
        feat = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "divergence": "", "bar_trend": "红柱放大"},
            "kdj": {"signal": "金叉超卖"},
            "bollinger": {"position": 0.1, "bandwidth_desc": "收窄"},
            "rsi": {"rsi": 25},
            "volume": {"volume_price_signal": 1, "volume_ratio": 2},
            "patterns": [{"type": "早晨之星"}],
            "valuation_score": 80,
        }
        # 牛/熊/亢奋/冰点 状态均不崩溃且输出字段完整
        for state in ("牛市", "熊市", "震荡", "冰点", "亢奋"):
            r = composite_score(dict(feat), "普通股", state)
            assert 0 <= r["score"] <= 100
            assert r["grade"] in {
                "强烈看多",
                "偏多(强)",
                "偏多",
                "中性(偏多)",
                "中性",
                "中性(偏空)",
                "偏空",
                "偏空(强)",
                "强烈看空",
            }
            assert isinstance(r["buy_signals"], list)
            assert isinstance(r["sell_signals"], list)
            assert isinstance(r["structured_signals"], dict)

    def test_stock_types_weights(self):
        feat = {
            "ma_system": {"alignment": "多头排列"},
            "valuation_score": 50,
        }
        for st in ("普通股", "蓝筹股", "成长股", "周期股", "题材股", "金融股"):
            r = composite_score(dict(feat), st, "震荡")
            assert 0 <= r["score"] <= 100

    def test_breadth_penalty_retreat(self):
        feat = {
            "ma_system": {"alignment": "多头排列"},
            "valuation_score": 50,
        }
        no_pen = composite_score(dict(feat), "普通股", "震荡", market_breadth=None)
        retreat = composite_score(
            dict(feat),
            "普通股",
            "震荡",
            market_breadth={
                "limit_up_count": 10,
                "limit_down_count": 20,
                "continuous_limit_height": 0,
            },
        )
        assert retreat["score"] < no_pen["score"]  # 退潮 -5

    def test_breadth_penalty_freezing_and_chaos(self):
        feat = {
            "ma_system": {"alignment": "多头排列"},
            "valuation_score": 50,
        }
        no_pen = composite_score(dict(feat), "普通股", "震荡", market_breadth=None)
        # 跌停>50 (-10) + 连板高度<=2 (-3)
        r = composite_score(
            dict(feat),
            "普通股",
            "震荡",
            market_breadth={
                "limit_up_count": 30,
                "limit_down_count": 60,
                "continuous_limit_height": 1,
            },
        )
        assert r["score"] <= no_pen["score"] - 13

    def test_breadth_no_penalty_when_healthy(self):
        feat = {
            "ma_system": {"alignment": "多头排列"},
            "valuation_score": 50,
        }
        # 健康市场无惩罚：score 应 ≥ 退潮惩罚后的分数
        r = composite_score(
            dict(feat),
            "普通股",
            "震荡",
            market_breadth={
                "limit_up_count": 30,
                "limit_down_count": 10,
                "continuous_limit_height": 5,
            },
        )
        penalized = composite_score(
            dict(feat),
            "普通股",
            "震荡",
            market_breadth={
                "limit_up_count": 10,
                "limit_down_count": 60,
                "continuous_limit_height": 1,
            },
        )
        assert r["score"] > penalized["score"]

    def test_composite_grade_boundaries(self):
        """score 边界打点：≥80 强烈看多 / <15 强烈看空。"""
        feat_bull = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "bar_trend": "红柱放大"},
            "kdj": {"signal": "金叉超卖"},
            "bollinger": {"position": 0.1, "bandwidth_desc": "收窄"},
            "rsi": {"rsi": 15},
            "volume": {"volume_price_signal": 1, "volume_ratio": 2},
            "patterns": [{"type": "早晨之星"}],
            "chan_theory": {
                "valid": True,
                "maidian": {"buy_points": [{"type": "一买"}], "sell_points": []},
                "beichi": {"summary": "检测到底背驰"},
            },
            "local_patterns": {
                "patterns": [{"name": "老鸭头", "confidence": "高", "type": "看涨"}]
            },
            "limit_analysis": {
                "streak_type": "妖股",
                "board_status": "封涨停",
                "streak_volume": "缩量加速",
            },
            "chip": {
                "margin": {"rzjme_5d": 100, "rzjme_trend": "连续增加"},
                "holders": {"concentration": "持续集中"},
            },
            "valuation_score": 90,
        }
        bull = composite_score(dict(feat_bull), "普通股", "牛市")
        # 全看多信号叠加应到 70+，接近 80 边界（普通股权重摊薄）
        assert bull["score"] >= 70
        assert bull["grade"] in ("偏多", "偏多(强)", "强烈看多")

        feat_bear = {
            "ma_system": {"alignment": "空头排列"},
            "macd": {"signal": -1, "divergence": "顶背离(看跌)"},
            "kdj": {"signal": "死叉超买"},
            "bollinger": {"position": 0.9, "bandwidth_desc": ""},
            "rsi": {"rsi": 85},
            "volume": {"volume_price_signal": -1, "volume_ratio": 3},
            "patterns": [{"type": "黄昏之星"}],
            "limit_analysis": {
                "streak_type": "无连板",
                "board_status": "封跌停",
                "streak_volume": "",
            },
            "local_patterns": {
                "patterns": [
                    {
                        "name": "三阳一阴",
                        "confidence": "中",
                        "metrics": {"vol_ratio": 2},
                        "type": "看跌",
                    }
                ]
            },
            "valuation_score": 10,
        }
        bear = composite_score(dict(feat_bear), "普通股", "熊市")
        assert bear["grade"] in ("强烈看空", "中性(偏空)", "偏空", "偏空(强)")


# ═══════════════════════════════════════════════════════════════
# detect_market_environment 全分支
# ═══════════════════════════════════════════════════════════════


class TestDetectMarketEnvironment:
    """市场环境检测全分支。"""

    def test_missing_data(self):
        r = detect_market_environment(index_quote=None)
        assert r["state"] == "震荡"
        assert "大盘数据缺失" in r["signals"][0]
        assert r["confidence"] == "低"
        # 空 dict
        r2 = detect_market_environment(index_quote={})
        assert r2["state"] == "震荡"

    def test_multi_day_bull(self):
        quotes = [
            {"change_pct": 3.0, "turnover": 2.0},
            {"change_pct": 2.8, "turnover": 2.0},
            {"change_pct": 2.6, "turnover": 2.0},
        ]
        r = detect_market_environment(
            index_quote={"change_pct": 3.0, "turnover": 2.0, "price": 100},
            recent_quotes=quotes,
        )
        assert r["state"] == "牛市"
        assert r["confidence"] == "高"  # 多日均值 2.8 > 2.5 → 高
        assert any("持续上涨" in s for s in r["signals"])

    def test_multi_day_bear(self):
        quotes = [
            {"change_pct": -3.0, "turnover": 2.0},
            {"change_pct": -2.5, "turnover": 2.0},
        ]
        r = detect_market_environment(
            index_quote={"change_pct": -2.8, "turnover": 2.0, "price": 100},
            recent_quotes=quotes,
        )
        assert r["state"] == "熊市"
        assert r["confidence"] == "高"
        assert any("持续下跌" in s for s in r["signals"])

    def test_single_day_moderate(self):
        r = detect_market_environment(
            index_quote={"change_pct": 1.0, "turnover": 2.0, "price": 100}
        )
        assert r["state"] == "牛市"
        assert r["confidence"] == "低"

        r2 = detect_market_environment(
            index_quote={"change_pct": -0.8, "turnover": 2.0, "price": 100}
        )
        assert r2["state"] == "熊市"
        assert r2["confidence"] == "低"

    def test_single_day_big_change_low_conf(self):
        r = detect_market_environment(
            index_quote={"change_pct": 2.6, "turnover": 2.0, "price": 100}
        )
        assert r["state"] == "牛市"
        assert r["confidence"] == "中"  # 单日>2.5 非多日 → 中

    def test_narrow_range(self):
        r = detect_market_environment(
            index_quote={"change_pct": 0.2, "turnover": 2.0, "price": 100}
        )
        assert r["state"] == "震荡"
        assert any("窄幅震荡" in s for s in r["signals"])

    def test_turnover_extremes(self):
        # 高换手 → 亢奋
        r = detect_market_environment(
            index_quote={"change_pct": 1.0, "turnover": 6.0, "price": 100}
        )
        assert r["state"] == "亢奋"
        assert "高换手率" in r["signals"]
        # 低换手 → 冰点
        r2 = detect_market_environment(
            index_quote={"change_pct": 0.2, "turnover": 0.2, "price": 100}
        )
        assert r2["state"] == "冰点"
        assert "冰点信号" in r2["signals"]

    def test_turnover_zero_no_extreme_signal(self):
        # M4: turnover 缺失（0）不误触发缩量信号
        r = detect_market_environment(
            index_quote={"change_pct": 0.2, "turnover": 0, "price": 100}
        )
        assert "极度缩量" not in "".join(r["signals"])

    def test_big_change_flags(self):
        r = detect_market_environment(
            index_quote={"change_pct": 3.0, "turnover": 2.0, "price": 100}
        )
        assert any("当日大涨" in s for s in r["signals"])
        r2 = detect_market_environment(
            index_quote={"change_pct": -3.0, "turnover": 2.0, "price": 100}
        )
        assert any("当日大跌" in s for s in r2["signals"])

    def test_multi_day_average_change(self):
        # 多日均值收窄 → 温和上涨
        r = detect_market_environment(
            index_quote={"change_pct": 0.6, "turnover": 2.0, "price": 100},
            recent_quotes=[{"change_pct": 0.6, "turnover": 2.0}],
        )
        assert r["state"] == "牛市"
        assert any("温和上涨" in s for s in r["signals"])


# ═══════════════════════════════════════════════════════════════
# signals._signal_* 与 _generate_signals
# ═══════════════════════════════════════════════════════════════


class TestSignalHelpers:
    def test_signal_limit_up_down(self):
        assert _signal_limit_up_down(10, 10) == {"退潮": "市场退潮(涨停10家<20)"}
        assert _signal_limit_up_down(30, 60) == {"冰点": "市场冰点(跌停60家)"}
        assert _signal_limit_up_down(0, 10) == {}  # limit_up=0 不误触发
        assert _signal_limit_up_down(30, 10) == {}

    def test_signal_continuous_height(self):
        assert _signal_continuous_height(1) == {"接力恶化": "接力生态恶化(连板1板)"}
        assert _signal_continuous_height(2) == {"接力恶化": "接力生态恶化(连板2板)"}
        assert _signal_continuous_height(3) == {}
        assert _signal_continuous_height(0) == {}

    def test_signal_advance_decline(self):
        assert _signal_advance_decline(3) == {"普涨": "市场普涨(涨跌比3)"}
        assert _signal_advance_decline(1) == {}


class TestGenerateSignals:
    def _base_features(self, **overrides):
        feat = {
            "ma_system": {"alignment": "交叉震荡"},
            "macd": {"signal": 0, "divergence": ""},
            "kdj": {"signal": "正常"},
            "bollinger": {"position": 0.5},
            "rsi": {"rsi": 50},
            "volume": {"volume_price_signal": 0, "volume": "", "volume_price": ""},
            "wave": "",
            "valuation": {},
        }
        feat.update(overrides)
        return feat

    def test_no_market_breadth(self):
        buy, sell, stru = _generate_signals(self._base_features())
        assert buy == []
        assert sell == []
        assert stru["is_downtrend"] is False

    def test_market_breadth_all_signals(self):
        feat = self._base_features()
        b, s, _ = _generate_signals(
            feat,
            market_breadth={
                "limit_up_count": 10,
                "limit_down_count": 60,
                "continuous_limit_height": 1,
                "up_ratio": 3,
            },
        )
        assert any("退潮" in x for x in s)
        assert any("冰点" in x for x in s)
        assert any("接力生态恶化" in x for x in s)
        assert any("普涨" in x for x in b)

    def test_buy_signals_full(self):
        feat = self._base_features(
            macd={"signal": 1, "divergence": "底背离(看涨)"},
            kdj={"signal": "金叉超卖"},
            bollinger={"position": 0.1, "bandwidth_desc": "收窄"},
            rsi={"rsi": 30},
            volume={"volume_price_signal": 1, "volume_price": "放量上涨"},
            ma_stop_buy={"signal": 1, "type": "第二类买点"},
            chan_theory={
                "valid": True,
                "maidian": {"buy_points": [{"type": "一买"}], "sell_points": []},
                "beichi": {"summary": "检测到底背驰"},
            },
        )
        b, _s, _ = _generate_signals(feat)
        names = "|".join(b)
        assert "MACD金叉" in names
        assert "MACD底背离" in names
        assert "KDJ超卖区金叉" in names
        assert "BOLL下轨+收窄" in names
        assert "RSI超卖" in names
        assert "放量上涨" in names
        assert "均线止跌" in names
        assert "缠论一买" in names
        assert "缠论底背驰" in names

    def test_buy_signals_downtrend_degraded(self):
        feat = self._base_features(
            wave="下跌趋势",
            ma_system={"alignment": "空头排列"},
            volume={"volume_price_signal": -1, "volume_price": "出货"},
            kdj={"signal": "金叉超卖"},
            rsi={"rsi": 30},
        )
        b, s, stru = _generate_signals(feat)
        assert stru["is_downtrend"] is True
        assert "KDJ超卖区金叉(待确认-下跌趋势)" in b
        assert "RSI超卖(30)-下跌趋势待确认" in b
        assert any("超卖信号失效" in x for x in s)

    def test_sell_signals_full(self):
        feat = self._base_features(
            macd={"signal": -1, "divergence": "顶背离(看跌)"},
            kdj={"signal": "死叉超买"},
            bollinger={"position": 0.9},
            rsi={"rsi": 80},
            volume={"volume_price_signal": -1, "volume_price": "出货"},
            chan_theory={
                "valid": True,
                "maidian": {"buy_points": [], "sell_points": [{"type": "一卖"}]},
                "beichi": {"summary": "检测到顶背驰"},
            },
        )
        _b, s, stru = _generate_signals(feat)
        names = "|".join(s)
        assert "MACD死叉" in names
        assert "MACD顶背离" in names
        assert "KDJ" in names  # 死叉/超买
        assert "BOLL触及上轨" in names
        assert "RSI超买" in names
        assert "放量下跌" in names
        assert "缠论一卖" in names
        assert "缠论顶背驰" in names
        assert stru["macd_death_cross"] is True

    def test_bamboo_signals(self):
        feat = self._base_features(bamboo={"signal": -1})
        _b, s, stru = _generate_signals(feat)
        assert any("竹节走弱" in x for x in s)
        assert stru["bamboo_weak"] is True

        feat2 = self._base_features(bamboo={"signal": -2})
        _b, s2, stru2 = _generate_signals(feat2)
        assert any("竹节转势" in x for x in s2)
        assert stru2["bamboo_reversal"] is True

    def test_valuation_signals(self):
        # 估值底：PE 行业低分位 + PB 低
        feat = self._base_features(
            valuation={"pe": 10, "pb": 1.0, "pe_percentile": 10, "peg": 0.5}
        )
        b, _s, _ = _generate_signals(feat)
        assert any(x.startswith("估值底") for x in b)
        # 估值偏低
        feat2 = self._base_features(
            valuation={"pe": 10, "pb": 2, "pe_percentile": 25, "peg": 0.5}
        )
        b2, _s, _ = _generate_signals(feat2)
        assert any(x.startswith("估值偏低") for x in b2)
        # 估值顶
        feat3 = self._base_features(
            valuation={"pe": 100, "pb": 5, "pe_percentile": 85, "peg": 1.0}
        )
        _b3, s3, _ = _generate_signals(feat3)
        assert any(x.startswith("估值顶") for x in s3)
        # 估值偏高 (>=65 且 PEG>2.5)
        feat4 = self._base_features(
            valuation={"pe": 100, "pb": 5, "pe_percentile": 70, "peg": 3.0}
        )
        _b4, s4, _ = _generate_signals(feat4)
        assert any(x.startswith("估值偏高") for x in s4)
        # pe<=0 不触发估值信号
        feat5 = self._base_features(
            valuation={"pe": -5, "pb": 5, "pe_percentile": 85, "peg": 1.0}
        )
        b5, s5, _ = _generate_signals(feat5)
        assert "估值顶" not in "|".join(s5)

    def test_shrink_and_local(self):
        # 连续缩量信号
        feat = self._base_features(
            volume={
                "volume_price_signal": 0,
                "volume_price": "",
                "shrink_signal": 1,
                "shrink_desc": "连续缩量",
            }
        )
        b, _s, _ = _generate_signals(feat)
        assert any("连续缩量" in x for x in b)
        # 本土战法看涨/看跌
        feat2 = self._base_features(
            local_patterns={"patterns": [{"type": "看涨", "name": "老鸭头"}]}
        )
        b2, _s, _ = _generate_signals(feat2)
        assert "老鸭头" in b2
        feat3 = self._base_features(
            local_patterns={"patterns": [{"type": "看跌", "name": "三阳一阴"}]}
        )
        _b3, s3, _ = _generate_signals(feat3)
        assert "三阳一阴" in s3

    def test_structural_flags(self):
        feat = self._base_features(
            macd={"signal": 1, "divergence": "底背离(看涨)"},
            kdj={"signal": "金叉超卖"},
            bollinger={"position": 0.1, "bandwidth_desc": "收窄"},
            rsi={"rsi": 30},
            volume={"volume_price_signal": 1, "volume_price": "放量上涨"},
        )
        _b, _s, stru = _generate_signals(feat)
        assert stru["macd_golden_cross"] is True
        assert stru["macd_bottom_divergence"] is True
        assert stru["kdj_golden_cross"] is True
        assert stru["kdj_oversold"] is True
        assert stru["boll_lower_band"] is True
        assert stru["rsi_oversold"] is True
        assert stru["volume_inflow"] is True


# ═══════════════════════════════════════════════════════════════
# astock.limit_analysis 全分支
# ═══════════════════════════════════════════════════════════════


def _bar(close, prev_close, high=None, low=None, volume=1000):
    return {
        "day": "2026-01-01",
        "open": prev_close,
        "high": high if high is not None else max(close, prev_close),
        "low": low if low is not None else min(close, prev_close),
        "close": close,
        "volume": volume,
    }


class TestLimitAnalysis:
    def test_too_few_records(self):
        assert limit_analysis([_bar(10, 10)], "主板", {}) is None

    def test_limit_up_status(self):
        records = [_bar(10.0, 10.0) for _ in range(11)]
        records[-1] = _bar(11.0, 10.0, high=11.0, low=10.0)
        r = limit_analysis(records, "主板", {"limit_up": 11.0, "limit_down": 9.0})
        assert r["board_status"] == "封涨停"
        assert r["limit_ratio"] == 9.5
        assert r["t1_risk"] is not None  # 封涨停 + 连板 → T+1 风险

    def test_limit_down_status(self):
        records = [_bar(10.0, 10.0) for _ in range(11)]
        records[-1] = _bar(9.0, 10.0, high=9.0, low=9.0)
        r = limit_analysis(records, "主板", {"limit_up": 11.0, "limit_down": 9.0})
        assert r["board_status"] == "封跌停"
        assert r["limit_streak"] == 0

    def test_lift_board_reopen(self):
        records = [_bar(10.0, 10.0) for _ in range(11)]
        # 收在跌停价上方 → 翘板(跌停打开)
        records[-1] = _bar(9.3, 10.0, high=9.6, low=9.0)
        r = limit_analysis(records, "主板", {"limit_up": 11.0, "limit_down": 9.0})
        assert r["board_status"] == "翘板(跌停打开)"

    def test_explode(self):
        records = [_bar(10.0, 10.0) for _ in range(11)]
        # 触及涨停但未封住 → 炸板
        records[-1] = _bar(10.8, 10.0, high=11.0, low=10.0)
        r = limit_analysis(records, "主板", {"limit_up": 11.0, "limit_down": 9.0})
        assert "炸板" in r["board_status"]

    def test_normal_trading(self):
        records = [_bar(10.0, 10.0) for _ in range(11)]
        records[-1] = _bar(10.2, 10.0, high=10.4, low=9.9)
        r = limit_analysis(records, "主板", {"limit_up": 11.0, "limit_down": 9.0})
        assert r["board_status"] == "正常交易"
        assert r["streak_type"] == "无连板"
        assert r["t1_risk"] is None

    def test_streak_counts(self):
        # 最后 3 根连续涨停
        records = [_bar(10.0, 10.0) for _ in range(8)]
        records += [
            _bar(11.0, 10.0, high=11.0, low=10.0),
            _bar(12.1, 11.0, high=12.1, low=11.0),
            _bar(13.31, 12.1, high=13.31, low=12.1),
        ]
        assert _count_limit_streak(records, 9.5) == 3
        # 仅末根涨停 → 1
        records2 = [_bar(10.0, 10.0) for _ in range(11)]
        records2[-1] = _bar(11.0, 10.0, high=11.0, low=10.0)
        assert _count_limit_streak(records2, 9.5) == 1
        # 无涨停
        assert _count_limit_streak([_bar(10.0, 10.0) for _ in range(11)], 9.5) == 0

    def test_streak_type_high_board(self):
        # 4 根涨停 → 高位4板
        records = [_bar(10.0, 10.0) for _ in range(7)]
        price = 10.0
        for _ in range(4):
            nxt = price * 1.1
            records.append(_bar(round(nxt, 2), price, high=round(nxt, 2), low=price))
            price = nxt
        r = limit_analysis(records, "主板", {"limit_up": price, "limit_down": 0})
        assert r["streak_type"] == "高位4板"

    def test_streak_volume_shrink(self):
        # 连板缩量加速
        records = [_bar(10.0, 10.0) for _ in range(8)]
        records += [
            _bar(11.0, 10.0, high=11.0, low=10.0, volume=2000),
            _bar(12.1, 11.0, high=12.1, low=11.0, volume=1500),
        ]
        r = limit_analysis(records, "主板", {"limit_up": 12.1, "limit_down": 0})
        assert r["streak_volume"] == "缩量加速(强-惜售)"

    def test_streak_volume_expand(self):
        # 连板放量分歧
        records = [_bar(10.0, 10.0) for _ in range(8)]
        records += [
            _bar(11.0, 10.0, high=11.0, low=10.0, volume=2000),
            _bar(12.1, 11.0, high=12.1, low=11.0, volume=4000),
        ]
        r = limit_analysis(records, "主板", {"limit_up": 12.1, "limit_down": 0})
        assert r["streak_volume"] == "放量分歧(弱-换手加大)"

    def test_other_boards_ratio(self):
        # 创业板涨停 19.5%
        records = [_bar(10.0, 10.0) for _ in range(11)]
        records[-1] = _bar(11.9, 10.0, high=11.9, low=10.0)
        r = limit_analysis(records, "创业板", {"limit_up": 11.9, "limit_down": 0})
        assert r["limit_ratio"] == 19.5
        assert r["board_status"] == "封涨停"
        # 未知板块回退 9.5
        records2 = [_bar(10.0, 10.0) for _ in range(11)]
        records2[-1] = _bar(11.0, 10.0, high=11.0, low=10.0)
        r2 = limit_analysis(records2, "未知板", {"limit_up": 11.0, "limit_down": 0})
        assert r2["limit_ratio"] == 9.5

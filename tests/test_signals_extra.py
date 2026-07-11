"""signals.py 买卖信号汇总补充测试。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from technical.signals import (
    _signal_limit_up_down,
    _signal_continuous_height,
    _signal_advance_decline,
    _generate_signals,
)


# ═══════════════════════════════════════════════════════════════
# _signal_limit_up_down
# ═══════════════════════════════════════════════════════════════


class TestSignalLimitUpDown:
    """涨停/跌停家数信号。"""

    def test_normal_market_no_signal(self):
        """涨停 >=20、跌停 <=50 -> 无信号。"""
        assert _signal_limit_up_down(50, 10) == {}

    def test_retreat_signal(self):
        """涨停 <20 且 >0 -> 退潮信号。"""
        sig = _signal_limit_up_down(15, 10)
        assert "退潮" in sig
        assert "15" in sig["退潮"]

    def test_freezing_signal(self):
        """跌停 >50 -> 冰点信号。"""
        sig = _signal_limit_up_down(30, 60)
        assert "冰点" in sig

    def test_zero_limit_up_no_retreat(self):
        """涨停为 0 -> 不报退潮（>0 条件不满足）。"""
        assert _signal_limit_up_down(0, 10) == {}

    def test_both_signals(self):
        """同时退潮 + 冰点。"""
        sig = _signal_limit_up_down(10, 60)
        assert "退潮" in sig
        assert "冰点" in sig


# ═══════════════════════════════════════════════════════════════
# _signal_continuous_height
# ═══════════════════════════════════════════════════════════════


class TestSignalContinuousHeight:
    """连板高度信号。"""

    def test_low_height_signal(self):
        """连板 <=2 且 >0 -> 接力恶化。"""
        sig = _signal_continuous_height(2)
        assert "接力恶化" in sig

    def test_high_height_no_signal(self):
        """连板 >2 -> 无信号。"""
        assert _signal_continuous_height(5) == {}

    def test_zero_height_no_signal(self):
        """连板为 0 -> 无信号（>0 条件不满足）。"""
        assert _signal_continuous_height(0) == {}


# ═══════════════════════════════════════════════════════════════
# _signal_advance_decline
# ═══════════════════════════════════════════════════════════════


class TestSignalAdvanceDecline:
    """涨跌比信号。"""

    def test_broad_rally(self):
        """涨跌比 >2 -> 普涨信号。"""
        sig = _signal_advance_decline(3)
        assert "普涨" in sig

    def test_normal_ratio_no_signal(self):
        """涨跌比 <=2 -> 无信号。"""
        assert _signal_advance_decline(1.5) == {}


# ═══════════════════════════════════════════════════════════════
# _generate_signals
# ═══════════════════════════════════════════════════════════════


class TestGenerateSignals:
    """_generate_signals 汇总买卖信号。"""

    def test_empty_features(self):
        """空 features -> 无买卖信号。"""
        buy, sell, structured = _generate_signals({})
        assert buy == []
        assert sell == []
        assert structured["macd_golden_cross"] is False

    def test_macd_golden_cross(self):
        """MACD 金叉 -> 买入信号。"""
        features = {"macd": {"signal": 1, "divergence": ""}}
        buy, sell, structured = _generate_signals(features)
        assert "MACD金叉" in buy
        assert structured["macd_golden_cross"] is True

    def test_macd_death_cross(self):
        """MACD 死叉 -> 卖出信号。"""
        features = {"macd": {"signal": -1, "divergence": ""}}
        buy, sell, structured = _generate_signals(features)
        assert "MACD死叉" in sell
        assert structured["macd_death_cross"] is True

    def test_macd_bottom_divergence(self):
        """MACD 底背离 -> 买入信号。"""
        features = {"macd": {"signal": 0, "divergence": "底背离(看涨)"}}
        buy, sell, structured = _generate_signals(features)
        assert "MACD底背离" in buy
        assert structured["macd_bottom_divergence"] is True

    def test_macd_top_divergence(self):
        """MACD 顶背离 -> 卖出信号。"""
        features = {"macd": {"signal": 0, "divergence": "顶背离(看跌)"}}
        buy, sell, structured = _generate_signals(features)
        assert "MACD顶背离" in sell

    def test_kdj_oversold_golden_cross(self):
        """KDJ 超卖金叉 -> 买入信号。"""
        features = {"kdj": {"signal": "金叉+超卖"}}
        buy, sell, structured = _generate_signals(features)
        assert any("KDJ超卖区金叉" in s for s in buy)

    def test_kdj_oversold_in_downtrend_downgraded(self):
        """下跌趋势中 KDJ 超卖金叉降级为待确认。"""
        features = {
            "kdj": {"signal": "金叉+超卖"},
            "ma_system": {"alignment": "空头排列"},
        }
        buy, sell, _ = _generate_signals(features)
        assert any("待确认" in s for s in buy)

    def test_boll_lower_band_contraction(self):
        """BOLL 下轨 + 收窄 -> 变盘买入。"""
        features = {
            "bollinger": {"position": 0.1, "bandwidth_desc": "收窄"},
        }
        buy, sell, _ = _generate_signals(features)
        assert any("BOLL下轨" in s for s in buy)

    def test_boll_upper_band_sell(self):
        """BOLL 触及上轨 -> 卖出。"""
        features = {"bollinger": {"position": 0.9, "bandwidth_desc": ""}}
        _, sell, _ = _generate_signals(features)
        assert any("BOLL" in s for s in sell)

    def test_rsi_oversold_buy(self):
        """RSI <35 -> 超卖买入。"""
        features = {"rsi": {"rsi": 25}}
        buy, sell, _ = _generate_signals(features)
        assert any("RSI超卖" in s for s in buy)

    def test_rsi_oversold_in_downtrend_downgraded(self):
        """下跌趋势中 RSI 超卖降级为待确认。"""
        features = {
            "rsi": {"rsi": 25},
            "wave": "下跌趋势",
        }
        buy, sell, _ = _generate_signals(features)
        assert any("待确认" in s for s in buy)
        assert any("失效" in s for s in sell)

    def test_rsi_overbought_sell(self):
        """RSI >70 -> 超买卖出。"""
        features = {"rsi": {"rsi": 80}}
        _, sell, _ = _generate_signals(features)
        assert any("RSI超买" in s for s in sell)

    def test_volume_inflow_buy(self):
        """放量上涨 -> 资金介入买入。"""
        features = {
            "volume": {
                "volume_price": "放量上涨",
                "volume_price_signal": 1,
            }
        }
        buy, _, _ = _generate_signals(features)
        assert any("放量上涨" in s for s in buy)

    def test_volume_outflow_sell(self):
        """放量下跌出货 -> 卖出。"""
        features = {
            "volume": {
                "volume_price": "放量下跌出货",
                "volume_price_signal": -1,
            }
        }
        _, sell, _ = _generate_signals(features)
        assert any("出货" in s for s in sell)

    def test_valuation_bottom_signal(self):
        """PE 低分位 + PB 低 -> 估值底买入。"""
        features = {
            "valuation": {"pe": 15, "pb": 1.0, "pe_percentile": 15, "peg": 0.8},
        }
        buy, sell, _ = _generate_signals(features)
        assert any("估值底" in s for s in buy)

    def test_valuation_top_signal(self):
        """PE 高分位 -> 估值顶卖出。"""
        features = {
            "valuation": {"pe": 100, "pb": 8, "pe_percentile": 85, "peg": 3.0},
        }
        _, sell, _ = _generate_signals(features)
        assert any("估值顶" in s for s in sell)

    def test_market_breadth_signals(self):
        """市场宽度触发卖/买信号。"""
        features = {}
        breadth = {
            "limit_up_count": 10,
            "limit_down_count": 60,
            "continuous_limit_height": 1,
            "up_ratio": 3,
        }
        buy, sell, _ = _generate_signals(features, market_breadth=breadth)
        assert any("退潮" in s for s in sell)
        assert any("冰点" in s for s in sell)
        assert any("接力" in s for s in sell)
        assert any("普涨" in s for s in buy)

    def test_structured_signals_complete(self):
        """结构化信号字段完整。"""
        features = {
            "macd": {"signal": -1, "divergence": "顶背离(看跌)"},
            "kdj": {"signal": "死叉+超买"},
            "bollinger": {"position": 0.9, "bandwidth_desc": ""},
            "rsi": {"rsi": 80},
            "volume": {"volume_price": "放量下跌出货", "volume_price_signal": -1},
        }
        _, _, structured = _generate_signals(features)
        assert structured["macd_death_cross"] is True
        assert structured["macd_top_divergence"] is True
        assert structured["kdj_death_cross"] is True
        assert structured["kdj_overbought"] is True
        assert structured["boll_upper_band"] is True
        assert structured["rsi_overbought"] is True
        assert structured["volume_outflow"] is True
        assert structured["is_downtrend"] is True

    def test_chan_theory_buy_points(self):
        """缠论买点信号。"""
        features = {
            "chan_theory": {
                "valid": True,
                "maidian": {"buy_points": [{"type": "一买"}, {"type": "二买"}]},
                "beichi": {"summary": ""},
            }
        }
        buy, sell, _ = _generate_signals(features)
        assert any("缠论一买" in s for s in buy)
        assert any("缠论二买" in s for s in buy)

    def test_chan_theory_sell_points(self):
        """缠论卖点信号。"""
        features = {
            "chan_theory": {
                "valid": True,
                "maidian": {"sell_points": [{"type": "一卖"}]},
                "beichi": {"summary": ""},
            }
        }
        _, sell, _ = _generate_signals(features)
        assert any("缠论一卖" in s for s in sell)

    def test_chan_theory_bottom_divergence(self):
        """缠论底背驰 -> 买入。"""
        features = {
            "chan_theory": {
                "valid": True,
                "maidian": {"buy_points": [], "sell_points": []},
                "beichi": {"summary": "检测到底背驰（30分钟）"},
            }
        }
        buy, _, _ = _generate_signals(features)
        assert any("缠论底背驰" in s for s in buy)

    def test_chan_theory_top_divergence(self):
        """缠论顶背驰 -> 卖出。"""
        features = {
            "chan_theory": {
                "valid": True,
                "maidian": {"buy_points": [], "sell_points": []},
                "beichi": {"summary": "检测到顶背驰"},
            }
        }
        _, sell, _ = _generate_signals(features)
        assert any("缠论顶背驰" in s for s in sell)

    def test_chan_theory_invalid_skipped(self):
        """缠论 valid=False -> 不产生信号。"""
        features = {"chan_theory": {"valid": False}}
        buy, sell, _ = _generate_signals(features)
        assert all("缠论" not in s for s in buy)
        assert all("缠论" not in s for s in sell)

    def test_local_patterns_bullish(self):
        """本土战法看涨信号。"""
        features = {
            "local_patterns": {"patterns": [{"type": "看涨", "name": "老鸭头"}]},
        }
        buy, _, _ = _generate_signals(features)
        assert "老鸭头" in buy

    def test_local_patterns_bearish(self):
        """本土战法看跌信号。"""
        features = {
            "local_patterns": {"patterns": [{"type": "看跌", "name": "三只乌鸦"}]},
        }
        _, sell, _ = _generate_signals(features)
        assert "三只乌鸦" in sell

    def test_local_patterns_mixed(self):
        """混合看涨看跌。"""
        features = {
            "local_patterns": {
                "patterns": [
                    {"type": "看涨", "name": "老鸭头"},
                    {"type": "看跌", "name": "黄昏之星"},
                ]
            }
        }
        buy, sell, _ = _generate_signals(features)
        assert "老鸭头" in buy
        assert "黄昏之星" in sell

    def test_valuation_low_pe_high_peg_sell(self):
        """PE 中位 + PEG 高 -> 估值偏高卖出。"""
        features = {
            "valuation": {"pe": 30, "pb": 3, "pe_percentile": 68, "peg": 3.0},
        }
        _, sell, _ = _generate_signals(features)
        assert any("估值偏高" in s for s in sell)

    def test_valuation_midrange_no_signal(self):
        """PE 中位 + PEG 低 -> 无估值信号。"""
        features = {
            "valuation": {"pe": 30, "pb": 3, "pe_percentile": 50, "peg": 1.0},
        }
        buy, sell, _ = _generate_signals(features)
        assert all("估值" not in s for s in buy)
        assert all("估值" not in s for s in sell)

    def test_valuation_pe_zero_no_signal(self):
        """PE=0 -> 不触发估值信号。"""
        features = {
            "valuation": {"pe": 0, "pb": 1, "pe_percentile": 10, "peg": 0},
        }
        buy, sell, _ = _generate_signals(features)
        assert all("估值" not in s for s in buy)

    def test_continuous_shrink_signal(self):
        """连续缩量信号。"""
        features = {
            "volume": {
                "volume_price": "",
                "volume_price_signal": 0,
                "shrink_signal": 1,
                "shrink_desc": "连续缩量5天",
            }
        }
        buy, _, _ = _generate_signals(features)
        assert any("连续缩量" in s for s in buy)

    def test_kdj_death_cross_only(self):
        """KDJ 死叉（非超买）-> 卖出。"""
        features = {"kdj": {"signal": "死叉"}}
        _, sell, _ = _generate_signals(features)
        assert any("KDJ" in s for s in sell)

    def test_kdj_overbought_only(self):
        """KDJ 超买（非死叉）-> 卖出。"""
        features = {"kdj": {"signal": "超买"}}
        _, sell, _ = _generate_signals(features)
        assert any("KDJ" in s for s in sell)

"""
technical/report.py::_render_risk_section 的单元测试。

重点覆盖破位检测逻辑（review#18 新增）：
- 止损价 < 现价 -> 正常输出"止损位 -X%"
- 止损价 >= 现价 -> 输出"⚠️ 破位警示"，不再用 abs() 掩盖
- 破位时若有下方支撑 -> 给出下一支撑作为新止损参考
- 破位时若无下方支撑 -> 提示"下方无有效支撑"

背景：原实现用 abs(stop_pct) + 写死"-"前缀，当 nearest_support > price
（股价已跌破支撑）时仍显示"距现价 -X%"，掩盖破位事实。
"""

import pytest

from technical.report import _render_risk_section


def _join(lines):
    return "\n".join(lines)


class TestRenderRiskSectionNormal:
    """止损价 < 现价：正常输出。"""

    def test_normal_stop_below_price(self):
        """止损 15 < 现价 18 -> 输出"止损位: 15.0 (距现价 -16.7%)"。"""
        features = {
            "support_resistance": {
                "nearest_support": 15.0,
                "nearest_resistance": 22.0,
                "supports": [{"level": 15.0, "source": "MA20", "strength": "中"}],
            }
        }
        meta = {"price_num": 18.0}

        out = _join(_render_risk_section(features, meta))

        assert "止损位: 15.0" in out
        assert "距现价 -16.7%" in out
        assert "破位" not in out


class TestRenderRiskSectionBreakdown:
    """止损价 >= 现价：破位检测。"""

    def test_breakdown_with_lower_support(self):
        """止损 20 > 现价 18，存在下方支撑 15 -> 警示 + 新止损参考。"""
        features = {
            "support_resistance": {
                "nearest_support": 20.0,
                "nearest_resistance": 25.0,
                "supports": [
                    {"level": 20.0, "source": "MA10", "strength": "中"},
                    {"level": 15.0, "source": "前低", "strength": "强"},
                ],
            }
        }
        meta = {"price_num": 18.0}

        out = _join(_render_risk_section(features, meta))

        # 破位警示
        assert "⚠️ 破位警示" in out
        assert "已跌破支撑 20.0" in out
        assert "已转为阻力" in out
        # 下一支撑
        assert "下一支撑" in out
        assert "15.0" in out
        assert "前低" in out
        # 不应出现虚假的"止损位: 20.0 (距现价 -X%)"
        assert "止损位: 20.0" not in out

    def test_breakdown_no_lower_support(self):
        """止损 20 > 现价 18，无下方支撑 -> 警示 + "下方无有效支撑"。"""
        features = {
            "support_resistance": {
                "nearest_support": 20.0,
                "nearest_resistance": 25.0,
                "supports": [
                    {"level": 20.0, "source": "MA10", "strength": "中"},
                ],
            }
        }
        meta = {"price_num": 18.0}

        out = _join(_render_risk_section(features, meta))

        assert "⚠️ 破位警示" in out
        assert "下方无有效支撑" in out
        assert "下一支撑" not in out

    def test_breakdown_picks_highest_lower_support(self):
        """破位时从多个下方支撑中选最高的（离现价最近的）作为新止损。"""
        features = {
            "support_resistance": {
                "nearest_support": 20.0,
                "nearest_resistance": 25.0,
                "supports": [
                    {"level": 20.0, "source": "MA10", "strength": "中"},
                    {"level": 12.0, "source": "前低", "strength": "强"},
                    {"level": 15.0, "source": "MA60", "strength": "中"},
                ],
            }
        }
        meta = {"price_num": 18.0}

        out = _join(_render_risk_section(features, meta))

        # 应选 15.0（下方支撑中最高），而非 12.0
        assert "下一支撑" in out
        assert "15.0" in out
        assert "MA60" in out
        assert "12.0" not in out


class TestRenderRiskSectionEdgeCases:
    """边界情况。"""

    def test_no_support_data(self):
        """nearest_support 为 None -> 不输出止损行，不崩溃。"""
        features = {"support_resistance": {"nearest_support": None}}
        meta = {"price_num": 18.0}

        lines = _render_risk_section(features, meta)

        out = _join(lines)
        assert "止损位" not in out
        assert "破位" not in out
        # 仍输出止盈和免责
        assert "纯技术视角" in out

    def test_zero_price(self):
        """price_num 为 0 -> 不输出止损行，不崩溃。"""
        features = {
            "support_resistance": {
                "nearest_support": 15.0,
                "nearest_resistance": 22.0,
                "supports": [],
            }
        }
        meta = {"price_num": 0}

        out = _join(_render_risk_section(features, meta))

        assert "止损位" not in out
        assert "纯技术视角" in out

    def test_stop_loss_pct_sign(self):
        """验证 stop_pct 计算公式：(现价 - 止损) / 现价。

        正常时为正（止损在下方），破位时为负（止损在上方）。
        abs() 不再用于输出层，确保符号语义正确。
        """
        # 正常：止损 16 < 现价 20 -> (20-16)/20 = +20%
        features_ok = {
            "support_resistance": {
                "nearest_support": 16.0,
                "nearest_resistance": 24.0,
                "supports": [{"level": 16.0, "source": "MA20", "strength": "中"}],
            }
        }
        out_ok = _join(_render_risk_section(features_ok, {"price_num": 20.0}))
        assert "距现价 -20.0%" in out_ok

        # 破位：止损 24 > 现价 20 -> (20-24)/20 = -20%，应触发破位警示
        features_bd = {
            "support_resistance": {
                "nearest_support": 24.0,
                "nearest_resistance": 28.0,
                "supports": [{"level": 24.0, "source": "MA10", "strength": "中"}],
            }
        }
        out_bd = _join(_render_risk_section(features_bd, {"price_num": 20.0}))
        assert "⚠️ 破位警示" in out_bd
        assert "上方 20.0%" in out_bd  # abs(-20.0%) = 20.0%
        # 不应出现"止损位: 24.0 (距现价 -20.0%)"这种掩盖破位的输出
        assert "止损位: 24.0" not in out_bd

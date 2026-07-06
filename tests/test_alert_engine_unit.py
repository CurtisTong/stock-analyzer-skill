"""alert_engine.py 单元测试：预警级别、预警检查、渲染。"""

import pytest
from unittest.mock import patch, MagicMock

# ── get_alert_level 纯函数测试 ──


class TestGetAlertLevel:
    """get_alert_level 测试。"""

    def test_urgent_override(self):
        from monitor.alert_engine import get_alert_level

        # urgent=True 时无论 alert_type 是什么，都返回 urgent
        assert get_alert_level("support_touch", urgent=True) == "urgent"
        assert get_alert_level("unknown_type", urgent=True) == "urgent"

    def test_stop_loss_is_urgent(self):
        from monitor.alert_engine import get_alert_level

        assert get_alert_level("stop_loss") == "urgent"

    def test_target_buy_is_urgent(self):
        from monitor.alert_engine import get_alert_level

        assert get_alert_level("target_buy") == "urgent"

    def test_macd_golden_is_important(self):
        from monitor.alert_engine import get_alert_level

        assert get_alert_level("macd_golden") == "important"

    def test_support_touch_is_important(self):
        from monitor.alert_engine import get_alert_level

        assert get_alert_level("support_touch") == "important"

    def test_support_touch_weak_is_normal(self):
        from monitor.alert_engine import get_alert_level

        assert get_alert_level("support_touch_weak") == "normal"

    def test_unknown_type_defaults_to_normal(self):
        from monitor.alert_engine import get_alert_level

        assert get_alert_level("nonexistent_type") == "normal"


# ── _check_alerts 纯函数测试 ──


class TestCheckAlerts:
    """_check_alerts 测试。"""

    def test_no_alerts_when_no_levels(self):
        from monitor.alert_engine import _check_alerts

        alerts = _check_alerts(price=100.0, levels={})
        assert alerts == []

    def test_support_touch_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {
            "supports": [
                {"level": 99.0, "strength": "强", "source": "MA20"},
            ]
        }
        alerts = _check_alerts(price=99.5, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "support_touch"
        assert alerts[0]["urgent"] is True

    def test_support_touch_weak_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {
            "supports": [
                {"level": 99.0, "strength": "中", "source": "MA60"},
            ]
        }
        alerts = _check_alerts(price=99.5, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "support_touch_weak"
        assert alerts[0]["urgent"] is False

    def test_resistance_touch_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {
            "resistances": [
                {"level": 101.0, "source": "前高"},
            ]
        }
        alerts = _check_alerts(price=101.5, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "resistance_touch"

    def test_target_buy_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {"target_buy": 100.0}
        alerts = _check_alerts(price=99.0, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "target_buy"
        assert alerts[0]["urgent"] is True

    def test_target_sell_alert(self):
        """target_sell 是止损价：价格跌破止损价时触发预警。"""
        from monitor.alert_engine import _check_alerts

        levels = {"target_sell": 120.0}
        # 价格低于止损价 → 触发
        alerts = _check_alerts(price=115.0, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "target_sell"
        assert alerts[0]["urgent"] is True
        assert "跌破" in alerts[0]["message"]

        # 价格高于止损价 → 不触发
        alerts_above = _check_alerts(price=121.0, levels=levels)
        assert len(alerts_above) == 0

    def test_macd_golden_cross_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {"macd_signal": "金叉"}
        alerts = _check_alerts(price=100.0, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "macd_golden"

    def test_macd_death_cross_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {"macd_signal": "死叉"}
        alerts = _check_alerts(price=100.0, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "macd_dead"

    def test_ma_break_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {"ma_breaks": ["突破MA20(18.5)"]}
        alerts = _check_alerts(price=18.6, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "ma_break"

    def test_near_limit_up_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {"near_limit_up": True, "limit_up": 110.0}
        alerts = _check_alerts(price=109.5, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "near_limit"
        assert "涨停" in alerts[0]["message"]

    def test_near_limit_down_alert(self):
        from monitor.alert_engine import _check_alerts

        levels = {"near_limit_down": True, "limit_down": 90.0}
        alerts = _check_alerts(price=90.5, levels=levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "near_limit"
        assert "跌停" in alerts[0]["message"]

    def test_stop_loss_alert(self):
        from monitor.alert_engine import _check_alerts

        position = {"cost": 100.0}
        # 价格跌到 90，亏损 10%，超过默认 -8% 止损线
        alerts = _check_alerts(price=90.0, levels={}, position=position)
        stop_alerts = [a for a in alerts if a["type"] == "stop_loss"]
        assert len(stop_alerts) == 1
        assert stop_alerts[0]["urgent"] is True

    def test_take_profit_alert(self):
        from monitor.alert_engine import _check_alerts

        position = {"cost": 100.0}
        # 价格涨到 125，盈利 25%，超过默认 20% 止盈线
        alerts = _check_alerts(price=125.0, levels={}, position=position)
        tp_alerts = [a for a in alerts if a["type"] == "take_profit"]
        assert len(tp_alerts) == 1
        assert tp_alerts[0]["urgent"] is False

    def test_no_stop_loss_within_threshold(self):
        from monitor.alert_engine import _check_alerts

        position = {"cost": 100.0}
        # 价格 95，亏损 5%，未触及 -8% 止损线
        alerts = _check_alerts(price=95.0, levels={}, position=position)
        stop_alerts = [a for a in alerts if a["type"] == "stop_loss"]
        assert len(stop_alerts) == 0

    def test_multiple_alerts(self):
        from monitor.alert_engine import _check_alerts

        levels = {
            "supports": [{"level": 99.0, "strength": "强", "source": "MA20"}],
            "macd_signal": "金叉",
        }
        position = {"cost": 100.0}
        # 价格 99.5：触及支撑 + MACD 金叉 + 未触发止损
        alerts = _check_alerts(price=99.5, levels=levels, position=position)
        types = {a["type"] for a in alerts}
        assert "support_touch" in types
        assert "macd_golden" in types
        assert "stop_loss" not in types


# ── render_scan 纯函数测试 ──


class TestRenderScan:
    """render_scan 测试。"""

    def test_empty_results(self):
        from monitor.alert_engine import render_scan

        output = render_scan([])
        assert "扫描标的: 0" in output

    def test_render_with_error(self):
        from monitor.alert_engine import render_scan

        results = [
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "price": 0,
                "error": "数据获取失败",
            }
        ]
        output = render_scan(results)
        assert "❌" in output
        assert "数据获取失败" in output

    def test_render_with_alerts(self):
        from monitor.alert_engine import render_scan

        results = [
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "price": 18.5,
                "change_pct": 1.2,
                "levels": {},
                "alerts": [
                    {"type": "macd_golden", "message": "MACD 金叉", "urgent": False}
                ],
            }
        ]
        output = render_scan(results)
        assert "宝丰能源" in output
        assert "18.5" in output
        assert "MACD 金叉" in output

    def test_render_with_supports_and_resistances(self):
        from monitor.alert_engine import render_scan

        results = [
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "price": 18.5,
                "change_pct": 0.0,
                "levels": {
                    "supports": [{"level": 18.0, "source": "MA20"}],
                    "resistances": [{"level": 19.5, "source": "前高"}],
                    "ma_values": {"MA20": 18.0, "MA60": 17.5},
                },
                "alerts": [],
            }
        ]
        output = render_scan(results)
        assert "支撑" in output
        assert "压力" in output
        assert "均线" in output


# ── ALERT_LEVELS 配置完整性测试 ──


class TestAlertLevelsConfig:
    """ALERT_LEVELS 配置测试。"""

    def test_all_alert_types_have_valid_level(self):
        from monitor.alert_engine import ALERT_LEVELS, _LEVEL_META

        for alert_type, cfg in ALERT_LEVELS.items():
            assert (
                cfg["level"] in _LEVEL_META
            ), f"{alert_type} has invalid level: {cfg['level']}"

    def test_all_alert_types_have_push_type(self):
        from monitor.alert_engine import ALERT_LEVELS

        for alert_type, cfg in ALERT_LEVELS.items():
            assert "push_type" in cfg, f"{alert_type} missing push_type"

"""monitor/rules.py 补充测试：覆盖 _check_alerts 更多分支 + check_portfolio_alerts。"""

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from monitor.rules import (
    _check_alerts,
    check_portfolio_alerts,
    get_alert_level,
    _load_notification_config,
    ALERT_LEVELS,
    _LEVEL_META,
)


# ═══════════════════════════════════════════════════════════════
# _check_alerts - 边界与组合场景
# ═══════════════════════════════════════════════════════════════


class TestCheckAlertsEdgeCases:
    def test_support_outside_range_no_alert(self):
        """价格远离支撑位 -> 不报警。"""
        levels = {"supports": [{"level": 10, "strength": "强", "source": "前低"}]}
        alerts = _check_alerts(20.0, levels)
        assert alerts == []

    def test_support_zero_level_no_alert(self):
        """支撑位 level=0 -> 不报警。"""
        levels = {"supports": [{"level": 0, "strength": "强", "source": ""}]}
        alerts = _check_alerts(0.0, levels)
        assert alerts == []

    def test_support_strong_urgent(self):
        """强支撑位触及 -> urgent=True。"""
        levels = {"supports": [{"level": 10, "strength": "强", "source": "前低"}]}
        alerts = _check_alerts(10.0, levels)
        assert len(alerts) == 1
        assert alerts[0]["urgent"] is True
        assert alerts[0]["type"] == "support_touch"

    def test_support_weak_normal(self):
        """弱支撑位触及 -> urgent=False, type=support_touch_weak。"""
        levels = {"supports": [{"level": 10, "strength": "中", "source": "前低"}]}
        alerts = _check_alerts(10.0, levels)
        assert len(alerts) == 1
        assert alerts[0]["urgent"] is False
        assert alerts[0]["type"] == "support_touch_weak"

    def test_resistance_outside_range_no_alert(self):
        levels = {"resistances": [{"level": 50, "source": "前高"}]}
        alerts = _check_alerts(10.0, levels)
        assert alerts == []

    def test_resistance_touch(self):
        levels = {"resistances": [{"level": 50, "source": "前高"}]}
        alerts = _check_alerts(50.0, levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "resistance_touch"
        assert alerts[0]["urgent"] is False

    def test_target_buy_not_reached(self):
        """价格高于目标买入价 -> 不报警。"""
        levels = {"target_buy": 10}
        alerts = _check_alerts(15.0, levels)
        assert alerts == []

    def test_target_buy_reached(self):
        levels = {"target_buy": 10}
        alerts = _check_alerts(10.0, levels)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "target_buy"
        assert alerts[0]["urgent"] is True

    def test_target_sell_above_no_alert(self):
        """价格高于止损价 -> 不报警。"""
        levels = {"target_sell": 8}
        alerts = _check_alerts(10.0, levels)
        assert alerts == []

    def test_target_sell_broken_with_distance(self):
        """跌破止损价且偏离。"""
        levels = {"target_sell": 10}
        alerts = _check_alerts(8.0, levels)
        assert len(alerts) == 1
        assert "偏离" in alerts[0]["message"]

    def test_macd_neutral_no_alert(self):
        levels = {"macd_signal": "中性"}
        alerts = _check_alerts(10.0, levels)
        assert all(a["type"] != "macd_golden" for a in alerts)
        assert all(a["type"] != "macd_dead" for a in alerts)

    def test_macd_unknown_signal_no_alert(self):
        levels = {"macd_signal": "未知"}
        alerts = _check_alerts(10.0, levels)
        assert all(a["type"] != "macd_golden" for a in alerts)

    def test_ma_break_multiple(self):
        """多个均线突破 -> 多条预警。"""
        levels = {"ma_breaks": ["突破MA20", "突破MA60"]}
        alerts = _check_alerts(10.0, levels)
        assert len(alerts) == 2
        for a in alerts:
            assert a["type"] == "ma_break"
            assert a["urgent"] is False

    def test_near_limit_up(self):
        levels = {"near_limit_up": True, "limit_up": 11}
        alerts = _check_alerts(10.0, levels)
        assert any(a["type"] == "near_limit" and "涨停" in a["message"] for a in alerts)

    def test_near_limit_down(self):
        levels = {"near_limit_down": True, "limit_down": 9}
        alerts = _check_alerts(10.0, levels)
        assert any(a["type"] == "near_limit" and "跌停" in a["message"] for a in alerts)

    def test_position_cost_zero_no_alert(self):
        """持仓 cost=0 -> 不触发止损/止盈。"""
        alerts = _check_alerts(10.0, {}, position={"cost": 0})
        assert all(a["type"] != "stop_loss" for a in alerts)
        assert all(a["type"] != "take_profit" for a in alerts)

    def test_position_within_threshold(self):
        """盈亏在止损/止盈阈值内 -> 不报警。"""
        alerts = _check_alerts(10.5, {}, position={"cost": 10})
        assert all(a["type"] != "stop_loss" for a in alerts)
        assert all(a["type"] != "take_profit" for a in alerts)

    def test_all_alerts_combined(self):
        """多种预警同时触发。"""
        levels = {
            "supports": [{"level": 10, "strength": "强", "source": "前低"}],
            "resistances": [{"level": 10, "source": "前高"}],
            "target_buy": 10,
            "macd_signal": "金叉",
            "near_limit_down": True,
            "limit_down": 9,
        }
        alerts = _check_alerts(10.0, levels, position={"cost": 100})
        # 至少 5 类预警
        types = {a["type"] for a in alerts}
        assert "support_touch" in types
        assert "resistance_touch" in types
        assert "target_buy" in types
        assert "macd_golden" in types
        assert "near_limit" in types


# ═══════════════════════════════════════════════════════════════
# get_alert_level
# ═══════════════════════════════════════════════════════════════


class TestGetAlertLevel:
    def test_urgent_override(self):
        assert get_alert_level("support_touch", urgent=True) == "urgent"

    def test_normal_type(self):
        assert get_alert_level("support_touch_weak") == "normal"

    def test_important_type(self):
        assert get_alert_level("macd_golden") == "important"

    def test_unknown_type_default_normal(self):
        assert get_alert_level("unknown_type") == "normal"


# ═══════════════════════════════════════════════════════════════
# _load_notification_config
# ═══════════════════════════════════════════════════════════════


class TestLoadNotificationConfig:
    def test_returns_dict_with_keys(self):
        cfg = _load_notification_config()
        assert "underperform_days" in cfg
        assert "index_change_threshold" in cfg
        assert "northbound_threshold_yi" in cfg

    def test_values_positive(self):
        cfg = _load_notification_config()
        assert cfg["underperform_days"] > 0
        assert cfg["index_change_threshold"] > 0
        assert cfg["northbound_threshold_yi"] > 0


# ═══════════════════════════════════════════════════════════════
# check_portfolio_alerts
# ═══════════════════════════════════════════════════════════════


class TestCheckPortfolioAlerts:
    def test_empty_positions(self):
        assert check_portfolio_alerts([], {}) == []

    def test_risk_state_upgrade_to_red(self):
        """风险状态 GREEN->RED -> urgent 预警。"""
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 11}},
            prev_risk_state="GREEN",
            current_risk_state="RED",
        )
        risk_alerts = [a for a in alerts if a["type"] == "risk_change"]
        assert len(risk_alerts) == 1
        assert risk_alerts[0]["urgent"] is True

    def test_risk_state_no_change_no_alert(self):
        """风险状态不变 -> 无预警。"""
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 11}},
            prev_risk_state="GREEN",
            current_risk_state="GREEN",
        )
        assert all(a["type"] != "risk_change" for a in alerts)

    def test_risk_state_downgrade_no_alert(self):
        """风险状态降级 RED->GREEN -> 无预警。"""
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 11}},
            prev_risk_state="RED",
            current_risk_state="GREEN",
        )
        assert all(a["type"] != "risk_change" for a in alerts)

    def test_index_change_large_move(self):
        """沪深300 大涨 -> index_change 预警。"""
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 10}},
            benchmark_change_pct=5.0,
        )
        assert any(a["type"] == "index_change" for a in alerts)

    def test_index_change_small_move_no_alert(self):
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 10}},
            benchmark_change_pct=0.5,
        )
        assert all(a["type"] != "index_change" for a in alerts)

    def test_northbound_large_inflow(self):
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 10}},
            northbound_net_yi=100,
        )
        nb = [a for a in alerts if a["type"] == "northbound_flow"]
        assert len(nb) == 1
        assert "流入" in nb[0]["message"]

    def test_northbound_large_outflow(self):
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 10}},
            northbound_net_yi=-100,
        )
        nb = [a for a in alerts if a["type"] == "northbound_flow"]
        assert len(nb) == 1
        assert "流出" in nb[0]["message"]

    def test_northbound_small_no_alert(self):
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 10}},
            northbound_net_yi=10,
        )
        assert all(a["type"] != "northbound_flow" for a in alerts)

    def test_concentration_single_overweight(self):
        """单一标的集中度超标 -> urgent 预警。"""
        alerts = check_portfolio_alerts(
            [
                {"code": "sh600000", "cost": 10, "quantity": 1000},
                {"code": "sh600001", "cost": 10, "quantity": 1},
            ],
            {"sh600000": {"price": 10}, "sh600001": {"price": 10}},
        )
        assert any(a["type"] == "concentration" and a["urgent"] for a in alerts)

    def test_concentration_top3_overweight(self):
        """前3持仓超标 -> 非紧急预警。"""
        alerts = check_portfolio_alerts(
            [
                {"code": "sh600000", "cost": 10, "quantity": 200},
                {"code": "sh600001", "cost": 10, "quantity": 200},
                {"code": "sh600002", "cost": 10, "quantity": 200},
                {"code": "sh600003", "cost": 10, "quantity": 1},
            ],
            {f"sh60000{i}": {"price": 10} for i in range(4)},
        )
        conc = [a for a in alerts if a["type"] == "concentration"]
        assert len(conc) >= 1

    def test_sector_moved_alert(self):
        """持仓板块异动 -> 预警。"""
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100, "tags": ["新能源"]}],
            {"sh600000": {"price": 10}},
            sector_changes={"新能源": 5.0},
        )
        assert any(a["type"] == "sector_moved" for a in alerts)

    def test_sector_small_move_no_alert(self):
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100, "tags": ["新能源"]}],
            {"sh600000": {"price": 10}},
            sector_changes={"新能源": 1.0},
        )
        assert all(a["type"] != "sector_moved" for a in alerts)

    def test_underperform_benchmark(self):
        """组合大幅跑输基准 -> 预警。"""
        alerts = check_portfolio_alerts(
            [{"code": "sh600000", "cost": 10, "quantity": 100}],
            {"sh600000": {"price": 9.5}},  # 亏损 5%
            benchmark_change_pct=2.0,  # 基准涨 2%，差 7%
        )
        assert any(a["type"] == "underperform_days" for a in alerts)


# ═══════════════════════════════════════════════════════════════
# 常量完整性
# ═══════════════════════════════════════════════════════════════


class TestAlertConstants:
    def test_all_alert_types_have_level(self):
        for atype, meta in ALERT_LEVELS.items():
            assert "level" in meta
            assert meta["level"] in ("urgent", "important", "normal")

    def test_all_alert_types_have_push_type(self):
        for atype, meta in ALERT_LEVELS.items():
            assert "push_type" in meta

    def test_level_meta_has_three_levels(self):
        assert set(_LEVEL_META.keys()) == {"urgent", "important", "normal"}
        for level, meta in _LEVEL_META.items():
            assert "name" in meta
            assert "notify" in meta
            assert "sound" in meta

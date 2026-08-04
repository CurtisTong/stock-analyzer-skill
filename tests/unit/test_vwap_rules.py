"""VWAP 分时均价线预警规则单元测试。

覆盖场景：
- VWAP 上穿（price 略高于 vwap，偏离<0.5%）-> vwap_cross_up
- VWAP 下穿（price 略低于 vwap，偏离>-0.5%）-> vwap_cross_down
- VWAP 偏离（|偏离|≥2%）-> vwap_deviation
- 偏离≥3% -> vwap_deviation urgent
- 无 vwap 数据 -> 不触发
- ALERT_LEVELS 注册验证
- gain_reduce + ma_stop_loss 回归验证（第一批规则恢复确认）
"""

import pytest

from monitor.rules import _check_alerts, ALERT_LEVELS


class TestVwapRules:
    """VWAP 分时均价线预警规则。"""

    def test_vwap_cross_up(self):
        """现价略高于 VWAP（偏离<0.5%）-> vwap_cross_up。"""
        vwap = 10.00
        price = 10.03  # 偏离 +0.3%
        levels = {"vwap": vwap, "price_vs_vwap": 0.3}
        alerts = _check_alerts(price, levels)
        cross_up = [a for a in alerts if a["type"] == "vwap_cross_up"]
        assert len(cross_up) == 1
        assert "上穿分时均价线" in cross_up[0]["message"]
        assert cross_up[0]["urgent"] is False

    def test_vwap_cross_down(self):
        """现价略低于 VWAP（偏离>-0.5%）-> vwap_cross_down。"""
        vwap = 10.00
        price = 9.97  # 偏离 -0.3%
        levels = {"vwap": vwap, "price_vs_vwap": -0.3}
        alerts = _check_alerts(price, levels)
        cross_down = [a for a in alerts if a["type"] == "vwap_cross_down"]
        assert len(cross_down) == 1
        assert "下穿分时均价线" in cross_down[0]["message"]

    def test_vwap_deviation_above_2pct(self):
        """现价高于 VWAP 超过2% -> vwap_deviation。"""
        vwap = 10.00
        price = 10.25  # 偏离 +2.5%
        levels = {"vwap": vwap, "price_vs_vwap": 2.5}
        alerts = _check_alerts(price, levels)
        dev = [a for a in alerts if a["type"] == "vwap_deviation"]
        assert len(dev) == 1
        assert "高于" in dev[0]["message"]
        assert dev[0]["urgent"] is False  # 2.5% < 3%，不紧急

    def test_vwap_deviation_above_3pct_urgent(self):
        """现价高于 VWAP 超过3% -> vwap_deviation urgent。"""
        vwap = 10.00
        price = 10.35  # 偏离 +3.5%
        levels = {"vwap": vwap, "price_vs_vwap": 3.5}
        alerts = _check_alerts(price, levels)
        dev = [a for a in alerts if a["type"] == "vwap_deviation"]
        assert len(dev) == 1
        assert dev[0]["urgent"] is True

    def test_vwap_deviation_below_2pct(self):
        """现价低于 VWAP 超过2% -> vwap_deviation。"""
        vwap = 10.00
        price = 9.75  # 偏离 -2.5%
        levels = {"vwap": vwap, "price_vs_vwap": -2.5}
        alerts = _check_alerts(price, levels)
        dev = [a for a in alerts if a["type"] == "vwap_deviation"]
        assert len(dev) == 1
        assert "低于" in dev[0]["message"]

    def test_no_vwap_no_alert(self):
        """无 vwap 数据 -> 不触发任何 VWAP 预警。"""
        levels = {}
        alerts = _check_alerts(10.0, levels)
        vwap_alerts = [a for a in alerts if "vwap" in a["type"]]
        assert len(vwap_alerts) == 0

    def test_vwap_far_above_no_cross(self):
        """现价远高于 VWAP（偏离>0.5%）-> 不触发 cross_up（只触发 deviation）。"""
        vwap = 10.00
        price = 10.10  # 偏离 +1.0%，不在 cross 的 0~0.5% 窗口
        levels = {"vwap": vwap, "price_vs_vwap": 1.0}
        alerts = _check_alerts(price, levels)
        cross_up = [a for a in alerts if a["type"] == "vwap_cross_up"]
        assert len(cross_up) == 0  # 偏离太大不算穿越
        # 偏离 1.0% < 2%，也不触发 deviation
        dev = [a for a in alerts if a["type"] == "vwap_deviation"]
        assert len(dev) == 0

    def test_alert_levels_registered(self):
        """ALERT_LEVELS 注册了三种 VWAP 预警类型。"""
        assert "vwap_cross_up" in ALERT_LEVELS
        assert "vwap_cross_down" in ALERT_LEVELS
        assert "vwap_deviation" in ALERT_LEVELS
        assert ALERT_LEVELS["vwap_cross_up"]["level"] == "important"
        assert ALERT_LEVELS["vwap_cross_down"]["level"] == "important"
        assert ALERT_LEVELS["vwap_deviation"]["level"] == "normal"


class TestGainReduceRules:
    """固定涨幅减仓预警回归验证（第一批规则恢复确认）。"""

    def test_gain_reduce_triggered(self):
        """盈利6%达到5%台阶 -> gain_reduce。"""
        alerts = _check_alerts(
            price=10.6,
            levels={"ma_values": {"MA20": 9.5}},
            position={"cost": 10.0},
        )
        gain = [a for a in alerts if a["type"] == "gain_reduce"]
        assert len(gain) == 1
        assert gain[0]["level"] == 5.0

    def test_gain_reduce_highest_step_only(self):
        """盈利10%只报最高台阶10%，不报5%。"""
        alerts = _check_alerts(
            price=11.0,
            levels={"ma_values": {"MA20": 10.0}},
            position={"cost": 10.0},
        )
        gain = [a for a in alerts if a["type"] == "gain_reduce"]
        assert len(gain) == 1
        assert gain[0]["level"] == 10.0

    def test_ma_stop_loss_triggered(self):
        """跌破MA20（2%以内）-> ma_stop_loss。"""
        alerts = _check_alerts(
            price=9.4,
            levels={"ma_values": {"MA20": 9.5}},
            position={"cost": 10.0},
        )
        ma_alerts = [a for a in alerts if a["type"] == "ma_stop_loss"]
        assert len(ma_alerts) == 1
        assert ma_alerts[0]["urgent"] is True

    def test_ma_stop_loss_not_triggered_far_below(self):
        """跌破MA20超过2% -> 不报 ma_stop_loss。"""
        alerts = _check_alerts(
            price=9.0,
            levels={"ma_values": {"MA20": 9.5}},
            position={"cost": 10.0},
        )
        ma_alerts = [a for a in alerts if a["type"] == "ma_stop_loss"]
        assert len(ma_alerts) == 0

    def test_gain_reduce_and_ma_stop_loss_registered(self):
        """ALERT_LEVELS 注册了 gain_reduce + ma_stop_loss。"""
        assert "gain_reduce" in ALERT_LEVELS
        assert "ma_stop_loss" in ALERT_LEVELS
        assert ALERT_LEVELS["ma_stop_loss"]["level"] == "urgent"

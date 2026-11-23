"""[review P1-24] 市场宽度东财 "-" 字段逐字段判空回归测试。

修复前：sh.get("f104", 0) + sz.get("f104", 0) 在字段为 "-" 时得到 "--"，
随后 down_count > 0 抛 TypeError 被外层 except 吞掉 → 全市场宽度静默降级。
"""

from __future__ import annotations

import json

import market_breadth as mb

LIMIT_DATA = {"limit_up_count": 5, "limit_down_count": 2, "continuous_limit_height": 3, "broken_limit_rate": 10.0}


def _fake_http(diff):
    payload = {"rc": 0, "data": {"diff": diff}}
    return lambda *args, **kwargs: json.dumps(payload)


def _install(monkeypatch, diff):
    monkeypatch.setattr(mb, "http_get", _fake_http(diff))
    monkeypatch.setattr(mb, "get_limit_data", lambda: dict(LIMIT_DATA))


class TestDashFields:
    def test_all_dash_fields_degrade_without_crash(self, monkeypatch):
        """[review P1-24] "-" 字段不得拼成 "--" 触发 TypeError。"""
        _install(monkeypatch, [{"f104": "-", "f105": "-", "f106": "-"}] * 2)
        result = mb.get_market_breadth()
        assert result["_degraded"] is True
        assert result["up_count"] is None and result["down_count"] is None
        assert result["up_ratio"] is None
        assert "-" in result["_degraded_reason"]
        # 涨跌停真实数据仍应保留
        assert result["limit_up_count"] == 5

    def test_partial_dash_field_also_degrades(self, monkeypatch):
        """[review P1-24] 逐字段判空：任一字段 "-" 即按宽度不可用处理。"""
        _install(
            monkeypatch,
            [
                {"f104": "-", "f105": 100, "f106": 10},
                {"f104": 200, "f105": 120, "f106": 20},
            ],
        )
        result = mb.get_market_breadth()
        assert result["_degraded"] is True
        assert result["up_count"] is None
        assert "-" in result["_degraded_reason"]  # 不能变成笼统的"整体拉取失败"
        assert result["limit_up_count"] == 5  # 涨跌停数据仍保留

    def test_valid_fields_keep_normal_path(self, monkeypatch):
        """[review P1-24] 正常数值路径回归：不得误判为降级。"""
        _install(
            monkeypatch,
            [
                {"f104": 2000, "f105": 1000, "f106": 100},
                {"f104": 1500, "f105": 800, "f106": 80},
            ],
        )
        result = mb.get_market_breadth()
        assert result.get("_degraded", False) is False
        assert result["up_count"] == 3500
        assert result["down_count"] == 1800
        assert result["up_ratio"] == round(3500 / 1800, 2)

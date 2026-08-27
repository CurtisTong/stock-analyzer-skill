"""第 1 条：实际组合总仓位计算测试。

需求：计算实际组合总仓位后再给建议（此前仅给单标的/行业集中度）。
实现：portfolio.json 顶层可选 total_assets（元），
manager.compute_total_position_ratio() 计算持仓成本/市值 ÷ 总资产；
未配置时返回 None + 提示，不猜测资金上下文。
"""

from __future__ import annotations

import json

from portfolio import PortfolioManager

_POS = [
    {
        "code": "sh600000",
        "name": "浦发银行",
        "cost": 10.0,
        "quantity": 1000,
        "buy_date": "2026-07-01",
        "tags": ["银行"],
    },
    {
        "code": "sz000858",
        "name": "五粮液",
        "cost": 120.0,
        "quantity": 100,
        "buy_date": "2026-07-01",
        "tags": ["白酒"],
    },
]


def _make_manager(tmp_path, total_assets=None):
    data = {"version": 2, "positions": _POS, "watchlist": []}
    if total_assets is not None:
        data["total_assets"] = total_assets
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return PortfolioManager(path=str(p))


class TestTotalPositionRatio:
    def test_missing_total_assets_returns_none(self, tmp_path):
        """未配置 total_assets：position_ratio=None + warning 提示。"""
        pm = _make_manager(tmp_path)
        r = pm.compute_total_position_ratio()
        assert r["total_assets"] is None
        assert r["position_ratio"] is None
        assert "未配置 total_assets" in r["warning"]
        # 成本合计仍返回
        assert r["position_cost"] == 10.0 * 1000 + 120.0 * 100

    def test_cost_ratio_with_total_assets(self, tmp_path):
        """配置 total_assets：成本口径占比 = 成本/总资产。"""
        # 成本 10000 + 12000 = 22000；总资产 100000 → 22%
        pm = _make_manager(tmp_path, total_assets=100000)
        r = pm.compute_total_position_ratio()
        assert r["total_assets"] == 100000.0
        assert r["position_ratio"] == 22.0
        assert r["warning"] is None

    def test_mv_ratio_with_price_lookup(self, tmp_path):
        """提供现价：市值口径占比单独计算。"""
        pm = _make_manager(tmp_path, total_assets=100000)
        prices = {"sh600000": 12.0, "sz000858": 130.0}
        r = pm.compute_total_position_ratio(prices)
        # 市值 = 12*1000 + 130*100 = 25000 → 25%
        assert r["position_mv"] == 25000.0
        assert r["position_ratio_mv"] == 25.0
        assert r["position_ratio"] == 22.0  # 成本口径不受现价影响

    def test_overweight_warning(self, tmp_path):
        """成本占比 >90% 触发仓位过重警告。"""
        # 成本 22000 / 总资产 23000 ≈ 95.65%
        pm = _make_manager(tmp_path, total_assets=23000)
        r = pm.compute_total_position_ratio()
        assert r["position_ratio"] > 90
        assert r["position_ratio"] == 95.65
        assert "仓位过重" in r["warning"]

    def test_health_report_includes_position_ratio(self, tmp_path):
        """health_report 输出带 position_ratio 字段（全局生效）。"""
        pm = _make_manager(tmp_path, total_assets=100000)
        report = pm.health_report(
            quotes={
                "sh600000": {"price": 12.0, "change_pct": 0},
                "sz000858": {"price": 130.0, "change_pct": 0},
            },
            auto_technical=False,
        )
        pr = report["position_ratio"]
        assert pr["position_ratio"] == 22.0
        assert pr["position_ratio_mv"] == 25.0

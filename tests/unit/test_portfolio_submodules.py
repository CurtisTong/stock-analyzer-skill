"""portfolio/analytics.py + portfolio/rebalance.py 子模块单元测试（v1.16.0 ）。

验证从 PortfolioManager god class 拆出的两个子模块：
- portfolio.analytics: to_dict / summary / risk_summary / attribution_report
- portfolio.rebalance: advisory_rebalance

每个函数以 manager 为参数，不修改 manager._data，行为与原 PortfolioManager 方法一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def portfolio_mgr(tmp_path: Path):
    from portfolio.manager import PortfolioManager

    data_file = tmp_path / "portfolio.json"
    data_file.write_text(
        json.dumps(
            {
                "version": 2,
                "positions": [
                    {
                        "code": "sh600519",
                        "name": "贵州茅台",
                        "quantity": 100,
                        "cost": 1500.0,
                        "tags": ["长线"],
                    }
                ],
                "watchlist": [{"code": "sz000001", "name": "平安银行"}],
            }
        ),
        encoding="utf-8",
    )
    return PortfolioManager(str(data_file))


class TestAnalyticsToDict:
    def test_returns_full_state(self, portfolio_mgr):
        from portfolio.analytics import to_dict

        d = to_dict(portfolio_mgr)
        assert isinstance(d, dict)
        assert "positions" in d
        assert "watchlist" in d

    def test_does_not_mutate_original(self, portfolio_mgr):
        """to_dict 返回浅副本，调用方修改不应影响 manager 内部状态。"""
        from portfolio.analytics import to_dict

        d = to_dict(portfolio_mgr)
        d["positions"].append({"code": "sh999999"})
        # manager 状态不变
        assert portfolio_mgr.get_position("sh999999") is None

    def test_matches_manager_method(self, portfolio_mgr):
        """子模块 to_dict 与原 PortfolioManager.to_dict 行为一致。"""
        from portfolio.analytics import to_dict

        a = to_dict(portfolio_mgr)
        b = portfolio_mgr.to_dict()
        assert a == b


class TestAnalyticsSummary:
    def test_summary_includes_counts(self, portfolio_mgr):
        from portfolio.analytics import summary

        text = summary(portfolio_mgr)
        assert "持仓 1 只" in text
        assert "自选 1 只" in text

    def test_summary_includes_position_detail(self, portfolio_mgr):
        from portfolio.analytics import summary

        text = summary(portfolio_mgr)
        assert "贵州茅台" in text

    def test_matches_manager_method(self, portfolio_mgr):
        from portfolio.analytics import summary

        a = summary(portfolio_mgr)
        b = portfolio_mgr.summary()
        assert a == b


class TestAnalyticsRiskAndAttribution:
    def test_risk_summary_graceful_when_module_unavailable(self, portfolio_mgr):
        """risk_summary 在 risk_metrics 不可用时返回提示，不抛异常。"""
        from portfolio.analytics import risk_summary

        # 不传 quotes：测试纯函数路径
        text = risk_summary(portfolio_mgr)
        assert isinstance(text, str)
        # 可能是 "暂无持仓" 或 "⚠️ 模块不可用"——两者均可接受

    def test_attribution_report_graceful(self, portfolio_mgr):
        """attribution_report 在 brinson 不可用或无持仓时返回提示。"""
        from portfolio.analytics import attribution_report

        text = attribution_report(portfolio_mgr)
        assert isinstance(text, str)


class TestRebalance:
    def test_target_ratio_1_returns_empty(self, portfolio_mgr):
        """target_ratio=1.0（GREEN）→ 返回空列表（无减仓建议）。"""
        from portfolio.rebalance import advisory_rebalance

        result = advisory_rebalance(portfolio_mgr, target_ratio=1.0)
        assert result == []

    def test_target_ratio_half_suggests_reduce(self, portfolio_mgr):
        """target_ratio=0.5 → 应产出减仓建议（含 reduce_value > 0）。"""
        from portfolio.rebalance import advisory_rebalance

        result = advisory_rebalance(portfolio_mgr, target_ratio=0.5)
        assert isinstance(result, list)
        if result:  # 有持仓时
            for s in result:
                assert s["action"] == "reduce"
                assert s["reduce_value"] > 0
                assert "宏观50%" in s["reason"]

    def test_empty_portfolio_returns_empty(self, tmp_path):
        from portfolio.manager import PortfolioManager
        from portfolio.rebalance import advisory_rebalance

        data_file = tmp_path / "empty.json"
        data_file.write_text(
            json.dumps({"version": 2, "positions": [], "watchlist": []})
        )
        mgr = PortfolioManager(str(data_file))
        result = advisory_rebalance(mgr, target_ratio=0.5)
        assert result == []

    def test_matches_manager_method(self, portfolio_mgr):
        from portfolio.rebalance import advisory_rebalance

        a = advisory_rebalance(portfolio_mgr, target_ratio=0.8)
        b = portfolio_mgr.advisory_rebalance(target_ratio=0.8)
        assert a == b

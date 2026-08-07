"""scripts/monitor/notifier.py 的单元测试。

覆盖内联 scan_all 与 check_and_push 的核心行为：
- 持仓+自选去重扫描
- 批量预取行情
- 返回结构（code/price/alerts/position 字段）
- check_and_push(dry_run=True) 不报 ImportError 且返回结构化 dict

按 FRAMEWORK.md 规范：mock 外部依赖（PortfolioManager/compute_key_levels/get_quotes），
不发起真实网络请求。
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


# ────────────────────────────────────────────────────────────────
# scan_all：持仓+自选去重扫描
# ────────────────────────────────────────────────────────────────


class TestScanAll:
    """scan_all 扫描持仓+自选股，返回关键点位集合。"""

    @pytest.fixture
    def _fake_pm(self):
        """构造 fake PortfolioManager，返回固定持仓+自选。"""

        class _FakePM:
            def get_positions(self):
                return [
                    {
                        "code": "sh600989",
                        "name": "宝丰能源",
                        "cost": 22.37,
                        "quantity": 2000,
                    },
                ]

            def get_watchlist(self):
                return [
                    {"code": "sz000001", "name": "平安银行"},
                    # 与持仓重复（不应出现两次）
                    {"code": "sh600989", "name": "宝丰能源"},
                ]

        return _FakePM()

    @pytest.fixture
    def _fake_levels(self):
        """fake compute_key_levels 返回结构。"""

        def _impl(code, position=None, watch=None):
            return {
                "code": code,
                "name": "测试",
                "price": 100.0,
                "change_pct": 1.5,
                "levels": {},
                "alerts": [],
                "position": position,
                "watch": watch,
                "error": None,
            }

        return _impl

    def test_scan_returns_positions_plus_watchlist(self, _fake_pm, _fake_levels):
        """持仓 1 只 + 自选 2 只（1 只与持仓重复），应扫描 2 只（去重）。"""
        from monitor import notifier

        with (
            patch.object(notifier, "compute_key_levels", _fake_levels),
            patch("data.get_quotes", return_value=[]),
        ):
            results = notifier.scan_all(pm=_fake_pm)

        assert len(results) == 2
        codes = {r["code"] for r in results}
        assert codes == {"sh600989", "sz000001"}

    def test_scan_dedupes_watchlist_against_positions(self, _fake_pm, _fake_levels):
        """自选股与持仓重复时，只扫描一次（去重）。"""
        from monitor import notifier

        with (
            patch.object(notifier, "compute_key_levels", _fake_levels),
            patch("data.get_quotes", return_value=[]),
        ):
            results = notifier.scan_all(pm=_fake_pm)

        # sh600989 只出现一次（持仓），自选里的重复被跳过
        count_600989 = sum(1 for r in results if r["code"] == "sh600989")
        assert count_600989 == 1

    def test_scan_passes_position_to_compute_key_levels(self, _fake_pm):
        """scan_all 应把持仓 dict 传给 compute_key_levels 的 position 参数。"""
        from monitor import notifier

        captured = []

        def _capture(code, position=None, watch=None):
            captured.append((code, position, watch))
            return {"code": code, "price": 0, "alerts": []}

        with (
            patch.object(notifier, "compute_key_levels", _capture),
            patch("data.get_quotes", return_value=[]),
        ):
            notifier.scan_all(pm=_fake_pm)

        # 持仓股应带 position 参数
        pos_calls = [(c, p) for c, p, w in captured if p is not None]
        assert any(c == "sh600989" for c, _ in pos_calls)

    def test_scan_passes_watch_to_compute_key_levels(self, _fake_pm):
        """scan_all 应把自选 dict 传给 compute_key_levels 的 watch 参数。"""
        from monitor import notifier

        captured = []

        def _capture(code, position=None, watch=None):
            captured.append((code, position, watch))
            return {"code": code, "price": 0, "alerts": []}

        with (
            patch.object(notifier, "compute_key_levels", _capture),
            patch("data.get_quotes", return_value=[]),
        ):
            notifier.scan_all(pm=_fake_pm)

        # 自选股应带 watch 参数
        watch_calls = [(c, w) for c, p, w in captured if w is not None]
        assert any(c == "sz000001" for c, _ in watch_calls)

    def test_scan_result_has_required_fields(self, _fake_pm, _fake_levels):
        """返回结构必须包含 code/price/alerts 字段（check_and_push 依赖）。"""
        from monitor import notifier

        with (
            patch.object(notifier, "compute_key_levels", _fake_levels),
            patch("data.get_quotes", return_value=[]),
        ):
            results = notifier.scan_all(pm=_fake_pm)

        for r in results:
            assert "code" in r
            assert "price" in r
            assert "alerts" in r

    def test_scan_batch_prefetch_failure_is_ignored(self, _fake_pm, _fake_levels):
        """批量预取行情失败时不应中断扫描（逐股降级）。"""
        from monitor import notifier

        with (
            patch.object(notifier, "compute_key_levels", _fake_levels),
            patch("data.get_quotes", side_effect=Exception("网络失败")),
        ):
            results = notifier.scan_all(pm=_fake_pm)

        # 即使预取失败，仍应返回扫描结果
        assert len(results) == 2

    def test_scan_empty_portfolio(self, _fake_levels):
        """持仓和自选都为空时返回空列表。"""

        class _EmptyPM:
            def get_positions(self):
                return []

            def get_watchlist(self):
                return []

        from monitor import notifier

        with (
            patch.object(notifier, "compute_key_levels", _fake_levels),
            patch("data.get_quotes", return_value=[]),
        ):
            results = notifier.scan_all(pm=_EmptyPM())

        assert results == []


# ────────────────────────────────────────────────────────────────
# check_and_push：端到端 dry_run
# ────────────────────────────────────────────────────────────────


class TestCheckAndPush:
    """check_and_push(dry_run=True) 不推送，返回结构化 dict。"""

    def test_dry_run_returns_structured_summary(self):
        """dry_run=True 时返回 scanned/alerts/pushed/details 结构，不报 ImportError。

        check_and_push 内部调用 scan_all（无 pm 参数，用单例），
        故此处 mock notifier.scan_all 直接返回固定结果。
        """
        from monitor import notifier

        fake_results = [
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "price": 23.0,
                "change_pct": 1.5,
                "alerts": [
                    {
                        "type": "price_above_ma5",
                        "message": "现价突破 MA5",
                        "urgent": False,
                    }
                ],
                "position": {"cost": 22.37, "quantity": 2000},
            }
        ]

        with (
            patch.object(notifier, "scan_all", return_value=fake_results),
            patch.object(notifier, "_should_notify_signal", return_value=True),
        ):
            result = notifier.check_and_push(dry_run=True, level="normal")

        assert isinstance(result, dict)
        assert result["scanned"] == 1
        assert result["alerts"] == 1
        assert result["pushed"] == 0  # dry_run 不推送
        assert "details" in result
        assert "timestamp" in result

    def test_dry_run_no_alerts(self):
        """无预警时 alerts=0，details 为空。"""
        from monitor import notifier

        fake_results = [
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "price": 23.0,
                "alerts": [],  # 无预警
            }
        ]

        with patch.object(notifier, "scan_all", return_value=fake_results):
            result = notifier.check_and_push(dry_run=True)

        assert result["scanned"] == 1
        assert result["alerts"] == 0
        assert result["details"] == []

    def test_notifier_import_succeeds(self):
        """import monitor.notifier 不应抛 ImportError（原 scanner 缺失会导致此失败）。"""
        from monitor import notifier

        assert hasattr(notifier, "check_and_push")
        assert hasattr(notifier, "scan_all")

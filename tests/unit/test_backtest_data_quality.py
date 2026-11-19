"""回测入口的数据完整性信封（P0-4b 第三批）。

回测唯一输入是 K 线：拿不到 total_return_pct 或返回 error 视为 kline 域 failed，
此时 conclusions_allowed 必须为 False，下游不得据此给仓位建议。
"""

from __future__ import annotations

import pytest

from backtest.cli import _with_data_quality


class TestBacktestEnvelope:
    def test_ok_when_result_complete(self):
        out = _with_data_quality({"total_return_pct": 12.5, "sharpe": 1.2})
        assert out["data_quality"]["status"] == "ok"
        assert out["data_quality"]["conclusions_allowed"] is True
        assert out["total_return_pct"] == 12.5

    def test_error_result_is_failed(self):
        out = _with_data_quality({"error": "K 线拉取为空"})
        assert out["data_quality"]["status"] == "failed"
        assert out["data_quality"]["missing_domains"] == ["kline"]
        assert out["data_quality"]["conclusions_allowed"] is False
        assert out["error"] == "K 线拉取为空"

    def test_missing_total_return_is_failed(self):
        out = _with_data_quality({"sharpe": None})
        assert out["data_quality"]["status"] == "failed"
        assert out["data_quality"]["conclusions_allowed"] is False

    def test_list_payload_left_untouched(self):
        """多策略对比是裸数组，形状不动（不塞信封）。"""
        rows = [{"strategy": "balanced", "total_return_pct": 3.0}]
        assert _with_data_quality(rows) == rows

    @pytest.mark.parametrize("value", [None, {"total_return_pct": 0.0}])
    def test_boundary_values(self, value):
        out = _with_data_quality(value if isinstance(value, dict) else {})
        assert out["data_quality"]["status"] in ("ok", "failed")

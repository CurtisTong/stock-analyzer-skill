"""WP4 FinanceMeta 单元测试。

验证：
- FinanceMeta dataclass 字段默认值
- get_finance 返回 (records, meta) tuple
- meta 字段填充逻辑（cache_hit/source/actual_periods 等）
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from data.types import FinanceMeta


class TestFinanceMetaDataclass:
    """FinanceMeta dataclass 字段测试。"""

    def test_default_values(self):
        """所有字段默认值应安全。"""
        m = FinanceMeta()
        assert m.source == ""
        assert m.fallback_source == ""
        assert m.requested_periods == 0
        assert m.actual_periods == 0
        assert m.is_periods_truncated is False
        assert m.is_degraded is False
        assert m.degraded_fields == []
        assert m.fetch_time == ""
        assert m.cache_hit is False
        assert m.is_stale is False
        assert m.stale_reason == ""
        assert m.last_error == ""

    def test_to_dict(self):
        """to_dict 输出完整字段。"""
        m = FinanceMeta(
            source="eastmoney",
            fallback_source="akshare_finance",
            requested_periods=8,
            actual_periods=4,
            is_periods_truncated=True,
            is_degraded=True,
            degraded_fields=["eps", "roe"],
            cache_hit=False,
            last_error="timeout",
        )
        d = m.to_dict()
        assert d["source"] == "eastmoney"
        assert d["fallback_source"] == "akshare_finance"
        assert d["requested_periods"] == 8
        assert d["actual_periods"] == 4
        assert d["is_periods_truncated"] is True
        assert d["is_degraded"] is True
        assert d["degraded_fields"] == ["eps", "roe"]
        assert d["last_error"] == "timeout"

    def test_degraded_fields_isolated_between_instances(self):
        """degraded_fields list 必须每个实例独立（default_factory）。"""
        m1 = FinanceMeta()
        m2 = FinanceMeta()
        m1.degraded_fields.append("eps")
        assert m2.degraded_fields == []  # 不被 m1 影响


@contextmanager
def _patch_finance_fetch(return_value):
    """Context manager：临时替换 data._finance_manager.fetch 的返回值。

    注意：_finance_manager 是懒加载，第一次访问前是 None。
    通过 _load_fetchers() 触发懒加载后再 patch。
    """
    import data as data_mod

    # 触发懒加载
    data_mod._load_fetchers()
    real_mgr = data_mod._finance_manager
    assert real_mgr is not None, "_finance_manager 懒加载失败"

    original_fetch = real_mgr.fetch
    real_mgr.fetch = lambda code, **kw: return_value
    try:
        yield
    finally:
        real_mgr.fetch = original_fetch


class TestGetFinanceReturnsTuple:
    """get_finance 返回 tuple 签名验证（mock fetchers 避免真实网络）。"""

    def test_returns_records_and_meta(self):
        """返回 (records, meta) 元组。"""
        from data import get_finance

        with _patch_finance_fetch(
            [
                {
                    "REPORT_DATE": "2024-12-31",
                    "EPSJB": "1.5",
                    "ROEJQ": "15.0",
                    "TOTALOPERATEREVETZ": "20.0",
                    "source": "eastmoney",
                }
            ]
        ):
            records, meta = get_finance("SH600989", use_cache=False, periods=4)
        assert isinstance(records, list)
        assert len(records) == 1
        assert isinstance(meta, FinanceMeta)
        assert meta.actual_periods == 1
        assert meta.requested_periods == 4
        assert meta.source == "eastmoney"
        assert meta.cache_hit is False
        assert meta.is_periods_truncated is True

    def test_empty_result_marks_degraded(self):
        """空结果 → meta.is_degraded=True。"""
        from data import get_finance

        with _patch_finance_fetch(None):
            records, meta = get_finance("SH600989", use_cache=False)
        assert records == []
        assert meta.is_degraded is True
        assert meta.actual_periods == 0

    def test_truncation_flag_set_when_actual_less_than_requested(self):
        """实际期数 < 请求期数 → is_periods_truncated=True。"""
        from data import get_finance

        with _patch_finance_fetch(
            [{"EPSJB": "1.0", "ROEJQ": "10.0", "source": "eastmoney"}] * 3
        ):
            records, meta = get_finance("SH600989", use_cache=False, periods=8)
        assert meta.actual_periods == 3
        assert meta.requested_periods == 8
        assert meta.is_periods_truncated is True

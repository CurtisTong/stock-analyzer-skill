"""common/formatters.py 的 format_footer 单元测试。

覆盖 L1：degraded 参数下 footer 加 ⚠️ emoji 警示。
"""

from __future__ import annotations

from common.formatters import format_footer


class TestFormatFooter:
    """format_footer 数据护栏条渲染。"""

    def test_basic_footer(self):
        """基本调用：数据时间戳 + 数据源 + TTL。"""
        result = format_footer(
            data_time="2026-08-07 10:30",
            sources=["行情", "财务"],
            ttl_sec=900,
        )
        assert "数据时间戳: 2026-08-07 10:30" in result
        assert "数据源: 行情, 财务" in result
        assert "数据 TTL: 900s" in result
        # 默认无 degraded，前缀是 📊
        assert "📊" in result
        assert "⚠️" not in result

    def test_failed_sources_shows_warning(self):
        """有 failed_sources 时显示 ⚠️ 失败源。"""
        result = format_footer(
            data_time="2026-08-07 10:30",
            sources=["行情"],
            failed_sources=["财务"],
        )
        assert "⚠️ 失败源: 财务" in result

    def test_degraded_prefix_overrides_normal(self):
        """degraded=True 时 footer 头部用 ⚠️ 数据降级 而非 📊。"""
        result = format_footer(
            data_time="2026-08-07 10:30",
            sources=["行情"],
            failed_sources=["财务"],
            degraded=True,
        )
        assert "⚠️ 数据降级 | " in result
        # 📊 在 degraded 模式下不出现（被 ⚠️ 取代）
        assert "📊" not in result

    def test_degraded_without_failed_sources(self):
        """degraded=True 但无 failed_sources（仅 data_warnings 触发）。"""
        result = format_footer(
            data_time="2026-08-07 10:30",
            sources=["行情"],
            degraded=True,
        )
        assert "⚠️ 数据降级 | " in result
        assert "📊" not in result

    def test_empty_inputs(self):
        """全部参数为空时返回空字符串。"""
        assert format_footer() == ""

    def test_only_data_time(self):
        """仅传 data_time。"""
        result = format_footer(data_time="2026-08-07 10:30")
        assert "数据时间戳: 2026-08-07 10:30" in result
        assert "数据源" not in result

    def test_no_data_time(self):
        """无 data_time 但有其他字段。"""
        result = format_footer(sources=["行情"])
        assert "数据源: 行情" in result
        assert "数据时间戳" not in result
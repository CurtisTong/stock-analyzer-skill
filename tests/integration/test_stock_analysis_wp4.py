"""回归测试：stock_analysis.analyze() 在 WP4 get_finance tuple 化后仍正常工作。

背景：
- WP4 (90b44e4) 把 get_finance 改为返回 (records, FinanceMeta) tuple
- stock_analysis._analyze 在 138 行直接调 f_finance.result() 拿 tuple
- 早期漏改 → AttributeError: 'list' object has no attribute 'to_dict'
- 由 /research SZ002920 full 调用栈暴露并修复（commit e0a3ea2）

此测试防止未来再次出现：
- 单测批量测试（helpers/engine）已正确解构，未触发本测试路径
- 但 research/CLI 路径走 business.stock_analysis.analyze，需要专项测试
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from business.stock_analysis import analyze
from data.types import FinanceMeta, FinanceRecord


def _make_fake_records(n=4):
    """构造 n 期 FinanceRecord（递增数据）。"""
    return [
        FinanceRecord(
            report_date=f"2025-{(3 - i) * 3 + 9:02d}-30" if i < 4 else "2024-12-31",
            eps=1.0 + i * 0.5,
            roe=10.0 + i,
            revenue_yoy=15.0,
            net_profit_yoy=20.0,
            gross_margin=20.0,
            net_margin=8.0,
            debt_ratio=50.0,
            bps=10.0,
            ocf_per_share=1.5,
            total_revenue=100.0 + i * 50,
            parent_net_profit=8.0 + i * 2,
            deducted_net_profit=7.0 + i * 2,
            total_liability=100.0,
            total_assets=200.0,
            net_assets=100.0,
            quick_ratio=1.5,
            current_ratio=2.0,
        )
        for i in range(n)
    ]


@contextmanager
def _patch_data_fetchers(fake_records):
    """mock 整个数据获取链路，避免真实网络请求。

    策略：
    - mock get_quote → fake Quote (limited fields)
    - mock get_kline → fake kline list
    - mock get_finance → (records, FinanceMeta) tuple
    """
    from datetime import date

    from common import normalize_quote_code, normalize_finance_code
    from data.types import KlineBar, Quote

    # 构造 fake Quote
    fake_quote = Quote(
        code=normalize_quote_code("SH600000"),
        name="测试股票",
        price=10.0,
        prev_close=9.8,
        change_pct=2.0,
        pe=15.0,
        pb=3.0,
        total_cap=100.0,
        source="fake",
        fetch_time="2026-07-21T18:00:00",
    )

    # 构造 fake kline（35 根满足 _MIN_KLINE_DAYS=30）
    fake_kline = [
        KlineBar(
            day=(date(2026, 6, 1).replace(day=1)).strftime("%Y-%m-%d"),
            open=10.0 + i * 0.1,
            high=10.2 + i * 0.1,
            low=9.8 + i * 0.1,
            close=10.1 + i * 0.1,
            volume=1000,
            source="fake",
            fetch_time="2026-07-21T18:00:00",
        )
        for i in range(35)
    ]

    # 构造 fake FinanceMeta
    fake_meta = FinanceMeta(
        source="fake",
        requested_periods=len(fake_records),
        actual_periods=len(fake_records),
        fetch_time="2026-07-21T18:00:00",
        cache_hit=False,
    )

    with (
        patch("business.stock_analysis.get_quote", return_value=fake_quote),
        patch("business.stock_analysis.get_kline", return_value=fake_kline),
        patch(
            "business.stock_analysis.get_finance",
            return_value=(fake_records, fake_meta),
        ),
    ):
        yield


class TestStockAnalysisAnalyzeWP4:
    """回归测试 stock_analysis.analyze 在 WP4 tuple 改造后正常返回。"""

    def test_analyze_returns_full_result_with_finance(self):
        """analyze 必须能正确处理 get_finance 的 (records, meta) tuple。"""
        records = _make_fake_records(4)

        with _patch_data_fetchers(records):
            result = analyze("SH600000", finance_periods=4)

        # 顶层基础字段
        assert result["code"] == "sh600000"
        assert "财务" in result.get("data_sources", [])
        assert result.get("data_failed", []) == []
        assert not result.get("data_warnings", [])

        # 财务摘要字段（WP2 关键：roe/eps 实际是 float）
        finance = result.get("finance", {})
        assert finance["eps"] == 1.0  # records[0].eps = 1.0 + 0*0.5
        assert finance["roe"] == 10.0
        assert finance["revenue_yoy"] == 15.0
        assert finance["net_profit_yoy"] == 20.0

    def test_analyze_handles_empty_finance_records(self):
        """空 records（meta 也无数据）时不崩。"""
        with _patch_data_fetchers([]):
            result = analyze("SH600000", include_finance=True, finance_periods=4)
        # 空 records 不应触发 finance 字段填充（避免空 dict）
        # 由 if finance 守卫
        assert "finance" not in result or result.get("finance") == {}

    def test_finance_summary_extracts_first_record(self):
        """确保 finance[0] 正确取第一期（而不是元组整个当作 list）。"""
        records = _make_fake_records(2)
        # records[0] 是最新期（i=0），records[1] 是次新期（i=1）
        records[0].eps = 1.0
        records[1].eps = 99.99  # 次新期特殊值（不应被取）

        with _patch_data_fetchers(records):
            result = analyze("SH600000", finance_periods=2)

        # 必须取 records[0] 而不是 records[1]
        finance = result.get("finance", {})
        assert finance["eps"] == 1.0
        assert finance["eps"] != 99.99

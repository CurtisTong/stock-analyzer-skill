"""WP6 finance_freshness 板块识别 + 差异化 deadline 单元测试。

验证：
- _board_for_code: 股票代码前缀 → 板块名
- _periods_for_board: 板块覆盖默认 periods
- check_finance_freshness: 带 code 参数正常工作
"""

from datetime import date

import pytest

from business.finance_freshness import (
    _board_for_code,
    _periods_for_board,
    check_finance_freshness,
)


class TestBoardForCode:
    """_board_for_code 单元测试。"""

    def test_shanghai_main_board(self):
        assert _board_for_code("SH600000") == "SH6"
        assert _board_for_code("SH601318") == "SH6"

    def test_shanghai_star_market(self):
        assert _board_for_code("SH688001") == "SH8"
        assert (
            _board_for_code("SH689009") == "SH8"
        )  # SH9 实际归到 SH8（688/689 都是科创板）

    def test_shenzhen_main_board(self):
        assert _board_for_code("SZ000001") == "SZ0"
        assert _board_for_code("SZ000807") == "SZ0"

    def test_shenzhen_chinext(self):
        assert _board_for_code("SZ300750") == "SZ3"
        assert _board_for_code("SZ301236") == "SZ3"

    def test_beijing_exchange(self):
        # WP6: BJ4/BJ8 都映射到统一的 "BJ8" 分组（北交所内部不细分）
        assert _board_for_code("BJ830799") == "BJ8"
        assert _board_for_code("BJ430047") == "BJ8"

    def test_case_insensitive(self):
        assert _board_for_code("sh600000") == "SH6"
        assert _board_for_code("sz000001") == "SZ0"

    def test_unknown_returns_default(self):
        assert _board_for_code("US:^GSPC") == "default"
        assert _board_for_code("") == "default"
        assert _board_for_code("XX999999") == "default"


class TestPeriodsForBoard:
    """_periods_for_board 合并逻辑测试。"""

    def test_no_override_returns_base(self):
        """无覆盖项时返回原 periods。"""
        base = {"Q1": {"report_end": "03-31", "deadline": "04-30"}}
        result = _periods_for_board("SH6", base)
        assert result == base

    def test_override_partial(self):
        """覆盖项只覆盖部分 pname。"""
        base = {
            "Q1": {"report_end": "03-31", "deadline": "04-30"},
            "full_year": {"report_end": "12-31", "deadline": "04-30"},
        }
        # 配置中 SH8 覆盖 full_year
        from business.finance_freshness import _load_disclosure_config

        cfg = _load_disclosure_config()
        cfg.setdefault("board_overrides", {})["SH8"] = {
            "full_year": {"deadline": "04-15"}  # 北交所年报提前
        }
        # 注：直接改 cfg 在测试范围内影响全局，但仅测试期间有效
        try:
            result = _periods_for_board("SH8", base)
            assert result["Q1"] == {"report_end": "03-31", "deadline": "04-30"}  # 不变
            assert result["full_year"]["deadline"] == "04-15"  # 覆盖
            assert result["full_year"]["report_end"] == "12-31"  # 保留
        finally:
            # 清理
            cfg["board_overrides"].pop("SH8", None)


class TestCheckFreshness:
    """check_finance_freshness 集成测试。"""

    def test_no_report_date_returns_not_stale(self):
        """无 report_date → 不判定（容错）。"""
        is_stale, msg = check_finance_freshness({}, today=date(2026, 5, 15))
        assert is_stale is False
        assert msg == ""

    def test_recent_data_not_stale(self):
        """最近报告期数据未过期。

        选 today = 2026-02-01 + report_date = 2025-12-31 → 应已披露 Q3 (09-30)
        但 fin 是年报 12-31（最新），所以 is_stale=True。
        正确的不 stale 场景：today = 2025-04-15 + report_date = 2025-03-31 (Q1)
        → Q1 截止日是 4/30 + grace=7 = 5/7，4/15 未到截止日，不 stale。
        """
        fin = {"report_date": "2025-03-31"}  # Q1
        is_stale, msg = check_finance_freshness(fin, today=date(2025, 4, 15))
        assert is_stale is False

    def test_old_data_after_deadline_is_stale(self):
        """旧报告期数据过截止日 → 过期。

        fin 持有 Q1 (2025-03-31)，today=2026-01-15，已过 Q3 deadline (10/31) + grace。
        fin 的 report_date=2025-03-31 < expected_end_date=2025-09-30 → stale。
        """
        fin = {"report_date": "2025-03-31"}  # Q1 2025
        is_stale, msg = check_finance_freshness(fin, today=date(2026, 1, 15))
        assert is_stale is True
        assert "过期" in msg
        assert "09-30" in msg  # 提示应已披露至 Q3

    def test_code_param_does_not_affect_when_no_override(self):
        """未配置 board_overrides 时，code 参数不影响结果。"""
        fin = {"report_date": "2025-09-30"}
        is_stale_main, _ = check_finance_freshness(
            fin, today=date(2026, 1, 15), code="SH600000"
        )
        is_stale_star, _ = check_finance_freshness(
            fin, today=date(2026, 1, 15), code="SH688001"
        )
        # 默认配置下主板和科创板判定一致
        assert is_stale_main == is_stale_star

    def test_auto_infer_code_from_fin(self):
        """未传 code 时，从 fin dict 推断 code → 板块提示注入。

        fin report_date=Q1 2025 + today=2026-01-15 → 应已披露 Q3 (09-30)
        → fin 陈旧，stale=True。
        """
        fin = {"report_date": "2025-03-31", "code": "SH688001"}
        is_stale, msg = check_finance_freshness(fin, today=date(2026, 1, 15))
        assert is_stale is True
        # 科创板 (SH688001) → 板块提示 SH8
        assert "(board=SH8)" in msg

    def test_invalid_report_date_format(self):
        """report_date 格式错误 → 不判定。"""
        fin = {"report_date": "not-a-date"}
        is_stale, msg = check_finance_freshness(fin, today=date(2026, 5, 15))
        assert is_stale is False
        assert msg == ""

"""WP3 FinanceRecord 有效性判定单元测试。

验证 _is_valid_records 多字段判定逻辑：
- 微利股（eps=0.01）不被误判为"无效"
- 盈亏平衡股（eps=0 / roe=0 / 但 gross_margin=30）不被误判
- 真无数据股（5 字段全 None）正确判无效
- 单字段非零即有效
"""

import pytest

from data import _is_valid_records
from data.types import FinanceRecord


def _make_record(**kwargs) -> FinanceRecord:
    """构造默认全 None 的 FinanceRecord，再覆盖指定字段。"""
    defaults = {
        "eps": None,
        "roe": None,
        "revenue_yoy": None,
        "net_profit_yoy": None,
        "gross_margin": None,
    }
    defaults.update(kwargs)
    return FinanceRecord(**defaults)


class TestIsValidRecords:
    """_is_valid_records 单元测试。"""

    def test_micro_profit_stock_not_misjudged(self):
        """微利股 eps=0.01 不被误判为无效（WP3 修复点）。

        旧逻辑: all(eps==0 and roe==0) → True（误判）
        新逻辑: 至少 1 字段非 None 且非 0 → 视为有效
        """
        records = [_make_record(eps=0.01)]
        assert _is_valid_records(records) is True

    def test_break_even_stock_not_misjudged(self):
        """盈亏平衡股 eps=0 但 gross_margin=30 → 视为有效。"""
        records = [_make_record(eps=0.0, roe=0.0, gross_margin=30.0)]
        assert _is_valid_records(records) is True

    def test_revenue_growth_only(self):
        """营收有数据但利润全 None（亏损股早期）→ 视为有效。"""
        records = [_make_record(revenue_yoy=15.5)]
        assert _is_valid_records(records) is True

    def test_truly_empty_data(self):
        """5 字段全 None → 视为无效。"""
        records = [_make_record()]
        assert _is_valid_records(records) is False

    def test_zero_everywhere(self):
        """5 字段全 0.0（旧字段默认值）→ 视为无效。"""
        records = [
            _make_record(
                eps=0.0, roe=0.0, revenue_yoy=0.0, net_profit_yoy=0.0, gross_margin=0.0
            )
        ]
        assert _is_valid_records(records) is False

    def test_multi_records_one_valid(self):
        """多期记录中只要有一期有效 → 整体有效。"""
        records = [
            _make_record(),  # 第一期无效
            _make_record(roe=15.5),  # 第二期有效
        ]
        assert _is_valid_records(records) is True

    def test_empty_list(self):
        """空列表 → 无效（无数据可判定）。"""
        assert _is_valid_records([]) is False

    def test_field_with_zero_valid_if_another_field_nonzero(self):
        """某字段为 0 但另一字段非 0 → 有效。"""
        records = [_make_record(eps=0.0, net_profit_yoy=-5.0)]
        assert _is_valid_records(records) is True

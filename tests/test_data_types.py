"""data/types.py 单元测试：数据类型定义与序列化。"""

import pytest
from data.types import (
    Quote,
    KlineBar,
    FinanceRecord,
    MarginData,
    HolderData,
    TopHolderRecord,
)


class TestQuote:
    """Quote 数据类型测试。"""

    def test_default_values(self):
        q = Quote()
        assert q.code == ""
        assert q.price == 0.0
        assert q.volume == 0

    def test_has_basic_data_true(self):
        q = Quote(price=18.5)
        assert q.has_basic_data() is True

    def test_has_basic_data_false(self):
        q = Quote(price=0.0)
        assert q.has_basic_data() is False

    def test_to_dict(self):
        q = Quote(code="sh600989", name="宝丰能源", price=18.5)
        d = q.to_dict()
        assert d["code"] == "sh600989"
        assert d["name"] == "宝丰能源"
        assert d["price"] == 18.5
        assert isinstance(d, dict)

    def test_custom_values(self):
        q = Quote(
            code="sz000807",
            name="云铝股份",
            price=15.0,
            change_pct=2.5,
            turnover=3.14,
            pe=12.5,
            source="tencent",
        )
        assert q.code == "sz000807"
        assert q.change_pct == 2.5
        assert q.source == "tencent"


class TestKlineBar:
    """KlineBar 数据类型测试。"""

    def test_default_values(self):
        bar = KlineBar()
        assert bar.day == ""
        assert bar.close == 0.0

    def test_to_dict(self):
        bar = KlineBar(day="2025-06-20", open=18.0, high=19.0, low=17.5, close=18.5)
        d = bar.to_dict()
        assert d["day"] == "2025-06-20"
        assert d["high"] == 19.0

    def test_with_volume_and_amount(self):
        bar = KlineBar(volume=1000000, amount=18500000.0, pct_chg=1.5)
        assert bar.volume == 1000000
        assert bar.pct_chg == 1.5


class TestFinanceRecord:
    """FinanceRecord 数据类型测试。"""

    def test_default_values(self):
        fr = FinanceRecord()
        assert fr.report_date == ""
        assert fr.eps == 0.0
        assert fr.roe == 0.0

    def test_to_dict(self):
        fr = FinanceRecord(
            report_date="2025-03-31",
            eps=0.5,
            roe=15.2,
            debt_ratio=45.0,
        )
        d = fr.to_dict()
        assert d["report_date"] == "2025-03-31"
        assert d["eps"] == 0.5

    def test_extended_fields(self):
        fr = FinanceRecord(
            goodwill=5.0,
            pledge_ratio=10.0,
            consecutive_dividend_years=5,
            dividend_yield=3.5,
        )
        assert fr.goodwill == 5.0
        assert fr.consecutive_dividend_years == 5


class TestMarginData:
    """MarginData 数据类型测试。"""

    def test_to_dict(self):
        md = MarginData(date="2025-06-20", code="600989", rzye=1e9, rqye=5e6)
        d = md.to_dict()
        assert d["date"] == "2025-06-20"
        assert d["rzye"] == 1e9


class TestHolderData:
    """HolderData 数据类型测试。"""

    def test_to_dict(self):
        hd = HolderData(
            end_date="2025-03-31",
            code="600989",
            holder_num=50000,
            concentration="集中",
        )
        d = hd.to_dict()
        assert d["holder_num"] == 50000
        assert d["concentration"] == "集中"


class TestTopHolderRecord:
    """TopHolderRecord 数据类型测试。"""

    def test_to_dict(self):
        thr = TopHolderRecord(
            end_date="2025-03-31",
            rank=1,
            holder_name="中国证券金融股份有限公司",
            is_institution=True,
        )
        d = thr.to_dict()
        assert d["rank"] == 1
        assert d["is_institution"] is True

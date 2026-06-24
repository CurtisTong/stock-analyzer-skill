"""股票池刷新模块测试（纯函数，无网络调用）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from refresh_pool import (
    _classify_board,
    _infer_exchange,
    passes_filter,
    sort_stocks,
    build_sector_pool,
)


class TestClassifyBoard:
    """_classify_board 函数测试。"""

    def test_kcb(self):
        """科创板 688xxx。"""
        assert _classify_board("688001") == "科创板"

    def test_cyb(self):
        """创业板 300xxx/301xxx。"""
        assert _classify_board("300001") == "创业板"
        assert _classify_board("301001") == "创业板"

    def test_main_board_sh(self):
        """沪市主板 60xxxx。"""
        assert _classify_board("600001") == "主板"

    def test_main_board_sz(self):
        """深市主板 00xxxx。"""
        assert _classify_board("000001") == "主板"

    def test_bse(self):
        """北交所 43/83/87/88/92 开头。"""
        assert _classify_board("430001") == "北交所"
        assert _classify_board("830001") == "北交所"
        assert _classify_board("870001") == "北交所"
        assert _classify_board("880001") == "北交所"
        assert _classify_board("920001") == "北交所"

    def test_other(self):
        """其他代码。"""
        assert _classify_board("123456") == "其他"


class TestInferExchange:
    """_infer_exchange 函数测试。"""

    def test_sh(self):
        """沪市 60/68 开头。"""
        assert _infer_exchange("600001") == "sh"
        assert _infer_exchange("688001") == "sh"

    def test_sz(self):
        """深市 00/30 开头。"""
        assert _infer_exchange("000001") == "sz"
        assert _infer_exchange("300001") == "sz"

    def test_bj(self):
        """北交所 43/83/87/88/92 开头。"""
        assert _infer_exchange("430001") == "bj"
        assert _infer_exchange("830001") == "bj"


class TestPassesFilter:
    """passes_filter 函数测试。"""

    def test_pass_normal_stock(self):
        """正常股票通过过滤。"""
        stock = {
            "code": "sh600001",
            "name": "测试股票",
            "amount": 100_000_000,  # 1 亿元
            "cap": 10_000_000_000,  # 100 亿元
        }
        ok, reason = passes_filter(stock)
        assert ok is True
        assert reason == ""

    def test_reject_st(self):
        """ST 股票被过滤。"""
        stock = {"code": "sh600001", "name": "ST 测试"}
        ok, reason = passes_filter(stock)
        assert ok is False
        assert "ST" in reason

    def test_reject_low_amount(self):
        """成交额过低被过滤。"""
        stock = {
            "code": "sh600001",
            "name": "测试股票",
            "amount": 1_000_000,  # 100 万元
            "cap": 10_000_000_000,
        }
        ok, reason = passes_filter(stock)
        assert ok is False
        assert "成交额" in reason

    def test_reject_low_cap(self):
        """市值过低被过滤。"""
        stock = {
            "code": "sh600001",
            "name": "测试股票",
            "amount": 100_000_000,
            "cap": 1_000_000_000,  # 10 亿元
        }
        ok, reason = passes_filter(stock)
        assert ok is False
        assert "市值" in reason

    def test_pass_kcb_lower_threshold(self):
        """科创板门槛较低（成交额 3000 万，市值 20 亿）。"""
        stock = {
            "code": "sh688001",
            "name": "科创板股票",
            "amount": 50_000_000,  # 5000 万元
            "cap": 3_000_000_000,  # 30 亿元
        }
        ok, reason = passes_filter(stock)
        assert ok is True

    def test_missing_fields_pass(self):
        """字段缺失时不触发过滤。"""
        stock = {"code": "sh600001", "name": "测试股票"}
        ok, reason = passes_filter(stock)
        assert ok is True


class TestSortStocks:
    """sort_stocks 函数测试。"""

    def test_sort_by_amount(self):
        """按成交额排序。"""
        stocks = [
            {"code": "a", "amount": 100},
            {"code": "b", "amount": 300},
            {"code": "c", "amount": 200},
        ]
        result = sort_stocks(stocks, "amount")
        assert [s["code"] for s in result] == ["b", "c", "a"]

    def test_sort_by_cap(self):
        """按市值排序。"""
        stocks = [
            {"code": "a", "cap": 100},
            {"code": "b", "cap": 300},
            {"code": "c", "cap": 200},
        ]
        result = sort_stocks(stocks, "cap")
        assert [s["code"] for s in result] == ["b", "c", "a"]

    def test_sort_by_pe_descending(self):
        """按 PE 排序（降序，高 PE 在前）。"""
        stocks = [
            {"code": "a", "pe": 30},
            {"code": "b", "pe": 10},
            {"code": "c", "pe": 20},
        ]
        result = sort_stocks(stocks, "pe")
        assert [s["code"] for s in result] == ["a", "c", "b"]

    def test_sort_by_turnover(self):
        """按换手率排序。"""
        stocks = [
            {"code": "a", "turnover": 1.0},
            {"code": "b", "turnover": 3.0},
            {"code": "c", "turnover": 2.0},
        ]
        result = sort_stocks(stocks, "turnover")
        assert [s["code"] for s in result] == ["b", "c", "a"]

    def test_missing_field_defaults_zero(self):
        """缺失字段默认为 0。"""
        stocks = [
            {"code": "a", "amount": 100},
            {"code": "b"},  # 缺失 amount
        ]
        result = sort_stocks(stocks, "amount")
        assert result[0]["code"] == "a"


class TestBuildSectorPool:
    """build_sector_pool 函数测试。"""

    def test_basic_build(self):
        """基本构建。"""
        stocks = [
            {
                "code": "sh600001",
                "name": "股票1",
                "amount": 100_000_000,
                "cap": 10_000_000_000,
            },
            {
                "code": "sh600002",
                "name": "股票2",
                "amount": 200_000_000,
                "cap": 20_000_000_000,
            },
            {
                "code": "sh600003",
                "name": "股票3",
                "amount": 300_000_000,
                "cap": 30_000_000_000,
            },
        ]
        result = build_sector_pool(stocks, top_n=2)
        assert len(result) == 2
        assert result[0] == "sh600003"  # 最高成交额

    def test_filter_st(self):
        """ST 股票被过滤。"""
        stocks = [
            {
                "code": "sh600001",
                "name": "正常股票",
                "amount": 100_000_000,
                "cap": 10_000_000_000,
            },
            {
                "code": "sh600002",
                "name": "ST 股票",
                "amount": 200_000_000,
                "cap": 20_000_000_000,
            },
        ]
        result = build_sector_pool(stocks, top_n=10)
        assert len(result) == 1
        assert result[0] == "sh600001"

    def test_sort_by_cap(self):
        """按市值排序。"""
        stocks = [
            {
                "code": "sh600001",
                "name": "小盘",
                "amount": 100_000_000,
                "cap": 10_000_000_000,
            },
            {
                "code": "sh600002",
                "name": "大盘",
                "amount": 100_000_000,
                "cap": 100_000_000_000,
            },
        ]
        result = build_sector_pool(stocks, top_n=10, sort_by="cap")
        assert result[0] == "sh600002"

    def test_empty_stocks(self):
        """空列表返回空结果。"""
        result = build_sector_pool([], top_n=10)
        assert result == []

    def test_all_filtered(self):
        """全部被过滤时返回空结果。"""
        stocks = [
            {
                "code": "sh600001",
                "name": "ST 股票",
                "amount": 100_000_000,
                "cap": 10_000_000_000,
            },
        ]
        result = build_sector_pool(stocks, top_n=10)
        assert result == []

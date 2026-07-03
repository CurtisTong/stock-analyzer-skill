"""data/pool.py 核心纯函数与解析函数测试（无真实网络调用）。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from data.pool import (
    build_dividend_pool,
    build_sector_pool,
    fetch_board_stocks,
    is_st,
    passes_filter,
    sort_stocks,
)


# ---------- is_st ----------


class TestIsSt:
    """is_st 函数测试。"""

    def test_normal_name(self):
        assert is_st("贵州茅台") is False

    def test_st_prefix(self):
        assert is_st("ST 辅仁") is True

    def test_star_st(self):
        assert is_st("*ST 康美") is True

    def test_st_in_middle(self):
        assert is_st("某ST股") is True

    def test_lowercase_st(self):
        assert is_st("st 某股") is True

    def test_empty_string(self):
        assert is_st("") is False


# ---------- passes_filter ----------


class TestPassesFilter:
    """passes_filter 函数测试。"""

    def test_pass_normal_stock(self):
        stock = {
            "code": "sh600519",
            "name": "贵州茅台",
            "amount": 500_000_000,  # 5 亿元
            "cap": 200_000_000_000,  # 2000 亿元
        }
        ok, reason = passes_filter(stock)
        assert ok is True
        assert reason == ""

    def test_reject_st(self):
        stock = {"code": "sh600519", "name": "ST 茅台", "amount": 999, "cap": 999}
        ok, reason = passes_filter(stock)
        assert ok is False
        assert "ST" in reason

    def test_reject_low_amount_main_board(self):
        # 主板门槛 5000 万元
        stock = {
            "code": "sh600001",
            "name": "普通股",
            "amount": 30_000_000,  # 3000 万元 < 5000 万
            "cap": 100_000_000_000,
        }
        ok, reason = passes_filter(stock)
        assert ok is False
        assert "成交额" in reason

    def test_reject_low_cap_main_board(self):
        # 主板门槛 40 亿元
        stock = {
            "code": "sh600001",
            "name": "普通股",
            "amount": 100_000_000,
            "cap": 3_000_000_000,  # 30 亿 < 40 亿
        }
        ok, reason = passes_filter(stock)
        assert ok is False
        assert "市值" in reason

    def test_kcb_lower_threshold(self):
        # 科创板门槛：成交额 3000 万，市值 20 亿
        stock = {
            "code": "sh688001",
            "name": "科创板股",
            "amount": 35_000_000,  # 3500 万 > 3000 万
            "cap": 2_500_000_000,  # 25 亿 > 20 亿
        }
        ok, reason = passes_filter(stock)
        assert ok is True

    def test_bse_lowest_threshold(self):
        # 北交所门槛：成交额 1000 万，市值 10 亿
        stock = {
            "code": "bj430001",
            "name": "北交所股",
            "amount": 12_000_000,  # 1200 万 > 1000 万
            "cap": 1_200_000_000,  # 12 亿 > 10 亿
        }
        ok, reason = passes_filter(stock)
        assert ok is True

    def test_missing_amount_passes(self):
        stock = {"code": "sh600001", "name": "普通股", "cap": 100_000_000_000}
        ok, reason = passes_filter(stock)
        assert ok is True

    def test_missing_cap_passes(self):
        stock = {"code": "sh600001", "name": "普通股", "amount": 100_000_000}
        ok, reason = passes_filter(stock)
        assert ok is True

    def test_none_amount_passes(self):
        stock = {
            "code": "sh600001",
            "name": "普通股",
            "amount": None,
            "cap": 100_000_000_000,
        }
        ok, reason = passes_filter(stock)
        assert ok is True


# ---------- sort_stocks ----------


class TestSortStocks:
    """sort_stocks 函数测试。"""

    def test_sort_by_amount_desc(self):
        stocks = [
            {"code": "a", "amount": 100},
            {"code": "b", "amount": 300},
            {"code": "c", "amount": 200},
        ]
        result = sort_stocks(stocks, "amount")
        assert [s["code"] for s in result] == ["b", "c", "a"]

    def test_sort_none_value_treated_as_zero(self):
        stocks = [
            {"code": "a", "amount": 100},
            {"code": "b", "amount": None},
        ]
        result = sort_stocks(stocks, "amount")
        assert result[0]["code"] == "a"


# ---------- build_sector_pool ----------


class TestBuildSectorPool:
    """build_sector_pool 函数测试。"""

    def test_top_n(self):
        stocks = [
            {"code": "a", "name": "股A", "amount": 100_000_000, "cap": 50_000_000_000},
            {"code": "b", "name": "股B", "amount": 200_000_000, "cap": 50_000_000_000},
            {"code": "c", "name": "股C", "amount": 300_000_000, "cap": 50_000_000_000},
        ]
        result = build_sector_pool(stocks, top_n=2)
        assert len(result) == 2
        assert result[0] == "c"  # 最高成交额

    def test_filters_st(self):
        stocks = [
            {"code": "a", "name": "正常", "amount": 100_000_000, "cap": 50_000_000_000},
            {"code": "b", "name": "ST 股", "amount": 999_000_000, "cap": 999_000_000_000},
        ]
        result = build_sector_pool(stocks, top_n=10)
        assert result == ["a"]


# ---------- build_dividend_pool ----------


class TestBuildDividendPool:
    """build_dividend_pool 函数测试。"""

    def test_pe_filter(self):
        all_pools = {"消费": ["sh600001", "sh600002"], "科技": ["sh600003"]}
        code_to_stock = {
            "sh600001": {"code": "sh600001", "pe": 15, "amount": 200_000_000},
            "sh600002": {"code": "sh600002", "pe": 25, "amount": 100_000_000},
            "sh600003": {"code": "sh600003", "pe": 10, "amount": 300_000_000},
        }
        result = build_dividend_pool(all_pools, code_to_stock)
        # pe < 20 的有 sh600001(15) 和 sh600003(10)，按 amount 降序
        assert result == ["sh600003", "sh600001"]

    def test_top_20_limit(self):
        all_pools = {"板块": [f"sh60000{i}" for i in range(30)]}
        code_to_stock = {
            f"sh60000{i}": {"code": f"sh60000{i}", "pe": 10, "amount": 100_000_000}
            for i in range(30)
        }
        result = build_dividend_pool(all_pools, code_to_stock)
        assert len(result) == 20


# ---------- fetch_board_stocks (mock) ----------


class TestFetchBoardStocks:
    """fetch_board_stocks 函数测试（mock common.http_get_cached）。

    data/pool.py 通过 _get_common_deps() 延迟导入 common.http_get_cached，
    因此 patch 目标为 common.http_get_cached（真实来源）。
    """

    @patch("common.http_get_cached")
    def test_parse_normal_response(self, mock_http):
        raw = json.dumps(
            {
                "data": {
                    "diff": [
                        {
                            "f12": "600519",
                            "f14": "贵州茅台",
                            "f2": 1800.0,
                            "f3": 2.5,
                            "f6": 500_000_000,
                            "f8": 0.3,
                            "f9": 30.0,
                            "f20": 200_000_000_000,
                        },
                        {
                            "f12": "000001",
                            "f14": "平安银行",
                            "f2": 12.0,
                            "f3": -0.5,
                            "f6": 300_000_000,
                            "f8": 0.8,
                            "f9": 5.0,
                            "f20": 50_000_000_000,
                        },
                    ]
                }
            }
        )
        mock_http.return_value = raw

        result = fetch_board_stocks("BK0475")
        assert len(result) == 2
        assert result[0]["code"] == "sh600519"
        assert result[0]["name"] == "贵州茅台"
        assert result[0]["price"] == 1800.0
        assert result[0]["change_pct"] == 2.5
        assert result[0]["amount"] == 500_000_000
        assert result[0]["pe"] == 30.0
        assert result[0]["cap"] == 200_000_000_000
        assert result[1]["code"] == "sz000001"

    @patch("common.http_get_cached")
    def test_empty_response(self, mock_http):
        mock_http.return_value = json.dumps({"data": None})
        result = fetch_board_stocks("BK0001")
        assert result == []

    @patch("common.http_get_cached")
    def test_skips_invalid_code(self, mock_http):
        raw = json.dumps(
            {
                "data": {
                    "diff": [
                        {"f12": "123", "f14": "短代码"},  # len != 6
                        {"f12": "", "f14": "空代码"},
                        {"f12": "600519", "f14": "正常", "f6": 0},
                    ]
                }
            }
        )
        mock_http.return_value = raw
        result = fetch_board_stocks("BK0475")
        assert len(result) == 1
        assert result[0]["code"] == "sh600519"

    @patch("common.http_get_cached")
    def test_retry_on_failure(self, mock_http):
        mock_http.side_effect = [
            ConnectionError("timeout"),
            json.dumps({"data": {"diff": [{"f12": "600519", "f14": "茅台", "f6": 0}]}}),
        ]
        result = fetch_board_stocks("BK0475", max_retries=2)
        assert len(result) == 1
        assert mock_http.call_count == 2

    @patch("common.http_get_cached")
    def test_all_retries_exhausted(self, mock_http):
        mock_http.side_effect = ConnectionError("down")
        result = fetch_board_stocks("BK0475", max_retries=1)
        assert result == []
        assert mock_http.call_count == 2  # 1 + 1 retry

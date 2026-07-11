"""data/pool.py 补充测试（覆盖率提升）。"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data.pool as pool_mod  # noqa: E402


class TestIsSt:
    def test_st(self):
        assert pool_mod.is_st("ST天宝") is True
        assert pool_mod.is_st("*ST海航") is True

    def test_normal(self):
        assert pool_mod.is_st("贵州茅台") is False


class TestPassesFilter:
    def test_normal_passes(self):
        stock = {"name": "贵州茅台", "code": "sh600519"}
        passed, reason = pool_mod.passes_filter(stock)
        assert passed is True

    def test_st_fails(self):
        stock = {"name": "ST天宝", "code": "sz002220"}
        passed, reason = pool_mod.passes_filter(stock)
        assert passed is False


class TestSaveAllMarketStocks:
    def test_save(self, tmp_path):
        stocks = {"消费": ["sh600519"]}
        target = tmp_path / "all_stocks.json"
        with patch.object(pool_mod, "ALL_STOCKS_FILE", str(target)), \
             patch("common.atomic_write_json") as mock_write:
            pool_mod.save_all_market_stocks(stocks)
            assert mock_write.called


class TestFetchAllMarketStocks:
    def test_returns_dict(self):
        with patch.object(pool_mod, "_get_filter"), \
             patch.object(pool_mod, "fetch_multiple_boards", return_value=[]):
            result = pool_mod.fetch_all_market_stocks()
            assert isinstance(result, dict)

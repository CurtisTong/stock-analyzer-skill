"""可选依赖数据源测试：AkshareFinanceFetcher + EfinanceFinanceFetcher。
以及 akshare/efinance 的 quote/kline fetcher。
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

try:
    import efinance as ef

    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False

requires_pandas = pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
requires_akshare = pytest.mark.skipif(not HAS_AKSHARE, reason="akshare not installed")
requires_efinance = pytest.mark.skipif(
    not HAS_EFINANCE, reason="efinance not installed"
)


# ═══════════════════════════════════════════════════════════════
# akshare_finance
# ═══════════════════════════════════════════════════════════════


class TestAkshareFinanceFetcher:
    """AkshareFinanceFetcher 测试。"""

    def _make_fetcher(self):
        from fetchers.finance.akshare_finance import AkshareFinanceFetcher

        return AkshareFinanceFetcher()

    def test_name_and_priority(self):
        f = self._make_fetcher()
        assert f.name == "akshare_finance"
        assert f.priority == 3

    def test_fetch_no_akshare(self):
        """akshare 未安装时返回 None。"""
        f = self._make_fetcher()
        with patch("fetchers.finance.akshare_finance.HAS_AKSHARE", False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_akshare
    def test_fetch_normal(self):
        """正常响应：返回 DataFrame 前 4 行。"""
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {"报告日期": "2025-03-31", "每股收益": 15.00},
                {"报告日期": "2024-12-31", "每股收益": 50.00},
                {"报告日期": "2024-09-30", "每股收益": 35.00},
                {"报告日期": "2024-06-30", "每股收益": 20.00},
                {"报告日期": "2024-03-31", "每股收益": 10.00},
            ]
        )
        mock_ak = MagicMock()
        mock_ak.stock_financial_abstract.return_value = df
        with (
            patch("fetchers.finance.akshare_finance.HAS_AKSHARE", True),
            patch("fetchers.finance.akshare_finance.ak", mock_ak),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert len(result) == 4  # 只取前 4 行
        assert result[0]["每股收益"] == 15.00

    @requires_pandas
    @requires_akshare
    def test_fetch_empty_df(self):
        """空 DataFrame：返回 None。"""
        f = self._make_fetcher()
        mock_ak = MagicMock()
        mock_ak.stock_financial_abstract.return_value = pd.DataFrame()
        with (
            patch("fetchers.finance.akshare_finance.HAS_AKSHARE", True),
            patch("fetchers.finance.akshare_finance.ak", mock_ak),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_akshare
    def test_fetch_none_df(self):
        """None DataFrame：返回 None。"""
        f = self._make_fetcher()
        mock_ak = MagicMock()
        mock_ak.stock_financial_abstract.return_value = None
        with (
            patch("fetchers.finance.akshare_finance.HAS_AKSHARE", True),
            patch("fetchers.finance.akshare_finance.ak", mock_ak),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_akshare
    def test_fetch_exception(self):
        """异常时返回 None。"""
        f = self._make_fetcher()
        mock_ak = MagicMock()
        mock_ak.stock_financial_abstract.side_effect = RuntimeError("api error")
        with (
            patch("fetchers.finance.akshare_finance.HAS_AKSHARE", True),
            patch("fetchers.finance.akshare_finance.ak", mock_ak),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_akshare
    def test_fetch_strips_prefix(self):
        """代码去掉交易所前缀后传给 akshare。"""
        f = self._make_fetcher()
        df = pd.DataFrame([{"报告日期": "2025-03-31", "每股收益": 15.00}])
        mock_ak = MagicMock()
        mock_ak.stock_financial_abstract.return_value = df
        with (
            patch("fetchers.finance.akshare_finance.HAS_AKSHARE", True),
            patch("fetchers.finance.akshare_finance.ak", mock_ak),
        ):
            f.fetch("sh600519")
        mock_ak.stock_financial_abstract.assert_called_once_with(symbol="600519")


# ═══════════════════════════════════════════════════════════════
# 注：原 TestEfinanceFinanceFetcher 已删除（PR-E）
# 原因：原 efinance_finance.py 用 get_quote_history（K 线数据）伪装成财务字段
# （EPSJB/ROEJQ 等），是最危险的"反向填充 schema"兜底。
# 测试 mock 的 get_base_info 与代码实际用的 get_quote_history 不一致，
# 是 v1.14.2 代码-测试漂移——删除 fetcher + 测试消除该错误数据源。
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# akshare_quote
# ═══════════════════════════════════════════════════════════════


class TestAkshareQuoteFetcher:
    """AkshareQuoteFetcher 测试。"""

    def _make_fetcher(self):
        from fetchers.quote.akshare_quote import AkshareQuoteFetcher

        return AkshareQuoteFetcher()

    def test_name_and_priority(self):
        f = self._make_fetcher()
        assert f.name == "akshare_quote"
        assert f.priority == 1

    def test_fetch_no_akshare(self):
        """akshare 未安装时返回 None。"""
        f = self._make_fetcher()
        with patch("fetchers.quote.akshare_quote.HAS_AKSHARE", False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_akshare
    def test_fetch_normal(self):
        """正常响应：返回行情数据。"""
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {
                    "代码": "600519",
                    "名称": "贵州茅台",
                    "最新价": 1800.00,
                    "昨收": 1790.00,
                    "今开": 1795.00,
                    "涨跌幅": 0.56,
                    "涨跌额": 10.00,
                    "最高": 1810.00,
                    "最低": 1790.00,
                    "成交量": 1234500,
                    "成交额": 2234567000,
                    "换手率": 0.15,
                    "市盈率-动态": 25.60,
                    "市净率": 8.20,
                    "总市值": 2260000000000,
                    "流通市值": 2260000000000,
                }
            ]
        )
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_spot_em.return_value = df
        with (
            patch("fetchers.quote.akshare_quote.HAS_AKSHARE", True),
            patch("fetchers.quote.akshare_quote.ak", mock_ak),
            patch("fetchers.quote.akshare_quote._ak_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["name"] == "贵州茅台"

    @requires_pandas
    @requires_akshare
    def test_fetch_empty_df(self):
        """空 DataFrame：返回 None。"""
        f = self._make_fetcher()
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame()
        with (
            patch("fetchers.quote.akshare_quote.HAS_AKSHARE", True),
            patch("fetchers.quote.akshare_quote.ak", mock_ak),
            patch("fetchers.quote.akshare_quote._ak_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_akshare
    def test_fetch_stock_not_found(self):
        """股票不在返回数据中：返回 None。"""
        f = self._make_fetcher()
        df = pd.DataFrame([{"代码": "000001", "名称": "平安银行", "最新价": 10.00}])
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_spot_em.return_value = df
        with (
            patch("fetchers.quote.akshare_quote.HAS_AKSHARE", True),
            patch("fetchers.quote.akshare_quote.ak", mock_ak),
            patch("fetchers.quote.akshare_quote._ak_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_akshare
    def test_fetch_exception(self):
        """异常时返回 None。"""
        f = self._make_fetcher()
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_spot_em.side_effect = RuntimeError("api error")
        with (
            patch("fetchers.quote.akshare_quote.HAS_AKSHARE", True),
            patch("fetchers.quote.akshare_quote.ak", mock_ak),
            patch("fetchers.quote.akshare_quote._ak_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# akshare_kline
# ═══════════════════════════════════════════════════════════════


class TestAkshareKlineFetcher:
    """AkshareKlineFetcher 测试。"""

    def _make_fetcher(self):
        from fetchers.kline.akshare_kline import AkshareKlineFetcher

        return AkshareKlineFetcher()

    def test_name_and_priority(self):
        f = self._make_fetcher()
        assert f.name == "akshare_kline"
        assert f.priority == 1

    def test_fetch_no_akshare(self):
        f = self._make_fetcher()
        with patch("fetchers.kline.akshare_kline.HAS_AKSHARE", False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_akshare
    def test_fetch_normal(self):
        """正常响应：返回 K 线数据。"""
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {
                    "日期": "2025-06-10",
                    "开盘": 1790.00,
                    "收盘": 1800.00,
                    "最高": 1810.00,
                    "最低": 1785.00,
                    "成交量": 12345,
                },
                {
                    "日期": "2025-06-11",
                    "开盘": 1800.00,
                    "收盘": 1805.00,
                    "最高": 1815.00,
                    "最低": 1795.00,
                    "成交量": 11000,
                },
            ]
        )
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.return_value = df
        with (
            patch("fetchers.kline.akshare_kline.HAS_AKSHARE", True),
            patch("fetchers.kline.akshare_kline.ak", mock_ak),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["day"] == "2025-06-10"
        assert result[0]["open"] == "1790.0"

    @requires_pandas
    @requires_akshare
    def test_fetch_empty_df(self):
        f = self._make_fetcher()
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()
        with (
            patch("fetchers.kline.akshare_kline.HAS_AKSHARE", True),
            patch("fetchers.kline.akshare_kline.ak", mock_ak),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_akshare
    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.side_effect = RuntimeError("api error")
        with (
            patch("fetchers.kline.akshare_kline.HAS_AKSHARE", True),
            patch("fetchers.kline.akshare_kline.ak", mock_ak),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_akshare
    def test_fetch_scale_60(self):
        """60 分钟 K 线。"""
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {
                    "日期": "2025-06-10 10:30",
                    "开盘": 1790.00,
                    "收盘": 1800.00,
                    "最高": 1810.00,
                    "最低": 1785.00,
                    "成交量": 12345,
                }
            ]
        )
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.return_value = df
        with (
            patch("fetchers.kline.akshare_kline.HAS_AKSHARE", True),
            patch("fetchers.kline.akshare_kline.ak", mock_ak),
        ):
            result = f.fetch("sh600519", scale=60)
        assert result is not None
        mock_ak.stock_zh_a_hist.assert_called_with(
            symbol="600519", period="60", adjust="qfq"
        )


# ═══════════════════════════════════════════════════════════════
# efinance_quote
# ═══════════════════════════════════════════════════════════════


class TestEfinanceQuoteFetcher:
    """EfinanceQuoteFetcher 测试。"""

    def _make_fetcher(self):
        from fetchers.quote.efinance_quote import EfinanceQuoteFetcher

        return EfinanceQuoteFetcher()

    def test_name_and_priority(self):
        f = self._make_fetcher()
        assert f.name == "efinance_quote"
        assert f.priority == 0

    def test_fetch_no_efinance(self):
        f = self._make_fetcher()
        with patch("fetchers.quote.efinance_quote.HAS_EFINANCE", False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_efinance
    def test_fetch_normal(self):
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {
                    "股票代码": "600519",
                    "股票名称": "贵州茅台",
                    "最新价": 1800.00,
                    "昨收": 1790.00,
                    "今开": 1795.00,
                    "涨跌幅": 0.56,
                    "涨跌额": 10.00,
                    "最高": 1810.00,
                    "最低": 1790.00,
                    "成交量": 1234500,
                    "成交额": 2234567000,
                    "换手率": 0.15,
                    "市盈率-动态": 25.60,
                    "市净率": 8.20,
                    "总市值": 2260000000000,
                    "流通市值": 2260000000000,
                }
            ]
        )
        mock_ef = MagicMock()
        mock_ef.stock.get_realtime_quotes.return_value = df
        with (
            patch("fetchers.quote.efinance_quote.HAS_EFINANCE", True),
            patch("fetchers.quote.efinance_quote.ef", mock_ef),
            patch("fetchers.quote.efinance_quote._ef_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["name"] == "贵州茅台"

    @requires_pandas
    @requires_efinance
    def test_fetch_empty_df(self):
        f = self._make_fetcher()
        mock_ef = MagicMock()
        mock_ef.stock.get_realtime_quotes.return_value = pd.DataFrame()
        with (
            patch("fetchers.quote.efinance_quote.HAS_EFINANCE", True),
            patch("fetchers.quote.efinance_quote.ef", mock_ef),
            patch("fetchers.quote.efinance_quote._ef_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_efinance
    def test_fetch_stock_not_found(self):
        f = self._make_fetcher()
        df = pd.DataFrame([{"股票代码": "000001", "股票名称": "平安银行"}])
        mock_ef = MagicMock()
        mock_ef.stock.get_realtime_quotes.return_value = df
        with (
            patch("fetchers.quote.efinance_quote.HAS_EFINANCE", True),
            patch("fetchers.quote.efinance_quote.ef", mock_ef),
            patch("fetchers.quote.efinance_quote._ef_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_efinance
    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_ef = MagicMock()
        mock_ef.stock.get_realtime_quotes.side_effect = RuntimeError("api error")
        with (
            patch("fetchers.quote.efinance_quote.HAS_EFINANCE", True),
            patch("fetchers.quote.efinance_quote.ef", mock_ef),
            patch("fetchers.quote.efinance_quote._ef_cache", {"df": None, "ts": 0}),
        ):
            result = f.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# efinance_kline
# ═══════════════════════════════════════════════════════════════


class TestEfinanceKlineFetcher:
    """EfinanceKlineFetcher 测试。"""

    def _make_fetcher(self):
        from fetchers.kline.efinance_kline import EfinanceKlineFetcher

        return EfinanceKlineFetcher()

    def test_name_and_priority(self):
        f = self._make_fetcher()
        assert f.name == "efinance_kline"
        assert f.priority == 0

    def test_fetch_no_efinance(self):
        f = self._make_fetcher()
        with patch("fetchers.kline.efinance_kline.HAS_EFINANCE", False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_efinance
    def test_fetch_normal(self):
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {
                    "日期": "2025-06-10",
                    "开盘": 1790.00,
                    "收盘": 1800.00,
                    "最高": 1810.00,
                    "最低": 1785.00,
                    "成交量": 12345,
                },
            ]
        )
        mock_ef = MagicMock()
        mock_ef.stock.get_quote_history.return_value = df
        with (
            patch("fetchers.kline.efinance_kline.HAS_EFINANCE", True),
            patch("fetchers.kline.efinance_kline.ef", mock_ef),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert len(result) == 1
        assert result[0]["day"] == "2025-06-10"

    @requires_pandas
    @requires_efinance
    def test_fetch_empty_df(self):
        f = self._make_fetcher()
        mock_ef = MagicMock()
        mock_ef.stock.get_quote_history.return_value = pd.DataFrame()
        with (
            patch("fetchers.kline.efinance_kline.HAS_EFINANCE", True),
            patch("fetchers.kline.efinance_kline.ef", mock_ef),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_efinance
    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_ef = MagicMock()
        mock_ef.stock.get_quote_history.side_effect = RuntimeError("api error")
        with (
            patch("fetchers.kline.efinance_kline.HAS_EFINANCE", True),
            patch("fetchers.kline.efinance_kline.ef", mock_ef),
        ):
            result = f.fetch("sh600519")
        assert result is None

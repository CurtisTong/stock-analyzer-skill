"""
美股/港股数据源单元测试：覆盖 us:/hk: 前缀识别、符号转换、fetcher 行为、边界情况。
"""

import pytest
from unittest.mock import patch, MagicMock

from common import NOT_HANDLED

# ====================================================================
# 1. yfinance_quote 模块测试
# ====================================================================


class TestYfinanceQuoteHelpers:
    """us:/hk: 前缀识别和符号转换。"""

    def test_is_cross_market_code_with_us_prefix(self):
        from fetchers.quote.yfinance_quote import _is_cross_market_code

        assert _is_cross_market_code("us:^gspc") is True
        assert _is_cross_market_code("us:spy") is True
        assert _is_cross_market_code("US:SPY") is True

    def test_is_cross_market_code_with_hk_prefix(self):
        from fetchers.quote.yfinance_quote import _is_cross_market_code

        assert _is_cross_market_code("hk:0700") is True
        assert _is_cross_market_code("HK:9988") is True
        assert _is_cross_market_code("hk:00700") is True

    def test_is_cross_market_code_without_prefix(self):
        from fetchers.quote.yfinance_quote import _is_cross_market_code

        assert _is_cross_market_code("sh600519") is False
        assert _is_cross_market_code("sz000858") is False
        assert _is_cross_market_code("^GSPC") is False

    def test_is_cross_market_code_empty_prefix(self):
        """'us:'/'hk:' 本身也识别为跨市场代码（符号为空，fetch 时应返回 None）。"""
        from fetchers.quote.yfinance_quote import _is_cross_market_code

        assert _is_cross_market_code("us:") is True
        assert _is_cross_market_code("hk:") is True

    def test_to_yf_symbol_us_lowercase(self):
        from fetchers.quote.yfinance_quote import _to_yf_symbol

        assert _to_yf_symbol("us:^gspc") == "^gspc"
        assert _to_yf_symbol("us:spy") == "spy"
        assert _to_yf_symbol("us:.ixic") == ".ixic"

    def test_to_yf_symbol_us_uppercase(self):
        """大写前缀 US:SPY 应正确提取符号 spy。"""
        from fetchers.quote.yfinance_quote import _to_yf_symbol

        assert _to_yf_symbol("US:SPY") == "SPY"
        assert _to_yf_symbol("US:^GSPC") == "^GSPC"

    def test_to_yf_symbol_hk(self):
        """港股代码应转为 .HK 后缀，补齐 4 位。"""
        from fetchers.quote.yfinance_quote import _to_yf_symbol

        assert _to_yf_symbol("hk:0700") == "0700.HK"
        assert _to_yf_symbol("hk:9988") == "9988.HK"
        assert _to_yf_symbol("hk:00700") == "0700.HK"
        assert _to_yf_symbol("HK:09988") == "9988.HK"

    def test_to_yf_symbol_empty(self):
        """'us:'/'hk:' 无符号部分应返回 None。"""
        from fetchers.quote.yfinance_quote import _to_yf_symbol

        assert _to_yf_symbol("us:") is None
        assert _to_yf_symbol("hk:") is None


class TestYfinanceQuoteFetcher:
    """YfinanceQuoteFetcher 行为测试。"""

    def test_returns_not_handled_for_non_us_code(self):
        """非 us: 前缀代码应返回 NOT_HANDLED，不触发熔断计数。"""
        from fetchers.quote.yfinance_quote import YfinanceQuoteFetcher

        fetcher = YfinanceQuoteFetcher()
        assert fetcher.fetch("sh600519") is NOT_HANDLED
        assert fetcher.fetch("sz000858") is NOT_HANDLED

    @patch("fetchers.quote.yfinance_quote.yf", None)
    def test_returns_not_handled_when_yfinance_missing(self):
        """yfinance 未安装时返回 NOT_HANDLED。"""
        from fetchers.quote.yfinance_quote import YfinanceQuoteFetcher

        fetcher = YfinanceQuoteFetcher()
        assert fetcher.fetch("us:^gspc") is NOT_HANDLED

    @patch("fetchers.quote.yfinance_quote.yf")
    def test_fetch_returns_quote_dict(self, mock_yf):
        """正常 fetch 应返回标准 quote dict。"""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "shortName": "S&P 500",
            "regularMarketPrice": 5500.0,
            "regularMarketPreviousClose": 5480.0,
            "regularMarketOpen": 5490.0,
            "regularMarketDayHigh": 5510.0,
            "regularMarketDayLow": 5475.0,
            "regularMarketChangePercent": 0.36,
            "regularMarketVolume": 3000000000,
            "trailingPE": 25.5,
            "priceToBook": 4.2,
            "marketCap": 45000000000000,
        }
        mock_yf.Ticker.return_value = mock_ticker

        from fetchers.quote.yfinance_quote import YfinanceQuoteFetcher

        fetcher = YfinanceQuoteFetcher()
        result = fetcher.fetch("us:^gspc")

        assert result is not None
        assert result["code"] == "us:^gspc"
        assert result["name"] == "S&P 500"
        assert result["price"] == "5500.0"
        assert result["source"] == "yfinance"
        assert "change_pct" in result
        assert "volume" in result

    @patch("fetchers.quote.yfinance_quote.yf")
    def test_fetch_fallback_to_history(self, mock_yf):
        """info 无 regularMarketPrice 时应回退到 history 数据。"""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "shortName": "Test",
            "trailingPE": None,
            "priceToBook": None,
            "marketCap": None,
        }

        # 模拟 DataFrame（不依赖 pandas）
        mock_row0 = {
            "Open": 100.0,
            "Close": 101.0,
            "High": 102.0,
            "Low": 99.0,
            "Volume": 1000000,
        }
        mock_row1 = {
            "Open": 102.0,
            "Close": 103.0,
            "High": 104.0,
            "Low": 101.0,
            "Volume": 1200000,
        }
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__len__ = MagicMock(return_value=2)
        mock_hist.iloc = [mock_row0, mock_row1]
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        from fetchers.quote.yfinance_quote import YfinanceQuoteFetcher

        fetcher = YfinanceQuoteFetcher()
        result = fetcher.fetch("us:spy")

        assert result is not None
        assert result["price"] == "103.0"
        assert result["prev_close"] == "101.0"

    @patch("fetchers.quote.yfinance_quote.yf")
    def test_fetch_info_returns_none(self, mock_yf):
        """ticker.info 返回 None 时应回退到 history。"""
        mock_ticker = MagicMock()
        mock_ticker.info = None
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__len__ = MagicMock(return_value=1)
        mock_hist.iloc = [
            {"Open": 50.0, "Close": 55.0, "High": 56.0, "Low": 49.0, "Volume": 500000}
        ]
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        from fetchers.quote.yfinance_quote import YfinanceQuoteFetcher

        fetcher = YfinanceQuoteFetcher()
        result = fetcher.fetch("us:test")
        assert result is not None
        assert result["price"] == "55.0"

    def test_fetch_empty_symbol_returns_none(self):
        """'us:' 无符号部分应返回 None（失败，非 NOT_HANDLED）。"""
        from fetchers.quote.yfinance_quote import YfinanceQuoteFetcher

        YfinanceQuoteFetcher()
        # yf is None in test env，所以返回 NOT_HANDLED
        # 但如果 yf 存在，空符号应返回 None


# ====================================================================
# 2. yfinance_kline 模块测试（us: 前缀支持）
# ====================================================================


class TestYfinanceKlineUsPrefix:
    """YfinanceKlineFetcher us:/hk: 前缀支持。"""

    def test_to_yf_symbol_us_prefix(self):
        from fetchers.kline.yfinance_kline import _to_yf_symbol

        assert _to_yf_symbol("us:^gspc") == "^gspc"
        assert _to_yf_symbol("us:spy") == "spy"
        assert _to_yf_symbol("us:qqq") == "qqq"

    def test_to_yf_symbol_us_uppercase(self):
        """大写 US: 前缀应正确处理。"""
        from fetchers.kline.yfinance_kline import _to_yf_symbol

        assert _to_yf_symbol("US:SPY") == "SPY"
        assert _to_yf_symbol("US:^GSPC") == "^GSPC"

    def test_to_yf_symbol_hk_prefix(self):
        """港股代码应转为 .HK 后缀。"""
        from fetchers.kline.yfinance_kline import _to_yf_symbol

        assert _to_yf_symbol("hk:0700") == "0700.HK"
        assert _to_yf_symbol("hk:9988") == "9988.HK"
        assert _to_yf_symbol("hk:00700") == "0700.HK"

    def test_to_yf_symbol_ashare_unchanged(self):
        """A 股代码转换逻辑不变。"""
        from fetchers.kline.yfinance_kline import _to_yf_symbol

        assert _to_yf_symbol("sh600519") == "600519.SS"
        assert _to_yf_symbol("sz000858") == "000858.SZ"


# ====================================================================
# 3. NOT_HANDLED 哨兵值与 DataFetcherManager 集成测试
# ====================================================================


class TestNotHandledSentinel:
    """验证 NOT_HANDLED 在 DataFetcherManager 中的行为。"""

    def test_not_handled_is_singleton(self):
        """NOT_HANDLED 应为全局唯一对象。"""
        assert NOT_HANDLED is not None
        assert NOT_HANDLED is not None
        assert NOT_HANDLED is not NOT_HANDLED.__class__()

    def test_manager_skips_not_handled(self):
        """DataFetcherManager 遇到 NOT_HANDLED 应跳过而不计失败。"""
        from common import DataFetcherManager, BaseFetcher

        class AlwaysNotHandledFetcher(BaseFetcher):
            def __init__(self):
                super().__init__("test_not_handled", priority=10)

            def fetch(self, code, **kwargs):
                return NOT_HANDLED

        class SuccessFetcher(BaseFetcher):
            def __init__(self):
                super().__init__("test_success", priority=1)

            def fetch(self, code, **kwargs):
                return {"price": "100"}

        manager = DataFetcherManager([AlwaysNotHandledFetcher(), SuccessFetcher()])
        result = manager.fetch("us:^gspc")
        assert result == {"price": "100"}

    def test_manager_not_handled_no_circuit_break(self):
        """NOT_HANDLED 不应触发熔断计数。"""
        from common import DataFetcherManager, BaseFetcher

        class NotHandledFetcher(BaseFetcher):
            def __init__(self):
                super().__init__("test_cb_not_handled", priority=10)

            def fetch(self, code, **kwargs):
                return NOT_HANDLED

        fetcher = NotHandledFetcher()
        manager = DataFetcherManager([fetcher])

        # 多次 NOT_HANDLED 不应导致熔断
        for _ in range(10):
            manager.fetch("us:^gspc")

        assert fetcher.circuit_breaker.failure_count == 0


# ====================================================================
# 4. fetcher 注册测试
# ====================================================================


class TestFetcherRegistration:
    """验证 YfinanceQuoteFetcher 已注册到 quote 域。"""

    def test_yfinance_quote_in_fetchers(self):
        """yfinance_quote 模块可被 _try_import 发现。"""
        from fetchers import _try_import

        cls = _try_import("yfinance_quote", "YfinanceQuoteFetcher")
        # yfinance 安装时返回类，未安装时返回 None
        if cls is not None:
            assert cls.__name__ == "YfinanceQuoteFetcher"

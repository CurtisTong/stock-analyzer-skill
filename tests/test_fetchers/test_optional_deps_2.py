"""可选依赖数据源测试：tushare + baostock + pytdx + yfinance。"""

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
    import tushare as ts

    HAS_TUSHARE = True
except ImportError:
    HAS_TUSHARE = False

try:
    import baostock as bs

    HAS_BAOSTOCK = True
except ImportError:
    HAS_BAOSTOCK = False

try:
    import yfinance as yf

    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

requires_pandas = pytest.mark.skipif(not HAS_PANDAS, reason="pandas not installed")
requires_tushare = pytest.mark.skipif(not HAS_TUSHARE, reason="tushare not installed")
requires_baostock = pytest.mark.skipif(
    not HAS_BAOSTOCK, reason="baostock not installed"
)
requires_yfinance = pytest.mark.skipif(
    not HAS_YFINANCE, reason="yfinance not installed"
)


# ═══════════════════════════════════════════════════════════════
# tushare_quote
# ═══════════════════════════════════════════════════════════════


class TestTushareQuoteFetcher:
    def _make_fetcher(self):
        from fetchers.quote.tushare_quote import TushareQuoteFetcher

        return TushareQuoteFetcher()

    def test_name(self):
        f = self._make_fetcher()
        assert f.name == "tushare_quote"

    def test_fetch_no_tushare(self):
        f = self._make_fetcher()
        with patch("fetchers.quote.tushare_quote._check_tushare", return_value=False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_tushare
    def test_fetch_normal(self):
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {
                    "close": 1800.00,
                    "pre_close": 1790.00,
                    "open": 1795.00,
                    "pct_chg": 0.56,
                    "change": 10.00,
                    "high": 1810.00,
                    "low": 1790.00,
                    "vol": 12345,
                    "amount": 2234567,
                }
            ]
        )
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value.daily.return_value = df
        with (
            patch("fetchers.quote.tushare_quote._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": mock_ts}),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["price"] == "1800.0"

    @requires_pandas
    @requires_tushare
    def test_fetch_empty_df(self):
        f = self._make_fetcher()
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value.daily.return_value = pd.DataFrame()
        with (
            patch("fetchers.quote.tushare_quote._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": mock_ts}),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_tushare
    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value.daily.side_effect = RuntimeError("error")
        with (
            patch("fetchers.quote.tushare_quote._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": mock_ts}),
        ):
            result = f.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# tushare_kline
# ═══════════════════════════════════════════════════════════════


class TestTushareKlineFetcher:
    def _make_fetcher(self):
        from fetchers.kline.tushare_kline import TushareKlineFetcher

        return TushareKlineFetcher()

    def test_name(self):
        f = self._make_fetcher()
        assert f.name == "tushare_kline"

    def test_fetch_no_tushare(self):
        f = self._make_fetcher()
        with patch("fetchers.kline.tushare_kline._check_tushare", return_value=False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_pandas
    @requires_tushare
    def test_fetch_normal(self):
        f = self._make_fetcher()
        df = pd.DataFrame(
            [
                {
                    "trade_date": "20250610",
                    "open": 1790.00,
                    "close": 1800.00,
                    "high": 1810.00,
                    "low": 1785.00,
                    "vol": 12345,
                },
                {
                    "trade_date": "20250611",
                    "open": 1800.00,
                    "close": 1805.00,
                    "high": 1815.00,
                    "low": 1795.00,
                    "vol": 11000,
                },
            ]
        )
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value.daily.return_value = df
        with (
            patch("fetchers.kline.tushare_kline._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": mock_ts}),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        # trade_date YYYYMMDD -> YYYY-MM-DD 格式化
        assert result[0]["day"] == "2025-06-10"
        assert result[1]["day"] == "2025-06-11"

    @requires_tushare
    def test_fetch_non_daily_scale(self):
        """非日线返回 None。"""
        f = self._make_fetcher()
        with patch("fetchers.kline.tushare_kline._check_tushare", return_value=True):
            result = f.fetch("sh600519", scale=60)
        assert result is None

    @requires_pandas
    def test_bj_code_maps_to_bj_exchange(self):
        """北交所代码（bj430047）应映射到 .BJ 而非 .SZ。"""
        f = self._make_fetcher()
        captured = {}

        def fake_daily(**kwargs):
            captured["ts_code"] = kwargs.get("ts_code")
            return pd.DataFrame(
                [{"trade_date": "20250610", "open": 1, "close": 1, "high": 1, "low": 1, "vol": 1}]
            )

        mock_ts = MagicMock()
        mock_ts.pro_api.return_value.daily.side_effect = fake_daily
        with (
            patch("fetchers.kline.tushare_kline._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": mock_ts}),
        ):
            f.fetch("bj430047")
        assert captured["ts_code"] == "430047.BJ"

    @requires_pandas
    def test_sh_code_maps_to_sh_exchange(self):
        """沪市代码应映射到 .SH。"""
        f = self._make_fetcher()
        captured = {}

        def fake_daily(**kwargs):
            captured["ts_code"] = kwargs.get("ts_code")
            return pd.DataFrame(
                [{"trade_date": "20250610", "open": 1, "close": 1, "high": 1, "low": 1, "vol": 1}]
            )

        mock_ts = MagicMock()
        mock_ts.pro_api.return_value.daily.side_effect = fake_daily
        with (
            patch("fetchers.kline.tushare_kline._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": mock_ts}),
        ):
            f.fetch("sh688001")
        assert captured["ts_code"] == "688001.SH"

    @requires_pandas
    def test_sz_code_maps_to_sz_exchange(self):
        """深市代码应映射到 .SZ。"""
        f = self._make_fetcher()
        captured = {}

        def fake_daily(**kwargs):
            captured["ts_code"] = kwargs.get("ts_code")
            return pd.DataFrame(
                [{"trade_date": "20250610", "open": 1, "close": 1, "high": 1, "low": 1, "vol": 1}]
            )

        mock_ts = MagicMock()
        mock_ts.pro_api.return_value.daily.side_effect = fake_daily
        with (
            patch("fetchers.kline.tushare_kline._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": mock_ts}),
        ):
            f.fetch("sz300001")
        assert captured["ts_code"] == "300001.SZ"


# ═══════════════════════════════════════════════════════════════
# baostock_kline
# ═══════════════════════════════════════════════════════════════


class TestBaostockKlineFetcher:
    def _make_fetcher(self):
        from fetchers.kline.baostock_kline import BaostockKlineFetcher

        return BaostockKlineFetcher()

    def test_name(self):
        f = self._make_fetcher()
        assert f.name == "baostock_kline"

    def test_fetch_no_baostock(self):
        f = self._make_fetcher()
        with patch("fetchers.kline.baostock_kline.HAS_BAOSTOCK", False):
            result = f.fetch("sh600519")
        assert result is None

    @requires_baostock
    def test_fetch_non_daily(self):
        """非日线返回 None。"""
        f = self._make_fetcher()
        with patch("fetchers.kline.baostock_kline.HAS_BAOSTOCK", True):
            result = f.fetch("sh600519", scale=60)
        assert result is None

    @requires_baostock
    def test_fetch_normal(self):
        f = self._make_fetcher()
        mock_rs = MagicMock()
        mock_rs.error_code = "0"
        mock_rs.next.side_effect = [True, True, False]
        mock_rs.get_row_data.side_effect = [
            ["2025-06-10", "1790.00", "1810.00", "1785.00", "1800.00", "12345"],
            ["2025-06-11", "1800.00", "1815.00", "1795.00", "1805.00", "11000"],
        ]
        mock_bs = MagicMock()
        mock_bs.login.return_value = None
        mock_bs.query_history_k_data_plus.return_value = mock_rs
        mock_bs.logout.return_value = None
        with (
            patch("fetchers.kline.baostock_kline.HAS_BAOSTOCK", True),
            patch("fetchers.kline.baostock_kline.bs", mock_bs),
        ):
            result = self._make_fetcher().fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["day"] == "2025-06-10"

    @requires_baostock
    def test_fetch_error_code(self):
        f = self._make_fetcher()
        mock_rs = MagicMock()
        mock_rs.error_code = "1"
        mock_bs = MagicMock()
        mock_bs.login.return_value = None
        mock_bs.query_history_k_data_plus.return_value = mock_rs
        mock_bs.logout.return_value = None
        with (
            patch("fetchers.kline.baostock_kline.HAS_BAOSTOCK", True),
            patch("fetchers.kline.baostock_kline.bs", mock_bs),
        ):
            result = f.fetch("sh600519")
        assert result is None

    @requires_baostock
    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_bs = MagicMock()
        mock_bs.login.side_effect = RuntimeError("error")
        with (
            patch("fetchers.kline.baostock_kline.HAS_BAOSTOCK", True),
            patch("fetchers.kline.baostock_kline.bs", mock_bs),
        ):
            result = f.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# pytdx_quote
# ═══════════════════════════════════════════════════════════════


class TestPytdxQuoteFetcher:
    def _make_fetcher(self):
        from fetchers.quote.pytdx_quote import PytdxQuoteFetcher

        return PytdxQuoteFetcher()

    def test_name(self):
        f = self._make_fetcher()
        assert f.name == "pytdx_quote"

    def test_fetch_no_pytdx(self):
        f = self._make_fetcher()
        with patch("fetchers.quote.pytdx_quote.HAS_PYTDX", False):
            result = f.fetch("sh600519")
        assert result is None

    def test_fetch_normal(self):
        f = self._make_fetcher()
        mock_api = MagicMock()
        mock_api.get_security_quotes.return_value = [
            {
                "price": 18.00,
                "last_close": 17.90,
                "open": 17.95,
                "high": 18.10,
                "low": 17.90,
                "vol": 12345,
                "amount": 2234567,
                "name": "贵州茅台",
            }
        ]
        mock_pool = MagicMock()
        mock_pool.get.return_value = (mock_api, "127.0.0.1", 7709)
        with (
            patch("fetchers.quote.pytdx_quote.HAS_PYTDX", True),
            patch("fetchers.quote.pytdx_quote.get_default_pool", return_value=mock_pool),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["name"] == "贵州茅台"

    def test_fetch_empty_data(self):
        f = self._make_fetcher()
        mock_api = MagicMock()
        mock_api.get_security_quotes.return_value = None
        mock_pool = MagicMock()
        mock_pool.get.return_value = (mock_api, "127.0.0.1", 7709)
        with (
            patch("fetchers.quote.pytdx_quote.HAS_PYTDX", True),
            patch("fetchers.quote.pytdx_quote.get_default_pool", return_value=mock_pool),
        ):
            result = f.fetch("sh600519")
        assert result is None

    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_api = MagicMock()
        mock_api.get_security_quotes.side_effect = RuntimeError("error")
        mock_pool = MagicMock()
        mock_pool.get.return_value = (mock_api, "127.0.0.1", 7709)
        with (
            patch("fetchers.quote.pytdx_quote.HAS_PYTDX", True),
            patch("fetchers.quote.pytdx_quote.get_default_pool", return_value=mock_pool),
        ):
            result = f.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# pytdx_kline
# ═══════════════════════════════════════════════════════════════


class TestPytdxKlineFetcher:
    def _make_fetcher(self):
        from fetchers.kline.pytdx_kline import PytdxKlineFetcher

        return PytdxKlineFetcher()

    def test_name(self):
        f = self._make_fetcher()
        assert f.name == "pytdx_kline"

    def test_fetch_no_pytdx(self):
        f = self._make_fetcher()
        with patch("fetchers.kline.pytdx_kline.HAS_PYTDX", False):
            result = f.fetch("sh600519")
        assert result is None

    def test_fetch_normal(self):
        f = self._make_fetcher()
        mock_api = MagicMock()
        mock_api.get_security_bars.return_value = [
            {
                "datetime": "2025-06-10",
                "open": 17.90,
                "close": 18.00,
                "high": 18.10,
                "low": 17.85,
                "vol": 12345,
            },
            {
                "datetime": "2025-06-11",
                "open": 18.00,
                "close": 18.05,
                "high": 18.15,
                "low": 17.95,
                "vol": 11000,
            },
        ]
        mock_pool = MagicMock()
        mock_pool.get.return_value = (mock_api, "127.0.0.1", 7709)
        with (
            patch("fetchers.kline.pytdx_kline.HAS_PYTDX", True),
            patch("fetchers.kline.pytdx_kline.get_default_pool", return_value=mock_pool),
        ):
            result = f.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["day"] == "2025-06-10"

    def test_fetch_empty_data(self):
        f = self._make_fetcher()
        mock_api = MagicMock()
        mock_api.get_security_bars.return_value = None
        mock_pool = MagicMock()
        mock_pool.get.return_value = (mock_api, "127.0.0.1", 7709)
        with (
            patch("fetchers.kline.pytdx_kline.HAS_PYTDX", True),
            patch("fetchers.kline.pytdx_kline.get_default_pool", return_value=mock_pool),
        ):
            result = f.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# yfinance_quote
# ═══════════════════════════════════════════════════════════════


class TestYfinanceQuoteFetcher:
    def _make_fetcher(self):
        from fetchers.quote.yfinance_quote import YfinanceQuoteFetcher

        return YfinanceQuoteFetcher()

    def test_name(self):
        f = self._make_fetcher()
        assert f.name == "yfinance_quote"

    def test_fetch_no_yfinance(self):
        f = self._make_fetcher()
        with patch("fetchers.quote.yfinance_quote.yf", None):
            from common import NOT_HANDLED

            result = f.fetch("us:spy")
            assert result is NOT_HANDLED

    def test_fetch_not_us_code(self):
        """非 us: 前缀返回 NOT_HANDLED。"""
        f = self._make_fetcher()
        from common import NOT_HANDLED

        mock_yf = MagicMock()
        with patch("fetchers.quote.yfinance_quote.yf", mock_yf):
            result = f.fetch("sh600519")
            assert result is NOT_HANDLED

    def test_fetch_normal(self):
        f = self._make_fetcher()
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 450.00,
            "regularMarketPreviousClose": 445.00,
            "regularMarketChangePercent": 1.12,
            "regularMarketOpen": 446.00,
            "regularMarketDayHigh": 452.00,
            "regularMarketDayLow": 444.00,
            "regularMarketVolume": 50000000,
            "shortName": "SPDR S&P 500",
            "trailingPE": 25.0,
            "priceToBook": 4.5,
            "marketCap": 500000000000,
        }
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        with patch("fetchers.quote.yfinance_quote.yf", mock_yf):
            result = f.fetch("us:spy")
        assert result is not None
        assert result["source"] == "yfinance"
        assert result["name"] == "SPDR S&P 500"

    def test_fetch_empty_symbol(self):
        """空符号返回 None。"""
        f = self._make_fetcher()
        mock_yf = MagicMock()
        with patch("fetchers.quote.yfinance_quote.yf", mock_yf):
            result = f.fetch("us:")
        assert result is None

    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_yf = MagicMock()
        mock_yf.Ticker.side_effect = RuntimeError("error")
        with patch("fetchers.quote.yfinance_quote.yf", mock_yf):
            result = f.fetch("us:spy")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# yfinance_kline
# ═══════════════════════════════════════════════════════════════


class TestYfinanceKlineFetcher:
    def _make_fetcher(self):
        from fetchers.kline.yfinance_kline import YfinanceKlineFetcher

        return YfinanceKlineFetcher()

    def test_name(self):
        f = self._make_fetcher()
        assert f.name == "yfinance_kline"

    def test_fetch_no_yfinance(self):
        f = self._make_fetcher()
        with patch("fetchers.kline.yfinance_kline.yf", None):
            result = f.fetch("us:spy")
        assert result is None

    @requires_pandas
    def test_fetch_normal(self):
        f = self._make_fetcher()
        df = pd.DataFrame(
            {
                "Open": [445.0, 448.0],
                "Close": [450.0, 452.0],
                "High": [452.0, 454.0],
                "Low": [443.0, 447.0],
                "Volume": [50000000, 48000000],
            },
            index=pd.to_datetime(["2025-06-10", "2025-06-11"]),
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        with patch("fetchers.kline.yfinance_kline.yf", mock_yf):
            result = f.fetch("us:spy")
        assert result is not None
        assert len(result) == 2
        assert result[0]["day"] == "2025-06-10"
        assert result[0]["close"] == "450.0"

    @requires_pandas
    def test_fetch_empty_df(self):
        f = self._make_fetcher()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        with patch("fetchers.kline.yfinance_kline.yf", mock_yf):
            result = f.fetch("us:spy")
        assert result is None

    def test_fetch_exception(self):
        f = self._make_fetcher()
        mock_yf = MagicMock()
        mock_yf.Ticker.side_effect = RuntimeError("error")
        with patch("fetchers.kline.yfinance_kline.yf", mock_yf):
            result = f.fetch("us:spy")
        assert result is None

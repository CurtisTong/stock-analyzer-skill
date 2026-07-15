"""测试 scripts/fetchers/quote/tushare_quote.py：Tushare 行情 fetcher。"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "tushare_quote_mod",
    PROJECT_ROOT / "scripts" / "fetchers" / "quote" / "tushare_quote.py",
)
tushare_quote = importlib.util.module_from_spec(_spec)
sys.modules["tushare_quote_mod"] = tushare_quote
_spec.loader.exec_module(tushare_quote)


class TestTushareQuoteFetcher:
    def test_init_without_tushare(self):
        """无 tushare 时 priority=2（不优先）。"""
        with patch("tushare_quote_mod._check_tushare", return_value=False):
            f = tushare_quote.TushareQuoteFetcher()
        assert f.name == "tushare_quote"
        assert f.priority == 2

    def test_init_with_tushare(self):
        """有 tushare 时 priority=-1（最优先）。"""
        with patch("tushare_quote_mod._check_tushare", return_value=True):
            f = tushare_quote.TushareQuoteFetcher()
        assert f.priority == -1

    def test_fetch_no_tushare(self):
        """无 tushare 时 fetch 返回 None。"""
        with patch("tushare_quote_mod._check_tushare", return_value=False):
            f = tushare_quote.TushareQuoteFetcher()
            result = f.fetch("sh600519")
        assert result is None

    def test_fetch_success(self):
        """使用真实 DataFrame 让 iloc[0] 工作。"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")

        row = pd.Series(
            {
                "close": 100.0,
                "pre_close": 99.0,
                "open": 99.5,
                "pct_chg": 1.0,
                "change": 1.0,
                "high": 101.0,
                "low": 98.0,
                "vol": 1000000,
                "amount": 1e8,
            }
        )
        fake_df = pd.DataFrame([row])

        with (
            patch("tushare_quote_mod._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": MagicMock()}),
        ):
            import sys

            ts_mock = sys.modules["tushare"]
            ts_mock.set_token = MagicMock()
            pro_mock = MagicMock()
            pro_mock.daily = MagicMock(return_value=fake_df)
            ts_mock.pro_api = MagicMock(return_value=pro_mock)
            f = tushare_quote.TushareQuoteFetcher()
            result = f.fetch("sh600519")
        assert result is not None
        assert result["source"] == "tushare"
        assert result["price"] == "100.0"

    def test_fetch_empty_df(self):
        """df 为空时返回 None。"""
        fake_df = MagicMock()
        fake_df.empty = True
        with (
            patch("tushare_quote_mod._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": MagicMock()}),
        ):
            import sys

            ts_mock = sys.modules["tushare"]
            ts_mock.set_token = MagicMock()
            ts_mock.pro_api = MagicMock(
                return_value=MagicMock(
                    daily=MagicMock(return_value=fake_df),
                )
            )
            f = tushare_quote.TushareQuoteFetcher()
            result = f.fetch("sh600519")
        assert result is None

    def test_fetch_exception(self):
        """异常时返回 None（不抛错）。"""
        with (
            patch("tushare_quote_mod._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": MagicMock()}),
        ):
            import sys

            ts_mock = sys.modules["tushare"]
            ts_mock.set_token = MagicMock()
            ts_mock.pro_api = MagicMock(side_effect=Exception("err"))
            f = tushare_quote.TushareQuoteFetcher()
            result = f.fetch("sh600519")
        assert result is None

    def test_exchange_inference(self):
        """exchange 推断 SH/SZ/BJ。"""
        from common import infer_exchange

        assert infer_exchange("sh600519") == "sh"
        assert infer_exchange("sz000001") == "sz"
        assert infer_exchange("bj430001") == "bj"

    def test_with_token(self):
        """设置 TUSHARE_TOKEN 时调用 ts.set_token。"""
        fake_df = MagicMock()
        fake_df.empty = True
        with (
            patch("tushare_quote_mod._check_tushare", return_value=True),
            patch.dict("sys.modules", {"tushare": MagicMock()}),
            patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
        ):
            import sys

            ts_mock = sys.modules["tushare"]
            ts_mock.set_token = MagicMock()
            ts_mock.pro_api = MagicMock(
                return_value=MagicMock(
                    daily=MagicMock(return_value=fake_df),
                )
            )
            f = tushare_quote.TushareQuoteFetcher()
            f.fetch("sh600519")
        ts_mock.set_token.assert_called_once_with("test_token")

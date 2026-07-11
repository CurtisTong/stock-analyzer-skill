"""fetchers/kline/baostock_kline.py 覆盖测试。

mock baostock import，覆盖 _ensure_logged_in、_logout、BaostockKlineFetcher.fetch
（含代码转换、查询、错误处理、scale 过滤等分支）。
"""

import importlib
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def baostock_module(monkeypatch):
    """注入假的 baostock 模块并 reload，使 bs / HAS_BAOSTOCK 绑定。"""
    fake_bs = MagicMock()
    fake_bs.login = MagicMock()
    fake_bs.logout = MagicMock()
    monkeypatch.setitem(sys.modules, "baostock", fake_bs)
    import fetchers.kline.baostock_kline as bk
    importlib.reload(bk)
    bk._bs_logged_in = False
    return bk, fake_bs


class TestEnsureLoggedIn:
    def test_first_call_logs_in(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._ensure_logged_in()
        fake_bs.login.assert_called_once()
        assert bk._bs_logged_in is True

    def test_second_call_skips_login(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._ensure_logged_in()
        bk._ensure_logged_in()
        assert fake_bs.login.call_count == 1

    def test_concurrent_login_once(self, baostock_module):
        bk, fake_bs = baostock_module
        barrier = threading.Barrier(4)

        def _call():
            barrier.wait()
            bk._ensure_logged_in()

        threads = [threading.Thread(target=_call) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert fake_bs.login.call_count == 1


class TestLogout:
    def test_logout_when_logged_in(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        bk._logout()
        fake_bs.logout.assert_called_once()
        assert bk._bs_logged_in is False

    def test_logout_when_not_logged_in(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._bs_logged_in = False
        bk._logout()
        fake_bs.logout.assert_not_called()

    def test_logout_handles_exception(self, baostock_module):
        bk, fake_bs = baostock_module
        fake_bs.logout.side_effect = RuntimeError("net")
        bk._bs_logged_in = True
        bk._logout()  # 不应抛异常
        assert bk._bs_logged_in is False


class TestBaostockKlineFetcherFetch:
    def test_no_baostock_returns_none(self, baostock_module):
        """HAS_BAOSTOCK=False 时返回 None。"""
        bk, _ = baostock_module
        with patch.object(bk, "HAS_BAOSTOCK", False):
            fetcher = bk.BaostockKlineFetcher()
            assert fetcher.fetch("sh600519") is None

    def test_non_daily_scale_returns_none(self, baostock_module):
        bk, _ = baostock_module
        bk._bs_logged_in = True
        fetcher = bk.BaostockKlineFetcher()
        # scale=60（分钟线）应返回 None
        assert fetcher.fetch("sh600519", scale=60) is None

    def test_sh_code_format(self, baostock_module):
        """60/68/51/56/58 开头的代码归 sh。"""
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        rs = MagicMock()
        rs.error_code = "0"
        rs.next = MagicMock(return_value=False)
        fake_bs.query_history_k_data_plus.return_value = rs
        fetcher = bk.BaostockKlineFetcher()
        fetcher.fetch("sh600519", scale=240, datalen=10)
        args = fake_bs.query_history_k_data_plus.call_args[0]
        assert args[0] == "sh.600519"

    def test_sz_code_format(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        rs = MagicMock()
        rs.error_code = "0"
        rs.next = MagicMock(return_value=False)
        fake_bs.query_history_k_data_plus.return_value = rs
        fetcher = bk.BaostockKlineFetcher()
        fetcher.fetch("sz000001", scale=240, datalen=10)
        args = fake_bs.query_history_k_data_plus.call_args[0]
        assert args[0] == "sz.000001"

    def test_query_error_returns_none(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        rs = MagicMock()
        rs.error_code = "1"  # 错误
        fake_bs.query_history_k_data_plus.return_value = rs
        fetcher = bk.BaostockKlineFetcher()
        assert fetcher.fetch("sh600519", scale=240) is None

    def test_successful_fetch(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        rs = MagicMock()
        rs.error_code = "0"
        rows = [
            ["2025-01-01", "10.0", "10.5", "9.8", "10.3", "1000"],
            ["2025-01-02", "10.3", "10.8", "10.2", "10.7", "1200"],
        ]
        rs.next = MagicMock(side_effect=[True, True, False])
        rs.get_row_data = MagicMock(side_effect=rows)
        fake_bs.query_history_k_data_plus.return_value = rs
        fetcher = bk.BaostockKlineFetcher()
        result = fetcher.fetch("sh600519", scale=240, datalen=10)
        assert len(result) == 2
        assert result[0]["day"] == "2025-01-01"
        assert result[0]["source"] == "baostock"
        assert result[1]["close"] == "10.7"

    def test_empty_result_returns_none(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        rs = MagicMock()
        rs.error_code = "0"
        rs.next = MagicMock(return_value=False)  # 无数据
        fake_bs.query_history_k_data_plus.return_value = rs
        fetcher = bk.BaostockKlineFetcher()
        assert fetcher.fetch("sh600519", scale=240) is None

    def test_query_exception_returns_none(self, baostock_module):
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        fake_bs.query_history_k_data_plus.side_effect = RuntimeError("net error")
        fetcher = bk.BaostockKlineFetcher()
        assert fetcher.fetch("sh600519", scale=240) is None

    def test_row_with_less_than_6_fields_skipped(self, baostock_module):
        """行字段不足 6 个时跳过。"""
        bk, fake_bs = baostock_module
        bk._bs_logged_in = True
        rs = MagicMock()
        rs.error_code = "0"
        rows = [
            ["2025-01-01", "10.0"],  # 不足 6 个，跳过
            ["2025-01-02", "10.3", "10.8", "10.2", "10.7", "1200"],  # 有效
        ]
        rs.next = MagicMock(side_effect=[True, True, False])
        rs.get_row_data = MagicMock(side_effect=rows)
        fake_bs.query_history_k_data_plus.return_value = rs
        fetcher = bk.BaostockKlineFetcher()
        result = fetcher.fetch("sh600519", scale=240, datalen=10)
        assert len(result) == 1


class TestFetcherInit:
    def test_fetcher_name_and_priority(self, baostock_module):
        bk, _ = baostock_module
        fetcher = bk.BaostockKlineFetcher()
        assert fetcher.name == "baostock_kline"
        assert fetcher.priority == 1

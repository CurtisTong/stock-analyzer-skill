import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetchWithFallback:
    def test_empty_list(self):
        from common.fetcher_base import fetch_with_fallback
        assert fetch_with_fallback([]) is None

    def test_single_fetcher(self):
        from common.fetcher_base import fetch_with_fallback, BaseFetcher, NOT_HANDLED
        mock_f = MagicMock()
        mock_f.is_available.return_value = True
        mock_f.fetch.return_value = {"data": "ok"}
        mock_f.priority = 10
        result = fetch_with_fallback([mock_f], "sh600519")
        assert result == {"data": "ok"}
        mock_f.on_success.assert_called()

    def test_fallback_on_failure(self):
        from common.fetcher_base import fetch_with_fallback
        f1 = MagicMock()
        f1.is_available.return_value = True
        f1.fetch.side_effect = Exception("fail")
        f1.priority = 10
        f2 = MagicMock()
        f2.is_available.return_value = True
        f2.fetch.return_value = {"data": "ok2"}
        f2.priority = 5
        result = fetch_with_fallback([f1, f2], "sh600519")
        assert result == {"data": "ok2"}
        f1.on_failure.assert_called()

    def test_all_fail(self):
        from common.fetcher_base import fetch_with_fallback
        f1 = MagicMock()
        f1.is_available.return_value = True
        f1.fetch.side_effect = Exception("fail")
        f1.priority = 10
        f2 = MagicMock()
        f2.is_available.return_value = True
        f2.fetch.side_effect = Exception("fail2")
        f2.priority = 5
        result = fetch_with_fallback([f1, f2], "sh600519")
        assert result is None

    def test_unsafe_code(self):
        from common.fetcher_base import fetch_with_fallback
        f1 = MagicMock()
        f1.is_available.return_value = True
        result = fetch_with_fallback([f1], "'; DROP TABLE--")
        assert result is None


class TestDataFetcherManager:
    def test_apply_source_config(self):
        from common.fetcher_base import DataFetcherManager, BaseFetcher
        f = MagicMock(spec=BaseFetcher)
        f.provider = "tencent"
        f.priority = 5
        f.enabled = True
        f.timeout = 10
        f.retry = 1
        cfg = {"tencent": {"priority": 99, "enabled": False, "timeout": 20, "retry": 3}}
        DataFetcherManager([f], source_config=cfg)
        assert f.priority == 99
        assert f.enabled is False

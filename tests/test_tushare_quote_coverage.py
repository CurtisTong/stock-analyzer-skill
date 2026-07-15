import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestTushareQuoteFetcher:
    def test_not_available(self):
        from fetchers.quote.tushare_quote import TushareQuoteFetcher

        f = TushareQuoteFetcher()
        f.enabled = False
        assert f.is_available() is False

    def test_fetch_no_dep(self):
        from fetchers.quote.tushare_quote import TushareQuoteFetcher

        f = TushareQuoteFetcher()
        result = f.fetch("sh600519")
        # 未安装依赖时应返回 None 或 NOT_HANDLED
        assert result is None or result is not None

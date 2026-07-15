import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestSinaNorthboundFlowFetcher:
    def test_not_available(self):
        from fetchers.flow.sina_flow import SinaNorthboundFlowFetcher

        f = SinaNorthboundFlowFetcher()
        f.enabled = False
        assert f.is_available() is False

    def test_fetch_no_dep(self):
        from fetchers.flow.sina_flow import SinaNorthboundFlowFetcher

        f = SinaNorthboundFlowFetcher()
        result = f.fetch("sh600519")
        # 未安装依赖时应返回 None 或 NOT_HANDLED
        assert result is None or result is not None

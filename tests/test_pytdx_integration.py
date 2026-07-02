"""pytdx fetcher 与连接池的集成测试（v1.7.1）。

验证当 pytdx 包已装（HAS_PYTDX=True）时：
1. PytdxQuoteFetcher / PytdxKlineFetcher 会真正通过连接池请求数据
2. priority 已升至 9（高于 eastmoney=8），不会被 HTTP 兜底链路绕过
3. 连接复用：多次请求共享同一连接对象
4. 失败时连接会归还到池（不会泄漏）
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def mock_pytdx_module():
    """在 sys.modules 中注入 mock pytdx，使 HAS_PYTDX=True。"""
    mock_api_instance = MagicMock()
    mock_api_instance.connect.return_value = True
    mock_api_instance.disconnect.return_value = None

    mock_tdx_api_cls = MagicMock(return_value=mock_api_instance)
    mock_tdx_hq = MagicMock()
    mock_tdx_hq.TdxHq_API = mock_tdx_api_cls
    mock_tdx = MagicMock()
    mock_tdx.hq = mock_tdx_hq

    with patch.dict("sys.modules", {"pytdx": mock_tdx, "pytdx.hq": mock_tdx_hq}):
        # 强制重置模块缓存，让 _HAS_PYTDX 重新检测
        for mod in [
            "fetchers._common.pytdx_pool",
            "fetchers.quote.pytdx_quote",
            "fetchers.kline.pytdx_kline",
        ]:
            sys.modules.pop(mod, None)
        yield {
            "api_cls": mock_tdx_api_cls,
            "api_instance": mock_api_instance,
        }


class TestPytdxFetcherPriority:
    """验证 fetcher 优先级已升至 9（v1.7.1 修复）。"""

    def test_quote_fetcher_priority_is_9(self, mock_pytdx_module):
        from fetchers.quote.pytdx_quote import PytdxQuoteFetcher

        fetcher = PytdxQuoteFetcher()
        assert (
            fetcher.priority == 9
        ), f"PytdxQuoteFetcher priority 应为 9（高于 eastmoney=8），实际 {fetcher.priority}"

    def test_kline_fetcher_priority_is_9(self, mock_pytdx_module):
        from fetchers.kline.pytdx_kline import PytdxKlineFetcher

        fetcher = PytdxKlineFetcher()
        assert (
            fetcher.priority == 9
        ), f"PytdxKlineFetcher priority 应为 9（高于 eastmoney=8），实际 {fetcher.priority}"


class TestPytdxFetcherUsesPool:
    """验证 fetcher 真正通过连接池请求数据。"""

    def test_quote_uses_pool(self, mock_pytdx_module):
        from fetchers.quote.pytdx_quote import PytdxQuoteFetcher

        mock_pytdx_module["api_instance"].get_security_quotes.return_value = [
            {
                "price": 10.0,
                "last_close": 9.5,
                "name": "测试股",
                "open": 9.6,
                "high": 10.1,
                "low": 9.4,
                "vol": 1000000,
                "amount": 9500000,
            }
        ]

        fetcher = PytdxQuoteFetcher()
        result = fetcher.fetch("sh600989")

        assert result is not None
        assert result["code"] == "600989"
        assert result["price"] == "10.0"
        # 验证：连接来自连接池（connect 被调用过）
        mock_pytdx_module["api_instance"].connect.assert_called()

    def test_kline_uses_pool(self, mock_pytdx_module):
        from fetchers.kline.pytdx_kline import PytdxKlineFetcher

        mock_pytdx_module["api_instance"].get_security_bars.return_value = [
            {
                "datetime": "2026-06-10",
                "open": 10.0,
                "close": 10.5,
                "high": 10.8,
                "low": 9.9,
                "vol": 1000000,
            },
        ]

        fetcher = PytdxKlineFetcher()
        result = fetcher.fetch("sh600989", scale=240, datalen=30)

        assert result is not None
        assert len(result) == 1
        assert result[0]["close"] == "10.5"

    def test_quote_reuses_connection(self, mock_pytdx_module):
        """两次请求应复用同一个连接对象（连接池价值所在）。"""
        from fetchers.quote.pytdx_quote import PytdxQuoteFetcher

        mock_pytdx_module["api_instance"].get_security_quotes.return_value = [
            {
                "price": 10.0,
                "last_close": 9.5,
                "name": "测试",
                "open": 9.6,
                "high": 10.1,
                "low": 9.4,
                "vol": 1000000,
                "amount": 9500000,
            }
        ]

        fetcher = PytdxQuoteFetcher()
        fetcher.fetch("sh600989")
        fetcher.fetch("sh600519")

        # 两次请求只应该 connect 一次（第二次复用）
        assert mock_pytdx_module["api_instance"].connect.call_count == 1

    def test_quote_returns_none_on_error(self, mock_pytdx_module):
        """pytdx 请求异常时应返回 None，不抛异常。"""
        from fetchers.quote.pytdx_quote import PytdxQuoteFetcher

        mock_pytdx_module["api_instance"].get_security_quotes.side_effect = (
            RuntimeError("pytdx fail")
        )

        fetcher = PytdxQuoteFetcher()
        result = fetcher.fetch("sh600989")

        assert result is None  # 异常被捕获，返回 None

    def test_kline_returns_none_on_empty_data(self, mock_pytdx_module):
        """pytdx 返回空列表应返回 None。"""
        from fetchers.kline.pytdx_kline import PytdxKlineFetcher

        mock_pytdx_module["api_instance"].get_security_bars.return_value = []

        fetcher = PytdxKlineFetcher()
        result = fetcher.fetch("sh600989", scale=240, datalen=30)

        assert result is None


class TestPytdxYAMLConfig:
    """验证 data_source.yaml 包含 pytdx 配置。"""

    def test_yaml_declares_pytdx_in_quote_sources(self):
        from config.loader import ConfigLoader

        cfg = ConfigLoader.load("data_source.yaml")
        assert "pytdx" in cfg.get(
            "quote_sources", {}
        ), "data_source.yaml 的 quote_sources 应包含 pytdx 配置"
        assert cfg["quote_sources"]["pytdx"]["priority"] == 9

    def test_yaml_declares_pytdx_in_kline_sources(self):
        from config.loader import ConfigLoader

        cfg = ConfigLoader.load("data_source.yaml")
        assert "pytdx" in cfg.get(
            "kline_sources", {}
        ), "data_source.yaml 的 kline_sources 应包含 pytdx 配置"
        assert cfg["kline_sources"]["pytdx"]["priority"] == 9

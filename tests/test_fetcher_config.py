"""P0-03: BaseFetcher timeout/retry 配置生效测试。

验证 data_source.yaml 中的 timeout/retry 字段被 _apply_source_config 正确读取，
并传递到 BaseFetcher 实例的 self.timeout/self.retry 属性。
"""

import sys
from pathlib import Path

# 确保 scripts/ 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common.fetcher_base import BaseFetcher, DataFetcherManager


class _StubFetcher(BaseFetcher):
    """测试用 stub fetcher，记录传入的 timeout/retry。"""

    def __init__(self, name, priority=0, provider=None):
        super().__init__(name, priority=priority, provider=provider)

    def fetch(self, code, **kwargs):
        return {"code": code, "timeout": self.timeout, "retry": self.retry}


def test_default_timeout_retry():
    """未配置时使用默认值 timeout=10, retry=3。"""
    f = _StubFetcher("test_quote", priority=5)
    assert f.timeout == 10
    assert f.retry == 3


def test_apply_source_config_sets_timeout_retry():
    """_apply_source_config 从 source_config 读取 timeout/retry。"""
    fetchers = [
        _StubFetcher("tencent_quote", priority=10, provider="tencent"),
        _StubFetcher("eastmoney_quote", priority=8, provider="eastmoney"),
    ]
    source_config = {
        "tencent": {"priority": 10, "enabled": True, "timeout": 5, "retry": 1},
        "eastmoney": {"priority": 8, "enabled": True, "timeout": 15, "retry": 2},
    }
    DataFetcherManager(fetchers, source_config=source_config)

    tencent = fetchers[0]
    eastmoney = fetchers[1]
    assert tencent.timeout == 5
    assert tencent.retry == 1
    assert eastmoney.timeout == 15
    assert eastmoney.retry == 2


def test_apply_source_config_partial_config():
    """只配 timeout 不配 retry 时，retry 保持默认。"""
    fetchers = [_StubFetcher("sina_quote", priority=5, provider="sina")]
    source_config = {"sina": {"timeout": 8}}
    DataFetcherManager(fetchers, source_config=source_config)
    assert fetchers[0].timeout == 8
    assert fetchers[0].retry == 3  # 默认值


def test_apply_source_config_no_timeout_retry():
    """配置中无 timeout/retry 时，保持默认值。"""
    fetchers = [_StubFetcher("ths_quote", priority=3, provider="ths")]
    source_config = {"ths": {"priority": 3, "enabled": True}}
    DataFetcherManager(fetchers, source_config=source_config)
    assert fetchers[0].timeout == 10
    assert fetchers[0].retry == 3


def test_fetcher_passes_timeout_to_result():
    """fetcher.fetch 返回值携带实际 timeout/retry，验证属性可被读取。"""
    f = _StubFetcher("test_quote", priority=5)
    f.timeout = 7
    f.retry = 2
    result = f.fetch("sh600989")
    assert result["timeout"] == 7
    assert result["retry"] == 2

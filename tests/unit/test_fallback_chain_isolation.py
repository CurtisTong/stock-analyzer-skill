"""降级链（数据血缘）隔离性测试（v1.24.0 复审修复）。

背景：降级链原本挂在 manager 单例上、每次 fetch 开头整体重置，
导致并发场景下指数的降级事件被贴到个股行上，缓存命中路径还会
保留上一次请求的残留链——血缘结论不可信。
"""

from __future__ import annotations

import threading

import pytest


class _FailingFetcher:
    """总是失败的 fetcher 桩。"""

    def __init__(self, name, provider, error=None):
        self.name = name
        self.provider = provider
        self.priority = 10
        self.error = error or RuntimeError("boom")
        self.enabled = True

    def is_available(self):
        return True

    def on_success(self):
        pass

    def on_failure(self):
        pass

    def fetch(self, code, **kwargs):
        raise self.error


class _OkFetcher:
    def __init__(self, name, provider):
        self.name = name
        self.provider = provider
        self.priority = 1
        self.enabled = True

    def is_available(self):
        return True

    def on_success(self):
        pass

    def on_failure(self):
        pass

    def fetch(self, code, **kwargs):
        return {"code": code, "source": self.provider}


def _manager(fetchers):
    from common.fetcher_base import DataFetcherManager

    return DataFetcherManager(fetchers)


class TestChainIsolation:
    def test_chain_scoped_by_code(self):
        """不同标的的降级事件不得互相污染。"""
        # 用普通异常而非 429：429 会写入进程级 RateLimiter 的退避窗口，
        # 污染后续用例（同 provider 被跳过 → 链为空），掩盖本用例要验证的行为
        m = _manager(
            [
                _FailingFetcher("fail_a", "testfail_a"),
                _OkFetcher("ok_a", "testok_a"),
            ]
        )
        m.fetch("sh600519")
        m.fetch("sz000001")

        chain_a = m.fallback_chain("sh600519")
        chain_b = m.fallback_chain("sz000001")
        assert len(chain_a) == 1
        assert len(chain_b) == 1
        assert chain_a[0]["provider"] == "testfail_a"
        assert chain_a[0]["event"] == "error"

    def test_unknown_code_has_empty_chain(self):
        """未 fetch 过的标的链为空（不会拿到别人的链）。"""
        m = _manager([_OkFetcher("ok_b", "testok_b")])
        m.fetch("sh600519")
        assert m.fallback_chain("sz000001") == []

    def test_concurrent_fetches_do_not_mix(self):
        """并发 fetch 不同 code 时，各链不得串台。"""
        m = _manager(
            [
                _FailingFetcher("fail_c", "testfail_c"),
                _OkFetcher("ok_c", "testok_c"),
            ]
        )
        results = {}

        def _worker(code):
            m.fetch(code)
            results[code] = m.fallback_chain(code)

        threads = [threading.Thread(target=_worker, args=(f"sh60000{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for code in results:
            chain = results[code]
            assert len(chain) == 1, f"{code} 的链被污染: {chain}"
            assert chain[0]["provider"] == "testfail_c"


class TestChainRendering:
    def test_render_uses_provider_and_detail(self):
        """血缘行格式：provider + detail（不是 fetcher 名 + 事件码）。"""
        from business.stock_analysis import _attach_fallback_details
        import data as data_mod

        chain = [
            {"provider": "sina", "name": "sina_quote", "event": "429", "detail": "rate limited"},
            {"provider": "xueqiu", "name": "xueqiu_quote", "event": "empty", "detail": "无数据"},
        ]

        class _FakeManager:
            def fallback_chain(self, code):
                return chain

        original = data_mod.get_last_fallback_chain
        try:
            data_mod.get_last_fallback_chain = lambda domain, code=None: chain
            result = {"data_sources": ["行情[tencent]"]}
            _attach_fallback_details(result, "quote", code="sh600519")
        finally:
            data_mod.get_last_fallback_chain = original

        text = result["data_sources"][-1]
        assert "sina rate limited" in text
        assert "xueqiu 无数据" in text
        assert "sina quote" not in text, "不该用 fetcher 名渲染"


class TestNoChainForCleanFetch:
    def test_clean_fetch_leaves_source_untouched(self):
        """无降级时血缘行保持干净（不追加空括号）。"""
        from business.stock_analysis import _attach_fallback_details
        import data as data_mod

        original = data_mod.get_last_fallback_chain
        try:
            data_mod.get_last_fallback_chain = lambda domain, code=None: []
            result = {"data_sources": ["行情[tencent]"]}
            _attach_fallback_details(result, "quote", code="sh600519")
        finally:
            data_mod.get_last_fallback_chain = original

        assert result["data_sources"] == ["行情[tencent]"]

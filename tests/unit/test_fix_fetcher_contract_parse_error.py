"""review 4.1-P2 回归测试：JSON 解码失败抛 ParseError，不再伪装成"无数据"。

覆盖本 agent 可改的 4 处：kline/eastmoney、kline/tencent、
finance/eastmoney、flow/eastmoney；同时验证真正的"无此数据"仍返回 None。
"""

from __future__ import annotations

import json

import pytest

from common.exceptions import ParseError


def _getter(response):
    def _http_get(url, timeout=10, max_retries=3):
        if isinstance(response, (bytes, bytearray)):
            return response
        return json.dumps(response).encode("utf-8")

    return _http_get


@pytest.mark.parametrize(
    "module,class_name,code",
    [
        ("fetchers.kline.eastmoney_kline", "EastmoneyKlineFetcher", "sh600519"),
        ("fetchers.kline.tencent_kline", "TencentKlineFetcher", "sh600519"),
        ("fetchers.finance.eastmoney_finance", "EastmoneyFinanceFetcher", "sh600519"),
        ("fetchers.flow.eastmoney_flow", "StockFlowFetcher", "sh600519"),
    ],
)
def test_json_decode_error_raises_parse_error(monkeypatch, module, class_name, code):
    """反爬 HTML/损坏 JSON -> ParseError（manager 记 error 并累计熔断）。"""
    import importlib

    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, "http_get", _getter(b"<html>blocked</html>"))

    with pytest.raises(ParseError):
        getattr(mod, class_name)().fetch(code)


@pytest.mark.parametrize(
    "module,class_name,code,empty_response",
    [
        ("fetchers.kline.eastmoney_kline", "EastmoneyKlineFetcher", "sh600519", {"rc": -1}),
        ("fetchers.kline.tencent_kline", "TencentKlineFetcher", "sh600519", {"code": -1}),
        ("fetchers.finance.eastmoney_finance", "EastmoneyFinanceFetcher", "sh600519", {}),
        ("fetchers.flow.eastmoney_flow", "StockFlowFetcher", "sh600519", {"rc": -1}),
    ],
)
def test_no_data_still_returns_none(monkeypatch, module, class_name, code, empty_response):
    """合法 JSON 但确实无数据 -> None（不误触发熔断）。"""
    import importlib

    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, "http_get", _getter(empty_response))

    assert getattr(mod, class_name)().fetch(code) is None


def test_manager_records_parse_error_as_error_event(monkeypatch):
    """manager 视角：ParseError 记为 error 血缘 + last_error，并触发 on_failure。"""
    import fetchers.finance.eastmoney_finance as mod
    from common.fetcher_base import DataFetcherManager

    monkeypatch.setattr(mod, "http_get", _getter(b"<html>403</html>"))

    fetcher = mod.EastmoneyFinanceFetcher()
    fetcher.circuit_breaker.reset()  # 避免全局单例残留状态影响断言
    mgr = DataFetcherManager([fetcher])

    assert mgr.fetch("sh600519") is None
    assert isinstance(mgr.last_error, ParseError)
    chain = mgr.fallback_chain("sh600519")
    assert len(chain) == 1
    assert chain[0]["event"] == "error"
    assert fetcher.circuit_breaker.failure_count == 1

"""数据血缘补齐：胜出源（provider）记录（P0-4b）。

降级链只回答"谁失败、为什么切"；报告首行要展示"最后是谁供的数"，需要 manager
记录最近的成功 provider。本文件锁定三件事：
1. manager 在主源成功与 429 重试成功两条路径都记录 provider；
2. 按 code 归档，不串标的；
3. data_quality 把它写进 winners，首行优先显示真实源。
"""

from __future__ import annotations

import pytest

from common.fetcher_base import BaseFetcher, DataFetcherManager
from common import data_quality as dq


class _Fetcher(BaseFetcher):
    def __init__(self, name, priority, provider, mode):
        super().__init__(name, priority=priority, provider=provider)
        self.mode = mode
        self.calls = 0

    def is_available(self):
        return True

    def fetch(self, code, **kwargs):
        self.calls += 1
        if self.mode == "raise":
            raise RuntimeError("boom")
        if self.mode == "empty":
            return None
        return {"code": code, "from": self.provider}


class TestManagerRecordsProvider:
    def test_primary_success_records_provider(self):
        mgr = DataFetcherManager([_Fetcher("quote_tencent", 10, "tencent", "ok")])
        assert mgr.fetch("sh600519") is not None
        assert mgr.success_provider("sh600519") == "tencent"

    def test_fallback_success_records_second_provider(self):
        first = _Fetcher("quote_sina", 10, "sina", "raise")
        second = _Fetcher("quote_tencent", 5, "tencent", "ok")
        mgr = DataFetcherManager([first, second])
        assert mgr.fetch("sh600519") is not None
        assert mgr.success_provider("sh600519") == "tencent"
        assert first.calls == 1

    def test_empty_then_success_records_winner(self):
        first = _Fetcher("quote_sina", 10, "sina", "empty")
        second = _Fetcher("quote_tencent", 5, "tencent", "ok")
        mgr = DataFetcherManager([first, second])
        mgr.fetch("sh600519")
        assert mgr.success_provider("sh600519") == "tencent"

    def test_provider_is_per_code(self):
        mgr = DataFetcherManager([_Fetcher("quote_tencent", 10, "tencent", "ok")])
        mgr.fetch("sh600519")
        mgr.fetch("sz000001")
        assert mgr.success_provider("sh600519") == "tencent"
        assert mgr.success_provider("sz000001") == "tencent"

    def test_all_fail_records_nothing(self):
        mgr = DataFetcherManager([_Fetcher("quote_sina", 10, "sina", "raise")])
        assert mgr.fetch("sh600519") is None
        assert mgr.success_provider("sh600519") is None

    def test_latest_provider_without_code(self):
        mgr = DataFetcherManager([_Fetcher("quote_tencent", 10, "tencent", "ok")])
        assert mgr.success_provider() is None
        mgr.fetch("sh600519")
        assert mgr.success_provider() == "tencent"


class TestEnvelopeWinners:
    def test_winners_filled_and_header_shows_provider(self, monkeypatch):
        monkeypatch.setattr(dq, "_chain_providers", lambda domain, code=None: [])
        monkeypatch.setattr(dq, "_winner_provider", lambda domain, code=None: "tencent")
        out = dq.envelope({"price": 12.5}, required=("quote",), field_map={"quote": ("price",)})
        assert out["data_quality"]["winners"] == {"quote": "tencent"}
        assert "tencent" in dq.render_header(out["data_quality"])

    def test_header_falls_back_to_chain_then_unrecorded(self, monkeypatch):
        monkeypatch.setattr(dq, "_winner_provider", lambda domain, code=None: None)
        monkeypatch.setattr(dq, "_chain_providers", lambda domain, code=None: ["sina", "xueqiu"])
        out = dq.envelope({"price": 1.0}, required=("quote",), field_map={"quote": ("price",)})
        assert "sina" in dq.render_header(out["data_quality"])

        monkeypatch.setattr(dq, "_chain_providers", lambda domain, code=None: [])
        out2 = dq.envelope({"price": 1.0}, required=("quote",), field_map={"quote": ("price",)})
        assert "未记录" in dq.render_header(out2["data_quality"])

    def test_degraded_status_not_allowed(self, monkeypatch):
        monkeypatch.setattr(dq, "_chain_providers", lambda domain, code=None: [])
        monkeypatch.setattr(dq, "_winner_provider", lambda domain, code=None: "tencent")
        out = dq.envelope(
            {"price": None},
            required=("quote",),
            field_map={"quote": ("price",)},
            failed=("quote",),
        )
        assert out["data_quality"]["conclusions_allowed"] is False
        assert "⚠️" in dq.render_header(out["data_quality"])


@pytest.mark.parametrize("domain", ["quote", "kline", "finance"])
def test_get_last_success_provider_returns_none_for_unknown(domain):
    """未 fetch 过时不得臆测 provider。"""
    from data import get_last_success_provider

    assert get_last_success_provider(domain, code="sh999999") is None

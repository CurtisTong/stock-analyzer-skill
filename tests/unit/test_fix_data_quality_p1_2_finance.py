"""P1-2 回归测试（2026-11-21 review §3.1 #2）：财务防穿透空缓存永不命中。"""

from __future__ import annotations


def _use_tmp_cache(monkeypatch, tmp_path):
    import common.cache as cache_mod

    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)


def test_empty_zero_cache_is_hit_and_prevents_refetch(monkeypatch, tmp_path):
    """写入 [] 后必须能命中，空列表不再是“未命中”。"""
    _use_tmp_cache(monkeypatch, tmp_path)
    import data as data_mod

    data_mod._load_fetchers()
    mgr = data_mod._finance_manager
    calls: list[str] = []

    def fake_fetch(code, periods=4, **kwargs):
        calls.append(code)
        return None  # 所有源都无响应

    original = mgr.fetch
    mgr.fetch = fake_fetch
    try:
        records, meta = data_mod.get_finance("SH600989")
        assert records == []
        assert meta.is_degraded is True
        assert meta.cache_hit is False  # 首次是真实 fetch

        records2, meta2 = data_mod.get_finance("SH600989")
        assert records2 == []
        assert calls == ["SH600989"], "空结果已缓存，5 分钟内不应重复打全源（P1-2）"
        assert meta2.cache_hit is True, "zero_key=[] 必须判为命中"
        assert meta2.is_degraded is True
    finally:
        mgr.fetch = original


def test_main_key_empty_list_routes_to_zero_cache(monkeypatch, tmp_path):
    """主 key 的 [] 也必须按“缓存存在（但无效）”处理，转 zero_key 而非直接穿透。"""
    _use_tmp_cache(monkeypatch, tmp_path)
    import data as data_mod
    from common import cache

    key = cache.cache_key_for_stock("finance", "SH600989", periods=4)
    cache.set_json(key, [])
    cache.set_json(f"{key}_zero", [])

    data_mod._load_fetchers()
    mgr = data_mod._finance_manager
    calls: list[str] = []
    original = mgr.fetch
    mgr.fetch = lambda code, **kw: calls.append(code) or [{"eps": 1.0}]
    try:
        records, meta = data_mod.get_finance("SH600989")
        assert records == []
        assert calls == [], "主 key 空列表 + zero_key 空列表应命中，不得重新 fetch（P1-2）"
        assert meta.cache_hit is True
        assert meta.is_degraded is True
    finally:
        mgr.fetch = original

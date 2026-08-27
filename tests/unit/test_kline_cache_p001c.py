"""本地 K 线缓存验证。

背景：screener 全市场模式每只标的重复拉 K 线曾触发 watchdog 超时。
a/b 已修复（watchdog 1800s + full_market 强制两阶段）；c 项要求本地缓存
K 线，key 为 code_scale_datalen，避免每次重新拉。

现状：get_kline 已接 common.cache 磁盘缓存（key 含 code + scale + datalen，
日 K TTL 1h，其他周期 6h），screener 的 prefetch_kline_all 亦走 get_kline。
本测试验证：同参二次调用命中缓存不重复 fetch；参数变化生成独立缓存。
"""


def _fake_record():
    return {
        "day": "2026-08-11",
        "open": "10.0",
        "high": "11.0",
        "low": "9.5",
        "close": "10.5",
        "volume": "1000",
        "amount": "10500.0",
        "pct_chg": "1.0",
        "source": "tencent",
    }


class TestKlineCacheHit:
    def test_second_call_hits_disk_cache(self, monkeypatch, tmp_path):
        """同 code/scale/datalen 二次调用命中缓存，fetch 仅执行一次。"""
        import common.cache as cache_mod
        import data as data_mod

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)

        data_mod._load_fetchers()
        real_mgr = data_mod._kline_manager
        assert real_mgr is not None, "_kline_manager 懒加载失败"

        calls = []
        original_fetch = real_mgr.fetch

        def fake_fetch(code, scale=240, datalen=30, **kw):
            calls.append(code)
            return [_fake_record()]

        real_mgr.fetch = fake_fetch
        try:
            bars1 = data_mod.get_kline("sh600989", scale=240, datalen=30)
            bars2 = data_mod.get_kline("sh600989", scale=240, datalen=30)
        finally:
            real_mgr.fetch = original_fetch

        assert len(calls) == 1, "第二次调用应命中磁盘缓存，不重复 fetch"
        assert len(bars1) == 1 and len(bars2) == 1

    def test_different_params_get_independent_cache(self, monkeypatch, tmp_path):
        """scale/datalen 变化生成独立 key，各自触发 fetch。"""
        import common.cache as cache_mod
        import data as data_mod

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)

        data_mod._load_fetchers()
        real_mgr = data_mod._kline_manager
        calls = []
        original_fetch = real_mgr.fetch

        def fake_fetch(code, scale=240, datalen=30, **kw):
            calls.append((code, scale, datalen))
            return [_fake_record()]

        real_mgr.fetch = fake_fetch
        try:
            data_mod.get_kline("sh600989", scale=240, datalen=30)
            data_mod.get_kline("sh600989", scale=240, datalen=30)  # 命中
            data_mod.get_kline("sh600989", scale=240, datalen=120)  # 不同 datalen
            data_mod.get_kline("sh600989", scale=1440, datalen=30)  # 不同 scale
        finally:
            real_mgr.fetch = original_fetch

        assert len(calls) == 3, "仅首次 30/240、120/240、30/1440 触发 fetch"

    def test_prefetch_kline_all_reuses_cache(self, monkeypatch, tmp_path):
        """prefetch_kline_all 走 get_kline 同缓存，重复批量调用不重复 fetch。"""
        import common.cache as cache_mod
        import data as data_mod

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)

        data_mod._load_fetchers()
        real_mgr = data_mod._kline_manager
        calls = []
        original_fetch = real_mgr.fetch

        def fake_fetch(code, scale=240, datalen=240, **kw):
            calls.append(code)
            return [_fake_record()]

        real_mgr.fetch = fake_fetch
        from data.helpers import prefetch_kline_all

        try:
            cache1 = prefetch_kline_all(["sh600989", "sz000001"])
            cache2 = prefetch_kline_all(["sh600989", "sz000001"])
        finally:
            real_mgr.fetch = original_fetch

        assert sorted(cache1) == sorted(cache2) == ["sh600989", "sz000001"]
        assert len(calls) == 2, "第二次批量调用全部命中缓存"

"""P2-1/P2-2/P2-3 回归：情绪面板的缓存语义、快照 schema、中位口径标签。"""

from __future__ import annotations

import pytest


@pytest.fixture
def pool_data(monkeypatch):
    """mock 涨停/炸板池数据（两个池各一只）。"""
    import data.sentiment_panel as panel
    import market_breadth as breadth

    limit = [
        {
            "c": "600519",
            "n": "茅台",
            "lbc": 2,
            "zbc": 0,
            "fund": 1e8,
            "ltsz": 1e10,
            "hs": 3.0,
            "zdp": 10.0,
            "hybk": "白酒",
        }
    ]
    broken = [
        {
            "c": "000001",
            "n": "平安",
            "lbc": 1,
            "zbc": 2,
            "fund": 1e7,
            "ltsz": 2e10,
            "hs": 4.0,
            "zdp": 6.5,
            "hybk": "银行",
        }
    ]

    calls = {"n": 0}

    def fake_fetch(endpoint, date):
        calls["n"] += 1
        return limit if endpoint == "getTopicZTPool" else broken

    monkeypatch.setattr(panel, "_fetch_pool", fake_fetch)
    # 测试隔离：重置模块级缓存（共享 state，monkeypatch 不会自动清理）
    panel._cache = {}
    panel._cache_ts = 0.0

    # 跌停家数通道：默认不可用（返回降级 → limit_down_count 留 None）
    def fake_limit_data():
        return {"_degraded": True}

    monkeypatch.setattr(breadth, "get_limit_data", fake_limit_data)
    return calls


class TestRefreshPanelCache:
    """P2-1：显式 date 与默认路径的缓存语义必须一致（按 date 为 key）。"""

    def test_explicit_date_cached(self, pool_data, monkeypatch):
        import data.sentiment_panel as panel

        first = panel.refresh_panel(date="20261020")
        assert first is not None
        first_fetches = pool_data["n"]
        assert first_fetches == 2  # 第一次：涨停池 + 炸板池
        second = panel.refresh_panel(date="20261020")
        assert second is not None
        # 同 date 第二次调用命中缓存，不再重复拉取
        assert (
            pool_data["n"] == first_fetches
        ), f"同 date 重复调用应命中缓存, 实际再拉取 {pool_data['n'] - first_fetches} 次"

    def test_different_dates_fetch_separately(self, pool_data, monkeypatch):
        import data.sentiment_panel as panel

        panel.refresh_panel(date="20261020")
        panel.refresh_panel(date="20261021")
        # 两个不同 date 各拉一次（涨停池+炸板池）= 4 次
        assert pool_data["n"] == 4

    def test_cache_keyed_by_date_not_global(self, pool_data, monkeypatch):
        """不同 date 的缓存不互相污染（修复前全局单槽缓存）。"""
        import data.sentiment_panel as panel

        a = panel.refresh_panel(date="20261020")
        b = panel.refresh_panel(date="20261021")
        assert a["date"] == "20261020"
        assert b["date"] == "20261021"


class TestSnapshotSchema:
    """P2-2：快照必须含 limit_down_count（设计文档 §4.2 引用字段）。"""

    def test_snapshot_has_limit_down_count_field(self, pool_data, monkeypatch):
        import data.sentiment_panel as panel

        snapshot = panel.refresh_panel(date="20261020")
        assert "limit_down_count" in snapshot
        # 降级通道 → None（诚实缺失，不伪装成 0）
        assert snapshot["limit_down_count"] is None

    def test_limit_down_count_not_taken_for_historical_backfill(self, monkeypatch):
        """历史回填不得写入"今天"的跌停家数（v1.28.0 修复）。

        get_limit_data() 内部用 datetime.now() 取当天的跌停池，回填历史日期时
        会把今天的跌停家数写进历史快照——存档数据被污染，且该文件是
        回测/IC 的数据源，后续接上赚钱效应因子即成真前视。
        现在只有采集当日才取该字段，历史回填一律留 None（诚实缺失）。
        """
        import data.sentiment_panel as panel
        import market_breadth as breadth

        called = {"n": 0}

        def ok_limit_data():
            called["n"] += 1
            return {"_degraded": False, "limit_down_count": 7}

        monkeypatch.setattr(breadth, "get_limit_data", ok_limit_data)
        snapshot = panel.refresh_panel(date="20261020")
        assert snapshot["limit_down_count"] is None
        assert called["n"] == 0, "历史回填不应调用只返回今天数据的通道"

    def test_limit_down_count_taken_for_today(self, monkeypatch):
        """当日采集仍应取跌停家数（字段要真的有值）。

        回归修复（2026-11-03）：本测试原先依赖真实涨停/炸板池接口
        （push2ex，当日无数据时 _fetch_pool 返回空 → refresh_panel 返回
        None → 断言 TypeError）。按 FRAMEWORK.md 规范 mock 池接口，
        让"当日采集"路径脱离网络确定性执行。
        """
        import data.sentiment_panel as panel
        import market_breadth as breadth
        from datetime import datetime

        def ok_limit_data():
            return {"_degraded": False, "limit_down_count": 7}

        def fake_pool(endpoint, date):
            return [{"c": "600989", "n": "宝丰能源", "hybk": "煤炭", "lbc": 1}]

        monkeypatch.setattr(breadth, "get_limit_data", ok_limit_data)
        monkeypatch.setattr(panel, "_fetch_pool", fake_pool)
        today = datetime.now().strftime("%Y%m%d")
        snapshot = panel.refresh_panel(date=today)
        assert snapshot is not None
        assert snapshot["limit_down_count"] == 7


class TestMedianChgLabel:
    """P2-3：median_chg_pct 口径是涨停+炸板合并（CLI 标签须诚实）。"""

    def test_median_mixes_both_pools(self, pool_data, monkeypatch):
        import data.sentiment_panel as panel

        snapshot = panel.refresh_panel(date="20261020")
        # 涨停 10.0 + 炸板 6.5 → 合并中位数 8.25
        assert snapshot["median_chg_pct"] == pytest.approx(8.25)

    def test_cli_label_mentions_both(self):
        import sentiment_panel

        src = open(sentiment_panel.__file__, encoding="utf-8").read()
        assert "涨停/炸板中位涨幅" in src, "CLI 标签必须说明包含炸板池（此前称'涨停中位涨幅'）"
        assert "涨停中位涨幅" not in src

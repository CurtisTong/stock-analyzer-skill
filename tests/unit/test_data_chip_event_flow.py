"""data.chip / data.event / data.flow 数据域单元测试。

通过替换 LazyFetcherRegistry 缓存与 fetch_with_breaker 返回值，
离线验证聚合逻辑与转换函数，触发方式见 fetch_with_breaker 熔断+限流单测。
"""

from types import SimpleNamespace

import pytest

import data.chip as chip
import data.event as event
import data.flow as flow


def _fake_fetcher(name="margin", result=None, exc=None):
    """构造最小 fetcher stub（满足 fetch_with_breaker 属性访问）。"""
    f = SimpleNamespace()
    f.name = name
    f.provider = "mock"
    f.is_available = lambda: True
    f.on_failure = lambda: None
    f.on_success = lambda: None

    def _fetch(*args, **kwargs):
        if exc is not None:
            raise exc
        return result

    f.fetch = _fetch
    return f


class TestChipDictConverters:
    """_dict_to_* 转换函数字段映射。"""

    def test_margin(self):
        m = chip._dict_to_margin(
            {
                "date": "2026-08-11",
                "code": "sh600989",
                "rzye": "1.5",
                "rqye": "2.5",
                "rzjme": "0.5",
                "rqyl": "100",
            }
        )
        assert m.date == "2026-08-11"
        assert m.rzye == 1.5
        assert m.rqye == 2.5
        assert m.rzjme == 0.5
        assert m.rqyl == 100.0
        assert m.rzmre == 0.0  # 缺失默认 0

    def test_holder(self):
        h = chip._dict_to_holder(
            {
                "end_date": "2026-06-30",
                "code": "sh600989",
                "holder_num": "12345",
                "holder_num_change": "-3.5",
                "concentration": "持续集中",
            }
        )
        assert h.holder_num == 12345
        assert h.holder_num_change == -3.5
        assert h.concentration == "持续集中"

    def test_top_holder(self):
        t = chip._dict_to_top_holder(
            {
                "end_date": "2026-06-30",
                "rank": "1",
                "holder_name": "张三",
                "holder_type": "个人",
                "hold_num": "100.5",
                "hold_ratio": "5.0",
                "change": "10",
                "change_type": "增持",
                "is_institution": True,
            }
        )
        assert t.rank == 1
        assert t.holder_name == "张三"
        assert t.is_institution is True
        assert t.change_type == "增持"


class TestChipGet:
    """get_margin / get_holders / get_top_holders 基础路径。"""

    @pytest.fixture(autouse=True)
    def _registry(self, monkeypatch, tmp_path):
        monkeypatch.setattr(chip._registry, "_cache", [])
        yield

    def test_margin_fetcher_none(self, monkeypatch):
        monkeypatch.setattr(chip._registry, "find", lambda name: None)
        assert chip.get_margin("sh600989") == []

    def test_margin_fetcher_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            chip._registry, "find", lambda name: _fake_fetcher(result=[])
        )
        assert chip.get_margin("sh600989") == []

    def test_margin_returns_data(self, monkeypatch):
        f = _fake_fetcher(result=[{"date": "2026-08-11", "rzye": "1.0"}])
        monkeypatch.setattr(chip._registry, "find", lambda name: f)
        data = chip.get_margin("sh600989", days=20)
        assert len(data) == 1
        assert data[0].rzye == 1.0

    def test_holders_and_top_holders(self, monkeypatch):
        fh = _fake_fetcher(
            result=[
                {"end_date": "2026-06-30", "holder_num": "100", "concentration": "波动"}
            ]
        )
        ft = _fake_fetcher(
            result=[{"end_date": "2026-06-30", "rank": "1", "holder_name": "A"}]
        )
        monkeypatch.setattr(
            chip._registry, "find", lambda name: fh if name == "holder" else ft
        )
        hs = chip.get_holders("sh600989", periods=4)
        assert len(hs) == 1 and hs[0].holder_num == 100
        ts = chip.get_top_holders("sh600989")
        assert len(ts) == 1 and ts[0].holder_name == "A"


class TestMarginSummary:
    """get_margin_summary 趋势/比/情绪判定。"""

    def _rows(self, rzjme_values, rzye=1e8, rqye=1e6):
        rs = []
        for i, v in enumerate(rzjme_values):
            rs.append(
                chip.MarginData(
                    date=f"2026-08-{10 - i:02d}",
                    rzye=rzye,
                    rqye=rqye,
                    rzjme=v,
                )
            )
        return rs

    def test_empty(self, monkeypatch):
        monkeypatch.setattr(chip, "get_margin", lambda code, days=20: [])
        assert chip.get_margin_summary("sh600989") == {}

    def test_increasing_and_bullish(self, monkeypatch):
        monkeypatch.setattr(
            chip, "get_margin", lambda code, days=20: self._rows([1, 2, 3])
        )
        s = chip.get_margin_summary("sh600989")
        assert s["rzjme_5d"] == 6
        assert s["rzjme_trend"] == "连续增加"
        assert s["rz_ratio"] == 100.0  # 1e8/1e6
        assert s["sentiment"] == "偏多"

    def test_decreasing_and_bearish(self, monkeypatch):
        _rows = self._rows([-1, -2, -3], rzye=1e8, rqye=1e8)
        monkeypatch.setattr(chip, "get_margin", lambda code, days=20: _rows)
        s = chip.get_margin_summary("sh600989")
        assert s["rzjme_trend"] == "连续减少"
        assert s["rz_ratio"] == 1.0
        assert s["sentiment"] == "偏空"

    def test_mixed_sum_positive_ratio_high_bullish(self, monkeypatch):
        """sum>0 且 rz_ratio>30 → 偏多（趋势波动不影响情绪判定）。"""
        monkeypatch.setattr(
            chip, "get_margin", lambda code, days=20: self._rows([1, -2, 3])
        )
        s = chip.get_margin_summary("sh600989")
        assert s["rzjme_5d"] == 2
        assert s["rzjme_trend"] == "波动"
        assert s["sentiment"] == "偏多"

    def test_neutral_when_sum_positive_but_low_ratio(self, monkeypatch):
        """sum>0 但 rz_ratio<=30（融券占比高）→ 中性。"""
        rows = self._rows([1, 2], rzye=1e8, rqye=1e7)  # ratio=10
        monkeypatch.setattr(chip, "get_margin", lambda code, days=20: rows)
        s = chip.get_margin_summary("sh600989")
        assert s["rzjme_5d"] == 3
        assert s["sentiment"] == "中性"

    def test_sorted_by_date_desc(self, monkeypatch):
        """返回顺序乱序时应按日期降序再取近5日。"""
        rows = self._rows([10.0, 20.0, 30.0])
        monkeypatch.setattr(
            chip, "get_margin", lambda code, days=20: list(reversed(rows))
        )
        s = chip.get_margin_summary("sh600989")
        assert s["rzjme_5d"] == 60.0


class TestHoldersSummary:
    """get_holders_summary 集中度/趋势。"""

    def _holder(self, change, concentration="波动"):
        return chip.HolderData(
            end_date="2026-06-30",
            holder_num=100,
            holder_num_change=change,
            concentration=concentration,
        )

    def test_empty(self, monkeypatch):
        monkeypatch.setattr(chip, "get_holders", lambda code, periods=4: [])
        assert chip.get_holders_summary("sh600989") == {}

    def test_concentrating(self, monkeypatch):
        hs = [self._holder(-1, "持续集中"), self._holder(-2), self._holder(-3)]
        monkeypatch.setattr(chip, "get_holders", lambda code, periods=4: hs)
        s = chip.get_holders_summary("sh600989")
        assert s["trend"] == "持续集中"
        assert s["concentration"] == "持续集中"
        assert s["change_rate"] == -1

    def test_dispersing(self, monkeypatch):
        hs = [self._holder(1), self._holder(2), self._holder(3)]
        monkeypatch.setattr(chip, "get_holders", lambda code, periods=4: hs)
        s = chip.get_holders_summary("sh600989")
        assert s["trend"] == "持续分散"
        assert s["concentration"] == "分散"

    def test_mixed_uses_latest_rating(self, monkeypatch):
        hs = [self._holder(1, "提升"), self._holder(-1), self._holder(2)]
        monkeypatch.setattr(chip, "get_holders", lambda code, periods=4: hs)
        s = chip.get_holders_summary("sh600989")
        assert s["trend"] == "波动"
        assert s["concentration"] == "提升"

    def test_single_period_data_insufficient(self, monkeypatch):
        monkeypatch.setattr(
            chip, "get_holders", lambda code, periods=4: [self._holder(-1)]
        )
        s = chip.get_holders_summary("sh600989")
        assert s["trend"] == "数据不足"
        assert s["concentration"] == "波动"


class TestEventGetEvents:
    """get_events 按子类型聚合 + 摘要生成。"""

    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.setattr(event._registry, "_cache", [])
        yield

    def _fets(self, **type_results):
        fets = []
        for name, data in type_results.items():
            fets.append(_fake_fetcher(name=name, result=data))
        return fets

    def test_no_fetchers_empty_summary(self, monkeypatch):
        monkeypatch.setattr(event._registry, "get_all", lambda: [])
        r = event.get_events("sh600519")
        assert r["summary"] == "近 30 日无重大事件"
        assert r["code"] == "sh600519"

    def test_aggregates_types_and_summary(self, monkeypatch):
        fets = self._fets(
            earnings={"type": "earnings", "items": [{"disclosure_date": "2026-08-20"}]},
            lockup={"type": "lockup", "items": [{"free_date": "2026-09-01"}]},
            dividend={"type": "dividend", "items": [{"ex_date": "2026-08-15"}]},
        )
        monkeypatch.setattr(event._registry, "get_all", lambda: fets)
        r = event.get_events("sh600519")
        assert r["earnings"][0]["disclosure_date"] == "2026-08-20"
        assert r["lockup"][0]["free_date"] == "2026-09-01"
        assert "📊 财报披露: 2026-08-20" in r["summary"]
        assert "🔓 解禁: 2026-09-01" in r["summary"]
        assert "💰 分红: 2026-08-15" in r["summary"]

    def test_shareholder_increase_direction(self, monkeypatch):
        fets = self._fets(
            shareholder={
                "type": "shareholder",
                "items": [{"direction": "increase", "end_date": "2026-08-01"}],
            }
        )
        monkeypatch.setattr(event._registry, "get_all", lambda: fets)
        r = event.get_events("sh600519")
        assert "👤 大股东增持: 2026-08-01" in r["summary"]

    def test_shareholder_decrease_direction(self, monkeypatch):
        fets = self._fets(
            shareholder={"type": "shareholder", "items": [{"end_date": "2026-08-01"}]}
        )
        monkeypatch.setattr(event._registry, "get_all", lambda: fets)
        r = event.get_events("sh600519")
        assert "👤 大股东减持: 2026-08-01" in r["summary"]

    def test_violation_and_forecast_summary(self, monkeypatch):
        fets = self._fets(
            violation={"type": "violation", "items": [{"punish_date": "2026-08-02"}]},
            forecast={
                "type": "forecast",
                "items": [{"forecast_type_raw": "预增", "notice_date": "2026-08-03"}],
            },
        )
        monkeypatch.setattr(event._registry, "get_all", lambda: fets)
        r = event.get_events("sh600519")
        assert "⚠️ 违规: 2026-08-02" in r["summary"]
        assert "📋 业绩预告(预增): 2026-08-03" in r["summary"]

    def test_fetcher_exception_skipped(self, monkeypatch):
        fets = self._fets(earnings={"type": "earnings", "items": []})
        fets[0].fetch = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("boom"))
        monkeypatch.setattr(event._registry, "get_all", lambda: fets)
        r = event.get_events("sh600519")
        assert r["earnings"] == []
        assert r["summary"] == "近 30 日无重大事件"

    def test_fetcher_without_items_ignored(self, monkeypatch):
        fets = self._fets(earnings={"type": "earnings", "items": []})
        monkeypatch.setattr(event._registry, "get_all", lambda: fets)
        r = event.get_events("sh600519")
        assert r["earnings"] == []
        assert "无重大事件" in r["summary"]


class TestFlowNorthBound:
    """get_northbound_flow 多源降级与格式转换。"""

    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.setattr(flow._registry, "_cache", [])
        yield

    def _nb_fetcher(self, days_data=None, name="northbound_eastmoney", exc=None):
        result = {"days": days_data} if days_data is not None else None
        return _fake_fetcher(name=name, result=result, exc=exc)

    def test_no_northbound_fetcher(self, monkeypatch):
        monkeypatch.setattr(flow._registry, "get_all", lambda: [])
        assert flow.get_northbound_flow("sh600519") == []

    def test_success_converts_days(self, monkeypatch):
        fetchers = [
            self._nb_fetcher(
                [{"date": "2026-08-11", "total_net": 100.0, "sh_net": 60, "sz_net": 40}]
            )
        ]
        monkeypatch.setattr(flow._registry, "get_all", lambda: fetchers)
        r = flow.get_northbound_flow("sh600519")
        assert len(r) == 1
        assert r[0]["date"] == "2026-08-11"
        assert r[0]["net_buy"] == 100.0
        assert r[0]["sh_net"] == 60

    def test_empty_days_falls_through_to_next_source(self, monkeypatch):
        """第一个源 days 为空 → 降级第二源。"""
        fetchers = [
            self._nb_fetcher(days_data=[], name="northbound_eastmoney"),
            self._nb_fetcher(
                [{"date": "2026-08-11", "total_net": 5, "sh_net": 3}],
                name="northbound_sina",
            ),
        ]
        monkeypatch.setattr(flow._registry, "get_all", lambda: fetchers)
        r = flow.get_northbound_flow("sh600519")
        assert len(r) == 1
        assert r[0]["sh_net"] == 3

    def test_fetch_exception_continues_next(self, monkeypatch):
        fetchers = [
            self._nb_fetcher(exc=ConnectionError("down"), name="northbound_eastmoney"),
            self._nb_fetcher(
                [{"date": "2026-08-11", "total_net": 8}], name="northbound_sina"
            ),
        ]
        monkeypatch.setattr(flow._registry, "get_all", lambda: fetchers)
        r = flow.get_northbound_flow("sh600519")
        assert len(r) == 1
        assert r[0]["net_buy"] == 8

    def test_all_sources_fail_returns_empty(self, monkeypatch):
        fetchers = [
            self._nb_fetcher(days_data=[], name="northbound_eastmoney"),
            self._nb_fetcher(days_data=[], name="northbound_sina"),
        ]
        monkeypatch.setattr(flow._registry, "get_all", lambda: fetchers)
        assert flow.get_northbound_flow("sh600519") == []


class TestFlowStockFlow:
    """get_stock_flow 个股资金流。"""

    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.setattr(flow._registry, "_cache", [])
        yield

    def test_fetcher_missing(self, monkeypatch):
        monkeypatch.setattr(flow._registry, "find", lambda name: None)
        assert flow.get_stock_flow("sh600519") is None

    def test_success(self, monkeypatch):
        f = _fake_fetcher(name="stock_flow", result={"type": "stock_flow", "days": []})
        monkeypatch.setattr(flow._registry, "find", lambda name: f)
        r = flow.get_stock_flow("sh600519")
        assert r is not None
        assert r["type"] == "stock_flow"

    def test_exception_returns_none(self, monkeypatch):
        f = _fake_fetcher(name="stock_flow", exc=ConnectionError("boom"))
        monkeypatch.setattr(flow._registry, "find", lambda name: f)
        assert flow.get_stock_flow("sh600519") is None

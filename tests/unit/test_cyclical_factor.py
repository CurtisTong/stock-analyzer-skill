"""周期因子 + macro_indicators 商品期货数据层单元测试。

覆盖 v2.5.x 修复：
- macro_indicators: akshare 实时拉取 + fixture 兜底 + 分位计算
- classifier: infer_industry 周期细分桶（铝/铜/钢铁/基础化工）
- cyclical: 品种映射（product_mapping 兜底）+ _cost_dimension 用分位产出 high/low
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════
# macro_indicators: akshare 实时 + fixture 兜底
# ═══════════════════════════════════════════════════════════════


def _make_futures_df(prices: list[float]):
    """构造模拟的 futures_zh_daily_sina 返回 DataFrame。"""
    import pandas as pd

    dates = pd.date_range(end="2026-08-04", periods=len(prices), freq="B")
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [100000] * len(prices),
            "hold": [200000] * len(prices),
            "settle": prices,
        }
    )


def _make_energy_index_df(values: list[float]):
    """构造模拟的 macro_china_energy_index 返回 DataFrame。"""
    import pandas as pd

    dates = pd.date_range(end="2026-08-04", periods=len(values), freq="B")
    return pd.DataFrame(
        {
            "日期": dates.strftime("%Y-%m-%d"),
            "最新值": values,
            "涨跌幅": [0.0] * len(values),
        }
    )


class TestCalcPercentile:
    """_calc_percentile 分位计算。"""

    def test_high_percentile(self):
        from macro_indicators import _calc_percentile

        # 末位是序列最高价
        history = list(range(1, 101))  # 1..100, 末位 100 是最高
        assert _calc_percentile(history) == 99.0

    def test_low_percentile(self):
        from macro_indicators import _calc_percentile

        history = list(range(100, 0, -1))  # 100..1, 末位 1 是最低
        assert _calc_percentile(history) == 0.0

    def test_mid_percentile(self):
        from macro_indicators import _calc_percentile

        history = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 55]
        pct = _calc_percentile(history)
        # 55 大于 10,20,30,40,50 共 5 个，5/11 = 45.5
        assert pct == 45.5

    def test_too_short_returns_none(self):
        from macro_indicators import _calc_percentile

        assert _calc_percentile([1, 2, 3]) is None
        assert _calc_percentile([]) is None


class TestFetchAluminumAkshare:
    """fetch_aluminum: akshare 实时优先 + fixture 兜底。"""

    def test_akshare_live_fetch(self, monkeypatch, tmp_path):
        """akshare 可用时返回实时价 + 分位，并回写 snapshot。"""
        from macro_indicators import fetch_aluminum

        # 模拟 250 个交易日价格，末位 23810（高分位）
        prices = [20000 + i * 15 for i in range(250)]  # 20000..23735
        prices[-1] = 23810  # 最新价高于全部历史 -> 高分位

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(
            json.dumps({"updated": "2020-01-01T00:00:00"})  # 过期，触发实时拉取
        )

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)
        monkeypatch.setattr(mi, "_akshare_get", lambda s: 23810.0)
        monkeypatch.setattr(mi, "_akshare_get_history", lambda s, lookback=250: prices)

        result = fetch_aluminum()
        assert result is not None
        assert result["source"] == "akshare"
        assert result["value"] == 23810.0
        assert result["symbol"] == "AL0"
        assert result["percentile"] is not None
        assert result["percentile"] > 90  # 23810 高于全部历史

        # 验证回写 snapshot
        saved = json.loads(snapshot.read_text())
        assert saved["aluminum_cny_t"] == 23810.0
        assert "aluminum_percentile_1y" in saved

    def test_fresh_fixture_short_circuits(self, monkeypatch, tmp_path):
        """新鲜 fixture（per-key TTL 内）直接返回，不调 akshare。"""
        from macro_indicators import fetch_aluminum

        now = datetime.now().isoformat(timespec="seconds")
        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(
            json.dumps(
                {
                    "updated": "2020-01-01T00:00:00",  # 全局过期
                    "aluminum_cny_t": 19500.0,
                    "aluminum_cny_t_ts": now,  # per-key 新鲜
                    "aluminum_percentile_1y": 45.0,
                }
            )
        )

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)

        call_count = 0

        def _fail_if_called(s):
            nonlocal call_count
            call_count += 1
            raise AssertionError("不应调用 akshare")

        monkeypatch.setattr(mi, "_akshare_get", _fail_if_called)

        result = fetch_aluminum()
        assert result is not None
        assert result["source"] == "fixture"
        assert result["value"] == 19500.0
        assert result["percentile"] == 45.0
        assert call_count == 0

    def test_akshare_failure_falls_back_to_stale_fixture(self, monkeypatch, tmp_path):
        """akshare 拉取失败时回退过期 fixture。"""
        from macro_indicators import fetch_aluminum

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(
            json.dumps(
                {
                    "updated": "2020-01-01T00:00:00",  # 过期
                    "aluminum_cny_t": 19500.0,
                }
            )
        )

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)
        monkeypatch.setattr(mi, "_akshare_get", lambda s: None)  # 模拟失败

        result = fetch_aluminum()
        assert result is not None
        assert result["source"] == "fixture(stale)"
        assert result["value"] == 19500.0

    def test_akshare_unavailable_no_fixture_returns_none(self, monkeypatch, tmp_path):
        """akshare 失败且无 fixture 时返回 None。"""
        from macro_indicators import fetch_aluminum

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(json.dumps({"updated": "2020-01-01T00:00:00"}))

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)
        monkeypatch.setattr(mi, "_akshare_get", lambda s: None)

        assert fetch_aluminum() is None


class TestPerKeyFreshnessIndependence:
    """per-key TTL 独立性：第一个 fetcher 成功后，第二个仍独立拉取。

    回归测试：修复前 _save_snapshot 刷新全局 updated，导致同批次后续 fetcher
    被 TTL 短路走 fixture（即使自己的数据是旧的）。修复后每个 key 独立判断。
    """

    def test_second_fetcher_not_short_circuited(self, monkeypatch, tmp_path):
        """连续调用两个不同 fetcher，第二个不应被第一个的回写短路。"""
        from macro_indicators import fetch_aluminum, fetch_copper

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(json.dumps({"updated": "2020-01-01T00:00:00"}))  # 全部过期

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)

        # 记录每个 symbol 是否被实际拉取
        fetched_symbols = []

        def _mock_get(symbol):
            fetched_symbols.append(symbol)
            return {"AL0": 23810.0, "CU0": 106650.0}[symbol]

        def _mock_history(symbol, lookback=250):
            return [20000 + i for i in range(250)]

        monkeypatch.setattr(mi, "_akshare_get", _mock_get)
        monkeypatch.setattr(mi, "_akshare_get_history", _mock_history)

        # 连续调用两个不同 fetcher
        res1 = fetch_aluminum()
        res2 = fetch_copper()

        # 两个都应成功拉取 akshare 实时数据
        assert res1["source"] == "akshare"
        assert res1["value"] == 23810.0
        assert res2["source"] == "akshare"
        assert res2["value"] == 106650.0

        # 核心断言：两个 symbol 都被实际拉取（第二个没被短路）
        assert "AL0" in fetched_symbols
        assert "CU0" in fetched_symbols

    def test_same_fetcher_cached_after_success(self, monkeypatch, tmp_path):
        """同一 fetcher 第二次调用应命中 per-key TTL 短路（不重复拉取）。"""
        from macro_indicators import fetch_aluminum

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(json.dumps({"updated": "2020-01-01T00:00:00"}))

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)

        call_count = 0

        def _counting_get(symbol):
            nonlocal call_count
            call_count += 1
            return 23810.0

        monkeypatch.setattr(mi, "_akshare_get", _counting_get)
        monkeypatch.setattr(
            mi, "_akshare_get_history", lambda s, lookback=250: [20000] * 250
        )

        # 第一次：实时拉取
        res1 = fetch_aluminum()
        assert res1["source"] == "akshare"
        assert call_count == 1

        # 第二次：per-key TTL 短路
        res2 = fetch_aluminum()
        assert res2["source"] == "fixture"
        assert call_count == 1  # 没有再次拉取

    def test_per_key_ts_written_to_snapshot(self, monkeypatch, tmp_path):
        """成功拉取后 snapshot 应写入 {key}_ts 字段。"""
        from macro_indicators import fetch_aluminum

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(json.dumps({"updated": "2020-01-01T00:00:00"}))

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)
        monkeypatch.setattr(mi, "_akshare_get", lambda s: 23810.0)
        monkeypatch.setattr(
            mi, "_akshare_get_history", lambda s, lookback=250: [20000] * 250
        )

        fetch_aluminum()

        saved = json.loads(snapshot.read_text())
        assert "aluminum_cny_t_ts" in saved
        assert "aluminum_percentile_1y" in saved


class TestFetchCoalEnergyIndex:
    """fetch_coal: 能源指数代理。"""

    def test_energy_index_proxy(self, monkeypatch, tmp_path):
        """akshare 能源指数可用时返回代理值 + 分位。"""
        from macro_indicators import fetch_coal

        values = [900 + i for i in range(100)]  # 900..999
        values[-1] = 1002  # 最新值高位

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(json.dumps({"updated": "2020-01-01T00:00:00"}))

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)
        monkeypatch.setattr(mi, "_akshare_get_energy_index", lambda: (1002.0, 99.0))

        result = fetch_coal()
        assert result is not None
        assert result["source"] == "energy_index_proxy"
        assert result["value"] == 1002.0
        assert result["percentile"] == 99.0
        assert "EMI00662539" in result["symbol"]

    def test_energy_index_failure_falls_back(self, monkeypatch, tmp_path):
        """能源指数失败时回退 stale fixture。"""
        from macro_indicators import fetch_coal

        snapshot = tmp_path / "macro_snapshot.json"
        snapshot.write_text(
            json.dumps({"updated": "2020-01-01T00:00:00", "coal_thermal_cny_t": 850.0})
        )

        import macro_indicators as mi

        monkeypatch.setattr(mi, "SNAPSHOT_PATH", snapshot)
        monkeypatch.setattr(mi, "_akshare_get_energy_index", lambda: (None, None))

        result = fetch_coal()
        assert result is not None
        assert result["source"] == "fixture(stale)"
        assert result["value"] == 850.0


# ═══════════════════════════════════════════════════════════════
# classifier: 周期细分桶
# ═══════════════════════════════════════════════════════════════


class TestInferIndustryCyclicalSubclass:
    """infer_industry 周期细分为铝/铜/钢铁/基础化工。"""

    def test_aluminum_subclass(self):
        from classifier import infer_industry

        assert infer_industry("云铝股份", "sz000807") == "铝"
        assert infer_industry("中国铝业", "sh601600") == "铝"

    def test_copper_subclass(self):
        from classifier import infer_industry

        assert infer_industry("江西铜业", "sh600362") == "铜"

    def test_steel_subclass(self):
        from classifier import infer_industry

        assert infer_industry("宝钢股份", "sh600019") == "钢铁"
        assert infer_industry("宝钢钢铁", "") == "钢铁"

    def test_chemical_subclass(self):
        from classifier import infer_industry

        assert infer_industry("万华化学", "sh600309") == "基础化工"

    def test_generic_cyclical_fallback(self):
        """无法细分的周期股回退粗类"周期"。"""
        from classifier import infer_industry

        assert infer_industry("紫金矿业", "sh601899") == "周期"
        assert infer_industry("海螺水泥", "sh600585") == "周期"

    def test_non_cyclical_unchanged(self):
        """非周期行业不受细分影响。"""
        from classifier import infer_industry

        assert infer_industry("贵州茅台白酒", "") == "消费"
        assert infer_industry("招商银行", "") == "银行"


# ═══════════════════════════════════════════════════════════════
# cyclical: 品种映射 + 成本维度分位
# ═══════════════════════════════════════════════════════════════


class TestResolveMaterial:
    """_resolve_material: product_mapping 优先，industry 映射兜底。"""

    def test_product_mapping_takes_priority(self):
        from strategies.factors.cyclical import _resolve_material

        # 紫金矿业名字含"矿业"->粗类"周期"，但 product_mapping 兜底到 copper
        assert _resolve_material("周期", "sh601899") == "copper"

    def test_industry_mapping_when_no_code(self):
        from strategies.factors.cyclical import _resolve_material

        assert _resolve_material("铝", "") == "aluminum"
        assert _resolve_material("铜", "") == "copper"
        assert _resolve_material("钢铁", "") == "rebar"

    def test_industry_mapping_when_code_not_in_mapping(self):
        from strategies.factors.cyclical import _resolve_material

        # code 不在 product_mapping 中，回退 industry 映射
        assert _resolve_material("铝", "sz999999") == "aluminum"

    def test_no_mapping_returns_none(self):
        from strategies.factors.cyclical import _resolve_material

        assert _resolve_material("默认", "") is None
        assert _resolve_material("科技", "sh688001") is None


class TestCostDimensionPercentile:
    """_cost_dimension: 用分位产出 high/low 信号。"""

    def _mock_fetcher(self, monkeypatch, price_data):
        """mock _fetch_raw_material_price 返回指定数据。"""
        from strategies.factors import cyclical

        monkeypatch.setattr(cyclical, "_fetch_raw_material_price", lambda k: price_data)

    def test_high_percentile_yields_high(self, monkeypatch):
        from strategies.factors.cyclical import _cost_dimension

        self._mock_fetcher(
            monkeypatch,
            {"value": 23810.0, "percentile": 85.0, "source": "akshare"},
        )
        result = _cost_dimension("铝", "sz000807")
        assert result["position"] == "high"
        assert result["evaluable"] is True
        assert "原料高位" in result["detail"]

    def test_low_percentile_yields_low(self, monkeypatch):
        from strategies.factors.cyclical import _cost_dimension

        self._mock_fetcher(
            monkeypatch,
            {"value": 12000.0, "percentile": 15.0, "source": "akshare"},
        )
        result = _cost_dimension("铝", "sz000807")
        assert result["position"] == "low"
        assert result["evaluable"] is True
        assert "原料低位" in result["detail"]

    def test_mid_percentile_yields_mid(self, monkeypatch):
        from strategies.factors.cyclical import _cost_dimension

        self._mock_fetcher(
            monkeypatch,
            {"value": 20000.0, "percentile": 50.0, "source": "akshare"},
        )
        result = _cost_dimension("铝", "sz000807")
        assert result["position"] == "mid"
        assert result["evaluable"] is True

    def test_no_percentile_yields_mid(self, monkeypatch):
        """有价格但无分位时返回中性（可评估但不产出信号）。"""
        from strategies.factors.cyclical import _cost_dimension

        self._mock_fetcher(
            monkeypatch,
            {"value": 19500.0, "percentile": None, "source": "fixture(stale)"},
        )
        result = _cost_dimension("铝", "sz000807")
        assert result["position"] == "mid"
        assert result["evaluable"] is True
        assert "无分位" in result["detail"]

    def test_no_price_data_not_evaluable(self, monkeypatch):
        from strategies.factors.cyclical import _cost_dimension

        self._mock_fetcher(monkeypatch, None)
        result = _cost_dimension("铝", "sz000807")
        assert result["position"] == "mid"
        assert result["evaluable"] is False
        assert "缺失" in result["detail"]

    def test_no_material_mapping(self, monkeypatch):
        from strategies.factors.cyclical import _cost_dimension

        result = _cost_dimension("科技", "sh688001")
        assert result["position"] == "mid"
        assert result["evaluable"] is False
        assert "无原料映射" in result["detail"]


class TestCyclicalScoreIntegration:
    """cyclical_score 端到端：成本维度真正参与评分。"""

    def test_yunlu_aluminum_uses_aluminum_not_rebar(self, monkeypatch):
        """云铝股份（铝桶）成本维度应用铝价，不再用螺纹钢。

        修复前：infer_industry("云铝股份")="周期"->_cost_dimension 用 rebar
        修复后：infer_industry("云铝股份")="铝"->_cost_dimension 用 aluminum
        """
        from strategies.factors import cyclical

        fetched_materials = []

        def _spy_fetch(material_key):
            fetched_materials.append(material_key)
            return {"value": 23810.0, "percentile": 85.0, "source": "akshare"}

        monkeypatch.setattr(cyclical, "_fetch_raw_material_price", _spy_fetch)

        fin = {"net_profit_yoy": 35.0, "roe_trend": [8.0, 9.5, 11.0, 12.5]}
        quote = {"pe": 14.0, "pb": 1.8}

        # 云铝股份：industry 经 infer_industry 细分为"铝"
        cyclical.cyclical_score(fin, quote, {}, "铝", "sz000807")

        # 确认成本维度拉取的是 aluminum，不是 rebar
        assert "aluminum" in fetched_materials
        assert "rebar" not in fetched_materials

    def test_cost_dimension_now_participates_in_scoring(self, monkeypatch):
        """成本维度产出 high 信号时影响总分（不再永远中性 50）。"""
        from strategies.factors import cyclical

        # 价格维度中性、供给维度中性、成本维度 high（原料高分位=周期顶部）
        monkeypatch.setattr(
            cyclical,
            "_fetch_raw_material_price",
            lambda k: {"value": 23810.0, "percentile": 90.0, "source": "akshare"},
        )

        fin = {"net_profit_yoy": 10.0, "roe_trend": [10.0, 10.0, 10.0]}
        quote = {"pe": 20.0, "pb": 2.0}  # 估值中性

        score = cyclical.cyclical_score(fin, quote, {}, "铝", "sz000807")

        # 成本维度 high + 价格/供给中性 -> 1 个高位信号 -> base_score=40（< 50）
        # 修复前成本维度永远 mid，三维度全中性 -> 50
        assert score < 50.0, f"成本维度应拉低分数（周期顶部风险），实际 {score}"

    def test_non_cyclical_returns_neutral(self):
        from strategies.factors.cyclical import cyclical_score

        score = cyclical_score(
            {"net_profit_yoy": 20.0}, {"pe": 30.0, "pb": 5.0}, {}, "科技", "sh688001"
        )
        assert score == 50.0

    def test_code_param_optional_backward_compat(self):
        """code 参数可选，不传时向后兼容。"""
        from strategies.factors.cyclical import cyclical_score

        # 不传 code 不应报错
        score = cyclical_score(
            {"net_profit_yoy": 20.0}, {"pe": 30.0, "pb": 5.0}, {}, "科技"
        )
        assert score == 50.0


class TestGetCyclePositionWithCode:
    """get_cycle_position 接受 code 参数。"""

    def test_code_param_accepted(self, monkeypatch):
        from strategies.factors import cyclical

        monkeypatch.setattr(
            cyclical,
            "_fetch_raw_material_price",
            lambda k: {"value": 23810.0, "percentile": 90.0, "source": "akshare"},
        )
        fin = {"net_profit_yoy": 10.0, "roe_trend": [10.0, 10.0, 10.0]}
        quote = {"pe": 20.0, "pb": 2.0}

        # 传 code 不报错
        position = cyclical.get_cycle_position(fin, quote, "铝", "sz000807")
        assert position in ("high", "mid", "low")

    def test_code_optional(self):
        from strategies.factors.cyclical import get_cycle_position

        # 不传 code 不报错
        position = get_cycle_position({}, {"pe": 0, "pb": 0}, "科技")
        assert position == "unknown"

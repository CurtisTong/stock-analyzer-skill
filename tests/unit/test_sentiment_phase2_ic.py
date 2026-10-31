"""情绪因子阶段 2 测试：IC 链路接通 + 无前瞻性。

背景：
- v3.0 的因子 IC 机制整条链路是纸面的——引擎算了 parts 不输出，
  compute_all_factor_ic / save_ic / load_ic 都没有调用方。
- 情绪因子进入回测必须按**历史时点**取快照；用最新快照算历史因子是未来函数。
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def snapshots(tmp_path, monkeypatch):
    """写两份历史快照（供按日期查询与晋级率验证）。"""
    import data.sentiment_panel as panel

    path = tmp_path / "sentiment_snapshots.json"
    monkeypatch.setattr(panel, "_snapshot_path", lambda: path)

    def _snap(date, codes):
        return {
            "date": date,
            "limit_up_count": len(codes),
            "broken_count": 0,
            "max_height": 2,
            "height_distribution": {"1": len(codes)},
            "median_chg_pct": 10.0,
            "sectors": {"专用设备": {"limit_up": len(codes), "broken": 0, "count": len(codes)}},
            "stocks": {
                c: {
                    "code": c,
                    "name": "测试",
                    "status": "limit_up",
                    "lbc": 2,
                    "zbc": 0,
                    "fund": 1e8,
                    "ltsz": 1e10,
                    "hs": 3.0,
                    "zdp": 10.0,
                    "sector": "专用设备",
                }
                for c in codes
            },
        }

    panel.save_snapshot(_snap("20261028", ["sh600001", "sh600002"]))
    panel.save_snapshot(_snap("20261029", ["sh600001"]))
    return path


class TestNoLookahead:
    """情绪因子必须按指定日期取快照（不能用最新快照算历史）。"""

    def test_score_at_uses_that_date(self, snapshots):
        from strategies.factors.sentiment import sentiment_score_at

        # 20261028 有两只，20261029 只有一只
        assert sentiment_score_at("sh600001", "20261028") is not None
        assert sentiment_score_at("sh600002", "20261028") is not None
        # sh600002 在 10-29 的快照里不存在 → 缺失
        assert sentiment_score_at("sh600002", "20261029") is None

    def test_missing_date_returns_none(self, snapshots):
        from strategies.factors.sentiment import sentiment_score_at

        assert sentiment_score_at("sh600001", "20260101") is None

    def test_latest_vs_at_can_differ(self, snapshots):
        """最新快照与指定日期快照是不同数据源（防止误用）。"""
        from strategies.factors.sentiment import sentiment_score, sentiment_score_at

        # 10-29 的 sh600001 存在，最新快照也是 10-29 → 两者一致
        assert sentiment_score("sh600001") == sentiment_score_at("sh600001", "20261029")
        # 10-28 的 sh600002 在最新快照里已不存在
        assert sentiment_score("sh600002") is None
        assert sentiment_score_at("sh600002", "20261028") is not None

    def test_panel_get_snapshot_by_date(self, snapshots):
        from data.sentiment_panel import get_snapshot

        assert get_snapshot("20261028")["limit_up_count"] == 2
        assert get_snapshot("20260101") is None


class TestIcPipelineConnected:
    """因子 IC 链路：engine 的 selections 必须带 parts。"""

    def test_selections_carry_parts(self):
        """引擎输出逐因子分值（IC 评估的前提）。"""
        import inspect

        from backtest import engine

        src = inspect.getsource(engine.simulate_strategy)
        assert '"parts"' in src, "engine 必须把 parts 写进 selections"

    def test_metrics_passes_full_selections(self):
        """metrics 透传全量 selections（前 20 条摘要不足以算 IC）。"""
        import inspect

        from backtest import metrics

        src = inspect.getsource(metrics.run_backtest)
        assert "all_selections" in src

    def test_ic_computable_from_selections(self):
        """构造 selections → IC 可算（链路端到端）。"""
        from strategies.factor.ic import compute_all_factor_ic

        selections = [
            {
                "date": f"2026-10-{d:02d}",
                "parts": {"momentum": 10 + i, "quality": 50 + i},
                "return_pct": i * 0.5,
                "regime": "bull",
            }
            for d in range(1, 3)
            for i in range(10)
        ]
        ic = compute_all_factor_ic(selections)
        assert "momentum" in ic
        assert ic["momentum"] > 0.9  # 两个截面日各自完全正相关
        assert ic["quality"] > 0.9

    def test_ic_cli_exists(self):
        """IC 评估 CLI 存在且可导入。"""
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        spec = importlib.util.spec_from_file_location("factor_ic_cli", root / "scripts" / "factor_ic.py")
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "cmd_evaluate")


class TestFactorIcCrossSectional:
    """P0-4 回归：IC 必须逐日**截面**计算（混池会污染截面相关性）。"""

    def test_level_shift_between_dates_not_polluting(self):
        """两日截面关系相同（各 +1.0），仅第二日收益整体平移——逐日 IC 不受漂移污染。"""
        from strategies.factor.ic import compute_factor_ic

        selections = []
        for d, shift in (("2026-10-01", 0.0), ("2026-10-02", 10.0)):
            for i in range(10):
                selections.append(
                    {
                        "date": d,
                        "parts": {"momentum": float(i)},
                        "return_pct": i * 0.5 + shift,  # 第二日收益整体 +10
                    }
                )
        ic = compute_factor_ic(selections, "momentum")
        assert ic == pytest.approx(1.0, abs=1e-4), f"截面关系被日期间水平漂移污染: {ic}"

    def test_insufficient_cross_section_returns_zero(self):
        """单日样本 < 5 不算 IC（此前混池后弱相关也会给非零值）。"""
        from strategies.factor.ic import compute_factor_ic

        selections = []
        for d in range(10):
            for i in range(4):  # 每天只有 4 只 → 全部剔除
                selections.append({"date": f"2026-11-{d:02d}", "parts": {"momentum": float(i)}, "return_pct": i})
        assert compute_factor_ic(selections, "momentum") == 0.0

    def test_daily_monotone_relation_survives_pooling(self):
        """每天单调关系保持（IC≈1），与旧混池实现区分度验证。"""
        from strategies.factor.ic import compute_factor_ic

        selections = []
        for d in range(3):
            for i in range(8):
                selections.append(
                    {"date": f"2026-12-{d:02d}", "parts": {"quality": float(i)}, "return_pct": float(i) * 2}
                )
        assert compute_factor_ic(selections, "quality") == pytest.approx(1.0, abs=1e-4)

    def test_ic_stats_reports_days_and_samples(self):
        from strategies.factor.ic import compute_factor_ic_stats

        selections = []
        for d in range(3):
            for i in range(8):
                selections.append({"date": f"2026-12-{d:02d}", "parts": {"m": float(i)}, "return_pct": float(i)})
        stats = compute_factor_ic_stats(selections, "m")
        assert stats["days"] == 3
        assert stats["samples"] == 24
        assert stats["ic"] == pytest.approx(1.0, abs=1e-4)


class TestIcToMultiplierFloor:
    """P1-2 回归：IC 衰减的下限必须是**相对**基础值，不能是绝对地板。"""

    def test_ic_negative_does_not_lift_depressed_base(self):
        from strategies.factor.ic import ic_to_multiplier

        # base 已被 extreme_drop 压到 0.24；IC<0 时衰减不得把权重拉回
        base = 0.24
        mult = ic_to_multiplier(-0.5, base)
        assert mult <= base  # 修复前 max(0.5, 0.24*0.5)=0.5 > base（权重被拉高）

    def test_floor_is_relative_to_base(self):
        from strategies.factor.ic import ic_to_multiplier

        base = 1.0
        # ic=-1 → decay=0 → 下限 0.5×base
        assert ic_to_multiplier(-1.0, base) == pytest.approx(0.5)
        # 大 base 时下限按比例放大，不是固定 0.5
        assert ic_to_multiplier(-1.0, 2.0) == pytest.approx(1.0)

    def test_positive_ic_keeps_base(self):
        from strategies.factor.ic import ic_to_multiplier

        assert ic_to_multiplier(0.3, 0.8) == pytest.approx(0.8)

    def test_zero_ic_keeps_base(self):
        from strategies.factor.ic import ic_to_multiplier

        assert ic_to_multiplier(0.0, 0.8) == pytest.approx(0.8)

    def test_engine_uses_historical_snapshot(self):
        """engine 的情绪因子按 bars[i].day 取快照（无前瞻）。"""
        import inspect

        from backtest import engine

        src = inspect.getsource(engine)
        assert "_sentiment_score_at" in src
        assert "sentiment_score_at(code, day.replace" in src

    def test_helper_returns_none_on_failure(self):
        """情绪因子异常时按缺失处理（不得拖垮回测）。"""
        from backtest.engine import _sentiment_score_at

        # 不存在的日期 → None（不是抛错）
        assert _sentiment_score_at("sh600519", "1900-01-01") is None


def _rotation_snapshot(date: str, sector_limit_up: int, total_limit_up: int = 30) -> dict:
    """构造板块轮动测试快照：sh600001 属"专用设备"，其余涨停在"半导体"。"""
    return {
        "date": date,
        "limit_up_count": total_limit_up,
        "broken_count": 0,
        "max_height": 2,
        "height_distribution": {"1": total_limit_up},
        "median_chg_pct": 10.0,
        "sectors": {
            "专用设备": {"limit_up": sector_limit_up, "broken": 0, "count": sector_limit_up},
            "半导体": {
                "limit_up": total_limit_up - sector_limit_up,
                "broken": 0,
                "count": total_limit_up - sector_limit_up,
            },
        },
        "stocks": {
            "sh600001": {
                "code": "sh600001",
                "name": "轮动测试",
                "status": "limit_up",
                "lbc": 2,
                "zbc": 0,
                "fund": 1e8,
                "ltsz": 1e10,
                "hs": 3.0,
                "zdp": 10.0,
                "sector": "专用设备",
            }
        },
    }


# 前 5 日（20261002~20261006）专用设备 3 家、后 5 日（20261007~20261011）4 家
# → 轮动环比 4/3=1.333 ∈ [1.0, 1.5) → +8；板块热度 13.33% → 88。
# 修复后 20261011 板块分 = 96；若轮动窗口读到未来快照（未来 3 日专用设备 1 家）
# → ratio 2.2/3=0.733 → +0，板块分 = 88 → 总分 77.25 vs 75.25。
_HIST_DATES = ["202610%02d" % d for d in range(1, 12)]
_FUTURE_DATES = ["20261012", "20261013", "20261014"]


class TestSectorRotationNoLookahead:
    """板块轮动加分的窗口必须按目标日期截断（防前视）。"""

    @pytest.fixture
    def rotation_snapshots(self, tmp_path, monkeypatch):
        import data.sentiment_panel as panel

        path = tmp_path / "sentiment_snapshots.json"
        monkeypatch.setattr(panel, "_snapshot_path", lambda: path)
        # 后 5 日 4 家、前 5 日 3 家
        for i, date in enumerate(_HIST_DATES):
            n = 4 if i >= 6 else 3
            panel.save_snapshot(_rotation_snapshot(date, n))
        return path

    def _expected_total(self) -> float:
        # 0.3*62.5(连板) + 0.25*94.0(封板) + 0.25*96(板块 88+8) + 0.2*55(活跃)
        return round(0.3 * 62.5 + 0.25 * 94.0 + 0.25 * 96 + 0.2 * 55, 2)

    def test_get_history_respects_as_of(self, rotation_snapshots):
        """get_history(as_of=...) 只返回不晚于该日的快照。"""
        import data.sentiment_panel as panel

        hist = panel.get_history(days=11, as_of="20261011")
        assert [s["date"] for s in hist] == _HIST_DATES
        # as_of 之后注入的快照不进入历史窗口
        hist_shorter = panel.get_history(days=3, as_of="20261006")
        assert [s["date"] for s in hist_shorter] == _HIST_DATES[3:6]

    def test_future_snapshots_do_not_change_historical_score(self, rotation_snapshots):
        """核心不变式：注入未来快照后，历史时点的情绪分必须不变。"""
        import data.sentiment_panel as panel
        from strategies.factors.sentiment import sentiment_score_at

        before = sentiment_score_at("sh600001", "20261011")
        assert before == pytest.approx(self._expected_total())

        # 注入 3 天未来快照（专用设备只剩 1 家——会把未修复实现的轮动环比压到 <1）
        for date in _FUTURE_DATES:
            panel.save_snapshot(_rotation_snapshot(date, 1))
        after = sentiment_score_at("sh600001", "20261011")
        assert after == pytest.approx(before), "未来快照改变了历史时点的情绪分 = 前视偏差"

    def test_fixture_sensitive_to_lookahead(self, rotation_snapshots, monkeypatch):
        """正向控制：若该轮动窗口真的忽略 as_of（旧行为），分数必须不同——证明 fixture 能抓 bug。"""
        import data.sentiment_panel as panel
        from strategies.factors.sentiment import sentiment_score_at

        import data.sentiment_panel as sp_mod

        real_get_history = sp_mod.get_history

        def buggy_get_history(days=5, as_of=None):
            return real_get_history(days)

        monkeypatch.setattr(sp_mod, "get_history", buggy_get_history)
        for date in _FUTURE_DATES:
            panel.save_snapshot(_rotation_snapshot(date, 1))

        polluted = sentiment_score_at("sh600001", "20261011")
        assert polluted != pytest.approx(self._expected_total())


class TestSentimentObservableInBacktest:
    """P0-2 回归：情绪因子在回测中必须可观测（T-1 语义）。

    修复前引擎用评估日当日的收盘后快照：涨停池成员在涨停日（= 入池日）被
    跳过规则排除，sentiment 分在回测里永不可观测。修复后评估日 T 使用
    T-1 快照——T-1 在池、T 日可交易的股票才能拿到分数（打板接力语义），
    同时消除"当日收盘数据用于当日决策"的半日前视。
    """

    def test_sentiment_appears_in_selections_from_t1_snapshot(self, monkeypatch, tmp_path):
        """T-1 快照在池 → 评估日选股的 parts 必须含 sentiment。"""
        from datetime import datetime, timedelta

        import backtest
        from backtest import engine
        from data.types import KlineBar
        import data.sentiment_panel as panel

        # 完全离线的 mock 面（不触网）
        monkeypatch.setattr(engine, "_detect_st_codes", lambda codes: set())
        _finance = {
            "eps": 50.0,
            "roe": 30.5,
            "revenue_yoy": 15.2,
            "net_profit_yoy": 18.3,
            "gross_margin": 91.5,
            "debt_ratio": 18.7,
            "ocf_per_share": 55.0,
        }
        monkeypatch.setattr(
            engine, "get_finance", lambda code: [type("FR", (), {"to_dict": lambda self: dict(_finance)})()]
        )
        monkeypatch.setattr(engine, "infer_industry", lambda name, code: "manufacturing")

        today = datetime.now()
        bars = []
        n = 70
        for i in range(n):
            d = today - timedelta(days=n - i)
            bars.append(
                KlineBar(
                    day=d.strftime("%Y-%m-%d"),
                    close=10 + i * 0.3,
                    open=10 + i * 0.3,
                    high=10 + i * 0.3,
                    low=10 + i * 0.3,
                    volume=1000,
                )
            )
        monkeypatch.setattr(engine, "get_kline", lambda code, scale=240, datalen=65: bars)

        # T-1 快照：第一个评估点 i=60 的前一根 K 线（bars[59]）在涨停池
        snap_date = bars[59].day.replace("-", "")  # 快照键为 YYYYMMDD
        path = tmp_path / "sentiment_snapshots.json"
        monkeypatch.setattr(panel, "_snapshot_path", lambda: path)
        panel.save_snapshot(
            {
                "date": snap_date,
                "limit_up_count": 1,
                "broken_count": 0,
                "max_height": 2,
                "height_distribution": {"1": 1},
                "median_chg_pct": 10.0,
                "sectors": {"专用设备": {"limit_up": 1, "broken": 0, "count": 1}},
                "stocks": {
                    "sh600519": {
                        "code": "sh600519",
                        "name": "情绪测试",
                        "status": "limit_up",
                        "lbc": 2,
                        "zbc": 0,
                        "fund": 1e8,
                        "ltsz": 1e10,
                        "hs": 3.0,
                        "zdp": 10.0,
                        "sector": "专用设备",
                    }
                },
            }
        )
        assert panel.get_snapshot(snap_date) is not None

        result = backtest.simulate_strategy(
            backtest.SimContext(strategy_name="balanced", codes=["sh600519"], top_n=1, holding_days=5)
        )
        assert "error" not in result, result
        selections = result["all_selections"]
        assert selections, "回测应产生选股记录"

        # 第一个评估日（i=60）T-1=bar[59] 在池且当日可交易 → parts 必须含 sentiment
        hit = [s for s in selections if s["date"] == bars[60].day]
        assert hit, f"评估日 {bars[60].day} 应有选股记录"
        assert "sentiment" in hit[0]["parts"], (
            f"T-1 快照（{snap_date}）在池，评估日 {bars[60].day} 的 parts 缺 sentiment——"
            "情绪因子在回测中不可达（P0-2 回归）"
        )
        assert 0 < hit[0]["parts"]["sentiment"] <= 100


class TestIcConsumerWired:
    """P1-3 回归：持久化 IC 必须被 overlay 消费（load_ic 不再是零调用方）。"""

    def _write_ic(self, monkeypatch, tmp_path, updated, ic_by_regime):

        from strategies.factor import ic as ic_mod

        p = tmp_path / "factor_ic.json"
        p.write_text(json.dumps({"updated": updated, "ic": ic_by_regime}), encoding="utf-8")
        monkeypatch.setattr(ic_mod, "IC_FILE", p)
        return p

    def test_fresh_negative_ic_applies_decay(self, monkeypatch, tmp_path):
        """新鲜 IC<0 → 无显式传参也应用衰减（消费端接通）。"""
        from datetime import datetime, timedelta

        from strategies.regime.classifier import RegimeState
        from strategies.regime.overlay import compute_overlay_weights

        updated = (datetime.now() - timedelta(hours=1)).isoformat()
        self._write_ic(monkeypatch, tmp_path, updated, {"range": {"momentum": -0.5}})
        weights = {"quality": 0.3, "valuation": 0.2, "momentum": 0.2, "liquidity": 0.1, "volatility": 0.1}
        base = compute_overlay_weights(weights, RegimeState.RANGE, use_persisted_ic=False)
        adjusted = compute_overlay_weights(weights, RegimeState.RANGE)
        assert adjusted["momentum"] < base["momentum"]

    def test_stale_ic_not_applied(self, monkeypatch, tmp_path):
        """7 天前的 IC 视为过期，不应用。"""
        from datetime import datetime, timedelta

        from strategies.regime.classifier import RegimeState
        from strategies.regime.overlay import compute_overlay_weights

        updated = (datetime.now() - timedelta(days=10)).isoformat()
        self._write_ic(monkeypatch, tmp_path, updated, {"range": {"momentum": -0.5}})
        weights = {"quality": 0.3, "valuation": 0.2, "momentum": 0.2, "liquidity": 0.1, "volatility": 0.1}
        base = compute_overlay_weights(weights, RegimeState.RANGE, use_persisted_ic=False)
        assert compute_overlay_weights(weights, RegimeState.RANGE) == base

    def test_missing_ic_file_noop(self, monkeypatch, tmp_path):
        """无 IC 文件 → 行为与关闭一致。"""
        from strategies.regime.classifier import RegimeState
        from strategies.regime.overlay import compute_overlay_weights

        weights = {"quality": 0.3, "valuation": 0.2, "momentum": 0.2, "liquidity": 0.1, "volatility": 0.1}
        base = compute_overlay_weights(weights, RegimeState.RANGE, use_persisted_ic=False)
        assert compute_overlay_weights(weights, RegimeState.RANGE) == base

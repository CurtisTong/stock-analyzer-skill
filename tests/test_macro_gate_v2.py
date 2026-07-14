"""宏观安全垫 v2.8 新增功能测试。

覆盖：UNKNOWN 状态、A 股维度、TTL 缓存过期、线程安全、仓位建议、
      pipeline 仓位截断、advisory_rebalance、ashare 波动率计算。
"""

import sys
import time
import threading
import statistics
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _seed_cache(gate, vix=None, tlt=None, ashare_vol=None):
    """预置缓存，跳过网络加载。"""
    gate._vix_cache = vix
    gate._tlt_cache = tlt
    gate._ashare_vol = ashare_vol
    gate._cache_ts = time.time()


def _enabled_safe_get(*a, **kw):
    """safe_get mock：enabled 返回 True，其余返回默认值。"""
    if a[1] == "enabled":
        return True
    return a[-1]


# ════════════════════════════════════════
# UNKNOWN 状态测试
# ════════════════════════════════════════


class TestUnknownState:
    """R3: 数据缺失 -> UNKNOWN（不再危险降级 GREEN）。"""

    def test_unknown_when_all_none(self):
        """VIX/TLT/ashare 均 None -> UNKNOWN。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=None, tlt=None, ashare_vol=None)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.UNKNOWN
            assert "数据全部缺失" in msg

    def test_unknown_position_ratio(self):
        """UNKNOWN.position_ratio == 0.5（保守半仓）。"""
        from strategies.macro.gate import MacroState

        assert MacroState.UNKNOWN.position_ratio == 0.5

    def test_partial_data_still_judges(self):
        """VIX=None, TLT 正常 -> 仍可判定（不因部分缺失直接 UNKNOWN）。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=None, tlt=82.0, ashare_vol=None)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            # TLT=82 < 85 -> YELLOW（不是 UNKNOWN）
            assert state == MacroState.YELLOW

    def test_macro_state_is_str_enum(self):
        """MacroState 是 str, Enum（JSON 友好）。"""
        from strategies.macro.gate import MacroState

        assert MacroState.GREEN == "GREEN"
        assert isinstance(MacroState.GREEN.value, str)

    def test_label_property(self):
        """MacroState.label 返回中文标签。"""
        from strategies.macro.gate import MacroState

        assert MacroState.RED.label == "系统性风险"
        assert MacroState.UNKNOWN.label == "数据缺失"


# ════════════════════════════════════════
# A 股维度测试
# ════════════════════════════════════════


class TestAShareDimension:
    """A 股沪深300波动率维度。"""

    def test_ashare_red(self):
        """ashare_vol=40, VIX/TLT 正常 -> RED。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=15.0, tlt=95.0, ashare_vol=40.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.RED
            assert "沪深300波动率 40.0%" in msg

    def test_ashare_yellow(self):
        """ashare_vol=28, VIX/TLT 正常 -> YELLOW。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=15.0, tlt=95.0, ashare_vol=28.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.YELLOW

    def test_ashare_green(self):
        """ashare_vol=15, VIX/TLT 正常 -> GREEN。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=15.0, tlt=95.0, ashare_vol=15.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.GREEN

    def test_message_has_both_dimensions(self):
        """状态消息同时包含美股和 A 股维度信息。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=18.0, tlt=90.0, ashare_vol=20.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            _, msg = gate.check()
            assert "VIX" in msg
            assert "TLT" in msg
            assert "沪深300波动率" in msg


# ════════════════════════════════════════
# TTL 缓存测试
# ════════════════════════════════════════


class TestTTLCache:
    """R1: TTL 缓存过期 + R2: 线程安全。"""

    def test_ttl_not_expired(self):
        """TTL 内不重新加载。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=25.0)
        # 缓存有效，直接返回缓存值
        assert gate._is_cache_valid() is True
        assert gate._fetch_vix() == 25.0

    def test_ttl_expired(self):
        """缓存过期后标记无效。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        # 模拟 10 分钟前加载（TTL=300s）
        gate._cache_ts = time.time() - 600
        assert gate._is_cache_valid() is False

    def test_cache_ts_zero_means_unloaded(self):
        """_cache_ts=0 表示未加载。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        assert gate._cache_ts == 0.0
        assert gate._is_cache_valid() is False

    def test_concurrent_check_no_exception(self):
        """R2: 8 线程并发 check() 无异常（镜像 test_config_loader_concurrent）。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=20.0, tlt=90.0, ashare_vol=18.0)
        results = []
        errors = []
        barrier = threading.Barrier(8)

        def worker():
            try:
                barrier.wait(timeout=5)
                with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
                    state, msg = gate.check()
                    results.append(state)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"并发异常: {errors}"
        assert len(results) == 8
        # 所有线程应得到相同状态
        assert all(r == results[0] for r in results)


# ════════════════════════════════════════
# 仓位建议测试
# ════════════════════════════════════════


class TestPositionRatio:
    """R6: 仓位建议 + YELLOW 消息含仓位上限。"""

    def test_green_position_ratio(self):
        """GREEN.position_ratio == 1.0。"""
        from strategies.macro.gate import MacroState

        assert MacroState.GREEN.position_ratio == 1.0

    def test_red_position_ratio(self):
        """RED.position_ratio == 0.0。"""
        from strategies.macro.gate import MacroState

        assert MacroState.RED.position_ratio == 0.0

    def test_yellow_message_has_ratio(self):
        """YELLOW 消息含 '仓位上限建议 50%'。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=28.0, tlt=90.0, ashare_vol=15.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state.value == "YELLOW"
            assert "仓位上限建议 50%" in msg


# ════════════════════════════════════════
# ashare.py 波动率计算测试
# ════════════════════════════════════════


@dataclass
class _MockBar:
    """模拟 KlineBar。"""
    day: str
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    amount: float = 0.0
    pct_chg: float = 0.0
    source: str = "test"
    fetch_time: str = ""


class TestAShareVol:
    """fetch_ashare_vol 波动率计算。"""

    def test_ashare_vol_calc(self):
        """正常 K 线 -> 返回合理年化波动率。"""
        from strategies.macro.ashare import fetch_ashare_vol

        # 生成 30 根有波动的 K 线
        bars = []
        base = 4000.0
        for i in range(30):
            # 交替涨跌 1%，制造 ~1% 日波动
            close = base * (1 + 0.01 * ((-1) ** i))
            bars.append(_MockBar(day=f"2025-01-{i+1:02d}", open=base, high=close*1.01, low=close*0.99, close=close))
            base = close

        with patch("data.get_kline", return_value=bars):
            vol = fetch_ashare_vol(window=20)
            assert vol is not None
            assert 5.0 < vol < 50.0  # 合理范围

    def test_ashare_vol_insufficient_data(self):
        """K 线不足 -> 返回 None。"""
        from strategies.macro.ashare import fetch_ashare_vol

        bars = [_MockBar(day=f"2025-01-{i+1:02d}", open=10, high=11, low=9, close=10) for i in range(5)]

        with patch("data.get_kline", return_value=bars):
            vol = fetch_ashare_vol(window=20)
            assert vol is None

    def test_ashare_vol_empty_bars(self):
        """空 K 线 -> 返回 None。"""
        from strategies.macro.ashare import fetch_ashare_vol

        with patch("data.get_kline", return_value=[]):
            vol = fetch_ashare_vol()
            assert vol is None

    def test_ashare_vol_exception_returns_none(self):
        """get_kline 抛异常 -> 返回 None。"""
        from strategies.macro.ashare import fetch_ashare_vol

        with patch("data.get_kline", side_effect=Exception("network error")):
            vol = fetch_ashare_vol()
            assert vol is None


# ════════════════════════════════════════
# Pipeline 仓位截断测试
# ════════════════════════════════════════


class TestPipelinePositionControl:
    """screening_pipeline 仓位截断。"""

    def test_yellow_truncates_rows(self):
        """YELLOW 时 rows 被截断为 top * 0.5。"""
        from strategies.macro.gate import MacroState

        # 构造 mock args
        args = MagicMock()
        args.no_macro = False
        args.top = 10
        args.two_stage = False
        args.no_regime = True
        args.no_normalize = True
        args.no_constraints = True
        args.snapshot = False
        args.full_market = False
        args.strategy = "balanced"

        # mock pipeline 依赖
        rows = [{"code": f"sh60000{i}", "score": 100 - i, "rejected": None} for i in range(10)]

        with patch("business.screening_pipeline.load_universe", return_value=["sh600001"]), \
             patch("business.screening_pipeline.fetch_batch_dicts", return_value=[{"code": "sh600001"}]), \
             patch("business.screening_pipeline.prefetch_finance_all", return_value={}), \
             patch("business.screening_pipeline.analyze_code", return_value=rows[0]), \
             patch("strategies.macro.MacroSafetyGate") as MockGate:
            MockGate.return_value.check.return_value = (
                MacroState.YELLOW, "🟡 避险升温 仓位上限建议 50%"
            )
            from business.screening_pipeline import run_screening
            result = run_screening(args)
            assert result["halted"] is False
            assert result["position_ratio"] == 0.5
            # top=10 * 0.5 = 5
            assert len(result["rows"]) <= 5

    def test_green_no_truncation(self):
        """GREEN 时不截断（position_ratio=1.0）。"""
        from strategies.macro.gate import MacroState

        args = MagicMock()
        args.no_macro = False
        args.top = 10
        args.two_stage = False
        args.no_regime = True
        args.no_normalize = True
        args.no_constraints = True
        args.snapshot = False
        args.full_market = False
        args.strategy = "balanced"

        rows = [{"code": f"sh60000{i}", "score": 100 - i, "rejected": None} for i in range(8)]

        with patch("business.screening_pipeline.load_universe", return_value=["sh600001"]), \
             patch("business.screening_pipeline.fetch_batch_dicts", return_value=[{"code": "sh600001"}]), \
             patch("business.screening_pipeline.prefetch_finance_all", return_value={}), \
             patch("business.screening_pipeline.analyze_code", return_value=rows[0]), \
             patch("strategies.macro.MacroSafetyGate") as MockGate:
            MockGate.return_value.check.return_value = (
                MacroState.GREEN, "🟢 宏观稳定"
            )
            from business.screening_pipeline import run_screening
            result = run_screening(args)
            assert result["position_ratio"] == 1.0

    def test_red_halt_returns_empty(self):
        """RED -> halted=True, position_ratio=0.0。"""
        from strategies.macro.gate import MacroState

        args = MagicMock()
        args.no_macro = False
        args.top = 10
        args.two_stage = False
        args.no_regime = True
        args.no_normalize = True
        args.no_constraints = True
        args.snapshot = False
        args.full_market = False
        args.strategy = "balanced"

        with patch("business.screening_pipeline.load_universe", return_value=["sh600001"]), \
             patch("business.screening_pipeline.fetch_batch_dicts", return_value=[{"code": "sh600001"}]), \
             patch("business.screening_pipeline.prefetch_finance_all", return_value={}), \
             patch("strategies.macro.MacroSafetyGate") as MockGate:
            MockGate.return_value.check.return_value = (
                MacroState.RED, "🔴 系统性风险"
            )
            from business.screening_pipeline import run_screening
            result = run_screening(args)
            assert result["halted"] is True
            assert result["position_ratio"] == 0.0
            assert len(result["rows"]) == 0


# ════════════════════════════════════════
# Advisory Rebalance 测试
# ════════════════════════════════════════


class TestAdvisoryRebalance:
    """portfolio advisory_rebalance 方法。"""

    def _make_pm(self, tmp_path, positions=None):
        """构造带测试持仓的 PortfolioManager（用 tmp_path 避免文件锁问题）。"""
        import json
        from portfolio.manager import PortfolioManager

        portfolio_file = tmp_path / "test_portfolio.json"
        data = {
            "version": 2,
            "positions": positions or [],
            "watchlist": [],
        }
        portfolio_file.write_text(json.dumps(data))
        return PortfolioManager(path=str(portfolio_file))

    def test_advisory_rebalance_generates_suggestions(self, tmp_path):
        """target_ratio=0.5 生成 reduce 建议。"""
        positions = [
            {"code": "sh600001", "name": "测试A", "cost": 10.0, "quantity": 1000, "buy_date": "", "tags": []},
            {"code": "sh600002", "name": "测试B", "cost": 20.0, "quantity": 500, "buy_date": "", "tags": []},
        ]
        pm = self._make_pm(tmp_path, positions)

        suggestions = pm.advisory_rebalance(target_ratio=0.5)
        assert len(suggestions) >= 1
        assert all(s["action"] == "reduce" for s in suggestions)
        assert all("宏观50%仓位控制" in s["reason"] for s in suggestions)

    def test_advisory_rebalance_no_positions(self, tmp_path):
        """无持仓 -> 空列表。"""
        pm = self._make_pm(tmp_path, positions=[])

        suggestions = pm.advisory_rebalance(target_ratio=0.5)
        assert suggestions == []

    def test_advisory_rebalance_with_quotes(self, tmp_path):
        """提供 quotes 时按市价计算。"""
        positions = [
            {"code": "sh600001", "name": "测试A", "cost": 10.0, "quantity": 1000, "buy_date": "", "tags": []},
        ]
        pm = self._make_pm(tmp_path, positions)

        # cost=10, quantity=1000 -> 成本市值 10000；quote=15 -> 市价市值 15000
        suggestions = pm.advisory_rebalance(target_ratio=0.5, quotes={"sh600001": 15.0})
        assert len(suggestions) == 1
        # 市价市值 15000 * 0.5 = 7500 target
        assert suggestions[0]["current_value"] == 15000.0
        assert suggestions[0]["target_value"] == 7500.0

    def test_advisory_rebalance_does_not_modify_portfolio(self, tmp_path):
        """调仓建议不修改 portfolio.json（纯只读）。"""
        import json
        positions = [
            {"code": "sh600001", "name": "测试A", "cost": 10.0, "quantity": 1000, "buy_date": "", "tags": []},
        ]
        pm = self._make_pm(tmp_path, positions)
        portfolio_file = pm._path

        mtime_before = portfolio_file.stat().st_mtime
        original_content = portfolio_file.read_text()

        suggestions = pm.advisory_rebalance(target_ratio=0.5)
        assert len(suggestions) >= 1

        # 文件未被修改
        mtime_after = portfolio_file.stat().st_mtime
        assert mtime_before == mtime_after
        assert portfolio_file.read_text() == original_content

    def test_advisory_rebalance_green_no_suggestion(self, tmp_path):
        """target_ratio=1.0（GREEN）-> 无减仓建议。"""
        positions = [
            {"code": "sh600001", "name": "测试A", "cost": 10.0, "quantity": 1000, "buy_date": "", "tags": []},
        ]
        pm = self._make_pm(tmp_path, positions)

        suggestions = pm.advisory_rebalance(target_ratio=1.0)
        assert suggestions == []


# ════════════════════════════════════════
# History 历史数据拉取测试
# ════════════════════════════════════════


class TestHistoryFetch:
    """history.py fetch_history（mock yfinance + get_kline，离线可测）。"""

    def test_fetch_history_writes_csv(self, tmp_path, monkeypatch):
        """fetch_history 落盘 CSV 并返回路径。"""
        import csv as csv_mod
        from strategies.macro import history

        # 重定向 HISTORY_FILE 到 tmp_path
        out_file = tmp_path / "macro_history.csv"
        monkeypatch.setattr(history, "HISTORY_FILE", out_file)

        # mock yfinance: 用轻量对象替代 DataFrame（避免 pandas/numpy 依赖问题）
        class _FakeRow:
            def __init__(self, close):
                self.Close = close
            def __getitem__(self, key):
                return self.Close

        class _FakeHist:
            def __init__(self, items):
                # items: [(date_str, close_value), ...]
                self._items = items
            def iterrows(self):
                from datetime import datetime
                for date_str, close in self._items:
                    yield datetime.strptime(date_str, "%Y-%m-%d"), _FakeRow(close)

        vix_hist = _FakeHist([("2025-01-01", 15.0), ("2025-01-02", 16.0), ("2025-01-03", 18.0)])
        tlt_hist = _FakeHist([("2025-01-01", 90.0), ("2025-01-02", 89.0), ("2025-01-03", 88.0)])

        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.history.side_effect = [vix_hist, tlt_hist]
        monkeypatch.setitem(sys.modules, "yfinance", mock_yf)

        # mock get_kline: 返回 25 根 K 线（足够 20 日波动率计算）
        bars = []
        base = 4000.0
        for i in range(25):
            close = base * (1 + 0.01 * ((-1) ** i))
            bars.append(_MockBar(day=f"2025-01-{i+1:02d}", open=base, high=close*1.01, low=close*0.99, close=close))
            base = close

        monkeypatch.setattr("data.get_kline", lambda *a, **kw: bars)

        path = history.fetch_history(years=1)

        assert path == str(out_file)
        assert out_file.exists()

        # 验证 CSV 内容
        with open(out_file, encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            rows = list(reader)
            assert len(rows) > 0
            assert "date" in rows[0]
            assert "vix" in rows[0]
            assert "tlt" in rows[0]
            assert "csi300_close" in rows[0]
            # 第一行波动率可能为空（数据不足），但后续行应有值
            assert any(r["csi300_vol_20d"] for r in rows)

    def test_fetch_history_empty_data(self, tmp_path, monkeypatch):
        """所有数据源空 -> 仍写入 header（0 数据行）。"""
        from strategies.macro import history

        out_file = tmp_path / "macro_history.csv"
        monkeypatch.setattr(history, "HISTORY_FILE", out_file)

        class _EmptyHist:
            def iterrows(self):
                return iter([])

        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.history.return_value = _EmptyHist()
        monkeypatch.setitem(sys.modules, "yfinance", mock_yf)
        monkeypatch.setattr("data.get_kline", lambda *a, **kw: [])

        path = history.fetch_history(years=1)
        assert out_file.exists()

        with open(out_file, encoding="utf-8") as f:
            lines = f.readlines()
            assert "date" in lines[0]  # header 存在

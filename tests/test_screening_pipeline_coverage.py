"""business/screening_pipeline.py 覆盖测试。

覆盖 _get_screening_service、analyze_code、analyze_code_phase1、
_apply_factor_normalization、run_screening 各分支。所有数据获取均 mock。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import business.screening_pipeline as sp


def _make_args(**kwargs):
    """构造 CLI Namespace。"""
    defaults = dict(
        min_amount=0, min_cap=0, exclude_loss=False,
        strategy="balanced", full_market=False, no_regime=True, no_macro=True,
        two_stage=False, no_normalize=False, top=10,
        no_constraints=False, sector_cap=5, snapshot=False, no_chip=True,
    )
    defaults.update(kwargs)
    return MagicMock(**{k: v for k, v in defaults.items() if not k.startswith("_")})


def _make_quote(code="sh600519", name="茅台", price=100, amount=1e9):
    return {"code": code, "name": name, "price": price, "amount": amount}


class TestGetScreeningService:
    def test_singleton(self):
        sp._screening_service_instance = None
        with patch("business.screening_pipeline.ScreeningService") as MockSvc:
            inst = MagicMock()
            MockSvc.return_value = inst
            s1 = sp._get_screening_service()
            s2 = sp._get_screening_service()
            assert s1 is s2
            assert s1 is inst
        sp._screening_service_instance = None


class TestAnalyzeCode:
    def test_with_finance_cache(self):
        args = _make_args()
        quote = _make_quote()
        fin_cache = {"sh600519": [{"roe": 15}]}
        kline_cache = {"sh600519": [MagicMock()]}
        with patch.object(sp, "_get_screening_service") as m_svc:
            m_svc.return_value._analyze_stock.return_value = {"code": "sh600519", "score": 80}
            result = sp.analyze_code(quote, "balanced", args, finance_cache=fin_cache, kline_cache=kline_cache)
        assert result["score"] == 80
        m_svc.return_value._analyze_stock.assert_called_once()

    def test_without_finance_cache(self):
        args = _make_args()
        quote = _make_quote()
        with patch("business.screening_pipeline.fetch_finance_first", return_value={"roe": 15}):
            with patch.object(sp, "_get_screening_service") as m_svc:
                m_svc.return_value._analyze_stock.return_value = {"code": "sh600519", "score": 80}
                result = sp.analyze_code(quote, "balanced", args)
        assert result["score"] == 80

    def test_no_kline_cache(self):
        args = _make_args()
        quote = _make_quote()
        with patch("business.screening_pipeline.fetch_finance_first", return_value={}):
            with patch.object(sp, "_get_screening_service") as m_svc:
                m_svc.return_value._analyze_stock.return_value = {"code": "sh600519"}
                result = sp.analyze_code(quote, "balanced", args, kline_cache={})
        assert result["code"] == "sh600519"


class TestAnalyzeCodePhase1:
    def test_basic(self):
        args = _make_args(no_chip=True)
        quote = _make_quote()
        fin_cache = {"sh600519": [{"roe": 15}]}
        with patch.object(sp, "_get_screening_service") as m_svc:
            m_svc.return_value._hard_filter.return_value = ([], [])
            with patch("business.screening_pipeline.infer_industry", return_value="白酒"):
                with patch("business.screening_pipeline.compute_phase1_parts", return_value={"quality": 80}):
                    with patch("business.screening_pipeline.compute_weighted_score", return_value=75):
                        with patch("business.screening_pipeline.build_result_row", return_value={"code": "sh600519", "score": 75}):
                            result = sp.analyze_code_phase1(quote, args, fin_cache)
        assert result["score"] == 75

    def test_no_finance_cache(self):
        args = _make_args()
        quote = _make_quote()
        with patch("business.screening_pipeline.fetch_finance_first", return_value={"roe": 15}):
            with patch.object(sp, "_get_screening_service") as m_svc:
                m_svc.return_value._hard_filter.return_value = (["low_amount"], [])
                with patch("business.screening_pipeline.infer_industry", return_value="白酒"):
                    with patch("business.screening_pipeline.compute_phase1_parts", return_value={"quality": 80}):
                        with patch("business.screening_pipeline.compute_weighted_score", return_value=75):
                            with patch("business.screening_pipeline.build_result_row", return_value={"code": "sh600519", "rejected": True}):
                                result = sp.analyze_code_phase1(quote, args)
        assert result["rejected"] is True

    def test_no_chip_sets_chip_50(self):
        args = _make_args(no_chip=True)
        quote = _make_quote()

        def _capture(fin, quote, industry, weights=None):
            return {"quality": 80}

        with patch("business.screening_pipeline.fetch_finance_first", return_value={}):
            with patch.object(sp, "_get_screening_service") as m_svc:
                m_svc.return_value._hard_filter.return_value = ([], [])
                with patch("business.screening_pipeline.infer_industry", return_value="白酒"):
                    with patch("business.screening_pipeline.compute_phase1_parts", side_effect=_capture):
                        with patch("business.screening_pipeline.compute_weighted_score", return_value=75) as m_score:
                            with patch("business.screening_pipeline.build_result_row", return_value={"code": "sh600519"}):
                                sp.analyze_code_phase1(quote, args)
        # compute_weighted_score 被调用时 parts 应包含 chip=50
        called_parts = m_score.call_args[0][0]
        assert called_parts["chip"] == 50


class TestApplyFactorNormalization:
    def test_less_than_3_returns(self):
        rows = [{"rejected": False, "score": 80}, {"rejected": False, "score": 70}]
        sp._apply_factor_normalization(rows, "balanced")
        # 不修改
        assert rows[0]["score"] == 80

    def test_all_rejected_returns(self):
        rows = [{"rejected": True, "score": 0}] * 5
        sp._apply_factor_normalization(rows, "balanced")
        assert rows[0]["score"] == 0

    def test_normalizes_valid_rows(self):
        rows = [
            {"code": "a", "rejected": False, "quality": 80, "score": 80},
            {"code": "b", "rejected": False, "quality": 70, "score": 70},
            {"code": "c", "rejected": False, "quality": 60, "score": 60},
        ]
        with patch("business.screening_pipeline.get_factor_keys", return_value=["quality"]):
            with patch("business.screening_pipeline.normalize_factors_batch", return_value=[
                {"quality": 1.0}, {"quality": 0.0}, {"quality": -1.0}
            ]):
                with patch("business.screening_pipeline.compute_weighted_score", side_effect=[90, 70, 50]):
                    sp._apply_factor_normalization(rows, "balanced")
        assert rows[0]["score"] == 90
        assert rows[0]["quality"] == 1.0


class TestRunScreeningEmpty:
    def test_empty_universe_halted(self):
        args = _make_args()
        with patch("business.screening_pipeline.load_universe", return_value=[]):
            result = sp.run_screening(args)
        assert result["halted"] is True
        assert result["rows"] == []


class TestRunScreeningBasic:
    def _setup_common_mocks(self, quotes, fin_cache=None):
        if fin_cache is None:
            fin_cache = {q["code"]: [] for q in quotes}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=[q["code"] for q in quotes]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        return [p.start() for p in patches], fin_cache

    def test_single_stage(self):
        quotes = [_make_quote("sh600519", "茅台"), _make_quote("sz000858", "五粮液")]
        mocks, _ = self._setup_common_mocks(quotes)
        args = _make_args(two_stage=False)
        try:
            with patch.object(sp, "analyze_code", side_effect=[
                {"code": "sh600519", "score": 80},
                {"code": "sz000858", "score": 70},
            ]):
                result = sp.run_screening(args)
        finally:
            for m in mocks:
                m.stop()
        assert result["halted"] is False
        assert len(result["rows"]) == 2
        assert result["rows"][0]["score"] == 80

    def test_single_stage_with_normalize(self):
        quotes = [_make_quote(f"sh60000{i}", f"S{i}") for i in range(4)]
        mocks, _ = self._setup_common_mocks(quotes)
        args = _make_args(two_stage=False, no_normalize=False)
        try:
            with patch.object(sp, "analyze_code", side_effect=[
                {"code": q["code"], "score": 80 - i, "rejected": False, "quality": 80 - i}
                for i, q in enumerate(quotes)
            ]):
                with patch.object(sp, "_apply_factor_normalization") as m_norm:
                    result = sp.run_screening(args)
        finally:
            for m in mocks:
                m.stop()
        m_norm.assert_called_once()
        assert result["halted"] is False

    def test_progress_callback(self):
        quotes = [_make_quote("sh600519", "茅台")]
        mocks, _ = self._setup_common_mocks(quotes)
        args = _make_args(two_stage=False)
        events = []
        try:
            with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                sp.run_screening(args, progress_callback=lambda e, p: events.append((e, p)))
        finally:
            for m in mocks:
                m.stop()
        assert any(e == "phase2" for e, _ in events)


class TestRunScreeningTwoStage:
    def test_two_stage_flow(self):
        quotes = [_make_quote(f"sh60000{i}", f"S{i}") for i in range(5)]
        fin_cache = {q["code"]: [] for q in quotes}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=[q["code"] for q in quotes]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=True, top=3, no_normalize=True)
        for p in patches:
            p.start()
        try:
            with patch.object(sp, "analyze_code_phase1", side_effect=[
                {"code": q["code"], "score": 80 - i, "rejected": False}
                for i, q in enumerate(quotes)
            ]):
                with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 85}):
                    result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["halted"] is False
        assert "p1_elapsed" in result["phase_stats"]


class TestRunScreeningRegime:
    def test_regime_detection(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, no_regime=False)
        for p in patches:
            p.start()
        try:
            with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                with patch("strategies.regime.detect_signals", return_value={"trend": "up"}):
                    with patch("strategies.regime.classify_regime", return_value=MagicMock(value="BULL")):
                        result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["regime"] is not None

    def test_regime_exception(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, no_regime=False)
        for p in patches:
            p.start()
        try:
            with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                with patch("strategies.regime.detect_signals", side_effect=RuntimeError("err")):
                    result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["regime"] is None


class TestRunScreeningMacro:
    def test_macro_red_halts(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, no_macro=False)
        for p in patches:
            p.start()
        try:
            with patch("strategies.macro.MacroSafetyGate") as MockGate:
                inst = MockGate.return_value
                macro_state = MagicMock()
                macro_state.value = "RED"
                inst.check.return_value = (macro_state, "risk")
                result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["halted"] is True
        assert result["macro_state"] is not None

    def test_macro_green_continues(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, no_macro=False)
        for p in patches:
            p.start()
        try:
            with patch("strategies.macro.MacroSafetyGate") as MockGate:
                inst = MockGate.return_value
                macro_state = MagicMock()
                macro_state.value = "GREEN"
                inst.check.return_value = (macro_state, "safe")
                with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                    result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["halted"] is False

    def test_macro_exception_continues(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, no_macro=False)
        for p in patches:
            p.start()
        try:
            with patch("strategies.macro.MacroSafetyGate", side_effect=RuntimeError("err")):
                with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                    result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["halted"] is False
        assert result["macro_state"] is None


class TestRunScreeningSnapshot:
    def test_snapshot_success(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, snapshot=True)
        for p in patches:
            p.start()
        try:
            with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                with patch("snapshots.save_snapshot", return_value="/tmp/snap.json"):
                    result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["snapshot_path"] == "/tmp/snap.json"

    def test_snapshot_exception(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, snapshot=True)
        for p in patches:
            p.start()
        try:
            with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                with patch("snapshots.save_snapshot", side_effect=RuntimeError("err")):
                    result = sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        assert result["snapshot_path"] is None


class TestRunScreeningConstraints:
    def test_apply_constraints(self):
        quotes = [_make_quote("sh600519", "茅台")]
        fin_cache = {"sh600519": []}
        patches = [
            patch("business.screening_pipeline.load_universe", return_value=["sh600519"]),
            patch("business.screening_pipeline.fetch_batch_dicts", return_value=quotes),
            patch("business.screening_pipeline.prefetch_finance_all", return_value=fin_cache),
            patch("business.screening_pipeline.prefetch_kline_all", return_value={}),
        ]
        args = _make_args(two_stage=False, no_constraints=False)
        for p in patches:
            p.start()
        try:
            with patch.object(sp, "analyze_code", return_value={"code": "sh600519", "score": 80}):
                with patch("business.screening_pipeline.apply_portfolio_constraints", return_value=[{"code": "sh600519", "score": 80}]) as m_c:
                    sp.run_screening(args)
        finally:
            for p in patches:
                p.stop()
        m_c.assert_called_once()

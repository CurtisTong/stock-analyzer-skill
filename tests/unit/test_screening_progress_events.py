"""screener 进度事件测试（P0-01 后续：数据预取阶段进度提示）。

覆盖：
1. run_screening 在 full_market 路径发射 data_prefetch 事件（quote→prescreen→finance→done）
   + phase1/phase2，顺序正确
2. 非 full_market 路径发射 data_prefetch(parallel)
3. _default_progress_callback 支持 file 参数（JSON 模式进度走 stderr，不污染 stdout）
"""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace


def _make_args(**overrides):
    base = dict(
        full_market=True,
        two_stage=False,
        no_regime=True,
        no_macro=True,
        strategy="balanced",
        top=5,
        no_normalize=True,
        no_constraints=True,
        snapshot=False,
        exclude_sector_momentum=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _collect(events):
    def _cb(event, payload=None):
        events.append(event)

    return _cb


class TestDataPrefetchEvents:
    def test_full_market_emits_prefetch_then_phases(self, monkeypatch):
        """full_market：data_prefetch(quote/prescreen/finance/done) 先于 phase1/phase2。"""
        import business.screening_pipeline as sp

        monkeypatch.setattr(sp, "load_universe", lambda args: ["sh600000", "sz000001"])
        monkeypatch.setattr(
            sp,
            "fetch_batch_dicts",
            lambda codes: [
                {"code": "sh600000", "amount": "100"},
                {"code": "sz000001", "amount": "200"},
            ],
        )
        monkeypatch.setattr(sp, "pre_screen_quotes", lambda q, args: q)
        monkeypatch.setattr(sp, "prefetch_finance_all", lambda codes: {})
        monkeypatch.setattr(sp, "prefetch_kline_all", lambda codes: {})
        monkeypatch.setattr(
            sp,
            "analyze_code_phase1",
            lambda q, args, finance_cache, regime=None: {
                "score": 100,
                "code": q["code"],
            },
        )
        monkeypatch.setattr(
            sp,
            "analyze_code",
            lambda q, strategy, args, finance_cache, regime=None, kline_cache=None: {
                "score": 100,
                "code": q["code"],
            },
        )
        monkeypatch.setattr(sp, "_apply_sector_momentum", lambda rows, x: rows)

        events = []
        result = sp.run_screening(_make_args(), progress_callback=_collect(events))

        assert result["rows"], "两阶段管线应产出结果"
        assert events[0] == "data_prefetch"
        assert events.count("data_prefetch") == 4  # quote/prescreen/finance/done
        # data_prefetch 全部在 phase1/phase2 之前
        first_phase = events.index("phase1") if "phase1" in events else len(events)
        prefetch_idx = [i for i, e in enumerate(events) if e == "data_prefetch"]
        assert prefetch_idx
        assert max(prefetch_idx) < first_phase

    def test_pool_mode_emits_parallel_prefetch(self, monkeypatch):
        """非 full_market：data_prefetch(parallel) 单个事件。"""
        import business.screening_pipeline as sp

        monkeypatch.setattr(sp, "load_universe", lambda args: ["sh600000"])
        monkeypatch.setattr(
            sp,
            "fetch_batch_dicts",
            lambda codes: [{"code": "sh600000", "amount": "100"}],
        )
        monkeypatch.setattr(sp, "prefetch_finance_all", lambda codes: {})
        monkeypatch.setattr(sp, "prefetch_kline_all", lambda codes: {})
        monkeypatch.setattr(
            sp,
            "analyze_code",
            lambda q, strategy, args, finance_cache, regime=None, kline_cache=None: {
                "score": 100,
                "code": q["code"],
            },
        )
        monkeypatch.setattr(sp, "_apply_sector_momentum", lambda rows, x: rows)

        events = []
        result = sp.run_screening(
            _make_args(full_market=False), progress_callback=_collect(events)
        )

        assert result["rows"]
        assert "data_prefetch" in events
        assert events.count("data_prefetch") == 2  # parallel + done


class TestCallbackStream:
    def test_data_prefetch_to_stderr(self, capsys):
        """file 参数指定 stderr 时，进度写入 stderr 不污染 stdout。"""
        from screener import _default_progress_callback

        _default_progress_callback(
            "data_prefetch", {"stage": "finance", "count": 500}, file=None
        )
        _default_progress_callback(
            "data_prefetch", {"stage": "quote", "count": 3323}, file=None
        )
        captured = capsys.readouterr()
        assert "拉取财务 Top 500" in captured.out
        assert "拉取行情 3323" in captured.out

    def test_callback_file_param_routes_to_given_stream(self):
        """JSON 模式：file=StringIO 时输出到该流，stdout 为空。"""
        from screener import _default_progress_callback

        stream = StringIO()
        _default_progress_callback(
            "data_prefetch", {"stage": "finance", "count": 500}, file=stream
        )
        assert "拉取财务 Top 500" in stream.getvalue()

"""盘前价格基准日回退单测（hermetic：monkeypatch 时钟与 K 线，不连网、不读真实持仓）。

2026-11-23 假红：周一 08:49 snapshot() 把 price_date 推成当日 11-23，与账本 11-20
撞成 FAIL。主修法是「从行情 K 线末根拿权威日期」，拿不到才回退到最近交易日推断。

monitor_holdings.py 位于仓库外共享目录 stock-team/monitor/，用 importlib 按路径加载。
同一逻辑的两处副本（共享脚本 + 本仓库）改动须同步（errata #18）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

_MONITOR = Path(os.environ.get("STOCK_TEAM_MONITOR_DIR", str(Path(__file__).resolve().parents[3] / "monitor")))
_MONITOR_SCRIPT = _MONITOR / "monitor_holdings.py"
if not _MONITOR_SCRIPT.is_file():
    pytest.skip(
        f"外部共享脚本不存在：{_MONITOR_SCRIPT}（可设置 STOCK_TEAM_MONITOR_DIR）",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def mh():
    spec = importlib.util.spec_from_file_location("monitor_holdings_under_test", _MONITOR_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestKlineLastDay:
    def test_returns_last_bar_day(self, mh, monkeypatch):
        payload = [
            {"day": "2026-11-19", "close": 1.0},
            {"day": "2026-11-20", "close": 2.0},
        ]

        class R:
            stdout = json.dumps(payload)

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
        assert mh.kline_last_day("sh000001") == "2026-11-20"

    def test_returns_none_on_failure(self, mh, monkeypatch):
        def boom(*a, **k):
            raise OSError("blocked")

        monkeypatch.setattr(subprocess, "run", boom)
        assert mh.kline_last_day() is None

    def test_returns_none_on_empty(self, mh, monkeypatch):
        class R:
            stdout = "[]"

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
        assert mh.kline_last_day() is None


class TestInferPriceDateFallback:
    def test_premarket_weekday_falls_back_to_friday(self, mh):
        # 周一 08:49 盘前 → 回退上周五
        d, src = mh.infer_price_date(datetime(2026, 11, 23, 8, 49))
        assert d == "2026-11-20"
        assert "盘前回退" in src

    def test_intraday_weekday_uses_today(self, mh):
        d, src = mh.infer_price_date(datetime(2026, 11, 23, 10, 0))
        assert d == "2026-11-23"
        assert "当日盘中" in src

    def test_before_930_even_minute(self, mh):
        # 边界：09:29 仍盘前；09:30 当日
        assert mh.infer_price_date(datetime(2026, 11, 23, 9, 29))[0] == "2026-11-20"
        assert mh.infer_price_date(datetime(2026, 11, 23, 9, 30))[0] == "2026-11-23"

    def test_weekend_falls_back_to_friday(self, mh):
        # 周日 20:49 → 回退周五
        d, src = mh.infer_price_date(datetime(2026, 11, 22, 20, 49))
        assert d == "2026-11-20"
        assert "非交易日回退" in src

    def test_holiday_falls_back(self, mh):
        # 假设 11-23 是节假日 → 回退上一交易日 11-20
        holidays = {"2026-11-23"}
        d, src = mh.infer_price_date(datetime(2026, 11, 23, 10, 0), holidays)
        assert d == "2026-11-20"
        assert "非交易日回退" in src

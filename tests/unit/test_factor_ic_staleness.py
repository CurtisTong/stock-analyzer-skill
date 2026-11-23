"""因子 IC 持久化的"不可用即视为没有"守卫（P0-4 配套）。

历史问题：scripts/data/factor_ic.json 被 tracked 且内容是全 0 占位，
load_ic() 会把 0.0 当成"有效但无预测力"的 IC 参与加权，看起来像"算过"。
本文件锁死四种不可用情形都返回空 dict 并记录原因，绝不拿 0 占位。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from strategies.factor import ic as ic_mod


def _write(tmp_path, ic_map, updated=None):
    path = tmp_path / "factor_ic.json"
    payload = {"updated": (updated or datetime.now()).isoformat(), "ic": ic_map}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate_ic_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ic_mod, "IC_FILE", tmp_path / "factor_ic.json")
    monkeypatch.setattr(ic_mod, "IC_STATUS", {"stale": True, "reason": "unknown", "updated": None, "age_days": None})


def test_missing_file_is_stale(tmp_path):
    assert ic_mod.load_ic() == {}
    status = ic_mod.ic_status()
    assert status["stale"] is True
    assert status["reason"] == "missing"


def test_all_zero_is_treated_as_missing(tmp_path):
    _write(tmp_path, {"range_low_vol": {"quality": 0.0, "momentum": 0.0}})
    assert ic_mod.load_ic() == {}
    assert ic_mod.ic_status()["reason"] == "all_zero"
    assert ic_mod.ic_status()["stale"] is True


def test_expired_is_stale(tmp_path):
    old = datetime.now() - timedelta(days=ic_mod.IC_FRESH_DAYS + 1)
    _write(tmp_path, {"range_low_vol": {"quality": 0.03}}, updated=old)
    assert ic_mod.load_ic() == {}
    assert ic_mod.ic_status()["reason"] == "expired"


def test_fresh_non_zero_ic_is_usable(tmp_path):
    _write(tmp_path, {"range_low_vol": {"quality": 0.03, "momentum": -0.05}})
    got = ic_mod.load_ic()
    assert got["range_low_vol"]["quality"] == 0.03
    status = ic_mod.ic_status()
    assert status["stale"] is False
    assert status["reason"] == "ok"


def test_corrupt_file_is_stale(tmp_path):
    (tmp_path / "factor_ic.json").write_text("{not json", encoding="utf-8")
    assert ic_mod.load_ic() == {}
    assert ic_mod.ic_status()["reason"] == "corrupt"

"""`get_kline(require_date=...)` 的单测（策略 2026-11-20 定的接口规格）。

核心约束：
- 命中缓存但末根日期不符 → 穿透重拉（TTL 1 小时不能当正确性保证）；
- 重拉后仍不符 → 抛 `DataNotReadyError` 且**不写缓存**（否则旧数据被固化，重试永远过不去）；
- 空列表仍是「无数据」（停牌/退市/新股），不抛异常；
- `require_date=None` 时行为与旧版完全一致。
"""

from __future__ import annotations

import pytest

from common.exceptions import DataError, DataNotReadyError


def _record(day: str, source: str = "sina") -> dict:
    return {
        "day": day,
        "open": "10.0",
        "high": "11.0",
        "low": "9.5",
        "close": "10.5",
        "volume": "1000",
        "amount": "10500.0",
        "pct_chg": "1.0",
        "source": source,
    }


@pytest.fixture
def env(monkeypatch, tmp_path):
    """把缓存目录指向 tmp，并接管 fetcher 的 fetch。"""
    import common.cache as cache_mod
    import data as data_mod

    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    data_mod._load_fetchers()
    manager = data_mod._kline_manager

    calls: list[str] = []
    state = {"records": [_record("2026-11-19")]}

    def fake_fetch(code, scale=240, datalen=30, **kwargs):
        calls.append(code)
        return state["records"]

    original = manager.fetch
    manager.fetch = fake_fetch
    yield data_mod, calls, state
    manager.fetch = original


def test_error_is_dataerror_subclass():
    err = DataNotReadyError("sh601857", 240, "2026-11-20", "2026-11-19", "sina")
    assert isinstance(err, DataError)
    assert err.details["require_date"] == "2026-11-20"
    assert err.details["actual_date"] == "2026-11-19"
    assert err.details["code"] == "sh601857"
    assert err.details["source"] == "sina"


def test_matching_date_returns_bars(env):
    data_mod, calls, _ = env
    bars = data_mod.get_kline("sh601857", require_date="2026-11-19")
    assert bars[-1].day == "2026-11-19"
    assert len(calls) == 1


def test_mismatch_raises_and_does_not_write_cache(env):
    """不匹配必须抛且不写缓存——写下去就固化了旧数据，重试永远过不去。"""
    data_mod, calls, _ = env
    with pytest.raises(DataNotReadyError) as exc:
        data_mod.get_kline("sh601857", require_date="2026-11-20")

    assert exc.value.details["actual_date"] == "2026-11-19"

    # 再调一次会重新 fetch（说明上一次没写缓存）
    with pytest.raises(DataNotReadyError):
        data_mod.get_kline("sh601857", require_date="2026-11-20")
    assert len(calls) == 2


def test_cache_hit_with_stale_date_forces_refetch(env):
    """缓存里是旧 bar 时，带 require_date 必须穿透重拉，不能直接返回。"""
    data_mod, calls, state = env

    # 先用旧数据把缓存灌满（不带 require_date）
    data_mod.get_kline("sh601857")
    assert len(calls) == 1

    # 上游已刷新到 11-20
    state["records"] = [_record("2026-11-20")]

    bars = data_mod.get_kline("sh601857", require_date="2026-11-20")

    assert len(calls) == 2, "缓存末根不符时必须穿透重拉"
    assert bars[-1].day == "2026-11-20"


def test_cache_hit_with_matching_date_does_not_refetch(env):
    """缓存末根已等于目标日 → 直接用，不重复发请求（重跑成本自动收敛）。"""
    data_mod, calls, state = env
    state["records"] = [_record("2026-11-20")]
    data_mod.get_kline("sh601857", require_date="2026-11-20")
    assert len(calls) == 1

    data_mod.get_kline("sh601857", require_date="2026-11-20")
    assert len(calls) == 1, "同一天重试应命中缓存，不重复发请求"


def test_empty_records_still_returns_empty_list(env):
    """空列表语义保持「无数据」，不抛异常。"""
    data_mod, _, state = env
    state["records"] = []
    assert data_mod.get_kline("sh601857", require_date="2026-11-20") == []


def test_without_require_date_behaviour_unchanged(env):
    data_mod, calls, state = env
    bars = data_mod.get_kline("sh601857")
    assert bars[-1].day == "2026-11-19"
    # 二次调用命中缓存
    data_mod.get_kline("sh601857")
    assert len(calls) == 1

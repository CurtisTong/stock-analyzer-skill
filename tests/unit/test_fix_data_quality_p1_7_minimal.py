"""P1-7 回归测试（2026-11-21 review §3.1 #7）：最小数据源标记被丢弃。"""

from __future__ import annotations

import pytest

from common import data_quality as dq
from data import _dict_to_quote
from data.types import Quote


@pytest.fixture(autouse=True)
def _no_industry_network(monkeypatch):
    import data as data_mod

    monkeypatch.setattr(data_mod, "_resolve_industry", lambda d, c: "")


def test_quote_new_fields_have_backcompatible_defaults():
    q = Quote()
    assert q.is_minimal is False
    assert q.is_realtime is True
    d = q.to_dict()
    assert d["is_minimal"] is False
    assert d["is_realtime"] is True


def test_ths_minimal_flags_passthrough_into_quote_and_dict():
    raw = {
        "code": "sh600989",
        "price": "10.5",
        "source": "ths",
        "is_minimal": True,
        "is_realtime": False,
        "pe": 0,
        "pb": 0,
    }
    q = _dict_to_quote(raw)
    assert q.is_minimal is True, "THS 的最小源标记不能丢（P1-7）"
    assert q.is_realtime is False
    d = q.to_dict()
    assert d["is_minimal"] is True
    assert d["is_realtime"] is False


def test_minimal_source_without_explicit_realtime_defaults_to_non_realtime():
    q = _dict_to_quote({"code": "sh600989", "source": "ths", "is_minimal": True})
    assert q.is_minimal is True
    assert q.is_realtime is False, "最小源未显式声明时应按非实时处理（P1-7）"


def test_minimal_quote_is_degraded_and_zero_valuations_nulled():
    rows = [
        {
            "code": "sh600989",
            "price": 10.5,
            "pe": 0,
            "pb": 0,
            "total_cap": 0,
            "circulating_cap": 0,
            "turnover": 0,
            "is_minimal": True,
            "is_realtime": False,
        }
    ]
    out = dq.envelope_rows(rows)
    d = out["data_quality"]
    assert d["status"] == "degraded", "最小源有价也必须判降级（P1-7）"
    assert d["degraded_domains"] == ["quote"]
    assert d["conclusions_allowed"] is False
    row = out["rows"][0]
    for key in ("pe", "pb", "total_cap", "circulating_cap", "turnover"):
        assert row[key] is None, f"{key} 是 0 占位，不得当真实估值（P1-7）"
    # 不修改调用方入参
    assert rows[0]["pe"] == 0


def test_non_minimal_zero_valuation_is_preserved():
    out = dq.envelope_rows([{"code": "sh600989", "price": 10.5, "pe": 0}])
    assert out["data_quality"]["status"] == "ok"
    assert out["rows"][0]["pe"] == 0, "非最小源的字段不得被误置 None"


def test_generic_envelope_handles_top_level_minimal_quote():
    """stock.py 等走 envelope() 的入口也能识别顶层最小源标记（P1-7）。"""
    out = dq.envelope(
        {"price": 10.5, "pe": 0, "pb": 0, "is_minimal": True, "is_realtime": False},
        required=("quote",),
        field_map={"quote": ("price",)},
        conclusion_keys=("score",),
    )
    assert out["data_quality"]["degraded_domains"] == ["quote"]
    assert out["data_quality"]["conclusions_allowed"] is False
    assert out["pe"] is None and out["pb"] is None
    assert out["price"] == 10.5, "真实价格仍保留"

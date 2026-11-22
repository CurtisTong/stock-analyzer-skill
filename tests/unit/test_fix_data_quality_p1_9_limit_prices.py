"""P1-9 回归测试（2026-11-21 review §3.1 #9）：腾讯涨跌停价字段定义了不输出。"""

from __future__ import annotations

import pytest

from common.parsers import TENCENT_FIELDS, parse_tencent_line
from fetchers.quote.tencent_quote import TencentQuoteFetcher


def _tencent_line(up: str = "11.00", down: str = "9.00") -> str:
    parts = ["0"] * 60
    parts[1] = "宝丰能源"
    parts[2] = "600989"
    parts[3] = "10.50"
    parts[TENCENT_FIELDS["limit_up"]] = up
    parts[TENCENT_FIELDS["limit_down"]] = down
    return f'v_sh600989="{"~".join(parts)}";'


def test_parse_tencent_line_outputs_limit_prices():
    rec = parse_tencent_line(_tencent_line())
    assert "limit_up" in rec, "字段位 47 必须输出（P1-9）"
    assert "limit_down" in rec, "字段位 48 必须输出（P1-9）"
    assert rec["limit_up"] == "11.00"
    assert rec["limit_down"] == "9.00"


def test_fetcher_and_data_layer_propagate_limit_prices(monkeypatch):
    import data as data_mod

    monkeypatch.setattr(data_mod, "_resolve_industry", lambda d, c: "")
    monkeypatch.setattr(
        "fetchers.quote.tencent_quote.http_get",
        lambda *a, **k: _tencent_line().encode("gbk"),
    )

    rec = TencentQuoteFetcher().fetch("sh600989")
    assert rec is not None
    assert rec["limit_up"] == "11.00"

    q = data_mod._dict_to_quote(rec)
    assert q.limit_up == 11.0
    assert q.limit_down == 9.0
    assert q.to_dict()["limit_up"] == 11.0
    assert q.to_dict()["limit_down"] == 9.0

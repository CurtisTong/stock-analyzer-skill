"""全市场股票池的板块归属回归测试。

背景（P0-0，2026-11-18）：`all_stocks.json` 的键是 `主板沪` / `主板深`，而
`board_type()` 只返回 `主板`。两条取数路径都因此丢掉全部主板股：

1. push2 路径：`boards[board]` 直接 `KeyError('主板')`，整段异常 →
2. 选股器路径：`if board in boards` 为 False，主板股被静默跳过。

实测主板沪 1632 + 主板深 1420 = 3052 只，占全市场 5382 只的 56.7%；
修复前最终池只有 2330 只、主板 0 只。本文件锁死"主板不被丢"的不变量。
"""

from __future__ import annotations

import json

import pytest

from common import board_type, infer_exchange
from data import pool

ALL_BOARD_KEYS = {"主板沪", "主板深", "创业板", "科创板", "北交所"}


@pytest.mark.parametrize(
    "board,exchange,expected",
    [
        ("主板", "sh", "主板沪"),
        ("主板", "sz", "主板深"),
        ("创业板", "sz", "创业板"),
        ("科创板", "sh", "科创板"),
        ("北交所", "bj", "北交所"),
    ],
)
def test_board_key_maps_to_pool_keys(board, exchange, expected):
    """board_type() 的板块名映射后必须落在 boards 的键上。"""
    key = pool._board_key(board, exchange)
    assert key == expected
    assert key in ALL_BOARD_KEYS


@pytest.mark.parametrize("code", ["600519", "000001", "300750", "688981", "920001"])
def test_board_key_covers_common_board_types(code):
    """常见板块的 (board_type, exchange) 组合都能映射进池键。"""
    assert pool._board_key(board_type(code), infer_exchange(code)) in ALL_BOARD_KEYS


def _push2_rows() -> list[dict]:
    """push2 diff 结构的最小样本：沪/深主板 + 创业板 + 科创板 + 北交所。"""
    return [
        {"f12": "600519", "f14": "贵州茅台"},
        {"f12": "000001", "f14": "平安银行"},
        {"f12": "300750", "f14": "宁德时代"},
        {"f12": "688981", "f14": "中芯国际"},
        {"f12": "920001", "f14": "北交所样本"},
    ]


def test_push2_path_keeps_main_board(monkeypatch):
    """push2 路径不得 KeyError('主板')，沪深主板都要进池。"""
    payload = {"data": {"total": 5, "diff": _push2_rows()}}

    def fake_http_get_cached(url, ttl=0):
        return json.dumps(payload)

    monkeypatch.setattr(
        pool,
        "_get_common_deps",
        lambda: (fake_http_get_cached, board_type, infer_exchange),
    )

    boards = {key: [] for key in ALL_BOARD_KEYS}
    pool._fetch_push2_market(boards)

    assert boards["主板沪"] == ["sh600519"]
    assert boards["主板深"] == ["sz000001"]
    assert boards["创业板"] == ["sz300750"]
    assert boards["科创板"] == ["sh688981"]
    assert boards["北交所"] == ["bj920001"]


def test_xuangu_fallback_keeps_main_board(monkeypatch):
    """push2 失败降级到选股器后，主板股也不能被静默丢弃。"""
    rows = [
        {"SECURITY_CODE": "600519", "SECURITY_NAME_ABBR": "贵州茅台"},
        {"SECURITY_CODE": "000001", "SECURITY_NAME_ABBR": "平安银行"},
        {"SECURITY_CODE": "300750", "SECURITY_NAME_ABBR": "宁德时代"},
        {"SECURITY_CODE": "688981", "SECURITY_NAME_ABBR": "中芯国际"},
        {"SECURITY_CODE": "920001", "SECURITY_NAME_ABBR": "北交所样本"},
    ]

    def boom(boards):
        raise ValueError("mock: push2 不可用")

    monkeypatch.setattr(pool, "_fetch_push2_market", boom)
    monkeypatch.setattr(pool, "_fetch_xuangu_page", lambda *a, **k: (rows, len(rows)))
    monkeypatch.setattr(pool, "_get_common_deps", lambda: (None, board_type, infer_exchange))

    boards = pool.fetch_all_market_stocks()

    assert boards["主板沪"] == ["sh600519"]
    assert boards["主板深"] == ["sz000001"]
    assert sum(len(v) for v in boards.values()) == 5

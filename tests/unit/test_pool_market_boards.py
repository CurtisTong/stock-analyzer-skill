"""全市场股票池的板块归属回归测试（P0-0）。

背景（2026-11-18）：`all_stocks.json` 的键是 `主板沪` / `主板深`，而
`board_type()` 只返回 `主板`。两条取数路径都因此丢掉全部主板股：

1. push2 路径：`boards[board]` 直接 `KeyError('主板')`，整段异常 → 降级；
2. 选股器路径：`if board in boards` 为 False，主板股被静默跳过。

实测主板沪 1632 + 主板深 1420 = 3052 只，占全市场 5382 只的 56.7%；
修复前最终池只有 2330 只、主板 0 只。

本文件全部用 monkeypatch 打桩，不读 `all_stocks.json`、不发网络请求，
CI 里可稳定重复执行（实时数据用例放 e2e/contracts，不放这里）。
"""

from __future__ import annotations

import json

import pytest

from common import board_type, infer_exchange
from data import pool

ALL_BOARD_KEYS = {"主板沪", "主板深", "创业板", "科创板", "北交所"}


def _fake_http_get_cached_factory(payload: dict):
    def fake_http_get_cached(url, ttl=0):
        return json.dumps(payload)

    return fake_http_get_cached


# ---------------------------------------------------------------------------
# _board_key：纯函数映射
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "board,exchange,expected",
    [
        ("主板", "sh", "主板沪"),
        ("主板", "sz", "主板深"),
        ("创业板", "sz", "创业板"),
        ("科创板", "sh", "科创板"),
        ("北交所", "bj", "北交所"),
        ("其他", "sh", "其他"),
    ],
)
def test_board_key_maps_to_pool_keys(board, exchange, expected):
    """非"主板"原样返回；"主板"按交易所拆成沪/深两个键。"""
    key = pool._board_key(board, exchange)
    assert key == expected


@pytest.mark.parametrize("code", ["600519", "000001", "300750", "688981", "920001"])
def test_board_key_covers_common_board_types(code):
    """常见板块的 (board_type, exchange) 组合都能映射进池键。"""
    assert pool._board_key(board_type(code), infer_exchange(code)) in ALL_BOARD_KEYS


# ---------------------------------------------------------------------------
# fetch_all_market_stocks：两条取数路径都不许丢主板
# ---------------------------------------------------------------------------


def _push2_rows(n_sh_main=1200, n_sz_main=1500, n_cyb=300, n_kcb=200, n_bj=53):
    """构造 push2 diff 样本，规模刻意超过 1000 只的成功阈值。"""
    rows: list[dict] = []
    for i in range(n_sh_main):
        rows.append({"f12": f"60{i:04d}", "f14": f"沪主板{i}"})
    for i in range(n_sz_main):
        rows.append({"f12": f"00{i:04d}", "f14": f"深主板{i}"})
    for i in range(n_cyb):
        rows.append({"f12": f"30{i:04d}", "f14": f"创业板{i}"})
    for i in range(n_kcb):
        rows.append({"f12": f"688{i:03d}", "f14": f"科创板{i}"})
    for i in range(n_bj):
        rows.append({"f12": f"920{i:03d}", "f14": f"北交所{i}"})
    return rows


def test_push2_path_keeps_main_board(monkeypatch):
    """push2 路径不得 KeyError('主板')，沪深主板都要进池。"""
    payload = {
        "data": {
            "total": 5,
            "diff": [
                {"f12": "600519", "f14": "贵州茅台"},
                {"f12": "000001", "f14": "平安银行"},
                {"f12": "300750", "f14": "宁德时代"},
                {"f12": "688981", "f14": "中芯国际"},
                {"f12": "920001", "f14": "北交所样本"},
            ],
        }
    }
    monkeypatch.setattr(
        pool,
        "_get_common_deps",
        lambda: (_fake_http_get_cached_factory(payload), board_type, infer_exchange),
    )

    boards = {key: [] for key in ALL_BOARD_KEYS}
    pool._fetch_push2_market(boards)

    assert boards["主板沪"] == ["sh600519"]
    assert boards["主板深"] == ["sz000001"]
    assert boards["创业板"] == ["sz300750"]
    assert boards["科创板"] == ["sh688981"]
    assert boards["北交所"] == ["bj920001"]


def test_fetch_all_market_stocks_push2_counts(monkeypatch):
    """push2 成功路径：沪深主板都非空，主板合计等于输入的沪深主板数。"""
    rows = _push2_rows(n_sh_main=1200, n_sz_main=1500, n_cyb=300, n_kcb=200, n_bj=53)
    payload = {"data": {"total": len(rows), "diff": rows}}
    monkeypatch.setattr(
        pool,
        "_get_common_deps",
        lambda: (_fake_http_get_cached_factory(payload), board_type, infer_exchange),
    )

    boards = pool.fetch_all_market_stocks()

    assert boards["主板沪"], "主板沪 不能为空"
    assert boards["主板深"], "主板深 不能为空"
    assert len(boards["主板沪"]) == 1200
    assert len(boards["主板深"]) == 1500
    assert len(boards["主板沪"]) + len(boards["主板深"]) == 2700
    assert sum(len(v) for v in boards.values()) == len(rows)


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


def test_fetch_all_market_stocks_fallback_counts(monkeypatch):
    """降级路径同样按交易所拆主板：主板合计等于输入的主板数。"""
    rows = _push2_rows(n_sh_main=620, n_sz_main=480, n_cyb=120, n_kcb=80, n_bj=20)
    xuangu_rows = [
        {"SECURITY_CODE": r["f12"], "SECURITY_NAME_ABBR": r["f14"]} for r in rows
    ]

    def boom(boards):
        raise ValueError("mock: push2 不可用")

    monkeypatch.setattr(pool, "_fetch_push2_market", boom)
    monkeypatch.setattr(pool, "_fetch_xuangu_page", lambda *a, **k: (xuangu_rows, len(xuangu_rows)))
    monkeypatch.setattr(pool, "_get_common_deps", lambda: (None, board_type, infer_exchange))

    boards = pool.fetch_all_market_stocks()

    assert boards["主板沪"], "主板沪 不能为空"
    assert boards["主板深"], "主板深 不能为空"
    assert len(boards["主板沪"]) + len(boards["主板深"]) == 620 + 480
    assert sum(len(v) for v in boards.values()) == len(rows)

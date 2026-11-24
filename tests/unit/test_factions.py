"""派别状态聚合单测（T5）。"""

import pytest

from technical.factions import aggregate_factions, _status_for_level


def _base_features():
    return {
        "support_resistance": {
            "supports": [
                {"level": 3500.0, "source": "前低", "strength": "强"},
                {"level": 3400.0, "source": "整数关口", "strength": "弱"},
            ],
            "resistances": [
                {"level": 3600.0, "source": "前高", "strength": "强"},
                {"level": 3700.0, "source": "整数关口", "strength": "弱"},
            ],
        },
        "ma_system": {"ma_supports": [("MA20", 3480.0)], "ma_resistances": [("MA5", 3560.0)]},
        "bollinger": {"lower": 3450.0, "upper": 3650.0},
        "box": {"bottom": 3420.0, "top": 3580.0},
        "wave": "下跌浪(高点降低+低点降低)",
    }


def test_status_for_level_support():
    assert _status_for_level(3500, 3548) == "待验证"  # 支撑在现价下方
    assert _status_for_level(3560, 3548) == "已跌破"  # 支撑在现价上方
    assert _status_for_level(None, 3548) == "缺失"


def test_status_for_level_resistance():
    assert _status_for_level(3600, 3548, "resistance") == "待验证"
    assert _status_for_level(3500, 3548, "resistance") == "已突破"


def test_aggregate_contains_expected_factions():
    closes = [3500 + i for i in range(60)]
    opens = closes[:]
    highs = [c + 2 for c in closes]
    lows = [c - 2 for c in closes]
    r = aggregate_factions(_base_features(), closes, opens, highs, lows, 3548.0)
    factions = {e["faction"] for e in r["entries"]}
    assert {"均线派", "布林派", "前底派", "股票箱", "整数派"}.issubset(factions)
    assert r["wave_structure"] == "空头结构"
    assert r["order"][0] in factions


def test_aggregate_fallen_count():
    closes = [3500 + i for i in range(60)]
    r = aggregate_factions(_base_features(), closes, closes, closes, closes, 3500.0)
    # 现价 3500，前低 3500/布林下轨3450等：level>=price 标已跌破
    supports = [e for e in r["supports"]]
    fallen = [e for e in supports if e["status"] == "已跌破"]
    assert r["fallen_count"] == len(fallen)


def test_aggregate_no_mutation():
    feat = _base_features()
    import copy
    before = copy.deepcopy(feat)
    aggregate_factions(feat, [1.0] * 60, [1.0] * 60, [1.0] * 60, [1.0] * 60, 1.0)
    assert feat == before


def test_aggregate_empty_features():
    r = aggregate_factions({}, [], [], [], [], 0.0)
    assert r["entries"] == []
    assert r["fallen_count"] == 0

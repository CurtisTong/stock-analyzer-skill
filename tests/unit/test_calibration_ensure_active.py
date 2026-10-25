"""
experts/calibration._ensure_active_experts 的单元测试（v1.23.1 修复 P1-3）。

背景：校准库缺失 sector_specialist/risk_manager/momentum_trader 三个 active
专家条目，而 verify_predictions 用 `expert_name in data["experts"]` 过滤，
导致这 3 位专家的校准数据永远无法长出（闭环失效）。修复后 _load 会：
1. 迁移 legacy 名 → active 名（原行为）
2. 丢弃 legacy 占位条目，只保留 8 位 active
3. 为缺失的 active 专家补齐 events=0/correct=0 占位
"""

from __future__ import annotations

from experts import calibration
from experts.registry import EXPERT_REGISTRY, _ensure_loaded


def _active_names() -> set[str]:
    _ensure_loaded()
    return {n for n, p in EXPERT_REGISTRY.items() if p.active}


def test_empty_data_contains_only_active_experts():
    data = calibration._empty_data()
    assert set(data["experts"].keys()) == _active_names()


def test_ensure_active_experts_fills_missing_active(monkeypatch):
    """缺 3 个 active 专家的历史数据 → 补齐 0/0 占位。"""
    data = {
        "predictions": [],
        "experts": {
            "lynch": {"events": 5, "correct": 2, "last_updated": "2026-06-16"},
            "soros": {"events": 5, "correct": 2, "last_updated": "2026-06-16"},
            "topic_leader": {"events": 10, "correct": 2, "last_updated": "2026-06-16"},
            "emotion_tech": {"events": 10, "correct": 4, "last_updated": "2026-06-16"},
            "value_institution": {"events": 10, "correct": 8, "last_updated": "2026-06-16"},
            # 缺 sector_specialist / risk_manager / momentum_trader
        },
    }
    out = calibration._ensure_active_experts(data)
    assert set(out["experts"].keys()) == _active_names()
    for name in ("sector_specialist", "risk_manager", "momentum_trader"):
        assert out["experts"][name] == {"events": 0, "correct": 0, "last_updated": None}
    # 原有数据不被覆盖
    assert out["experts"]["lynch"] == {"events": 5, "correct": 2, "last_updated": "2026-06-16"}


def test_ensure_active_experts_prunes_legacy_placeholders():
    """legacy 专家占位条目（0/0）应被清除——legacy 不参与校准与卡片。"""
    data = {
        "predictions": [],
        "experts": {
            "lynch": {"events": 5, "correct": 2, "last_updated": "2026-06-16"},
            "buffett": {"events": 0, "correct": 0, "last_updated": None},
            "xu_xiang": {"events": 0, "correct": 0, "last_updated": None},
        },
    }
    out = calibration._ensure_active_experts(data)
    assert "buffett" not in out["experts"]
    assert "xu_xiang" not in out["experts"]
    assert set(out["experts"].keys()) == _active_names()


def test_load_returns_all_active_experts(monkeypatch, tmp_path):
    """_load 落盘数据缺 3 个 active → 读取时自动补齐（不写盘）。"""
    payload = {
        "_migrated": True,
        "predictions": [],
        "experts": {
            "lynch": {"events": 5, "correct": 2, "last_updated": "2026-06-16"},
            "soros": {"events": 5, "correct": 2, "last_updated": "2026-06-16"},
            "topic_leader": {"events": 10, "correct": 2, "last_updated": "2026-06-16"},
            "emotion_tech": {"events": 10, "correct": 4, "last_updated": "2026-06-16"},
            "value_institution": {"events": 10, "correct": 8, "last_updated": "2026-06-16"},
        },
    }
    path = tmp_path / "expert_calibration.json"
    path.write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")

    backup = calibration._CALIBRATION_FILE
    calibration._CALIBRATION_FILE = path
    try:
        data = calibration._load()
    finally:
        calibration._CALIBRATION_FILE = backup

    assert set(data["experts"].keys()) == _active_names()
    assert data["experts"]["momentum_trader"]["events"] == 0

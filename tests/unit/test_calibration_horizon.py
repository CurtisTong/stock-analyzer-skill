"""专家校准 horizon 分桶结算测试（v1.24.0）。

每位专家按自己的验证窗口独立到期独立结算（短线 14 天先结算，
长线 180 天到期后补结算），替换统一 30 天窗。旧记录无
expert_horizons 字段时沿用 verify_after 一次性结算（完全兼容）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from experts import calibration as cal_mod

SHORT_EXPERTS = ["topic_leader", "emotion_tech", "momentum_trader"]
MID_EXPERTS = ["sector_specialist", "risk_manager"]
LONG_EXPERTS = ["lynch", "soros", "value_institution"]
ALL_EXPERTS = LONG_EXPERTS + MID_EXPERTS + SHORT_EXPERTS

SCORES = {name: 70 for name in ALL_EXPERTS}


def _empty_data():
    return {
        "experts": {n: {"events": 0, "correct": 0, "last_updated": None} for n in ALL_EXPERTS},
        "predictions": [],
        "_migrated": True,
    }


@pytest.fixture
def store(monkeypatch):
    """_load/_save 重定向到内存 dict（save 捕获最新快照）。"""
    state = _empty_data()
    monkeypatch.setattr(cal_mod, "_load", lambda: state)
    monkeypatch.setattr(cal_mod, "_save", lambda d: state.update(d))
    return state


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _price_fn(return_pct: float = 6.0):
    def fn(stock, start, end):
        return return_pct

    return fn


class TestRecordHorizons:
    def test_record_writes_per_expert_horizons(self, store):
        cal_mod.record_prediction("sh600519", SCORES, "看多", timestamp=f"{_days_ago(0)} 10:00:00")
        pred = store["predictions"][0]
        assert set(pred["expert_horizons"]) == set(ALL_EXPERTS)
        # 短线窗口最短 → 顶层 verify_after = 短线到期日
        short_end = pred["expert_horizons"]["topic_leader"]
        assert pred["verify_after"] == short_end
        # 窗口排序：短线 < 行业 < 长线
        assert (
            pred["expert_horizons"]["topic_leader"]
            < pred["expert_horizons"]["sector_specialist"]
            < pred["expert_horizons"]["lynch"]
        )

    def test_unknown_expert_falls_back_to_default(self, store):
        cal_mod.record_prediction("sh600519", {"unknown_expert": 60}, "看多", timestamp=f"{_days_ago(0)} 10:00:00")
        pred = store["predictions"][0]
        assert pred["expert_horizons"]["unknown_expert"] == (
            datetime.now() + timedelta(days=cal_mod.DEFAULT_HORIZON_DAYS)
        ).strftime("%Y-%m-%d")


class TestSettledByHorizon:
    def test_short_term_settles_first(self, store):
        """记录于 20 天前：短线组已到期，长线/行业组未到期。"""
        cal_mod.record_prediction("sh600519", SCORES, "看多", timestamp=f"{_days_ago(20)} 10:00:00")
        result = cal_mod.verify_predictions(get_price_fn=_price_fn())

        assert result["verified"] == 0  # 未全部结算，不置 verified
        assert sorted(result["details"][0]["settled_experts"]) == sorted(SHORT_EXPERTS)
        assert result["details"][0]["fully_settled"] is False
        for name in SHORT_EXPERTS:
            assert store["experts"][name]["events"] == 1
        for name in LONG_EXPERTS + MID_EXPERTS:
            assert store["experts"][name]["events"] == 0
        pred = store["predictions"][0]
        assert pred["verified"] is False
        assert sorted(pred["settled_experts"]) == sorted(SHORT_EXPERTS)

    def test_long_term_settles_later(self, store):
        """记录于 200 天前：全部到期，一次跑完全结算。"""
        cal_mod.record_prediction("sh600519", SCORES, "看多", timestamp=f"{_days_ago(200)} 10:00:00")
        result = cal_mod.verify_predictions(get_price_fn=_price_fn())

        assert result["verified"] == 1
        assert result["details"][0]["fully_settled"] is True
        assert all(store["experts"][n]["events"] == 1 for n in ALL_EXPERTS)
        pred = store["predictions"][0]
        assert pred["verified"] is True

    def test_mid_horizon_partial_then_complete(self, store):
        """记录于 100 天前：短线+行业组到期，长线组仍待结算。"""
        cal_mod.record_prediction("sh600519", SCORES, "看多", timestamp=f"{_days_ago(100)} 10:00:00")
        result = cal_mod.verify_predictions(get_price_fn=_price_fn())

        assert sorted(result["details"][0]["settled_experts"]) == sorted(SHORT_EXPERTS + MID_EXPERTS)
        assert store["predictions"][0]["verified"] is False

        # 长线到期（再无时间流逝手段——200 天前的记录补一次跑已含长线窗口）
        cal_mod.record_prediction("sz000858", SCORES, "看多", timestamp=f"{_days_ago(200)} 10:00:00")
        result2 = cal_mod.verify_predictions(get_price_fn=_price_fn())
        assert result2["verified"] == 1  # sz000858 全结算

    def test_direction_correctness_per_expert_score(self, store):
        """看多方向 + 价格 +6% → 到期结算的短线专家 correct+1。"""
        scores = {**{n: 70 for n in SHORT_EXPERTS}, "lynch": 20}  # lynch 看空
        cal_mod.record_prediction("sh600519", scores, "看多", timestamp=f"{_days_ago(20)} 10:00:00")
        cal_mod.verify_predictions(get_price_fn=_price_fn(6.0))
        assert all(store["experts"][n]["correct"] == 1 for n in SHORT_EXPERTS)


class TestLegacyCompat:
    def test_legacy_record_settles_all_at_once(self, store):
        """旧记录（无 expert_horizons）：沿用 verify_after 一次性结算。"""
        legacy = {
            "id": "pred_legacy_sh600519",
            "stock": "sh600519",
            "date": _days_ago(40),
            "direction": "看多",
            "composite_score": 60,
            "expert_scores": dict(SCORES),
            "verified": False,
            "verify_after": _days_ago(5),  # 已到期
            "actual_return": None,
            "actual_direction": None,
        }
        store["predictions"].append(legacy)
        result = cal_mod.verify_predictions(get_price_fn=_price_fn())

        assert result["verified"] == 1
        assert legacy["verified"] is True
        assert all(store["experts"][n]["events"] == 1 for n in ALL_EXPERTS)

    def test_price_failure_skips_and_retries(self, store):
        """价格获取失败 → skipped，不结算不锁定。"""
        cal_mod.record_prediction("sh600519", SCORES, "看多", timestamp=f"{_days_ago(200)} 10:00:00")

        def failing_fn(stock, start, end):
            raise ValueError("无价格")

        result = cal_mod.verify_predictions(get_price_fn=failing_fn)
        assert result["skipped"] == 1
        assert store["predictions"][0]["verified"] is False
        assert store["predictions"][0].get("settled_experts", []) == []

        # 恢复后可正常结算
        result2 = cal_mod.verify_predictions(get_price_fn=_price_fn())
        assert result2["verified"] == 1

    def test_mark_only_settles_without_calibration_update(self, store):
        cal_mod.record_prediction("sh600519", SCORES, "看多", timestamp=f"{_days_ago(200)} 10:00:00")
        cal_mod.verify_predictions(mark_only=True)
        pred = store["predictions"][0]
        assert pred["verified"] is True
        assert all(store["experts"][n]["events"] == 0 for n in ALL_EXPERTS)


class TestPendingByHorizon:
    def test_pending_counts_due_unsettled(self, store):
        cal_mod.record_prediction("sh600519", SCORES, "看多", timestamp=f"{_days_ago(20)} 10:00:00")
        # 短线已到期未结算 → pending
        assert len(cal_mod.get_pending_predictions()) == 1
        cal_mod.verify_predictions(get_price_fn=_price_fn())
        # 短线已结算、长线未到期 → 不再 pending
        assert cal_mod.get_pending_predictions() == []

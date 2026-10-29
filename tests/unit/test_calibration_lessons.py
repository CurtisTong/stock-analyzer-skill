"""反思记忆测试（v1.24.0）。

错误结算生成结构化教训（lessons 字段，滚动保留 MAX_LESSONS 条）→
run_debate 注入近 LESSON_INJECT_LIMIT 条 → formatter 渲染"上轮教训"段。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from experts import calibration as cal_mod

# 用 6 位专家的 name/score/direction 与 calibration fixture 对齐
EXPERTS = ["lynch", "soros", "value_institution", "topic_leader", "emotion_tech", "risk_manager"]


def _scores(direction_score: int = 70):
    return {n: direction_score for n in EXPERTS}


def _empty_data():
    return {
        "experts": {n: {"events": 0, "correct": 0, "last_updated": None} for n in EXPERTS},
        "predictions": [],
        "_migrated": True,
    }


@pytest.fixture
def store(monkeypatch):
    state = _empty_data()
    monkeypatch.setattr(cal_mod, "_load", lambda: state)
    monkeypatch.setattr(cal_mod, "_save", lambda d: state.update(d))
    return state


def _days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _price_fn(return_pct):
    def fn(stock, start, end):
        return return_pct

    return fn


class TestLessonGeneration:
    def test_wrong_settlement_generates_lesson(self, store):
        cal_mod.record_prediction("sh600519", _scores(70), "看多", timestamp=f"{_days_ago(200)} 10:00:00")
        cal_mod.verify_predictions(get_price_fn=_price_fn(-8.0))  # 看多但下跌 → 全错

        for name in EXPERTS:
            rec = store["experts"][name]
            assert rec["events"] == 1
            assert rec["correct"] == 0
            lessons = rec.get("lessons", [])
            assert len(lessons) == 1
            assert lessons[0]["direction"] in ("强烈看多", "看多")
            assert lessons[0]["actual_direction"] == "下跌"
            assert lessons[0]["improvement"]  # 规则式改进提示
            assert lessons[0]["stock"] == "sh600519"

    def test_correct_settlement_no_lesson(self, store):
        cal_mod.record_prediction("sh600519", _scores(70), "看多", timestamp=f"{_days_ago(200)} 10:00:00")
        cal_mod.verify_predictions(get_price_fn=_price_fn(6.0))  # 看多且上涨 → 全对

        for name in EXPERTS:
            assert store["experts"][name].get("lessons", []) == []

    def test_lessons_rollover_keeps_last_five(self, store):
        """连续 8 次错误结算 → 只留最近 5 条。"""
        for i in range(8):
            cal_mod.record_prediction(f"sh{i:06d}", _scores(70), "看多", timestamp=f"{_days_ago(200 + i)} 10:00:00")
        cal_mod.verify_predictions(get_price_fn=_price_fn(-8.0))

        for name in EXPERTS:
            lessons = store["experts"][name].get("lessons", [])
            assert len(lessons) == cal_mod.MAX_LESSONS
            assert lessons[-1]["stock"] == "sh000007"  # 最新错单保留

    def test_short_term_lesson_mentions_signal_decay(self, store):
        cal_mod.record_prediction("sh600519", _scores(70), "看多", timestamp=f"{_days_ago(200)} 10:00:00")
        cal_mod.verify_predictions(get_price_fn=_price_fn(-8.0))
        topic_lesson = store["experts"]["topic_leader"]["lessons"][0]
        # 短线组措辞含"衰减/门槛"，长线组措辞含"证伪"
        assert ("衰减" in topic_lesson["improvement"]) or ("门槛" in topic_lesson["improvement"])
        lynch_lesson = store["experts"]["lynch"]["lessons"][0]
        assert "证伪" in lynch_lesson["improvement"]


class TestDebateInjectionAndRender:
    def test_run_debate_injects_lessons(self, store, monkeypatch):
        cal_mod.record_prediction("sh600519", _scores(70), "看多", timestamp=f"{_days_ago(200)} 10:00:00")
        cal_mod.verify_predictions(get_price_fn=_price_fn(-8.0))
        # 重置校准 mock 指向（record 写全局真实文件之外的内存态已被 store 接管）

        from experts.decide import run_debate
        import experts.vote_engine as ve_mod

        # aggregate_votes 内部依赖较多，这里直接 patch 掉避免数据耦合
        fake_result = {
            "composite_score": 45,
            "direction": "看多",
            "expert_results": [{"name": n, "score": 70} for n in EXPERTS],
        }
        monkeypatch.setattr(ve_mod, "aggregate_votes", lambda *a, **k: dict(fake_result))

        result = run_debate("sh600519", fake_result["expert_results"])
        assert "_lessons" in result
        assert "lynch" in result["_lessons"]
        assert len(result["_lessons"]["lynch"]) == 1

        # formatter 渲染"上轮教训"段
        from experts.formatter import format_debate_output

        out = format_debate_output(result)
        assert "上轮教训" in out
        assert "lynch" in out
        assert "improvement" in out or "↳" in out

    def test_no_lessons_skips_section(self):
        from experts.formatter import format_debate_output

        out = format_debate_output(
            {
                "market_state": "震荡",
                "long_weight": 0.6,
                "short_weight": 0.4,
                "long_votes": {"bull": 3, "bear": 1},
                "short_votes": {"bull": 1, "bear": 2},
                "long_avg": 6.0,
                "short_avg": 5.0,
                "composite_score": 60,
                "direction": "看多",
                "confidence": 60,
            }
        )
        assert "上轮教训" not in out

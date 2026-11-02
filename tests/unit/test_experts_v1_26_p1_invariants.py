"""experts 模块 v1.26.0 P1 修复的不变量测试。

锁定 2026-11-02 深度审查发现的 P1 修复行为。这些用例在修复前失败，
现在必须全部通过——防止回归。

对应修复：
- P1 弃权对称（单组模式排除显式弃权）
- P1 整组弃权 → 中性/仓位 0
- P1 veto_results 与 risk_coefficients 并行生效
- P1 弱信号 fallback 与 composite 同口径
- P1 校准落库用原始判断分（不被风险折扣污染）
- P1 校准全局/分组公式一致
- P1 校准因子样本门槛
- P1 同日重录不重复结算
- P1 校准文件损坏不覆盖历史
- P1 长线组校准因子参与信心计算
- P1 market_detector 缺 change_pct → 防御型
- P1 market_detector 宽度数据不被丢弃
- P1 buffett_sub_score / yangjia_sub_score 路径可达
- P1 估值维度使用行业差异化 PE 分位
"""

import json
import logging

import pytest

from experts.types import ExpertProfile

logging.disable(logging.CRITICAL)

_MARKET_STATE = {"state": "震荡", "long_weight": 0.5, "short_weight": 0.5, "reason": "t"}


def _expert(name, score, group="long_term", **kw):
    result = {
        "name": name,
        "group": group,
        "score": score,
        "direction": "看多" if score >= 60 else "中性",
    }
    result.update(kw)
    return result


def _abstain(name, group="long_term"):
    return {"name": name, "group": group, "score": None, "direction": "弃权", "abstain": True}


# ═══════════════════════════════════════════════════════════════
# 弃权对称性
# ═══════════════════════════════════════════════════════════════


class TestAbstainSymmetry:
    """单组与双组模式的弃权处理必须一致。"""

    def test_single_group_excludes_explicit_abstain(self):
        """单组模式必须排除 abstain=True 的专家（与双组一致）。"""
        from experts.vote_engine import aggregate_group_votes

        results = [
            _expert("a", 80),
            _expert("b", 75),
            _expert("c", 80, abstain=True),
        ]
        out = aggregate_group_votes(results, group="long_term")
        assert out["abstained"] == 1
        assert out["votes"]["total"] == 2

    def test_single_group_matches_dual_group(self):
        """同一输入，单组与双组的弃权计数一致。"""
        from experts.vote_engine import aggregate_group_votes, aggregate_votes

        results = [
            _expert("a", 80),
            _expert("b", 75),
            _expert("c", 80, abstain=True),
        ]
        single = aggregate_group_votes(results, group="long_term")
        dual = aggregate_votes(results, market_state=_MARKET_STATE)
        assert single["abstained"] == dual["abstained"] == 1
        assert single["votes"]["total"] == dual["long_votes"]["total"] == 2

    def test_whole_group_abstain_is_neutral_zero_position(self):
        """整组全部弃权 → 方向中性、仓位 0（decide.md §一.2 与 §三 裁决表）。"""
        from experts.vote_engine import aggregate_votes

        results = [
            _abstain("a"),
            _abstain("b"),
            _expert("c", 80, group="short_term"),
        ]
        out = aggregate_votes(results, market_state=_MARKET_STATE)
        assert out["direction"] == "中性"
        assert out["position"]["position_pct"] == 0

    def test_whole_group_abstain_not_polarized(self):
        """整组弃权不得判为"两极分化"。"""
        from experts.vote_engine import aggregate_votes

        results = [
            _abstain("a"),
            _abstain("b"),
            _expert("c", 85, group="short_term"),
            _expert("d", 80, group="short_term"),
            _expert("e", 82, group="short_term"),
        ]
        out = aggregate_votes(results, market_state=_MARKET_STATE)
        notes = " ".join(out.get("notes", []))
        assert "两极分化" not in notes


# ═══════════════════════════════════════════════════════════════
# 风险通道并行
# ═══════════════════════════════════════════════════════════════


class TestRiskChannelsParallel:
    """risk_coefficients 与 veto_results 是两条独立通道，不应互相吞并。"""

    def test_veto_not_swallowed_by_risk_coefficients(self):
        """同时传入两者时，veto_results 仍必须生效。"""
        from experts.vote_engine import aggregate_votes

        results = [
            _expert("a", 80),
            _expert("b", 80),
            _expert("c", 80, group="short_term"),
        ]
        out = aggregate_votes(
            results,
            market_state=_MARKET_STATE,
            risk_coefficients={"a": 0.5},
            veto_results={"b": {"ROE<10%": True}},
        )
        notes = " ".join(out.get("notes", []))
        assert "风险折扣" in notes
        assert "一票否决" in notes

    def test_veto_takes_stricter_result(self):
        """刚性底线（0 分）不得被 veto 的 20 分抬回。"""
        from experts.vote_engine import aggregate_votes

        results = [_expert("a", 80)]
        out = aggregate_votes(
            results,
            market_state=_MARKET_STATE,
            risk_coefficients={"a": 0.0},
            veto_results={"a": {"ROE<10%": True}},
        )
        scored = out["expert_results"][0]
        assert scored["score"] == 0.0


# ═══════════════════════════════════════════════════════════════
# 方向与综合分同源
# ═══════════════════════════════════════════════════════════════


class TestDirectionMatchesComposite:
    """方向判定必须与 composite 同口径，不得自相矛盾。"""

    def test_weak_signal_fallback_uses_weighted_average(self):
        """弱信号兜底的方向必须与 composite 同为加权口径。"""
        from experts.vote_engine import aggregate_votes

        market_state = {"state": "震荡", "long_weight": 0.4, "short_weight": 0.6, "reason": "t"}
        results = [
            _expert("a", 55),
            _expert("b", 45),
            _expert("c", 50),
            _expert("d", 52),
            _expert("e", 48),
            _expert("f", 40, group="short_term"),
        ]
        out = aggregate_votes(results, market_state=market_state)
        composite = out["composite_score"]
        direction = out["direction"]
        # 方向与 composite 必须落在同一阈值区间
        if composite >= 60:
            assert direction in ("看多", "强烈看多")
        elif composite >= 40:
            assert direction in ("中性", "谨慎看多", "谨慎看空")
        else:
            assert direction in ("看空", "强烈看空", "谨慎看空")


# ═══════════════════════════════════════════════════════════════
# 校准落库不被风险折扣污染
# ═══════════════════════════════════════════════════════════════


class TestCalibrationUsesOriginalScore:
    """落库的专家分必须是原始判断分，不是风险折扣分。"""

    def test_original_score_preserved(self):
        """风险折扣后仍保留 _original_score。"""
        from experts.vote_engine import aggregate_votes

        results = [_expert("a", 80)]
        out = aggregate_votes(results, market_state=_MARKET_STATE, risk_coefficients={"a": 0.5})
        scored = out["expert_results"][0]
        assert scored["score"] == 40.0
        assert scored["_original_score"] == 80.0

    def test_record_prediction_uses_original_score(self, tmp_path, monkeypatch):
        """decide.record_prediction 落库用 _original_score。"""
        import experts.calibration as cal_mod
        import experts.decide as decide_mod

        saved = {}

        def _fake_record(**kwargs):
            saved.update(kwargs)
            return "pred-1"

        monkeypatch.setattr(cal_mod, "record_prediction", _fake_record)
        monkeypatch.setattr("experts.registry._ensure_loaded", lambda: None)

        results = [_expert("a", 80)]
        out = decide_mod.run_debate(
            "sh600000",
            results,
            market_state=_MARKET_STATE,
        )
        assert out["_pred_id"] == "pred-1"
        assert saved["expert_scores"]["a"] == 80.0


# ═══════════════════════════════════════════════════════════════
# 校准公式与样本门槛
# ═══════════════════════════════════════════════════════════════


class TestCalibrationFormulaConsistency:
    """全局与分组因子必须同公式；样本不足不参与计算。"""

    def test_group_formula_matches_global(self, monkeypatch):
        """分组因子必须用与全局相同的公式（对同一组数据逐一比对）。"""
        from experts import calibration as cal_mod
        from experts.registry import EXPERT_REGISTRY, _ensure_loaded

        _ensure_loaded()
        experts = {
            "lynch": {"events": 20, "correct": 14},
            "soros": {"events": 20, "correct": 12},
        }
        # （v1.26.0）因子计算改为从 _load 读取（需同时判断是否有真实样本）
        monkeypatch.setattr(cal_mod, "_load", lambda strict=False: {"experts": experts, "_meta": {"source": "live"}})

        # 长线组 active 专家的胜率序列（无数据的按中性 0.5 计入）
        long_names = [n for n, p in EXPERT_REGISTRY.items() if p.active and p.group == "long_term"]
        rates = []
        for name in long_names:
            rec = experts.get(name, {})
            events = rec.get("events", 0)
            rates.append(rec.get("correct", 0) / events if events >= cal_mod.MIN_CALIBRATION_SAMPLES else 0.5)

        expected = cal_mod._calibration_factor_from_rates(rates)
        group = cal_mod.compute_group_calibration("long_term")
        assert abs(group - expected) < 1e-9

    def test_small_sample_excluded(self, monkeypatch):
        """样本数低于门槛的专家不参与因子计算。"""
        from experts import calibration as cal_mod
        from experts.registry import EXPERT_REGISTRY, _ensure_loaded

        _ensure_loaded()
        # lynch 只有 1 条样本且全错；若参与计算会显著拉低因子
        experts = {
            "lynch": {"events": 1, "correct": 0},
            "soros": {"events": 30, "correct": 24},
        }
        monkeypatch.setattr(cal_mod, "_load", lambda strict=False: {"experts": experts, "_meta": {"source": "live"}})

        rates = []
        for name, profile in EXPERT_REGISTRY.items():
            if not profile.active:
                continue
            rec = experts.get(name, {})
            events = rec.get("events", 0)
            if events >= cal_mod.MIN_CALIBRATION_SAMPLES:
                rates.append(rec.get("correct", 0) / events)
            else:
                rates.append(0.5)  # 无数据或样本不足 → 中性

        expected = cal_mod._calibration_factor_from_rates(rates)
        factor = cal_mod.compute_calibration_factor()
        assert abs(factor - expected) < 1e-9
        # lynch 的 1 样本未按 0% 计入（否则 rates 里会是 0.0）
        assert 0.0 not in rates


# ═══════════════════════════════════════════════════════════════
# 同日重录不重复结算
# ═══════════════════════════════════════════════════════════════


class TestNoDoubleSettlement:
    """同日同股重录不得导致同一次预测被结算两遍。"""

    def test_rerecord_preserves_settled_state(self, tmp_path, monkeypatch):
        """重录保留已结算标记，不清空。"""
        import experts.calibration as cal_mod

        state = {
            "predictions": [
                {
                    "id": "sh600000-2026-01-01",
                    "stock": "sh600000",
                    "date": "2026-01-01",
                    "direction": "看多",
                    "composite_score": 70.0,
                    "expert_scores": {"lynch": 70.0},
                    "verified": True,
                    "verify_after": "2026-07-01",
                    "expert_horizons": {"lynch": "2026-07-01"},
                    "settled_experts": ["lynch"],
                    "actual_return": 10.0,
                    "actual_direction": "上涨",
                }
            ],
            "experts": {"lynch": {"events": 1, "correct": 1}},
            "_migrated": True,
        }
        monkeypatch.setattr(cal_mod, "_load", lambda strict=False: state)
        monkeypatch.setattr(cal_mod, "_save", lambda data, assume_locked=False: None)

        cal_mod.record_prediction(
            "sh600000",
            {"lynch": 75.0},
            "看多",
            timestamp="2026-01-01 10:00:00",
        )
        pred = state["predictions"][0]
        # 已结算的 lynch 不得被清空（否则会二次结算，events 1→2）
        assert pred["settled_experts"] == ["lynch"]
        assert pred["verified"] is True


# ═══════════════════════════════════════════════════════════════
# 校准文件损坏
# ═══════════════════════════════════════════════════════════════


class TestCorruptCalibrationFile:
    """损坏文件不得被静默覆盖。"""

    def test_write_path_raises_and_backs_up(self, tmp_path, monkeypatch):
        """写路径遇损坏文件必须抛错，并保留备份。"""
        import experts.calibration as cal_mod

        corrupt = tmp_path / "expert_calibration.json"
        corrupt.write_text('{"predictions": [ broken', encoding="utf-8")
        monkeypatch.setattr(cal_mod, "_CALIBRATION_FILE", corrupt)

        with pytest.raises(ValueError, match="损坏"):
            cal_mod._load(strict=True)

        backups = list(tmp_path.glob("*.corrupted-*.json"))
        assert backups, "损坏文件应被备份"
        assert backups[0].read_text(encoding="utf-8").startswith("{")

    def test_read_path_degrades(self, tmp_path, monkeypatch):
        """只读路径降级为空数据，不抛错。"""
        import experts.calibration as cal_mod

        corrupt = tmp_path / "expert_calibration.json"
        corrupt.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(cal_mod, "_CALIBRATION_FILE", corrupt)

        data = cal_mod._load()
        assert data["predictions"] == []


# ═══════════════════════════════════════════════════════════════
# 长线组校准因子参与计算
# ═══════════════════════════════════════════════════════════════


class TestLongGroupCalibrationConsumed:
    """长线组校准因子必须参与信心计算，不能只展示。"""

    def test_long_group_penalty_applied(self, monkeypatch):
        """长线组校准为负时应扣减信心指数并留下说明。"""
        import experts.vote_engine as ve

        monkeypatch.setattr(
            "experts.calibration.compute_group_calibration",
            lambda group: -0.5 if group == "long_term" else 0.0,
        )
        results = [
            _expert("a", 75),
            _expert("b", 75),
            _expert("c", 75, group="short_term"),
        ]
        out = ve.aggregate_votes(results, market_state=_MARKET_STATE)
        notes = " ".join(out.get("notes", []))
        assert "长线组校准惩罚" in notes


# ═══════════════════════════════════════════════════════════════
# market_detector fail-safe
# ═══════════════════════════════════════════════════════════════


class TestMarketDetectorFailSafe:
    """缺数据时不得比"防御型"更乐观。"""

    def test_missing_change_pct_is_defensive(self):
        """index_quote 无 change_pct → 防御型（修复前是"震荡"）。"""
        from experts.market_detector import classify_market_state

        assert classify_market_state(index_quote={"price": 3000}) == "防御型"

    def test_breadth_only_can_detect_ice(self):
        """仅宽度数据可得时，冰点信号仍应触发。"""
        from experts.market_detector import classify_market_state

        ice = {"advance_ratio": 0.08, "limit_down_count": 80, "new_high_low_ratio": 0.15}
        assert classify_market_state(breadth_data=ice) == "冰点"


# ═══════════════════════════════════════════════════════════════
# 子评分路径可达
# ═══════════════════════════════════════════════════════════════


class TestSubScorePaths:
    """合并型专家的子评分必须能被 vote_engine 读到。"""

    def test_yangjia_sub_score_in_dim_scores(self):
        """yangjia_sub_score 在 dim_scores 里也要能读到。"""
        from experts.vote_engine import _get_yangjia_emotion_score

        yangjia = {
            "name": "emotion_tech",
            "score": 60,
            "breakdown": {"情绪": 10},
            "dim_scores": {"情绪": 50, "yangjia_sub_score": 100},
        }
        assert _get_yangjia_emotion_score(yangjia) == 100.0

    def test_buffett_sub_score_triggers_warning(self):
        """dim_scores 里的 buffett_sub_score 应触发巴菲特否决警示。"""
        from experts.vote_engine import aggregate_votes

        results = [
            _expert("value_institution", 70, dim_scores={"buffett_sub_score": 30, "情绪": 50}),
            _expert("topic_leader", 70, group="short_term"),
        ]
        out = aggregate_votes(results, market_state=_MARKET_STATE, horizon="medium")
        notes = " ".join(out.get("notes", []))
        assert "巴菲特" in notes


# ═══════════════════════════════════════════════════════════════
# 估值维度使用行业差异化 PE 分位
# ═══════════════════════════════════════════════════════════════


class TestValuationUsesIndustryPercentile:
    """估值维度必须使用 strategies.factors.score_utils 的行业差异化分位。"""

    def test_industry_differentiation_active(self):
        """不同行业的同一 PE 应给出不同估值分。"""
        from experts.scoring._utils import _score_valuation

        default = _score_valuation({"pe": 30, "pb": 2}, {})
        bank = _score_valuation({"pe": 30, "pb": 2}, {}, industry="银行")
        assert default != bank, "行业差异化阈值未生效（导入路径错误或被静默兜底）"

    def test_import_path_exists(self):
        """strategies.factors.score_utils 必须可导入。"""
        import strategies.factors.score_utils as su

        assert callable(su.pe_percentile)


# ═══════════════════════════════════════════════════════════════
# 专家维度权重镜像
# ═══════════════════════════════════════════════════════════════


class TestExpertWeightMirror:
    """md §九 权重表与 YAML 必须一致（守护存在）。"""

    def test_weight_sync_contract_exists(self):
        """TestWeightSync 类必须真实存在（此前只是注释里的虚构引用）。"""
        import importlib

        mod = importlib.import_module("tests.contracts.test_expert_weight_sync")
        assert hasattr(mod, "TestWeightSync")

    def test_md_weights_parse(self):
        """能从专家 md 解析出维度权重。"""
        import importlib
        from pathlib import Path

        mod = importlib.import_module("tests.contracts.test_expert_weight_sync")
        md = Path("experts/buffett.md")
        if not md.exists():
            pytest.skip("md 不存在")
        weights = mod._parse_md_weights(md)
        assert weights, "buffett.md 应能解析出维度权重"
        assert abs(sum(weights.values()) - 100.0) <= 1.0


# ═══════════════════════════════════════════════════════════════
# debate 生产闭环
# ═══════════════════════════════════════════════════════════════


class TestDebateProductionLoop:
    """run_debate 必须有生产调用方，且落库可控。"""

    def test_cli_exposes_debate_mode(self):
        """experts_cli 必须提供 --debate 入口（此前 run_debate 无生产调用方）。"""
        import importlib
        import inspect

        mod = importlib.import_module("scripts.dev.experts_cli")
        assert hasattr(mod, "run_debate_for_stock"), "缺少 debate 闭环入口"
        sig = inspect.signature(mod.run_debate_for_stock)
        assert "record" in sig.parameters, "run_debate_for_stock 应支持关闭落库"

    def test_run_debate_supports_record_flag(self):
        """experts.decide.run_debate 必须支持 record=False（试跑不落库）。"""
        import inspect

        from experts.decide import run_debate

        sig = inspect.signature(run_debate)
        assert "record" in sig.parameters
        assert sig.parameters["record"].default is True

    def test_record_false_does_not_write(self, tmp_path, monkeypatch):
        """record=False 时不得写校准库。"""
        import experts.calibration as cal_mod
        from experts.decide import run_debate

        called = []
        monkeypatch.setattr(cal_mod, "record_prediction", lambda **kw: called.append(kw) or "x")

        results = [_expert("a", 70), _expert("b", 70, group="short_term")]
        run_debate("sh600000", results, market_state=_MARKET_STATE, record=False)
        assert not called, "record=False 时不应调用 record_prediction"

    def test_record_true_writes_original_scores(self, monkeypatch):
        """record=True 时落库的是原始判断分。"""
        import experts.calibration as cal_mod
        from experts.decide import run_debate

        captured = {}
        monkeypatch.setattr(cal_mod, "record_prediction", lambda **kw: captured.update(kw) or "pred-1")

        results = [_expert("a", 80)]
        out = run_debate("sh600000", results, market_state=_MARKET_STATE)
        # 无风险折扣时落库分 = 原始分
        assert captured["expert_scores"]["a"] == 80.0
        assert out["_pred_id"] == "pred-1"


class TestNoneSafeScoring:
    """上游把缺失字段显式置 None 时，专家不得崩溃。"""

    def test_xu_xiang_handles_none_market_fields(self):
        """sector_limit_up_count / seal_ratio 为 None 时不崩。"""
        from experts.scoring import xu_xiang

        data = {
            "quote": {"pe": 20.0, "pb": 2.0, "circulating_cap": 80.0},
            "finance": {"eps": 0.5},
            "market_features": {
                "limit_up_count": None,
                "limit_down_count": None,
                "sector_limit_up_count": None,
                "seal_to_circ_ratio": None,
                "advance_ratio": None,
                "index_above_ma20": None,
            },
            "kline_data": {},
        }
        result = xu_xiang.score(data)  # 不得抛 TypeError
        assert isinstance(result, dict)
        assert all(isinstance(v, (int, float)) for v in result.values() if v is not None)

    def test_all_active_experts_survive_none_market_fields(self):
        """8 位 active 专家在 None 字段下均不崩溃。"""
        from experts import list_active_experts
        from experts.scoring import score_expert_precise

        data = {
            "quote": {
                "pe": None,
                "pb": None,
                "price": None,
                "circulating_cap": None,
                "pe_percentile": None,
                "name": None,
                "amount": None,
            },
            "finance": {
                "roe": None,
                "net_profit_yoy": None,
                "debt_ratio": None,
                "eps": None,
                "ocf_per_share": None,
            },
            "kline_features": {"trend": None, "rsi": None, "macd_signal": None},
            "kline_data": {},
            "market_features": {
                "limit_up_count": None,
                "limit_down_count": None,
                "advance_ratio": None,
                "break_rate": None,
                "limit_up_30d_count": None,
                "sector_limit_up_count": None,
            },
        }
        for profile in list_active_experts():
            result = score_expert_precise(profile, data)
            assert result["score"] is None or isinstance(result["score"], (int, float))


# ═══════════════════════════════════════════════════════════════
# P2/P3 修复（v1.26.0 二次审查）
# ═══════════════════════════════════════════════════════════════


class TestDefensiveKeyAccess:
    """公共 API 不应因调用方漏字段而崩溃。"""

    def test_missing_score_key_treated_as_abstain(self):
        """缺 score 键 → 按弃权处理，不抛 KeyError。"""
        from experts.vote_engine import aggregate_votes

        results = [
            {"name": "a", "group": "long_term", "direction": "看多"},  # 无 score
            _expert("b", 70),
        ]
        out = aggregate_votes(results, market_state=_MARKET_STATE)
        assert out["abstained"] == 1

    def test_none_score_treated_as_abstain(self):
        """score=None 但无 abstain 标记 → 按弃权处理。"""
        from experts.vote_engine import aggregate_votes

        results = [
            {"name": "a", "group": "long_term", "score": None, "direction": "看多"},
            _expert("b", 70),
        ]
        out = aggregate_votes(results, market_state=_MARKET_STATE)
        assert out["abstained"] == 1

    def test_missing_direction_defaults_from_score(self):
        """缺 direction 键 → 由分数推导，不抛 KeyError。"""
        from experts.vote_engine import aggregate_votes

        results = [
            {"name": "a", "group": "long_term", "score": 75},  # 无 direction
            _expert("b", 70),
        ]
        out = aggregate_votes(results, market_state=_MARKET_STATE)
        assert out["direction"] in ("看多", "强烈看多", "中性")


class TestGroupCalibrationIsolation:
    """分组校准的单组失败不得影响另一组。"""

    def test_one_group_failure_does_not_block_other(self, monkeypatch):
        """短线组抛错时，长线组惩罚仍应生效。"""
        import experts.vote_engine as ve

        def _boom(group):
            if group == "short_term":
                raise RuntimeError("boom")
            return -0.5

        monkeypatch.setattr("experts.calibration.compute_group_calibration", _boom)
        results = [_expert("a", 75), _expert("b", 75), _expert("c", 75, group="short_term")]
        out = ve.aggregate_votes(results, market_state=_MARKET_STATE)
        notes = " ".join(out.get("notes", []))
        assert "长线组校准惩罚" in notes


class TestPartialCalibrationEntry:
    """残缺校准条目不得中断整轮 verify。"""

    def test_missing_events_key_does_not_crash(self, tmp_path, monkeypatch):
        """专家条目缺 events 键 → 从 0 起算，不抛 KeyError。"""
        import experts.calibration as cal_mod

        state = {
            "predictions": [
                {
                    "id": "pred_x",
                    "stock": "sh600000",
                    "date": "2026-01-01",
                    "direction": "看多",
                    "expert_scores": {"lynch": 70.0},
                    "verified": False,
                    "verify_after": "2026-01-15",
                    "expert_horizons": {"lynch": "2026-01-15"},
                    "settled_experts": [],
                }
            ],
            # lynch 条目缺 events 键
            "experts": {"lynch": {"correct": 3}},
            "_migrated": True,
        }
        monkeypatch.setattr(cal_mod, "_load", lambda strict=False: state)
        monkeypatch.setattr(cal_mod, "_save", lambda data, assume_locked=False: None)

        result = cal_mod.verify_predictions(get_price_fn=lambda *a: 10.0)
        assert result["verified"] == 1
        assert state["experts"]["lynch"]["events"] == 1


class TestVetoEvaluatorMissingness:
    """数据缺失判定须用键存在性，不能把合法值当缺失。"""

    def test_loss_making_company_not_treated_as_missing(self):
        """ROE=0（亏损）不应被判为"数据缺失"而跳过风险折扣。"""
        from experts.veto_evaluator import _check_roe_low

        result = _check_roe_low({"finance": {"roe": 0.0, "debt_ratio": 30.0}})
        assert result.evaluable is True
        assert result.triggered is True


class TestFcfConsecutive:
    """FCF 连续 2 年为负 → 0.3 档（而非恒 0.6）。"""

    def test_single_year_negative_is_0_6(self):
        from experts.veto_evaluator import _check_fcf_negative

        result = _check_fcf_negative({"finance": {"ocf_per_share": -0.5}})
        assert result.risk_coeff == 0.6

    def test_two_consecutive_negative_is_0_3(self):
        from experts.veto_evaluator import _check_fcf_negative

        result = _check_fcf_negative(
            {
                "finance": {"ocf_per_share": -0.5},
                "finance_records": [{"ocf_per_share": -0.5}, {"ocf_per_share": -0.3}],
            }
        )
        assert result.risk_coeff == 0.3


class TestReasoningChainWeights:
    """推理链的别名维度权重不得显示 0%。"""

    def test_alias_dimension_weight_resolved(self):
        """soros 的"情绪/反身性"应显示 30% 而非 0%。"""
        from experts.registry import EXPERT_REGISTRY, _ensure_loaded
        from experts.scoring._utils import generic_score_with_reasoning

        _ensure_loaded()
        profile = EXPERT_REGISTRY["soros"]
        result = generic_score_with_reasoning(
            profile,
            lambda d: {"情绪/反身性": 80.0},
            {},
        )
        dim = result["dimensions"]["情绪/反身性"]
        assert dim["weight"] > 0, "别名维度权重不得为 0"


class TestNoDoubleComputation:
    """合并型专家的子专家不得被重复计算。"""

    def test_value_institution_scores_sub_experts_once(self, monkeypatch):
        """value_institution.score_with_reasoning 只算一次子专家。"""
        from experts.registry import _ensure_loaded
        from experts.scoring import institution, value_anchor
        from experts.scoring.value_institution import score_with_reasoning

        _ensure_loaded()
        calls = {"va": 0, "inst": 0}
        orig_va, orig_inst = value_anchor.score, institution.score

        def _va(d):
            calls["va"] += 1
            return orig_va(d)

        def _inst(d):
            calls["inst"] += 1
            return orig_inst(d)

        monkeypatch.setattr(value_anchor, "score", _va)
        monkeypatch.setattr(institution, "score", _inst)

        score_with_reasoning(
            {
                "quote": {"pe": 20, "pb": 2, "circulating_cap": 80},
                "finance": {"roe": 15, "net_profit_yoy": 10, "debt_ratio": 40, "eps": 0.5},
                "kline_features": {"trend": 1, "rsi": 50, "macd_signal": 1},
                "market_features": {"limit_up_count": 30, "advance_ratio": 0.5},
            }
        )
        assert calls["va"] == 1
        assert calls["inst"] == 1


# ═══════════════════════════════════════════════════════════════
# 剩余项修复（v1.26.0 第三批）
# ═══════════════════════════════════════════════════════════════


class TestMarkOnlyDoesNotDestroySamples:
    """mark_only 不得让样本永久无法结算。"""

    def test_mark_only_keeps_sample_settleable(self, tmp_path, monkeypatch):
        """mark_only 后仍能用真实价格结算该样本。"""
        import experts.calibration as cal_mod

        state = {
            "predictions": [
                {
                    "id": "pred_x",
                    "stock": "sh600000",
                    "date": "2026-01-01",
                    "direction": "看多",
                    "expert_scores": {"lynch": 70.0},
                    "verified": False,
                    "verify_after": "2026-01-15",
                    "expert_horizons": {"lynch": "2026-01-15"},
                    "settled_experts": [],
                }
            ],
            "experts": {"lynch": {"events": 0, "correct": 0}},
            "_meta": {"source": "live"},
            "_migrated": True,
        }
        monkeypatch.setattr(cal_mod, "_load", lambda strict=False: state)
        monkeypatch.setattr(cal_mod, "_save", lambda data, assume_locked=False: None)

        cal_mod.verify_predictions(mark_only=True)
        assert state["predictions"][0]["settled_experts"] == []
        assert state["predictions"][0].get("marked_experts") == ["lynch"]

        result = cal_mod.verify_predictions(get_price_fn=lambda *a: 10.0)
        assert result["verified"] == 1
        assert state["experts"]["lynch"]["events"] == 1


class TestSyntheticSamplesExcluded:
    """合成（回测初始化）样本不得参与校准。"""

    def test_synthetic_library_detected(self):
        from experts.calibration import is_synthetic_calibration

        assert is_synthetic_calibration({"_meta": {"source": "backtest_2026-06-16"}})
        assert not is_synthetic_calibration({"_meta": {"source": "live"}})

    def test_synthetic_migration_separates_counters(self):
        """合成胜率迁移到 synthetic_* 字段，events/correct 归零。"""
        import experts.calibration as cal_mod

        data = {
            "experts": {"lynch": {"events": 10, "correct": 8}},
            "_meta": {"source": "backtest_2026-06-16"},
        }
        migrated = cal_mod._migrate_synthetic_experts(data)
        rec = migrated["experts"]["lynch"]
        assert rec["synthetic_events"] == 10
        assert rec["synthetic_correct"] == 8
        assert rec["events"] == 0
        assert rec["correct"] == 0

    def test_migration_is_idempotent(self):
        import experts.calibration as cal_mod

        data = {
            "experts": {"lynch": {"events": 10, "correct": 8}},
            "_meta": {"source": "backtest_2026-06-16"},
        }
        once = cal_mod._migrate_synthetic_experts(dict(data))
        twice = cal_mod._migrate_synthetic_experts(once)
        assert twice["experts"]["lynch"]["synthetic_events"] == 10
        assert twice["experts"]["lynch"]["events"] == 0

    def test_no_real_samples_means_no_calibration(self, monkeypatch):
        """没有真实结算样本时因子为 0（不做校准）。"""
        import experts.calibration as cal_mod

        monkeypatch.setattr(
            cal_mod,
            "_load",
            lambda strict=False: {
                "experts": {"lynch": {"events": 0, "correct": 0}},
                "_meta": {"source": "live"},
            },
        )
        assert cal_mod.compute_calibration_factor() == 0.0
        assert cal_mod.compute_group_calibration("long_term") == 0.0


class TestCalibrationLocking:
    """读-改-写必须在跨进程排他锁内完成。"""

    def test_lock_context_manager_available(self):
        """_calibration_lock 必须存在（_save 的 assume_locked 依赖它）。"""
        from experts import calibration as cal_mod

        assert hasattr(cal_mod, "_calibration_lock")

    def test_save_accepts_assume_locked(self):
        """_save 支持 assume_locked（避免同进程双 flock 死锁）。"""
        import inspect

        from experts.calibration import _save

        assert "assume_locked" in inspect.signature(_save).parameters


class TestIndustryPassedToVeto:
    """行业分类须传给周期位置否决。"""

    def test_stock_data_carries_industry(self):
        """experts_cli 构造的 stock_data 必须带 industry。"""
        import inspect

        import scripts.dev.experts_cli as cli

        src = inspect.getsource(cli.build_stock_data)
        assert '"industry"' in src


class TestDegradedMarketData:
    """上游降级的市场宽度数据不得被当成真实值。"""

    def _degraded_stock_data(self):
        return {
            "quote": {
                "pe": 25,
                "pb": 3,
                "price": 10,
                "circulating_cap": 80,
                "pe_percentile": 50,
                "name": "测试",
                "amount": 8e9,
            },
            "finance": {"roe": 15, "net_profit_yoy": 20, "debt_ratio": 40, "eps": 0.8},
            "kline_features": {"trend": 1, "rsi": 45, "macd_signal": 1},
            "market_features": {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "advance_ratio": 0.5,
                "break_rate": 0,
                "limit_up_30d_count": None,
                "sector_limit_up_count": None,
                "_degraded": True,
                "_degraded_reason": "指数 API 异常",
            },
        }

    def test_degraded_detected(self):
        from experts.scoring.availability import is_degraded_market_data

        assert is_degraded_market_data(self._degraded_stock_data()["market_features"])
        assert not is_degraded_market_data({"limit_up_count": 125})

    def test_degraded_fields_neutralized(self):
        """降级字段被置 None（不可得），不再是占位 0。"""
        from experts.scoring.availability import normalize_market_features

        data = self._degraded_stock_data()
        normalized = normalize_market_features(data)
        assert normalized["limit_up_count"] is None
        assert normalized["advance_ratio"] is None
        # 降级标记本身保留
        assert normalized["_degraded"] is True

    def test_non_degraded_unchanged(self):
        """未降级时字段原样保留。"""
        from experts.scoring.availability import normalize_market_features

        data = self._degraded_stock_data()
        data["market_features"] = {"limit_up_count": 125, "advance_ratio": 0.85}
        normalized = normalize_market_features(data)
        assert normalized["limit_up_count"] == 125
        assert normalized["advance_ratio"] == 0.85

    def test_sentiment_signal_absent_when_degraded(self):
        """降级时题材信号不可得。"""
        from experts.scoring.availability import available_signals, SIGNAL_SENTIMENT

        signals = available_signals(self._degraded_stock_data())
        assert SIGNAL_SENTIMENT not in signals

    def test_emotion_tech_abstains_on_degraded(self):
        """降级时短线情绪专家弃权（而非被打成强烈看空）。"""
        from experts.registry import EXPERT_REGISTRY, _ensure_loaded
        from experts.scoring import score_expert_precise

        _ensure_loaded()
        result = score_expert_precise(EXPERT_REGISTRY["emotion_tech"], self._degraded_stock_data())
        assert result["abstain"] is True
        assert result["direction"] == "弃权"

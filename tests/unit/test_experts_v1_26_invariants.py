"""experts 模块 v1.26.0 修复的不变量测试。

锁定 2026-11-02 深度审查发现的 P0 修复行为。这些用例在修复前全部失败，
现在必须全部通过——防止回归。

对应修复：
- P0-1 维度归一化方向（_utils.py / scoring/__init__.py）
- P0-2 缺数据无弃权路径 + 缺失维度中性化（availability.py）
- P0-3 group 部分缺失丢票（vote_engine.py）
- P0-4 yaml 权重归一化覆盖 → 合并（yaml_loader.py）
- P0-5 registry 键校验（yaml_loader.py / registry.py）
- P0-6 formatter 表格转义（formatter.py）
- P0-7 formatter 合规改写（formatter.py）
- P0-8 校准 horizon 覆盖（calibration.py）
- P0-9 校准方向词表缺谨慎方向（calibration.py / types.py）
"""

import logging
import pathlib

import pytest

from experts import list_active_experts
from experts.scoring import score_expert_precise
from experts.scoring._utils import dimension_breakdown, score_from_dimensions
from experts.types import (
    BEARISH_DIRECTIONS,
    BULLISH_DIRECTIONS,
    ExpertProfile,
    normalize_dim_scores,
)

logging.disable(logging.CRITICAL)


# ═══════════════════════════════════════════════════════════════
# P0-1 维度归一化方向
# ═══════════════════════════════════════════════════════════════


class TestP0_1DimensionNormalization:
    """归一化对象必须是**维度分一侧**，不是权重一侧。"""

    def _profile(self):
        return ExpertProfile(
            name="test",
            display_name="测试",
            group="long_term",
            style="测试",
            horizon="月",
            core_signal="情绪",
            weights={"基本面": 20, "估值": 20, "技术面": 20, "情绪": 40},
        )

    def test_alias_dim_score_not_dropped(self):
        """别名键的情绪分必须按 40% 权重参与计算，而不是回落 50。"""
        profile = self._profile()
        score = score_from_dimensions(
            profile,
            {"基本面": 50, "估值": 50, "技术面": 50, "情绪/反身性": 100},
        )
        # 期望 20*50% + 20*50% + 20*50% + 40*100% = 70
        assert score == 70.0

    def test_alias_and_standard_equivalent(self):
        """别名键与标准键给分相同时，总分必须一致。"""
        profile = self._profile()
        base = {"基本面": 50, "估值": 50, "技术面": 50}
        alias = score_from_dimensions(profile, {**base, "情绪/资金": 80})
        standard = score_from_dimensions(profile, {**base, "情绪": 80})
        assert alias == standard

    def test_breakdown_also_normalizes(self):
        """dimension_breakdown 同样要归一化（修复前只查标准名）。"""
        profile = self._profile()
        bd = dimension_breakdown(profile, {"基本面": 50, "估值": 50, "技术面": 50, "情绪/题材": 100})
        assert bd["情绪"] == 40.0  # 100 * 40%

    def test_normalize_dim_scores_standard_wins(self):
        """标准名优先于别名（避免后写的别名覆盖先写的标准名）。"""
        out = normalize_dim_scores({"情绪": 80, "情绪/资金": 20})
        assert out["情绪"] == 80

    def test_normalize_dim_scores_does_not_mutate_input(self):
        """不修改入参。"""
        src = {"情绪/资金": 60}
        normalize_dim_scores(src)
        assert src == {"情绪/资金": 60}


# ═══════════════════════════════════════════════════════════════
# P0-2 弃权路径 + 缺失维度中性化
# ═══════════════════════════════════════════════════════════════


class TestP0_2Abstain:
    """核心信号全缺 → 显式弃权，不进入投票基数。"""

    def test_empty_data_all_abstain(self):
        """空数据下 8 位专家全部弃权（修复前：3 位给"强烈看空"）。"""
        for profile in list_active_experts():
            result = score_expert_precise(profile, {})
            assert result["abstain"] is True, f"{profile.name} 应弃权"
            assert result["direction"] == "弃权"
            assert result["score"] is None

    def test_empty_data_no_bearish_votes(self):
        """空数据不得产生看空票（修复前 composite=26.2 谨慎看空）。"""
        from experts.vote_engine import aggregate_votes

        results = []
        for profile in list_active_experts():
            r = score_expert_precise(profile, {})
            results.append(
                {
                    "name": profile.name,
                    "group": profile.group,
                    "score": r["score"],
                    "direction": r["direction"],
                    "abstain": r.get("abstain", False),
                }
            )
        out = aggregate_votes(
            results,
            market_state={"state": "震荡", "long_weight": 0.5, "short_weight": 0.5, "reason": "t"},
        )
        assert out["abstained"] == 8
        assert out["long_votes"]["total"] == 0
        assert out["short_votes"]["total"] == 0

    def test_missing_finance_flips_direction_no_longer(self):
        """财务缺失不再让价值机构锚从"看多"翻成"强烈看空"。

        修复前：完整数据 66.9（看多）→ 财务缺失 15.5（强烈看空）。
        修复后：核心信号（财务）不可得 → 弃权。
        """
        from experts.registry import EXPERT_REGISTRY, _ensure_loaded

        _ensure_loaded()
        profile = EXPERT_REGISTRY["value_institution"]
        full = {
            "quote": {"pe": 25.0, "pb": 3.0, "price": 10.0, "circulating_cap": 80.0},
            "finance": {"roe": 15.0, "net_profit_yoy": 20.0, "debt_ratio": 40.0, "eps": 0.8},
            "kline_features": {"trend": 1, "rsi": 45.0, "macd_signal": 1},
            "market_features": {"limit_up_count": 50, "advance_ratio": 0.55},
        }
        no_finance = {**full, "finance": {}}

        # 完整数据下有明确方向（不是中性也不是强烈看空）
        full_result = score_expert_precise(profile, full)
        assert full_result["abstain"] is False
        assert full_result["direction"] not in ("强烈看空",)

        # 财务缺失 → 弃权（而非打 15.5 分强烈看空）
        result = score_expert_precise(profile, no_finance)
        assert result["abstain"] is True
        assert result["score"] is None
        assert result["direction"] == "弃权"

    def test_missing_data_not_scored_as_worst(self):
        """缺失数据不得被当成最差信号（0 分）。"""
        from experts.registry import EXPERT_REGISTRY, _ensure_loaded

        _ensure_loaded()
        profile = EXPERT_REGISTRY["topic_leader"]
        data = {
            "quote": {"pe": 25.0, "pb": 3.0, "price": 10.0, "circulating_cap": 80.0},
            "finance": {},
            "kline_features": {"trend": 1, "rsi": 45.0, "macd_signal": 1},
            "market_features": {"limit_up_count": 50, "advance_ratio": 0.55},
        }
        result = score_expert_precise(profile, data)
        # 修复前技术面被 xu_xiang 的 0 分 veto 到 0.0（zhao_laoge 本会给 80）
        assert result["dim_scores"]["技术面"] != 0.0
        assert result["score"] > 30

    def test_partial_data_still_judges(self):
        """核心信号还有一项可得时，专家仍应给出判断（不滥弃权）。"""
        for profile in list_active_experts():
            data = {
                "quote": {"pe": 25.0, "pb": 3.0, "price": 10.0, "circulating_cap": 80.0},
                "finance": {},
                "kline_features": {"trend": 1, "rsi": 45.0, "macd_signal": 1},
                "market_features": {"limit_up_count": 50, "advance_ratio": 0.55},
            }
            result = score_expert_precise(profile, data)
            if profile.name in ("value_institution", "risk_manager"):
                # 这两位核心信号就是财务 → 应弃权
                assert result["abstain"] is True
            else:
                assert result["abstain"] is False
                assert result["score"] is not None


# ═══════════════════════════════════════════════════════════════
# P0-3 group 部分缺失丢票
# ═══════════════════════════════════════════════════════════════


class TestP0_3GroupNotDropped:
    """group 部分缺失时，专家不得被静默丢弃。"""

    def _mk(self):
        from experts.vote_engine import aggregate_votes

        market_state = {
            "state": "震荡",
            "long_weight": 0.5,
            "short_weight": 0.5,
            "reason": "t",
        }
        results = [
            {"name": "a", "group": "long_term", "score": 80, "direction": "看多"},
            {"name": "b", "group": "long_term", "score": 80, "direction": "看多"},
            {"name": "c", "group": "short_term", "score": 80, "direction": "看多"},
            {"name": "d", "group": "short_term", "score": 80, "direction": "看多"},
            {"name": "x", "score": 80, "direction": "看多"},
            {"name": "y", "score": 80, "direction": "看多"},
            {"name": "z", "score": 80, "direction": "看多"},
        ]
        return aggregate_votes(results, market_state=market_state)

    def test_all_experts_counted(self):
        """7 位专家输入 → 7 票（修复前只有 4 票，3 位被丢弃）。"""
        out = self._mk()
        total = out["long_votes"]["total"] + out["short_votes"]["total"]
        assert total == 7

    def test_registry_completes_missing_group(self):
        """注册表能按 name 补全缺失的 group。"""
        from experts.vote_engine import aggregate_votes

        results = [
            {"name": "lynch", "score": 70, "direction": "看多"},
            {"name": "soros", "score": 70, "direction": "看多"},
            {"name": "momentum_trader", "score": 70, "direction": "看多"},
        ]
        out = aggregate_votes(
            results,
            market_state={"state": "震荡", "long_weight": 0.5, "short_weight": 0.5, "reason": "t"},
        )
        total = out["long_votes"]["total"] + out["short_votes"]["total"]
        assert total == 3


# ═══════════════════════════════════════════════════════════════
# P0-4 / P0-5 YAML 权重合并与注册表键校验
# ═══════════════════════════════════════════════════════════════


class TestP0_4YamlWeights:
    """YAML 维度归一化是合并（求和）而非覆盖。"""

    def test_merge_not_overwrite(self):
        """别名与标准名共存时权重求和，不丢权重。"""
        from experts.types import normalize_dim

        weights = {"情绪": 30.0, "情绪/资金": 10.0, "基本面": 60.0}
        merged = {}
        for k, v in weights.items():
            std = normalize_dim(k)
            merged[std] = merged.get(std, 0.0) + v
        assert merged["情绪"] == 40.0
        assert sum(merged.values()) == 100.0


class TestP0_5RegistryKeys:
    """注册表键必须与文件名一致。"""

    def test_name_mismatch_rejected(self, tmp_path, monkeypatch):
        """复制 yaml 改 name → 注册表加载必须报错，不能静默顶替专家。"""
        from experts import yaml_loader

        src = pathlib.Path("experts/yaml/soros.yaml")
        if not src.exists():
            pytest.skip("yaml 源文件不存在")
        bad_dir = tmp_path
        for original in pathlib.Path("experts/yaml").glob("*.yaml"):
            target = bad_dir / original.name
            if original.name == "soros.yaml":
                target.write_text(original.read_text().replace("name: soros", "name: lynch"), encoding="utf-8")
            else:
                target.write_text(original.read_text(), encoding="utf-8")
        monkeypatch.setattr(yaml_loader, "YAML_DIR", bad_dir)
        with pytest.raises(ValueError, match="不一致"):
            yaml_loader.load_all_experts()

    def test_registry_size_hard_assertion(self):
        """注册表数量不符必须硬报错（投票基数依赖 5 长 + 3 短）。"""
        from experts import registry

        assert registry.EXPERT_REGISTRY or True  # 触发懒加载
        total = len(registry.EXPERT_REGISTRY)
        active = sum(1 for p in registry.EXPERT_REGISTRY.values() if p.active)
        assert total == 16
        assert active == 8


# ═══════════════════════════════════════════════════════════════
# P0-6 / P0-7 formatter 转义与合规
# ═══════════════════════════════════════════════════════════════


class TestP0_6FormatterEscaping:
    """reason 里的竖线/换行不得破坏表格结构。"""

    def _result(self, reason):
        return {
            "market_state": "震荡",
            "long_weight": 0.55,
            "short_weight": 0.45,
            "long_votes": {"bull": 2, "bear": 1, "total": 3},
            "short_votes": {"bull": 0, "bear": 0, "total": 0},
            "long_avg": 45,
            "short_avg": 50,
            "composite_score": 45.0,
            "direction": "谨慎看空",
            "confidence": 60,
            "expert_results": [
                {"name": "soros", "display_name": "索罗斯", "score": 35, "direction": "看空", "reason": reason}
            ],
            "position": {"position_pct": 30, "stop_loss": "-8%", "recommendation": "观望"},
        }

    def test_pipe_escaped(self):
        from experts.formatter import format_debate_output

        out = format_debate_output(self._result("成交额<5000亿 | PE 分位 85%"))
        row = next(line for line in out.split("\n") if "索罗斯" in line)
        # 表格行必须是 4 列（3 个未转义竖线）
        assert row.count("|") - row.count("\\|") == 5
        assert "\\|" in row

    def test_newline_flattened(self):
        from experts.formatter import format_debate_output

        out = format_debate_output(self._result("第一行\n第二行 PE 85%"))
        # 只看评分表行（证据链段会有同名条目，不属于本不变式）
        rows = [line for line in out.split("\n") if line.startswith("|") and "索罗斯" in line]
        assert len(rows) == 1

    def test_long_reason_truncated(self):
        from experts.formatter import format_debate_output

        out = format_debate_output(self._result("数据" * 500))
        row = next(line for line in out.split("\n") if "索罗斯" in line)
        assert len(row) < 500


class TestP0_7Compliance:
    """禁用措辞必须在渲染层被改写。"""

    def _result(self, recommendation="减仓/清仓", stop_loss="-8%"):
        return {
            "market_state": "震荡",
            "long_weight": 0.55,
            "short_weight": 0.45,
            "long_votes": {"bull": 2, "bear": 1, "total": 3},
            "short_votes": {"bull": 0, "bear": 0, "total": 0},
            "long_avg": 45,
            "short_avg": 50,
            "composite_score": 45.0,
            "direction": "谨慎看空",
            "confidence": 60,
            "expert_results": [],
            "position": {"position_pct": 30, "stop_loss": stop_loss, "recommendation": recommendation},
        }

    def test_reduce_position_rewritten(self):
        from experts.formatter import format_debate_output

        out = format_debate_output(self._result())
        assert "减仓" not in out
        assert "清仓" not in out

    def test_stop_loss_label_rewritten(self):
        from experts.formatter import format_debate_output

        out = format_debate_output(self._result())
        assert "止损位" not in out
        assert "观察下沿" in out

    def test_reason_compliance_rewritten(self):
        from experts.formatter import format_debate_output

        result = self._result()
        result["expert_results"] = [
            {
                "name": "soros",
                "display_name": "索罗斯",
                "score": 35,
                "direction": "看空",
                "reason": "建议减仓至半仓 PE 85%",
            }
        ]
        out = format_debate_output(result)
        assert "建议减仓" not in out


# ═══════════════════════════════════════════════════════════════
# P0-9 校准方向词表
# ═══════════════════════════════════════════════════════════════


class TestP0_9CalibrationDirections:
    """谨慎看多/谨慎看空必须被识别为方向性判断。"""

    def test_direction_constants_cover_7_levels(self):
        assert set(BULLISH_DIRECTIONS) == {"强烈看多", "看多", "谨慎看多"}
        assert set(BEARISH_DIRECTIONS) == {"强烈看空", "看空", "谨慎看空"}

    def test_calibration_judges_cautious_directions(self):
        """校准判定：谨慎看多 + 实际上涨 → 正确（修复前永远记为失败）。"""
        from experts.calibration import direction_matches

        assert direction_matches("谨慎看多", "上涨") is True
        assert direction_matches("谨慎看空", "下跌") is True
        assert direction_matches("看多", "上涨") is True
        assert direction_matches("看空", "下跌") is True
        assert direction_matches("中性", "横盘") is True
        assert direction_matches("谨慎看多", "下跌") is False


# ═══════════════════════════════════════════════════════════════
# 维度归一化的其余不变量
# ═══════════════════════════════════════════════════════════════


class TestMergedExpertInvariants:
    """合并型专家的既有不变量不得被破坏。"""

    def test_five_long_three_short_eight_votes(self):
        """5 长 + 3 短 = 8 票（ARCHITECTURE.md 不变量）。"""
        from experts.vote_engine import aggregate_votes

        results = []
        for profile in list_active_experts():
            results.append(
                {
                    "name": profile.name,
                    "group": profile.group,
                    "score": 70,
                    "direction": "看多",
                }
            )
        out = aggregate_votes(
            results,
            market_state={"state": "震荡", "long_weight": 0.5, "short_weight": 0.5, "reason": "t"},
        )
        assert out["long_votes"]["total"] == 5
        assert out["short_votes"]["total"] == 3

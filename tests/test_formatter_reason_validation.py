"""测试 experts/formatter.py 的 reason 数据基础性校验。

Phase 1.3 新增的防御性校验逻辑：
- _validate_reason: 检测禁用表述（"反向加分"/"反向指标"等）和缺失数据引用
- _MODEL_LIMITATION_NOTE: 模型边界声明，注入报告尾部

背景：debate 模式中 LLM 自由生成的 reason 字段可能越界，编造
"反向加分""周期顶部否决"等无数据支撑的论述。formatter.py 在
渲染层做兜底检测，违规时追加警告标记。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import formatter


# ═══════════════════════════════════════════════════════════════
# _validate_reason: 禁用表述检测
# ═══════════════════════════════════════════════════════════════


class TestValidateReasonForbiddenPhrases:
    """禁用表述检测：LLM 编造的"反向"论述应被标记。"""

    @pytest.mark.parametrize(
        "phrase",
        [
            "反向加分",
            "反向指标",
            "反向参考",
            "该分数可作为反向",
            "作为反向",
        ],
    )
    def test_forbidden_phrase_flagged(self, phrase):
        """每种禁用表述都应触发警告标记。"""
        reason = f"该股基本面差，{phrase}，建议关注"
        result = formatter._validate_reason(reason)
        assert "⚠含禁用表述" in result
        assert phrase in result

    def test_forbidden_phrase_preserves_original_text(self):
        """警告标记追加在末尾，不修改 reason 原文（保留可追溯性）。"""
        reason = "估值偏高，反向加分"
        result = formatter._validate_reason(reason)
        assert result.startswith("估值偏高，反向加分")
        assert "⚠" in result


# ═══════════════════════════════════════════════════════════════
# _validate_reason: 缺失数据引用检测
# ═══════════════════════════════════════════════════════════════


class TestValidateReasonMissingData:
    """缺失数据引用检测：纯定性结论应被标记。"""

    @pytest.mark.parametrize(
        "reason",
        [
            "基本面优秀",
            "估值合理",
            "技术面良好",
            "处于周期顶部",
            "情绪冰点机会",
        ],
    )
    def test_no_data_token_flagged(self, reason):
        """不含任何数字的纯定性 reason 应触发缺数据警告。"""
        result = formatter._validate_reason(reason)
        assert "⚠理由缺数据引用" in result

    @pytest.mark.parametrize(
        "reason",
        [
            "ROE 22%->基本面100",
            "PE 35倍处行业85%分位->估值25",
            "涨停家数12家<阈值->情绪冰点",
            "负债率28%<30%+FCF/EPS0.9->安全边际100",
            "估值：33×22.5%=7.42",
            "综合分72/100",
        ],
    )
    def test_with_data_token_passes(self, reason):
        """含数字（含百分号、小数）的 reason 不应触发缺数据警告。"""
        result = formatter._validate_reason(reason)
        assert "⚠理由缺数据引用" not in result
        assert "⚠含禁用表述" not in result


# ═══════════════════════════════════════════════════════════════
# _validate_reason: 边界情况
# ═══════════════════════════════════════════════════════════════


class TestValidateReasonEdgeCases:
    def test_empty_reason(self):
        """空 reason 或 '-' 原样返回（不标记）。"""
        assert formatter._validate_reason("") == ""
        assert formatter._validate_reason("-") == "-"

    def test_none_reason(self):
        """None 原样返回。"""
        assert formatter._validate_reason(None) is None

    def test_forbidden_takes_priority_over_missing_data(self):
        """同时含禁用表述且缺数据时，禁用表述优先标记（更严重的违规）。"""
        reason = "反向加分"  # 既含禁用表述又无数据
        result = formatter._validate_reason(reason)
        assert "⚠含禁用表述" in result
        # 不应同时出现两个警告
        assert "⚠理由缺数据引用" not in result


# ═══════════════════════════════════════════════════════════════
# format_debate_output: 集成校验
# ═══════════════════════════════════════════════════════════════


class TestDebateOutputReasonValidation:
    """format_debate_output 渲染时应对违规 reason 追加标记。"""

    def _make_result(self, reason):
        return {
            "expert_results": [
                {"name": "buffett", "display_name": "巴菲特", "score": 72,
                 "direction": "看多", "reason": reason},
            ],
            "market_state": "震荡",
            "long_weight": 0.7, "short_weight": 0.3,
            "long_votes": {"bull": 1, "bear": 0},
            "short_votes": {"bull": 0, "bear": 0},
            "long_avg": 72, "short_avg": 0,
            "composite_score": 72,
            "direction": "看多",
            "confidence": 80,
            "position": {"position_pct": 30, "stop_loss": "-5%",
                         "recommendation": "买入", "steps": "-"},
        }

    def test_valid_reason_no_warning(self):
        output = formatter.format_debate_output(
            self._make_result("ROE 22%->基本面100")
        )
        # RISK_DISCLAIMER 含 ⚠️ 字符，只检查 reason 相关的警告标记
        assert "⚠含禁用表述" not in output
        assert "⚠理由缺数据引用" not in output

    def test_forbidden_reason_flagged_in_output(self):
        output = formatter.format_debate_output(
            self._make_result("反向加分")
        )
        assert "⚠含禁用表述" in output

    def test_missing_data_reason_flagged_in_output(self):
        output = formatter.format_debate_output(
            self._make_result("基本面优秀")
        )
        assert "⚠理由缺数据引用" in output


# ═══════════════════════════════════════════════════════════════
# _MODEL_LIMITATION_NOTE: 模型边界声明
# ═══════════════════════════════════════════════════════════════


class TestModelLimitationNote:
    def test_note_exists(self):
        """模型边界声明常量已定义。"""
        assert hasattr(formatter, "_MODEL_LIMITATION_NOTE")
        assert "模型边界" in formatter._MODEL_LIMITATION_NOTE
        assert "不符合本体系投资标准" in formatter._MODEL_LIMITATION_NOTE

    def test_note_in_debate_output(self):
        """模型边界声明注入 debate 输出尾部。"""
        result = {
            "expert_results": [],
            "market_state": "震荡",
            "long_weight": 0.7, "short_weight": 0.3,
            "long_votes": {"bull": 0, "bear": 0},
            "short_votes": {"bull": 0, "bear": 0},
            "long_avg": 0, "short_avg": 0,
            "composite_score": 50,
            "direction": "中性",
            "confidence": 50,
            "position": {"position_pct": 0, "stop_loss": "-",
                         "recommendation": "观望", "steps": "-"},
        }
        output = formatter.format_debate_output(result)
        assert "模型边界" in output
        assert "不符合本体系投资标准" in output

    def test_note_in_group_output(self):
        """模型边界声明也注入单组模式输出尾部。"""
        result = {
            "group": "long_term",
            "expert_results": [],
            "votes": {"bull": 0, "bear": 0},
            "avg_score": 50,
            "direction": "中性",
            "confidence": 50,
            "position": {"position_pct": 0, "stop_loss": "-"},
        }
        output = formatter.format_group_output(result)
        assert "模型边界" in output

    def test_note_in_brief_output(self):
        """简要输出也注入模型边界声明。"""
        result = {
            "direction": "中性",
            "confidence": 50,
            "composite_score": 50,
            "position": {"position_pct": 0, "stop_loss": "-"},
        }
        output = formatter.format_debate_brief(result)
        assert "模型边界" in output

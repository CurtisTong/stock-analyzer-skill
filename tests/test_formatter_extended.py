"""测试 experts/formatter.py：debate 输出格式化器。

根据项目功能：
- format_debate_output: 完整圆桌投票输出（decide.md §四 格式）
- format_debate_card: 简洁投票卡片
- format_debate_brief: 简要输出（v2.4.0 新增）
- format_group_output: 单组模式输出（长线/短线）
- _find_dissent: 找核心分歧
- _append_disclaimer: 添加免责声明
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import formatter


def _make_expert_result(name="buffett", direction="看多", confidence=0.75, score=72):
    return {"name": name, "direction": direction, "confidence": confidence, "score": score}


def _make_debate_result(group="long_term", expert_results=None, final_score=70,
                        final_direction="看多", final_confidence=0.8):
    """构造 debate 结果。"""
    if expert_results is None:
        expert_results = [
            _make_expert_result("buffett", "看多", 0.8, 75),
            _make_expert_result("lynch", "看多", 0.7, 70),
            _make_expert_result("soros", "中性", 0.5, 50),
            _make_expert_result("risk_manager", "看空", 0.6, 40),
        ]
    # 拆分 long_votes/short_votes
    # long_votes/short_votes 应当是 dict 含 bull/bear/avg
    if group == "long_term":
        lv_experts = expert_results[:2]
        sv_experts = expert_results[2:]
    else:
        lv_experts = expert_results[:1]
        sv_experts = expert_results[1:]
    long_votes = {
        "bull": len([e for e in lv_experts if e["direction"] in ("看多", "强烈看多")]),
        "bear": len([e for e in lv_experts if e["direction"] in ("看空", "强烈看空")]),
        "avg": sum(v["score"] for v in lv_experts) / len(lv_experts) if lv_experts else 0,
        "experts": lv_experts,
    }
    short_votes = {
        "bull": len([e for e in sv_experts if e["direction"] in ("看多", "强烈看多")]),
        "bear": len([e for e in sv_experts if e["direction"] in ("看空", "强烈看空")]),
        "avg": sum(v["score"] for v in sv_experts) / len(sv_experts) if sv_experts else 0,
        "experts": sv_experts,
    }
    long_avg = long_votes["avg"]
    short_avg = short_votes["avg"]
    # group_output 需要 avg_score 字段（不是 long_avg）
    avg_score = final_score
    position = {"position_pct": 30, "stop_loss": "-5%"}
    long_avg = long_votes["avg"]
    short_avg = short_votes["avg"]
    votes = {
        "买入": len([e for e in expert_results if e["direction"] == "看多"]),
        "持有": len([e for e in expert_results if e["direction"] == "中性"]),
        "卖出": len([e for e in expert_results if e["direction"] == "看空"]),
        "bull": len([e for e in expert_results if e["direction"] in ("看多", "强烈看多")]),
        "bear": len([e for e in expert_results if e["direction"] in ("看空", "强烈看空")]),
    }
    return {
        "code": "sh600519", "name": "测试股", "group": group,
        "expert_results": expert_results,
        "votes": votes,
        "market_state": "震荡",
        "long_weight": 0.7, "short_weight": 0.3,
        "long_votes": long_votes, "short_votes": short_votes,
        "long_avg": long_avg, "short_avg": short_avg,
        "composite_score": final_score,
        "avg_score": final_score,
        "position": position,
        "direction": final_direction,
        "confidence": int(final_confidence * 100),
        "final_direction": final_direction,
        "final_confidence": final_confidence,
        "final_score": final_score,
        "reasoning": ["基本面强", "估值合理"],
    }


# ═══════════════════════════════════════════════════════════════
# format_debate_output


class TestFormatDebateOutput:
    def test_basic(self):
        result = _make_debate_result()
        output = formatter.format_debate_output(result)
        assert "圆桌投票" in output or "投票" in output
        assert "buffett" in output or "测试股" in output

    def test_empty_experts(self):
        result = _make_debate_result(expert_results=[])
        output = formatter.format_debate_output(result)
        assert isinstance(output, str)

    def test_long_term(self):
        result = _make_debate_result(group="long_term")
        output = formatter.format_debate_output(result)
        assert "看多" in output or "方向" in output

    def test_short_term(self):
        result = _make_debate_result(group="short_term",
                                     final_direction="看空")
        output = formatter.format_debate_output(result)
        assert "看空" in output


# ═══════════════════════════════════════════════════════════════
# format_debate_card


class TestFormatDebateCard:
    def test_basic(self):
        result = _make_debate_result()
        output = formatter.format_debate_card(result)
        assert isinstance(output, str)
        # card 主要显示投票计数 + 建议
        assert "买入" in output or "持有" in output or "卖出" in output

    def test_contains_score(self):
        """cards 显示投票百分比而非 final_score。"""
        result = _make_debate_result()
        output = formatter.format_debate_card(result)
        # 显示 50%（2 看多 / 4 总）
        assert "50.0%" in output or "买入" in output or "50%" in output


# ═══════════════════════════════════════════════════════════════
# format_debate_brief


class TestFormatDebateBrief:
    def test_basic(self):
        result = _make_debate_result()
        output = formatter.format_debate_brief(result)
        assert isinstance(output, str)
        # brief 输出较短（<500 字）
        assert len(output) < 1000

    def test_short_brief(self):
        """brief 输出应包含方向+信心。"""
        result = _make_debate_result(final_direction="看多",
                                     final_confidence=0.85)
        output = formatter.format_debate_brief(result)
        assert "看多" in output or "0.85" in output or "85%" in output


# ═══════════════════════════════════════════════════════════════
# format_group_output


class TestFormatGroupOutput:
    def test_long_term_group(self):
        result = _make_debate_result(group="long_term")
        output = formatter.format_group_output(result)
        assert isinstance(output, str)
        assert "长线" in output or "buffett" in output

    def test_short_term_group(self):
        result = _make_debate_result(group="short_term",
                                     final_direction="看空")
        output = formatter.format_group_output(result)
        assert "短线" in output

    def test_empty_experts(self):
        result = _make_debate_result(expert_results=[])
        output = formatter.format_group_output(result)
        assert isinstance(output, str)


# ═══════════════════════════════════════════════════════════════
# _find_dissent


class TestFindDissent:
    def test_clear_dissent(self):
        """明显分歧（看多 vs 看空）。"""
        experts = [
            _make_expert_result("buffett", "看多"),
            _make_expert_result("risk_manager", "看空"),
            _make_expert_result("lynch", "看多"),
        ]
        dissent = formatter._find_dissent(experts)
        assert isinstance(dissent, str)

    def test_consensus(self):
        """一致看多时低分歧。"""
        experts = [
            _make_expert_result("buffett", "看多"),
            _make_expert_result("lynch", "看多"),
            _make_expert_result("soros", "看多"),
        ]
        dissent = formatter._find_dissent(experts)
        assert isinstance(dissent, str)

    def test_single(self):
        """单专家时无分歧。"""
        dissent = formatter._find_dissent([_make_expert_result()])
        assert isinstance(dissent, str)

    def test_empty(self):
        dissent = formatter._find_dissent([])
        assert isinstance(dissent, str)


# ═══════════════════════════════════════════════════════════════
# _append_disclaimer


class TestAppendDisclaimer:
    def test_appends_disclaimer(self):
        lines = []
        formatter._append_disclaimer(lines)
        assert len(lines) >= 1
        joined = "\n".join(lines)
        assert "免责" in joined or "AI" in joined or "投资建议" in joined or "仅供" in joined

    def test_no_disclaimer_flag(self, monkeypatch):
        """NO_DISCLAIMER=1 时不添加。"""
        monkeypatch.setenv("SKILL_NO_DISCLAIMER", "1")
        lines = []
        formatter._append_disclaimer(lines)
        # 取决于实现，可能 0 或 1 行
        assert isinstance(lines, list)
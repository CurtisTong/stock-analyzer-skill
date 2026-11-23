"""[review P1-23] long_term PE 历史分位现场计算回归测试。

修复前：quote.get("pe_percentile") 无数据源恒 -1，
"历史低位 +15 / 历史高位 -15" 三分支永不触发。
"""

from __future__ import annotations

from business.long_term import LongTermEvaluator

EVALUATOR = LongTermEvaluator()


class TestPePercentileReachable:
    def test_low_pe_triggers_low_percentile(self):
        """[review P1-23] 低 PE 必须触发历史低位分支（+15 分）。"""
        score, reasoning = EVALUATOR._calc_valuation({"pe": 8, "pb": 2}, {})
        assert any("历史低位" in line for line in reasoning), reasoning
        assert score > 50

    def test_high_pe_triggers_high_percentile(self):
        """[review P1-23] 高 PE 必须触发历史高位分支（-15 分）。"""
        score, reasoning = EVALUATOR._calc_valuation({"pe": 100, "pb": 2}, {})
        assert any("历史高位" in line for line in reasoning), reasoning
        assert score < 50

    def test_no_pe_keeps_percentile_inactive(self):
        """[review P1-23] 无 PE 数据时分位分支不应误触发。"""
        score, reasoning = EVALUATOR._calc_valuation({"pe": 0, "pb": 2}, {})
        assert not any("历史分位" in line for line in reasoning), reasoning
        assert score == 50

    def test_explicit_percentile_still_respected(self):
        """[review P1-23] 调用方显式提供分位时保持兼容。"""
        _score, reasoning = EVALUATOR._calc_valuation({"pe": 20, "pe_percentile": 90, "pb": 2}, {})
        assert any("历史高位" in line for line in reasoning), reasoning

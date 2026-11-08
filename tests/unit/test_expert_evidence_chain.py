"""专家圆桌证据链渲染测试（v1.33.0 可复核性加固）。

定位承诺"每个结论挂数据源与时间戳"。此前 debate 输出只有分数和理由，
读者无法判断分数来自哪些维度、数据从哪来、何时抓取。本测试锁住：
每张票必须给依据字段（维度分），整轮必须给数据源与评分时间。
"""

from __future__ import annotations

import pytest

from experts.formatter import format_debate_output


def _result(expert_results, **extra):
    base = {
        "market_state": "震荡",
        "long_weight": 0.55,
        "short_weight": 0.45,
        "long_votes": {"bull": 1, "bear": 0, "total": 1},
        "short_votes": {"bull": 0, "bear": 0, "total": 0},
        "long_avg": 60,
        "short_avg": 50,
        "composite_score": 60.0,
        "direction": "看多",
        "confidence": 55,
        "expert_results": expert_results,
        "position": {"position_pct": 20, "stop_loss": "-8%", "recommendation": "观望"},
    }
    base.update(extra)
    return base


class TestEvidenceChain:
    def test_each_vote_shows_dimension_evidence(self):
        out = format_debate_output(
            _result(
                [
                    {
                        "name": "lynch",
                        "display_name": "林奇",
                        "score": 68,
                        "direction": "看多",
                        "reason": "ROE 18% 且 PE 22 倍",
                        "dim_scores": {"基本面": 82.0, "估值": 61.0, "技术面": 45.0, "风险": 70.0},
                    }
                ]
            )
        )
        assert "### 🔍 证据链" in out
        assert "林奇" in out
        assert "基本面 82" in out and "风险 70" in out
        # 只取 top-3，最低的技术面 45 不出现
        assert "技术面 45" not in out

    def test_abstain_vote_shows_reason_not_score(self):
        out = format_debate_output(
            _result(
                [
                    {
                        "name": "topic_leader",
                        "display_name": "题材龙头",
                        "score": None,
                        "direction": "弃权",
                        "abstain": True,
                        "abstain_reason": "价量/题材信号均不可得",
                    }
                ]
            )
        )
        assert "弃权" in out
        assert "价量/题材信号均不可得" in out

    def test_provenance_from_raw_meta(self):
        out = format_debate_output(
            _result(
                [{"name": "soros", "display_name": "索罗斯", "score": 55, "dim_scores": {"技术面": 55.0}}],
                raw_meta={
                    "quote": [{"source": "tencent", "fetch_time": "2026-11-08 14:30:00"}],
                    "finance_raw": {"SH600519": [{"source": "eastmoney_finance"}]},
                },
                as_of="2026-11-08 14:31",
            )
        )
        assert "行情 tencent @ 2026-11-08 14:30:00" in out
        assert "财务 eastmoney_finance" in out
        assert "评分时间 2026-11-08 14:31" in out

    def test_degraded_market_breadth_is_flagged(self):
        out = format_debate_output(
            _result(
                [{"name": "soros", "display_name": "索罗斯", "score": 55, "dim_scores": {"技术面": 55.0}}],
                stock_data={"market_features": {"_degraded": True, "_degraded_reason": "指数 API 异常"}},
            )
        )
        assert "市场宽度降级" in out and "指数 API 异常" in out

    def test_missing_provenance_is_explicit(self):
        """没有 provenance 时不能留空——空着会被误读成"没问题"。"""
        out = format_debate_output(
            _result([{"name": "soros", "display_name": "索罗斯", "score": 55, "dim_scores": {"技术面": 55.0}}])
        )
        assert "数据源未标注" in out

    def test_missing_dim_scores_states_the_assumption(self):
        out = format_debate_output(
            _result([{"name": "soros", "display_name": "索罗斯", "score": 55, "dim_scores": {}}])
        )
        assert "维度分缺失，按中性处理" in out

    @pytest.mark.parametrize("score", [0, 100])
    def test_score_bounds_render(self, score):
        out = format_debate_output(
            _result([{"name": "soros", "display_name": "索罗斯", "score": score, "dim_scores": {"风险": 50.0}}])
        )
        assert f"{score} 分" in out

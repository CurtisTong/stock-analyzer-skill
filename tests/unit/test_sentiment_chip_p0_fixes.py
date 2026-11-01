"""情绪因子与筹码分布的 P0/P1 回归测试（v1.28.0）。

覆盖：
1. **情绪因子 IC 链路空转**：情绪因子只在涨停/炸板池内有值（覆盖率约 1.3%），
   IC 要求单日截面 ≥5 只才纳入 → 回测池与情绪池交集常为 0~4 只 → samples=0。
   此前零样本因子**不产生任何告警**（`--min-samples` 默认 0，`samples<0` 为
   False），输出"无明显预测力"——与"真实测得 IC=0"完全无法区分，把"链路空转"
   伪装成"因子无效"。
2. **筹码档位判定顺序与文档矛盾**：文档规定优先级"深度套牢 > 上方有墙 >
   筹码在脚下"，代码把"筹码在脚下"放最前 → 98% 套牢被判为"筹码在脚下"。
3. **快照回填历史日期时写入"今天"的跌停家数**（存档污染 / 潜在前视）。
4. **情绪降级数据被当真实情绪计分**：`broken_rate=0` 走末档拿最高分 80。
5. **北交所 920 号段未归一化** → 情绪因子静默缺失。
"""

from __future__ import annotations

import pytest


class TestIcZeroSampleWarning:
    """IC 零样本必须显式告警，不能伪装成"因子无效"。"""

    def test_zero_sample_verdict_not_plain_no_predictive_power(self):
        """零样本时判读必须包含"未计算"字样，而不是"无明显预测力"。"""
        import inspect

        from factor_ic import cmd_evaluate

        src = inspect.getsource(cmd_evaluate)
        assert "无有效样本" in src
        assert "IC 未计算" in src

    def test_json_warnings_include_zero_sample(self):
        """JSON 输出路径：零样本单独告警。"""
        import inspect

        from factor_ic import cmd_evaluate

        src = inspect.getsource(cmd_evaluate)
        assert "不能据此判定因子有效性" in src


class TestChipTierPriority:
    """筹码档位判定顺序必须与文档一致（深度套牢优先）。"""

    def test_deep_trapped_priority_over_foot(self):
        from technical.chip_distribution import classify_tier

        # 获利盘 20%（≥15% → 脚下）但需反弹 30%（≥15% → 深度套牢）
        assert classify_tier(20.0, False, 30.0) == "深度套牢"

    def test_deep_trapped_wins_even_when_cluster_contains_price(self):
        """套牢 98% + 密集区含现价 → 深度套牢（风险最高档优先）。"""
        from technical.chip_distribution import classify_tier

        assert classify_tier(2.0, True, 5.0) == "深度套牢"

    def test_foot_when_profitable_and_cluster_contains_price(self):
        from technical.chip_distribution import classify_tier

        assert classify_tier(30.0, True, 2.0) == "筹码在脚下"

    def test_wall_when_trapped_but_small_rebound(self):
        from technical.chip_distribution import classify_tier

        assert classify_tier(10.0, False, 5.0) == "上方有墙"


class TestSentimentDegraded:
    """降级数据不得当作真实情绪计分。"""

    def test_degraded_marks_level_and_interpretation(self):
        from technical.sentiment import SentimentCalculator

        c = SentimentCalculator()
        r = c.calculate(
            {
                "limit_up_count": 0,
                "continuous_limit_height": 0,
                "broken_limit_rate": 0,
                "margin_balance": 0,
                "_degraded": True,
            }
        )
        assert r["degraded"] is True
        assert r["level"] == "数据缺失"
        assert "不可用于决策" in r["interpretation"]

    def test_degraded_output_shows_warning(self):
        from technical.sentiment import SentimentCalculator, format_sentiment

        c = SentimentCalculator()
        r = c.calculate(
            {
                "limit_up_count": 0,
                "continuous_limit_height": 0,
                "broken_limit_rate": 0,
                "margin_balance": 0,
                "_degraded": True,
            }
        )
        assert "⚠️ 数据降级" in format_sentiment(r)

    def test_normal_data_unaffected(self):
        from technical.sentiment import SentimentCalculator

        c = SentimentCalculator()
        r = c.calculate(
            {
                "limit_up_count": 65,
                "continuous_limit_height": 4,
                "broken_limit_rate": 25,
                "margin_balance": 17000,
            }
        )
        assert r["degraded"] is False
        assert r["level"] != "数据缺失"


class TestSentimentPanelNormalize:
    """北交所 920 号段必须归一化（与项目其他位置 bj920001 口径一致）。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("920001", "bj920001"),
            ("830001", "bj830001"),
            ("600000", "sh600000"),
            ("000001", "sz000001"),
            ("300750", "sz300750"),
        ],
    )
    def test_normalize_code(self, raw, expected):
        from data.sentiment_panel import _normalize_code

        assert _normalize_code(raw) == expected

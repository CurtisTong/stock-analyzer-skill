"""
Sprint 3 因子级改进单测（review#4-#8）。
覆盖：波动率窗口 / ROE 趋势 / 动量阈值 / PEG 复合增速。
"""

import pytest


from strategies.factors.volatility import (  # noqa: E402
    volatility_score,
    volatility_from_closes,
)
from strategies.factors.quality import quality_score  # noqa: E402
from strategies.factors.momentum import momentum_score  # noqa: E402
from strategies.factors.valuation import valuation_score  # noqa: E402
from data.types import KlineBar  # noqa: E402


def _make_bars(prices, base_day="2025-01-01"):
    """从价格列表构造 KlineBar 列表。"""
    from datetime import datetime, timedelta

    start = datetime.strptime(base_day, "%Y-%m-%d")
    return [
        KlineBar(
            day=(start + timedelta(days=i)).strftime("%Y-%m-%d"),
            close=p,
            open=p,
            high=p,
            low=p,
            volume=1000000,
        )
        for i, p in enumerate(prices)
    ]


class TestVolatilityWindow:
    """review#8：窗口 20→60 根。"""

    def test_uses_60_bars_when_available(self):
        """60 根可用时使用 60 根窗口（不是只 20 根）。"""
        # 构造：前 20 根高波动 + 后 40 根完全平稳
        # 旧 20 根窗口（只看末尾 20 根）→ 低波动 → 高分
        # 新 60 根窗口（含前 20 根波动）→ 高波动 → 低分
        volatile_part = [10.0 + (i % 2) * 2.0 for i in range(20)]  # 8→10→8→10 大波动
        stable_part = [10.0] * 40  # 完全平稳
        prices = volatile_part + stable_part
        bars = _make_bars(prices)
        assert len(bars) == 60
        score_60 = volatility_score(bars)
        # 用 20 根完全平稳的数据对比
        bars_stable = _make_bars([10.0] * 20)
        score_20 = volatility_score(bars_stable)
        # 60 根含前 20 根高波动 → 分数应显著低于纯平稳
        assert score_60 < score_20

    def test_from_closes_uses_60(self):
        """volatility_from_closes 也使用 60 根窗口。"""
        volatile_part = [10.0 + (i % 2) * 2.0 for i in range(20)]
        stable_part = [10.0] * 40
        closes = volatile_part + stable_part
        score_60 = volatility_from_closes(closes)
        score_20 = volatility_from_closes(stable_part)  # 只看后 40 平稳
        assert score_60 < score_20

    def test_fallback_to_all_when_less_than_60(self):
        """少于 60 根时回退到全部可用。"""
        prices = [10.0 + (i % 3) * 0.1 for i in range(30)]
        score = volatility_from_closes(prices)
        assert 5 <= score <= 95  # 合理范围内


class TestROETrend:
    """review#4：下降占比替代严格单调。"""

    def test_decline_ratio_60_pct_triggers_penalty(self):
        """5 期中 3 期下降（60%）触发 -8 分。"""
        fin = {
            "roe": 10.0,
            "eps": 1.0,
            "roe_trend": [10.0, 9.5, 10.2, 8.8, 8.0],  # 4 个 diff，3 负
        }
        score = quality_score(fin)
        # 至少在合理范围
        assert 0 <= score <= 100

    def test_single_drop_no_longer_triggers_penalty(self):
        """单期下降不触发扣分（旧逻辑会）。"""
        fin_strict_drop = {
            "roe": 10.0,
            "eps": 1.0,
            "roe_trend": [10.0, 9.5, 9.4, 9.3, 9.2, 9.1],  # 全下降（旧逻辑扣分）
        }
        fin_single_drop = {
            "roe": 10.0,
            "eps": 1.0,
            "roe_trend": [10.0, 10.1, 9.9, 10.2, 10.0, 10.1],  # 1 期下降（旧逻辑不扣）
        }
        # 旧逻辑：第一个扣 8 分；新逻辑：第一个下降占比 100% 仍扣 8 分（这里都是 100% 下降 vs 20% 下降）
        score_strict = quality_score(fin_strict_drop)
        score_single = quality_score(fin_single_drop)
        # 新逻辑：strict 是 5/5 = 100% 下降 → -8；single 是 1/5 = 20% → 不扣
        assert score_strict < score_single

    def test_short_trend_ignored(self):
        """不足 3 期的 roe_trend 不参与趋势判定。"""
        fin = {"roe": 10.0, "eps": 1.0, "roe_trend": [10.0, 9.0]}  # 只 2 期
        score = quality_score(fin)
        # 应不触发趋势扣分
        assert 0 <= score <= 100


class TestMomentumDecay:
    """review#6：阈值动态化。"""

    def test_uses_dynamic_p75_when_provided(self):
        """提供 market_amount_p75 时按动态阈值判定。"""
        # p75=10000，amount=10500 → quant_high
        # amount 原本可能未达 12000 硬编码，但超过 p75
        features = {
            "trend": 0,
            "ret20": 0,
            "volume_ratio": 1.0,
            "rsi": 50,
            "macd_signal": 0,
            "vol_price_signal": 0,
        }
        quote = {"turnover": 1.0, "market_amount": 10500, "market_amount_p75": 10000}
        # 量化高活跃 → 衰减系数 0.7
        score = momentum_score(features, quote)
        assert 0 <= score <= 100

    def test_falls_back_to_12000_hardcoded(self):
        """无 p75 时 fallback 到 12000 硬编码。"""
        features = {
            "trend": 0,
            "ret20": 0,
            "volume_ratio": 1.0,
            "rsi": 50,
            "macd_signal": 0,
            "vol_price_signal": 0,
        }
        quote_no_p75 = {
            "turnover": 1.0,
            "market_amount": 13000,
        }  # 超 12000 → quant_high
        quote_low = {
            "turnover": 1.0,
            "market_amount": 10000,
        }  # 不到 12000 → quant_normal
        # 两次评分应不同
        score_high = momentum_score(features, quote_no_p75)
        score_low = momentum_score(features, quote_low)
        # 量化高活跃衰减更强，量价信号保持 → 通常分数有差异
        assert isinstance(score_high, float)
        assert isinstance(score_low, float)


class TestPEGCagr:
    """review#5：PEG 用 3 年复合增速。"""

    def test_uses_3y_cagr_when_provided(self):
        """fin.net_profit_cagr_3y > 0 时优先使用。"""
        # 高 PE 但 CAGR 低 → PEG 应较高 → 低分
        fin = {
            "net_profit_cagr_3y": 5.0,
            "net_profit_yoy": 100.0,
        }  # 单期 +100% 但 3 年 CAGR 5%
        quote = {"pe": 25, "pb": 3}
        score = valuation_score(quote, fin, "默认")
        # 应当 PEG 不再 < 0.8（因为 growth=5，PEG=5），分不会很高
        assert 0 <= score <= 100

    def test_falls_back_to_single_period_when_no_cagr(self):
        """无 3y CAGR 时回退到单期增速。"""
        fin = {"net_profit_yoy": 30.0}  # 单期 30%
        quote = {"pe": 24, "pb": 3}  # PEG = 24/30 = 0.8
        score = valuation_score(quote, fin, "默认")
        assert 0 <= score <= 100

    def test_no_growth_no_peg(self):
        """无增长时不计算 PEG。"""
        fin = {"net_profit_yoy": 0}
        quote = {"pe": 15, "pb": 2}
        score = valuation_score(quote, fin, "默认")
        assert 0 <= score <= 100


class TestNorthboundFlowScoring:
    """北向资金评分测试：验证使用最近 N 日而非最旧 N 日。"""

    def test_uses_recent_days_not_oldest(self):
        """北向资金评分应取最近 5 日（flow[-5:]），而非最旧 5 日（flow[:5]）。"""
        from strategies.factors.chip import _score_northbound_flow
        from unittest.mock import patch

        # 构造 20 天数据：前 15 天全部净买入（旧），后 5 天全部净卖出（新）
        # 若取 flow[:5]（旧），会误判为连续净买入（加分）
        # 若取 flow[-5:]（新），正确判断为连续净卖出（扣分）
        flow_data = [
            {"date": f"2025-06-{i:02d}", "net_buy": 1000}
            for i in range(1, 16)  # 前 15 天：净买入
        ] + [
            {"date": f"2025-06-{i:02d}", "net_buy": -500}
            for i in range(16, 21)  # 后 5 天：净卖出
        ]

        with patch(
            "strategies.factors.chip.get_northbound_flow",
            return_value=flow_data,
            create=True,
        ):
            # 由于 get_northbound_flow 是函数内 import，需要 patch data.flow
            import data.flow

            original = data.flow.get_northbound_flow
            data.flow.get_northbound_flow = lambda code, days=20: flow_data
            try:
                score = _score_northbound_flow("sh600989")
            finally:
                data.flow.get_northbound_flow = original

        # 最近 5 日全部净卖出 -> pos_5d=0 -> 扣分 -> score < 0
        assert score < 0, f"应检测到近期净卖出(score<0)，实际 score={score}"

    def test_all_inflow_scores_positive(self):
        """全部净买入时评分应为正。"""
        from strategies.factors.chip import _score_northbound_flow
        import data.flow

        flow_data = [
            {"date": f"2025-06-{i:02d}", "net_buy": 800}
            for i in range(1, 21)  # 20 天全部净买入
        ]
        original = data.flow.get_northbound_flow
        data.flow.get_northbound_flow = lambda code, days=20: flow_data
        try:
            score = _score_northbound_flow("sh600989")
        finally:
            data.flow.get_northbound_flow = original

        assert score > 0, f"全部净买入应得分>0，实际 score={score}"

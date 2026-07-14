"""(#6) 动量 Amihud 非流动性惩罚测试。

覆盖：
- Amihud 指标计算（_calc_amihud）
- 高流动性股票不惩罚
- 低流动性股票动量评分打折 ×0.8
- 数据缺失时不惩罚
- 量化高活跃衰减叠加
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.factors.momentum import momentum_score  # noqa: E402
from technical.pipeline import _calc_amihud  # noqa: E402


class TestCalcAmihud:
    """Amihud 指标计算。"""

    def test_empty_data_returns_zero(self):
        assert _calc_amihud([], []) == 0.0
        assert _calc_amihud([10], [1000]) == 0.0

    def test_normal_calculation(self):
        """正常计算：|return| / amount 的均值。"""
        # close: 10 -> 11 (10% 涨) -> 10 (9% 跌)
        # amount: 1e8, 1e8
        closes = [10, 11, 10]
        amounts = [0, 1e8, 1e8]  # 第一天无前日，跳过
        illiq = _calc_amihud(closes, amounts, window=20)
        # day 1: |0.1| / 1e8 = 1e-9
        # day 2: |(10-11)/11| / 1e8 = 0.0909 / 1e8 = 9.09e-10
        # mean = (1e-9 + 9.09e-10) / 2 = 9.545e-10
        assert illiq > 0
        assert 5e-10 < illiq < 2e-9

    def test_high_liquidity_low_amihud(self):
        """高成交额 -> 低 Amihud（流动性好）。"""
        closes = [10, 11, 10, 11, 10]
        amounts = [0, 1e12, 1e12, 1e12, 1e12]  # 极高成交额
        illiq = _calc_amihud(closes, amounts)
        assert illiq < 1e-10  # 极低

    def test_low_liquidity_high_amihud(self):
        """低成交额 -> 高 Amihud（流动性差）。"""
        closes = [10, 11, 10, 11, 10]
        amounts = [0, 1e4, 1e4, 1e4, 1e4]  # 极低成交额
        illiq = _calc_amihud(closes, amounts)
        assert illiq > 1e-6  # 高于 1e-7 阈值

    def test_zero_amount_skipped(self):
        """成交额为 0 的日期跳过。"""
        closes = [10, 11, 10]
        amounts = [0, 0, 1e8]  # 只有最后一天有成交额
        illiq = _calc_amihud(closes, amounts)
        # 只有 1 个有效值
        assert illiq > 0


class TestMomentumAmihudPenalty:
    """momentum_score 中的 Amihud 惩罚。"""

    def _make_features(self, **overrides):
        defaults = {
            "trend": 1,
            "ret20": 5.0,
            "volume_ratio": 1.2,
            "macd_signal": 0,
            "rsi": 60,
            "rsi_signal": 0,
            "vol_price_signal": 0,
            "amihud_illiq": 0,  # 默认无惩罚
        }
        defaults.update(overrides)
        return defaults

    def _make_quote(self, **overrides):
        defaults = {
            "turnover": 3.0,
            "pe": 15,
            "pe_percentile": 30,
            "market_amount": 5000,
            "market_amount_p75": 0,
        }
        defaults.update(overrides)
        return defaults

    def test_no_amihud_no_penalty(self):
        """无 Amihud 数据时不惩罚。"""
        features = self._make_features(amihud_illiq=0)
        quote = self._make_quote()
        score = momentum_score(features, quote)
        # 应为正常动量评分（无惩罚）
        assert 0 < score <= 100

    def test_high_liquidity_no_penalty(self):
        """高流动性（低 Amihud）不惩罚。"""
        features = self._make_features(amihud_illiq=1e-9)  # 很低
        quote = self._make_quote()
        score_high_liq = momentum_score(features, quote)

        features_no = self._make_features(amihud_illiq=0)
        score_no = momentum_score(features_no, quote)

        # 低 Amihud（<1e-7）不惩罚，与无 Amihud 相同
        assert score_high_liq == score_no

    def test_low_liquidity_penalty(self):
        """低流动性（高 Amihud > 1e-7）动量评分打折 ×0.8。"""
        features_high_liq = self._make_features(amihud_illiq=1e-9)
        features_low_liq = self._make_features(amihud_illiq=1e-5)  # 高于阈值

        quote = self._make_quote()
        score_high = momentum_score(features_high_liq, quote)
        score_low = momentum_score(features_low_liq, quote)

        # 低流动性评分应低于高流动性（×0.8 惩罚）
        assert score_low < score_high
        # 惩罚幅度约 20%
        assert abs(score_low / score_high - 0.8) < 0.05

    def test_penalty_combined_with_quant_decay(self):
        """Amihud 惩罚与量化高活跃衰减可叠加。"""
        # 量化高活跃 + 低流动性
        features = self._make_features(amihud_illiq=1e-5)
        quote = self._make_quote(market_amount=15000, market_amount_p75=12000)
        score = momentum_score(features, quote)
        assert 0 <= score <= 100  # 不崩溃

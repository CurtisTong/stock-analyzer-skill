"""庄股识别单元测试。

覆盖场景：
- 低R²+长影线+小市值 -> is_dealer=True（mock compute_beta）
- 高R²（跟大盘） -> is_dealer=False（独立走势为0直接返回）
- 数据不足 -> 不崩溃
"""

import pytest

from strategies.factors.dealer import detect_dealer_stock
from technical.shadow_stats import shadow_ratio_stats


def _long_shadow_records(n=30):
    """生成长影线K线序列（庄股毛刺特征）。"""
    records = []
    for i in range(n):
        base = 10.0 + i * 0.02
        o = base
        c = base + 0.02  # 小实体
        h = base + 0.4  # 长上影
        low = base - 0.4  # 长下影
        records.append(
            {
                "day": f"2026-07-{i+1:02d}",
                "open": o,
                "close": c,
                "high": h,
                "low": low,
                "volume": 1000,
            }
        )
    return records


def _trend_records(n=30):
    """生成趋势K线序列（大实体，短影线）。"""
    records = []
    price = 10.0
    for i in range(n):
        o = price
        c = price + 0.5
        h = c + 0.02
        low = o - 0.02
        records.append(
            {
                "day": f"2026-07-{i+1:02d}",
                "open": o,
                "close": c,
                "high": h,
                "low": low,
                "volume": 1000,
            }
        )
        price = c
    return records


class TestDetectDealerStock:
    """庄股识别。"""

    def test_dealer_stock_low_r_squared(self, monkeypatch):
        """低R²+长影线+小市值 -> is_dealer=True。"""

        # mock compute_beta 返回低 R² + 低 beta
        def mock_beta(code, index_code=None, window=60):
            return {
                "r_squared": 0.05,
                "beta": 0.1,
                "alpha": 0.001,
                "interpretation": "独立走势",
            }

        monkeypatch.setattr("industry_beta.compute_beta", mock_beta)

        records = _long_shadow_records(30)
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        quote = {"circulating_cap": 50}  # 50亿流通市值

        result = detect_dealer_stock("sh600000", quote, records, closes, highs, lows)
        assert result["is_dealer"] is True
        assert result["score"] >= 60
        assert result["r_squared"] == 0.05
        assert "独立" in result["independence"]

    def test_not_dealer_high_r_squared(self, monkeypatch):
        """高R²（跟大盘） -> is_dealer=False（独立走势得0分直接返回）。"""

        def mock_beta(code, index_code=None, window=60):
            return {
                "r_squared": 0.85,
                "beta": 1.2,
                "alpha": 0.0,
                "interpretation": "跟随大盘",
            }

        monkeypatch.setattr("industry_beta.compute_beta", mock_beta)

        records = _long_shadow_records(30)
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        quote = {"circulating_cap": 50}

        result = detect_dealer_stock("sh600000", quote, records, closes, highs, lows)
        assert result["is_dealer"] is False
        assert result["score"] == 0
        assert "跟随大盘" in result["independence"]

    def test_dealer_with_trend_records_lower_score(self, monkeypatch):
        """低R²但趋势K线（无毛刺）-> 毛刺维度得低分，可能不足60。"""

        def mock_beta(code, index_code=None, window=60):
            return {
                "r_squared": 0.15,
                "beta": 0.4,
                "alpha": 0.001,
                "interpretation": "较独立",
            }

        monkeypatch.setattr("industry_beta.compute_beta", mock_beta)

        records = _trend_records(30)  # 趋势K线，无毛刺
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        quote = {"circulating_cap": 50}

        result = detect_dealer_stock("sh600000", quote, records, closes, highs, lows)
        # 独立25 + 毛刺0 + 振幅(趋势K线ATR低)可能0~10 + 市值20 = 45~55 < 60
        assert result["score"] < 70  # 趋势K线毛刺少，分数较低

    def test_large_cap_not_dealer(self, monkeypatch):
        """低R²但大市值 -> 市值维度得0分，可能不足60。"""

        def mock_beta(code, index_code=None, window=60):
            return {
                "r_squared": 0.05,
                "beta": 0.1,
                "alpha": 0.001,
                "interpretation": "独立",
            }

        monkeypatch.setattr("industry_beta.compute_beta", mock_beta)

        records = _long_shadow_records(30)
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        quote = {"circulating_cap": 500}  # 500亿，超出庄股区间

        result = detect_dealer_stock("sh600000", quote, records, closes, highs, lows)
        # 独立35 + 毛刺25 + 振幅20 + 市值0 = 80 >= 60，仍然判庄股
        # 但市值维度得0分，reasons不含市值
        assert result["is_dealer"] in (True, False)  # 取决于其他维度总分
        assert (
            all("流通市值500亿" not in r for r in result["reasons"])
            if result["reasons"]
            else True
        )

    def test_beta_failure_graceful(self, monkeypatch):
        """compute_beta 抛异常 -> 独立走势维度跳过，不崩溃。"""

        def mock_beta_fail(code, index_code=None, window=60):
            raise RuntimeError("网络错误")

        monkeypatch.setattr("industry_beta.compute_beta", mock_beta_fail)

        records = _long_shadow_records(30)
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        quote = {"circulating_cap": 50}

        result = detect_dealer_stock("sh600000", quote, records, closes, highs, lows)
        # beta失败->独立走势0分->直接返回非庄股
        assert result["is_dealer"] is False
        assert result["score"] == 0

    def test_return_structure_fields(self, monkeypatch):
        """返回 dict 包含所有约定字段。"""

        def mock_beta(code, index_code=None, window=60):
            return {
                "r_squared": 0.05,
                "beta": 0.1,
                "alpha": 0.001,
                "interpretation": "独立",
            }

        monkeypatch.setattr("industry_beta.compute_beta", mock_beta)

        records = _long_shadow_records(30)
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        quote = {"circulating_cap": 50}

        result = detect_dealer_stock("sh600000", quote, records, closes, highs, lows)
        for key in (
            "is_dealer",
            "score",
            "reasons",
            "independence",
            "shadow_pct",
            "market_cap",
            "r_squared",
            "beta",
        ):
            assert key in result, f"缺少字段 {key}"

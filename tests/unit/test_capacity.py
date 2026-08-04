"""容量票识别单元测试。

覆盖场景：
- 大市值+高成交额+多头排列 -> is_capacity=True
- 小市值 -> is_capacity=False
- 大市值但空头排列 -> score 不足
- 数据不足 -> 降级处理不崩溃
"""

import pytest

from strategies.factors.capacity import detect_capacity_stock


def _uptrend_closes(n=30, base=10.0):
    """生成多头排列的上升收盘价序列。"""
    closes = []
    price = base
    for i in range(n):
        price = round(price + 0.3, 2)
        closes.append(price)
    return closes


def _downtrend_closes(n=30, base=20.0):
    """生成空头排列的下降收盘价序列。"""
    closes = []
    price = base
    for i in range(n):
        price = round(price - 0.3, 2)
        closes.append(price)
    return closes


class TestDetectCapacityStock:
    """容量票识别。"""

    def test_full_capacity_stock(self):
        """大市值+高成交额+多头排列 -> is_capacity=True。"""
        quote = {"total_cap": 500, "amount": 15e8}  # 500亿市值，15亿成交额
        closes = _uptrend_closes(30)
        result = detect_capacity_stock(quote, closes)
        assert result["is_capacity"] is True
        assert result["score"] >= 70
        assert "总市值" in result["reasons"][0]

    def test_small_cap_not_capacity(self):
        """小市值 -> is_capacity=False。"""
        quote = {"total_cap": 50, "amount": 3e8}  # 50亿市值，3亿成交额
        closes = _uptrend_closes(30)
        result = detect_capacity_stock(quote, closes)
        assert result["is_capacity"] is False
        assert result["score"] < 70

    def test_large_cap_but_downtrend(self):
        """大市值但空头排列 -> score 不足（趋势+溢价维度得0分）。"""
        quote = {"total_cap": 500, "amount": 15e8}
        closes = _downtrend_closes(30)
        result = detect_capacity_stock(quote, closes)
        # 市值30+成交额30=60，趋势0+溢价0=60 < 70
        assert result["is_capacity"] is False
        assert result["score"] < 70

    def test_mid_cap_mid_amount(self):
        """中等市值+中等成交额+多头排列 -> 接近但可能不足70。"""
        quote = {"total_cap": 250, "amount": 7e8}  # 250亿，7亿
        closes = _uptrend_closes(30)
        result = detect_capacity_stock(quote, closes)
        # 市值20+成交额20+趋势25+溢价15=80 >= 70
        assert result["is_capacity"] is True

    def test_insufficient_kline_data(self):
        """K线数据不足 -> 趋势维度降级，不崩溃。"""
        quote = {"total_cap": 500, "amount": 15e8}
        closes = [10.0, 10.5, 11.0]  # 只有3根，不够算MA20
        result = detect_capacity_stock(quote, closes)
        assert result is not None
        # 市值30+成交额30=60，趋势维度数据不足得0
        assert result["trend"] == "数据不足"

    def test_empty_quote(self):
        """空行情不崩溃。"""
        result = detect_capacity_stock({}, _uptrend_closes(30))
        assert result is not None
        assert result["is_capacity"] is False

    def test_return_structure_fields(self):
        """返回 dict 包含所有约定字段。"""
        quote = {"total_cap": 500, "amount": 15e8}
        closes = _uptrend_closes(30)
        result = detect_capacity_stock(quote, closes)
        for key in ("is_capacity", "score", "reasons", "cap", "amount_yi", "trend"):
            assert key in result, f"缺少字段 {key}"

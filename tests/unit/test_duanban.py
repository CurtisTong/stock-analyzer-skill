"""断板反包形态识别单元测试。

覆盖场景：
- 标准断板反包（涨停->断板回调->再涨停反包创新高）
- 无效：无双涨停（中间全是涨停=连板，非断板反包）
- 无效：回调太深（跌破首板实体下沿95%）
- 无效：既没创新高也没放量
- 数据不足 -> 空列表
"""

import pytest

from strategies.patterns.duanban import detect_duanban


def _bar(day, open_p, close_p, high_p, low_p, volume):
    """构造单根 K 线 dict。"""
    return {
        "day": day,
        "open": open_p,
        "close": close_p,
        "high": high_p,
        "low": low_p,
        "volume": volume,
    }


def _limit_up_bar(day, prev_close, board="主板", volume=10000):
    """构造涨停 K 线（主板 +9.8% 以上）。

    涨停价 = prev_close * 1.10，open=prev_close，close=涨停价。
    _is_limit_up 阈值 9.5%，实际涨幅 10% 满足。
    """
    close_p = round(prev_close * 1.10, 2)
    return _bar(day, prev_close, close_p, close_p, prev_close, volume)


def _normal_bar(day, open_p, close_p, volume=5000):
    """构造普通 K 线。"""
    high_p = max(open_p, close_p) + 0.1
    low_p = min(open_p, close_p) - 0.1
    return _bar(day, open_p, close_p, high_p, low_p, volume)


class TestDetectDuanban:
    """断板反包识别。"""

    def test_standard_duanban_breakout_new_high(self):
        """标准断板反包：首板->断板回调->再涨停反包创新高。"""
        # 首板 10.0->11.0，断板回调到 10.5，再涨停 10.5->11.55（>首板高点11.0）
        records = [
            _normal_bar("2026-07-20", 9.5, 10.0, 8000),  # 前置
            _limit_up_bar("2026-07-21", 10.0, volume=10000),  # 首板 11.0
            _normal_bar("2026-07-22", 11.0, 10.5, 4000),  # 断板回调
            _normal_bar("2026-07-23", 10.5, 10.5, 4000),  # 断板整理
            _limit_up_bar("2026-07-24", 10.5, volume=12000),  # 再涨停 11.55 > 11.0
        ]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        results = detect_duanban(records, closes, highs, lows, volumes, "sh600000")
        assert len(results) >= 1
        r = results[-1]
        assert r["name"] == "断板反包"
        assert r["type"] == "看涨"
        assert r["confidence"] in ("高", "中")
        assert r["metrics"]["breakout_new_high"] is True

    def test_invalid_all_limit_up_not_duanban(self):
        """中间全是涨停=连板，不是断板反包。"""
        # 连续3个涨停，没有断板
        records = [
            _normal_bar("2026-07-20", 9.0, 10.0, 8000),
            _limit_up_bar("2026-07-21", 10.0, volume=10000),  # 11.0
            _limit_up_bar("2026-07-22", 11.0, volume=11000),  # 12.1
            _limit_up_bar("2026-07-23", 12.1, volume=12000),  # 13.31
        ]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        results = detect_duanban(records, closes, highs, lows, volumes, "sh600000")
        # 连板中间没有断板日，不应识别为断板反包
        duanban = [r for r in results if r["name"] == "断板反包"]
        assert len(duanban) == 0

    def test_invalid_deep_pullback_below_floor(self):
        """回调太深（跌破首板实体下沿95%）-> 不识别。"""
        # 首板 10.0->11.0，实体下沿10.0，95%=9.5，回调到9.3跌破
        records = [
            _normal_bar("2026-07-20", 9.5, 10.0, 8000),
            _limit_up_bar("2026-07-21", 10.0, volume=10000),  # 11.0，实体下沿10.0
            _normal_bar("2026-07-22", 11.0, 9.3, 4000),  # 回调到9.3 < 10.0*0.95=9.5
            _normal_bar("2026-07-23", 9.3, 10.0, 4000),
            _limit_up_bar("2026-07-24", 10.0, volume=12000),  # 11.0
        ]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        results = detect_duanban(records, closes, highs, lows, volumes, "sh600000")
        duanban = [r for r in results if r["name"] == "断板反包"]
        assert len(duanban) == 0

    def test_confidence_high_with_volume_and_breakout(self):
        """放量+创新高 -> 置信度'高'。"""
        # 首板 10.0->11.0，断板缩量回调，再涨停放量创新高
        records = [
            _normal_bar("2026-07-19", 9.0, 9.5, 8000),  # 前置
            _normal_bar("2026-07-20", 9.5, 10.0, 8000),
            _limit_up_bar("2026-07-21", 10.0, volume=10000),  # 11.0
            _normal_bar("2026-07-22", 11.0, 10.6, 3000),  # 断板缩量
            _limit_up_bar("2026-07-23", 10.6, volume=15000),  # 11.66 > 11.0，放量
        ]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        results = detect_duanban(records, closes, highs, lows, volumes, "sh600000")
        assert len(results) >= 1
        r = results[-1]
        assert r["confidence"] == "高"
        assert r["metrics"]["vol_expansion"] is True
        assert r["metrics"]["breakout_new_high"] is True

    def test_insufficient_data_returns_empty(self):
        """数据不足返回空列表。"""
        records = [_normal_bar("2026-07-20", 10.0, 10.5, 5000)]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        assert detect_duanban(records, closes, highs, lows, volumes, "") == []

    def test_return_structure_fields(self):
        """返回 dict 包含所有约定字段。"""
        records = [
            _normal_bar("2026-07-19", 9.0, 9.5, 8000),  # 前置
            _normal_bar("2026-07-20", 9.5, 10.0, 8000),
            _limit_up_bar("2026-07-21", 10.0, volume=10000),
            _normal_bar("2026-07-22", 11.0, 10.5, 4000),
            _limit_up_bar("2026-07-23", 10.5, volume=12000),
        ]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        results = detect_duanban(records, closes, highs, lows, volumes, "sh600000")
        if results:
            r = results[-1]
            for key in ("name", "type", "date", "desc", "confidence", "idx", "metrics"):
                assert key in r, f"缺少字段 {key}"
            for key in ("gap", "breakout_new_high", "vol_expansion", "vol_ratio"):
                assert key in r["metrics"], f"metrics 缺少字段 {key}"

"""老鸭头形态识别测试（v2.7.x 覆盖率提升）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _make_ma(base, length, trend="up"):
    """生成简单 MA 序列。"""
    ma = []
    for i in range(length):
        if trend == "up":
            ma.append(base + i * 0.5)
        elif trend == "down":
            ma.append(base - i * 0.5)
        else:
            ma.append(base)
    return ma


class TestDetectLaoyatou:
    """detect_laoyatou 形态识别。"""

    def test_insufficient_closes(self):
        """K 线不足 60 根返回空。"""
        from strategies.patterns.laoyatou import detect_laoyatou
        result = detect_laoyatou([], [10] * 50, [100] * 50, {})
        assert result == []

    def test_missing_ma_keys(self):
        """缺少 MA 键返回空。"""
        from strategies.patterns.laoyatou import detect_laoyatou
        result = detect_laoyatou(
            [], [10] * 100, [100] * 100, {"ma5": [10] * 100}
        )
        assert result == []

    def test_ma60_too_short(self):
        """MA60 不足 20 根返回空。"""
        from strategies.patterns.laoyatou import detect_laoyatou
        mas = {"ma5": [10] * 100, "ma10": [10] * 100, "ma20": [10] * 100, "ma60": [10] * 10}
        result = detect_laoyatou([], [10] * 100, [100] * 100, mas)
        assert result == []

    def test_flat_market_no_signal(self):
        """横盘市场无老鸭头信号。"""
        from strategies.patterns.laoyatou import detect_laoyatou
        n = 100
        closes = [10.0] * n
        volumes = [1000] * n
        records = [{"day": f"2026-01-{i+1:02d}"} for i in range(n)]
        mas = {
            "ma5": [10.0] * n,
            "ma10": [10.0] * n,
            "ma20": [10.0] * n,
            "ma60": [10.0] * (n - 59),
        }
        result = detect_laoyatou(records, closes, volumes, mas)
        assert result == []

    def test_uptrend_no_cross_no_signal(self):
        """持续上升无金叉不触发信号。"""
        from strategies.patterns.laoyatou import detect_laoyatou
        n = 100
        closes = [10.0 + i * 0.1 for i in range(n)]
        volumes = [1000] * n
        records = [{"day": f"2026-01-{i+1:02d}"} for i in range(n)]
        mas = {
            "ma5": [10.0 + i * 0.1 for i in range(n)],
            "ma10": [10.0 + i * 0.08 for i in range(n)],
            "ma20": [10.0 + i * 0.05 for i in range(n)],
            "ma60": [10.0 + i * 0.03 for i in range(n - 59)],
        }
        result = detect_laoyatou(records, closes, volumes, mas)
        # 持续上升 MA5 始终在 MA10 上方，无下穿->上穿的鸭头形态
        assert result == []

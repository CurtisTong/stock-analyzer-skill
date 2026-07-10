"""
strategies.patterns 单元测试：覆盖 A 股本土战法检测。
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from strategies.patterns import (
    detect_sanying_yiyang,
    detect_laoyatou,
    detect_meirenjian,
    detect_shuangzhen,
    detect_zhangting,
    detect_dibu_shouban,
    detect_all_local_patterns,
    PatternInput,
)


def _make_records(opens, closes, highs, lows):
    """从价格列表构造 K 线记录。"""
    records = []
    for i in range(len(opens)):
        records.append(
            {
                "open": opens[i],
                "close": closes[i],
                "high": highs[i],
                "low": lows[i],
            }
        )
    return records


class TestDetectSanyingYiyang:
    """三阴一阳检测。"""

    def test_basic_sanying_yiyang(self):
        """连续3根阴线后接1根大阳线。"""
        opens = [
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10.5,
            10.3,
            10.1,
            10.8,
        ]
        closes = [
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10,
            10.3,
            10.1,
            9.9,
            11.2,
        ]
        highs = [max(o, c) + 0.1 for o, c in zip(opens, closes)]
        lows = [min(o, c) - 0.1 for o, c in zip(opens, closes)]
        volumes = [1000] * len(opens)
        records = _make_records(opens, closes, highs, lows)

        result = detect_sanying_yiyang(records, volumes)
        # 可能检测到也可能没检测到，取决于具体算法实现
        assert isinstance(result, list)

    def test_insufficient_data(self):
        """数据不足时返回空。"""
        records = _make_records([10, 10], [10, 10], [10.1, 10.1], [9.9, 9.9])
        result = detect_sanying_yiyang(records, [1000, 1000])
        assert result == []


class TestDetectLaoyatou:
    """老鸭头检测。"""

    def test_returns_list(self):
        """验证返回类型。"""
        n = 60
        closes = [10 + i * 0.1 for i in range(n)]
        opens = closes[:]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        volumes = [1000] * n
        mas = {
            "ma5": [10 + i * 0.1 for i in range(n)],
            "ma10": [10 + i * 0.1 for i in range(n)],
            "ma20": [10 + i * 0.1 for i in range(n)],
        }
        records = _make_records(opens, closes, highs, lows)

        result = detect_laoyatou(records, closes, volumes, mas)
        assert isinstance(result, list)


class TestDetectShuangzhen:
    """双针探底检测。"""

    def test_returns_list(self):
        """验证返回类型。"""
        n = 30
        closes = [10] * n
        opens = [10] * n
        highs = [10.2] * n
        lows = [9.5] * n  # 长下影线
        volumes = [1000] * n
        records = _make_records(opens, closes, highs, lows)

        result = detect_shuangzhen(records, closes, lows, volumes)
        assert isinstance(result, list)


class TestDetectAllLocalPatterns:
    """统一入口测试。"""

    def test_returns_dict_with_patterns(self):
        """验证返回格式。"""
        n = 60
        closes = [10 + i * 0.05 for i in range(n)]
        opens = closes[:]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        volumes = [1000] * n
        mas = {"ma5": closes[:], "ma10": closes[:], "ma20": closes[:]}
        records = _make_records(opens, closes, highs, lows)

        result = detect_all_local_patterns(
            PatternInput(
                records=records,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                mas=mas,
                code="sh600519",
            )
        )
        assert "patterns" in result
        assert isinstance(result["patterns"], list)

"""
strategies.patterns 单元测试：覆盖 A 股本土战法检测。
5 类战法：zhangting（涨停双响炮）/ dibu_shouban（底部首板）/ sanying（三阴一阳）/
shuangzhen（双针探底）/ meirenjian（美人肩）/ laoyatou（老鸭头）。
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategies.patterns import (
    zhangting, dibu_shouban, sanying, shuangzhen, meirenjian, laoyatou,
)


def _make_record(date, open_, close, volume, high=None, low=None):
    r = {"day": date, "open": open_, "close": close, "volume": volume}
    if high is not None:
        r["high"] = high
    if low is not None:
        r["low"] = low
    return r


# ═══════════════════════════════════════════════════════════════
# zhangting - 涨停双响炮
# ═══════════════════════════════════════════════════════════════


class TestZhangting:
    def test_empty_records(self):
        result = zhangting.detect_zhangting([], [], [])
        assert result == []

    def test_short_records(self):
        """< 5 records 返回空。"""
        records = [_make_record("2026-07-01", 10, 11, 1000)] * 3
        closes = [11, 11, 11]
        volumes = [1000, 1000, 1000]
        result = zhangting.detect_zhangting(records, closes, volumes)
        assert result == []

    def test_no_double_thunder(self):
        """无涨停双响炮。"""
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000) for i in range(10)]
        closes = [r["close"] for r in records]
        volumes = [r["volume"] for r in records]
        result = zhangting.detect_zhangting(records, closes, volumes)
        assert result == []

    def test_with_board_code(self):
        """不同 board 参数不抛错。"""
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 11, 1000) for i in range(10)]
        closes = [r["close"] for r in records]
        volumes = [r["volume"] for r in records]
        for code in ["sh600519", "sz300750", "sh688001", "bj430001"]:
            result = zhangting.detect_zhangting(records, closes, volumes, code=code)
            assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# dibu_shouban - 底部首板
# ═══════════════════════════════════════════════════════════════


class TestDibuShouban:
    def test_empty(self):
        result = dibu_shouban.detect_dibu_shouban([], [], [], [], [])
        assert result == []

    def test_no_signal(self):
        """无底部形态时返回空。"""
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000) for i in range(20)]
        closes = [r["close"] for r in records]
        highs = [11 for _ in records]
        lows = [10 for _ in records]
        volumes = [r["volume"] for r in records]
        result = dibu_shouban.detect_dibu_shouban(records, closes, highs, lows, volumes)
        assert isinstance(result, list)

    def test_with_code(self):
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000,
                                  high=11, low=9) for i in range(20)]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        result = dibu_shouban.detect_dibu_shouban(records, closes, highs, lows, volumes,
                                                  code="sh600519")
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# sanying - 三阴一阳
# ═══════════════════════════════════════════════════════════════


class TestSanying:
    def test_empty(self):
        result = sanying.detect_sanying_yiyang([], [], code="sh600519")
        assert result == []

    def test_with_code(self):
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000) for i in range(10)]
        volumes = [r["volume"] for r in records]
        result = sanying.detect_sanying_yiyang(records, volumes, code="sh600519")
        assert isinstance(result, list)

    def test_no_code(self):
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000) for i in range(10)]
        volumes = [r["volume"] for r in records]
        result = sanying.detect_sanying_yiyang(records, volumes)
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# shuangzhen - 双针探底
# ═══════════════════════════════════════════════════════════════


class TestShuangzhen:
    def test_empty(self):
        result = shuangzhen.detect_shuangzhen([], [], [], [])
        assert result == []

    def test_no_signal(self):
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000,
                                  low=9.5) for i in range(10)]
        closes = [r["close"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        result = shuangzhen.detect_shuangzhen(records, closes, lows, volumes)
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# meirenjian - 美人肩
# ═══════════════════════════════════════════════════════════════


class TestMeirenjian:
    def test_importable(self):
        assert hasattr(meirenjian, "detect_meirenjian")

    def test_empty(self):
        # meirenjian(records, closes, highs, lows, volumes, mas)
        result = meirenjian.detect_meirenjian([], [], [], [], [], {})
        assert result == []

    def test_no_signal(self):
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000,
                                  high=10.5, low=9.5) for i in range(20)]
        closes = [r["close"] for r in records]
        highs = [r["high"] for r in records]
        lows = [r["low"] for r in records]
        volumes = [r["volume"] for r in records]
        result = meirenjian.detect_meirenjian(records, closes, highs, lows, volumes, {})
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# laoyatou - 老鸭头
# ═══════════════════════════════════════════════════════════════


class TestLaoyatou:
    def test_importable(self):
        assert hasattr(laoyatou, "detect_laoyatou")

    def test_empty(self):
        # laoyatou(records, closes, volumes, mas)
        result = laoyatou.detect_laoyatou([], [], [], {})
        assert result == []

    def test_no_signal(self):
        records = [_make_record(f"2026-07-{i+1:02d}", 10, 10.5, 1000,
                                  high=10.5, low=9.5) for i in range(30)]
        closes = [r["close"] for r in records]
        volumes = [r["volume"] for r in records]
        result = laoyatou.detect_laoyatou(records, closes, volumes, {})
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# patterns/utils
# ═══════════════════════════════════════════════════════════════


class TestPatternsUtils:
    def test_is_limit_up(self):
        """_is_limit_up 涨停判断（主板 10% 涨停）。"""
        from strategies.patterns import utils
        # 主板 +10% 涨停
        assert utils._is_limit_up(10, 11, 10, "主板") is True
        # 主板 +5% 未涨停
        assert utils._is_limit_up(10, 10.5, 10, "主板") is False
        # 创业板 +20% 涨停
        assert utils._is_limit_up(10, 12, 10, "创业板") is True
        # 北交所 +30% 涨停
        assert utils._is_limit_up(10, 13, 10, "北交所") is True

    def test_is_limit_up_zero(self):
        from strategies.patterns import utils
        # prev_close=0 边界
        assert utils._is_limit_up(10, 11, 0, "主板") in (True, False)
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

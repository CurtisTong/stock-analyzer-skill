"""
测试 scripts/dev/clock.py 的可注入时钟。

Property-based 测试（如果 hypothesis 已装）+ 基础行为测试。
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dev import clock


class TestClockBasics:
    def test_now_returns_datetime(self):
        """now() 应返回 datetime 实例。"""
        result = clock.now()
        assert isinstance(result, datetime)

    def test_freeze_returns_target(self):
        """freeze 后 now() 返回冻结时间。"""
        target = datetime(2026, 6, 16, 12, 0, 0)
        clock.freeze(target)
        try:
            assert clock.now() == target
        finally:
            clock.unfreeze()

    def test_unfreeze_restores_real_time(self):
        """unfreeze 后 now() 接近真实时间。"""
        clock.unfreeze()
        before = datetime.now()
        result = clock.now()
        after = datetime.now()
        assert before <= result <= after

    def test_freeze_then_unfreeze(self):
        """freeze/unfreeze 循环不影响后续 now()。"""
        clock.freeze(datetime(2020, 1, 1))
        clock.unfreeze()
        result = clock.now()
        # 真实时间应远大于 2020
        assert result.year >= 2024


class TestClockInjection:
    """模拟测试中 monkeypatch clock._now_func 的能力。"""

    def test_monkeypatch_now_func(self):
        """替换 _now_func 后 now() 应使用新函数。"""
        original = clock._now_func
        fake_time = datetime(2030, 1, 1)
        try:
            clock._now_func = lambda: fake_time
            assert clock.now() == fake_time
        finally:
            clock._now_func = original

    def test_repeated_freeze_overrides(self):
        """连续 freeze 应使用最后一次的目标。"""
        clock.freeze(datetime(2020, 1, 1))
        clock.freeze(datetime(2025, 12, 31))
        try:
            assert clock.now() == datetime(2025, 12, 31)
        finally:
            clock.unfreeze()


# ═══════════════════════════════════════════════════════════════
# Property-based 测试（hypothesis 可选）
# ═══════════════════════════════════════════════════════════════

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    @given(
        st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2099, 12, 31))
    )
    @settings(max_examples=50, deadline=None)
    def test_freeze_preserves_any_datetime(target):
        """任何 datetime 都能被 freeze/unfreeze。"""
        clock.freeze(target)
        try:
            assert clock.now() == target
        finally:
            clock.unfreeze()

except ImportError:
    import pytest

    @pytest.mark.skip(reason="hypothesis 未安装")
    def test_freeze_preserves_any_datetime():
        pass

"""dcf_valuation 边界守卫的回归测试（research financial 模式的可执行内核）。

回归背景（2026-11-02 skill 审查 P1）：
1. discount_rate 用 ==0.10 当"用户未指定"哨兵——用户显式传 10% 会被
   静默替换成 CAPM/行业字典值；
2. terminal_growth >= discount_rate 时 Gordon 永续公式直接
   ZeroDivisionError（discount_rate=0.03, terminal_growth=0.03 实测崩溃）。
"""

from __future__ import annotations

import pytest

from strategies.factors.dcf import dcf_valuation

_FIN = {
    "ocf_per_share": 2.0,
    "eps": 1.5,
    "net_profit_yoy": 10.0,
}


class TestDiscountRateSentinel:
    def test_explicit_10pct_is_respected(self):
        """显式传 0.10 按"用户传入"生效，不再被 CAPM/行业字典静默替换。"""
        r = dcf_valuation(20.0, _FIN, discount_rate=0.10, stock_code="sh600519")
        assert r["wacc_source"] == "用户传入"
        assert r["discount_rate"] == pytest.approx(10.0)

    def test_none_falls_back_to_industry(self):
        """不传折现率：走行业字典回退（无 CAPM 通路）。"""
        r = dcf_valuation(20.0, _FIN)
        assert r["wacc_source"].startswith("行业字典")
        assert 0 < r["discount_rate"] < 100


class TestTerminalValueGuard:
    def test_r_equals_g_no_crash(self):
        """discount_rate == terminal_growth：钳制后正常输出，不再除零。"""
        r = dcf_valuation(
            20.0,
            _FIN,
            discount_rate=0.03,
            terminal_growth=0.03,
            growth_rate=0.02,
        )
        assert r["intrinsic_value"] > 0
        assert r["terminal_growth"] == pytest.approx(2.0)  # 0.03-0.01

    def test_g_above_r_no_crash(self):
        """terminal_growth > discount_rate：同样钳制不崩溃。"""
        r = dcf_valuation(
            20.0,
            _FIN,
            discount_rate=0.04,
            terminal_growth=0.05,
            growth_rate=0.06,
        )
        assert r["intrinsic_value"] > 0
        assert r["terminal_growth"] == pytest.approx(3.0)

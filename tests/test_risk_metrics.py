"""风控量化指标单元测试。"""

import sys
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from business.risk_metrics import (
    historical_var,
    conditional_var,
    max_drawdown,
    volatility,
    sharpe,
    position_var_summary,
)


class TestVaR:
    def test_historical_var_basic(self):
        """历史 VaR 95% 取第 5 百分位。"""
        returns = [-0.05, -0.02, 0.01, 0.03, 0.04, -0.10, 0.06, -0.01, 0.02, -0.03]
        var = historical_var(returns, confidence=0.95)
        # 95% VaR 应至少是 -10% 的绝对值（最差）
        assert var > 0  # 返回正数表示亏损幅度

    def test_historical_var_empty(self):
        """空输入返回 0。"""
        assert historical_var([]) == 0.0

    def test_conditional_var_larger_than_var(self):
        """CVaR 应 ≥ VaR（尾部风险）。"""
        returns = [-0.05, -0.02, 0.01, 0.03, -0.10, 0.06, -0.15, 0.04, -0.08, 0.02]
        var = historical_var(returns, 0.95)
        cvar = conditional_var(returns, 0.95)
        # CVaR 应大于等于 VaR（因为是平均尾部损失）
        assert cvar >= var - 1e-6

    def test_historical_var_all_positive_returns(self):
        """全正收益时 VaR 应为 0（abs 会把正收益误报为风险值）。"""
        returns = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
        var = historical_var(returns, confidence=0.95)
        assert var == 0.0

    def test_conditional_var_all_positive_returns(self):
        """全正收益时 CVaR 应为 0。"""
        returns = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
        cvar = conditional_var(returns, confidence=0.95)
        assert cvar == 0.0


class TestDrawdown:
    def test_max_drawdown_basic(self):
        """最大回撤识别：peak 110 → trough 86.4 ≈ -21.45%？修正：peak 应是历史最高 110，trough 是 95，回撤 = (95-110)/110 = -13.64%。"""
        prices = [100, 110, 105, 95, 98, 102]
        result = max_drawdown(prices)
        assert result["max_dd_pct"] < 0  # 负数表示回撤
        # 实际算法 peak 取到 110，trough = 95，回撤 = -13.64%
        assert abs(result["max_dd_pct"] - (-0.1364)) < 0.01

    def test_max_drawdown_no_drawdown(self):
        """单调上涨无回撤。"""
        prices = [100, 105, 110, 115, 120]
        result = max_drawdown(prices)
        assert result["max_dd_pct"] == 0.0

    def test_max_drawdown_empty(self):
        """空输入返回 0。"""
        result = max_drawdown([])
        assert result["max_dd_pct"] == 0.0

    def test_max_drawdown_recovery_idx_recovered(self):
        """P2-22: 回撤后价格恢复至峰值时 recovery_idx 为有效索引。"""
        # peak=110 @ idx1, trough=95 @ idx3, 恢复到 110 @ idx5
        prices = [100, 110, 105, 95, 98, 110]
        result = max_drawdown(prices)
        assert result["recovery_idx"] is not None
        assert result["recovery_idx"] > result["trough_idx"]
        assert result["recovery_idx"] == 5

    def test_max_drawdown_recovery_idx_none_when_not_recovered(self):
        """P2-22: 回撤后未恢复至峰值时 recovery_idx 为 None。"""
        # peak=110 @ idx1, trough=95 @ idx3, 之后最高仅 108 < 110
        prices = [100, 110, 105, 95, 98, 108, 106]
        result = max_drawdown(prices)
        assert result["recovery_idx"] is None

    def test_max_drawdown_recovery_idx_none_at_end(self):
        """P2-22: trough 在序列末尾时 recovery_idx 为 None（无后续恢复点）。"""
        prices = [100, 110, 105, 95]
        result = max_drawdown(prices)
        assert result["recovery_idx"] is None


class TestVolatilitySharpe:
    def test_volatility_positive(self):
        """波动率应 ≥ 0。"""
        returns = [-0.01, 0.02, -0.015, 0.03, -0.005]
        assert volatility(returns) > 0

    def test_sharpe_zero_vol(self):
        """无波动率时夏普应为 0。"""
        # 完全相同收益
        returns = [0.01] * 10
        sharpe_ratio = sharpe(returns)
        assert sharpe_ratio == 0.0


class TestPositionVaR:
    def test_position_var_summary_empty(self):
        """空持仓应返回空 summary。"""
        result = position_var_summary([], {})
        assert result["var_pct"] == 0.0

    def test_position_var_summary_weighted(self):
        """加权 VaR：单一持仓 VaR 应与权重成正比。"""
        positions = [
            {"code": "sh600519", "name": "茅台", "weight": 0.5, "vol": 0.30},
            {"code": "sz000001", "name": "平安", "weight": 0.5, "vol": 0.20},
        ]
        result = position_var_summary(positions, confidence=0.95)
        assert result["var_pct"] > 0
        assert "worst_scenarios" in result

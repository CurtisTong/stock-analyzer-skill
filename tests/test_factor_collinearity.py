"""P2-05: 因子共线性诊断与去相关测试。

验证 compute_factor_correlation_matrix / compute_vif / decorrelate_factors
的数学正确性，以及 decorrelate 集成到 compute_weighted_score_with_norm 的行为。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategies.factors.registry import (
    compute_factor_correlation_matrix,
    compute_vif,
    decorrelate_factors,
    _solve_linear,
)


def test_diagonal_is_one():
    """对角线相关系数应为 1.0。"""
    matrix = compute_factor_correlation_matrix(
        {"a": [1, 2, 3, 4], "b": [5, 6, 7, 8]}
    )
    assert matrix["a"]["a"] == 1.0
    assert matrix["b"]["b"] == 1.0


def test_perfect_positive_correlation():
    """完全正相关（线性倍数）应得 1.0。"""
    matrix = compute_factor_correlation_matrix(
        {"a": [1, 2, 3, 4], "b": [2, 4, 6, 8]}
    )
    assert matrix["a"]["b"] == 1.0
    assert matrix["b"]["a"] == 1.0


def test_perfect_negative_correlation():
    """完全负相关应得 -1.0。"""
    matrix = compute_factor_correlation_matrix(
        {"a": [1, 2, 3, 4], "b": [8, 6, 4, 2]}
    )
    assert matrix["a"]["b"] == -1.0


def test_symmetric():
    """矩阵应对称。"""
    matrix = compute_factor_correlation_matrix(
        {"a": [1, 2, 3, 4], "b": [3, 1, 4, 1], "c": [5, 5, 5, 5]}
    )
    for i in matrix:
        for j in matrix[i]:
            assert matrix[i][j] == matrix[j][i]


def test_missing_data_pair_returns_none():
    """数据长度不一致的因子对相关系数为 None。"""
    matrix = compute_factor_correlation_matrix(
        {"a": [1, 2, 3, 4], "b": [5, 6]}
    )
    assert matrix["a"]["b"] is None


def test_constant_factor():
    """常量因子（方差=0）相关系数为 None，避免除零。"""
    matrix = compute_factor_correlation_matrix(
        {"a": [1, 2, 3, 4], "b": [5, 5, 5, 5]}
    )
    assert matrix["a"]["b"] is None


# ═══════════════════════════════════════════════════════════════
# VIF 测试
# ═══════════════════════════════════════════════════════════════


class TestVIF:
    """方差膨胀因子（VIF）测试。"""

    def test_independent_factors_low_vif(self):
        """不相关因子 VIF 应接近 1.0。"""
        vif = compute_vif({
            "a": [1, 3, 2, 5, 4, 6, 8, 7],
            "b": [5, 2, 8, 3, 6, 1, 4, 7],
        })
        assert vif["a"] is not None
        assert vif["a"] < 10.0, f"独立因子 VIF={vif['a']} 应 < 10"

    def test_collinear_factors_high_vif(self):
        """高度共线因子 VIF 应 > 5。"""
        # b = 2*a, c = 3*a -> b 和 c 完全共线
        vif = compute_vif({
            "a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "b": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
            "c": [3, 6, 9, 12, 15, 18, 21, 24, 27, 30],
        })
        # b 和 c 完全线性相关 -> VIF 应很大或 inf
        assert vif["b"] is not None
        assert vif["b"] > 5.0 or vif["b"] == float("inf"), f"共线因子 VIF={vif['b']} 应 > 5"

    def test_insufficient_data_returns_none(self):
        """数据不足（<3）返回 None。"""
        vif = compute_vif({"a": [1, 2], "b": [3, 4]})
        assert vif["a"] is None
        assert vif["b"] is None

    def test_single_factor_vif_one(self):
        """仅一个因子时 VIF = 1.0（无共线性）。"""
        vif = compute_vif({"a": [1, 2, 3, 4, 5]})
        assert vif["a"] == 1.0


# ═══════════════════════════════════════════════════════════════
# 去相关测试
# ═══════════════════════════════════════════════════════════════


class TestDecorrelate:
    """残差化去相关测试。"""

    def test_no_change_below_threshold(self):
        """相关系数低于阈值时不做处理。"""
        parts = [
            {"a": 1, "b": 10},
            {"a": 2, "b": 8},
            {"a": 3, "b": 12},
            {"a": 4, "b": 6},
        ]
        result = decorrelate_factors(parts, threshold=0.99)
        # 低相关，不应改变
        assert all(r == p for r, p in zip(result, parts))

    def test_collinear_pair_residualized(self):
        """高相关因子对中，B 被 A 残差化。"""
        # b 完全由 a 线性决定：b = 2*a + 1
        parts = [
            {"a": 1, "b": 3},
            {"a": 2, "b": 5},
            {"a": 3, "b": 7},
            {"a": 4, "b": 9},
            {"a": 5, "b": 11},
        ]
        result = decorrelate_factors(parts, threshold=0.5)
        # b 应被残差化（不再是 2*a+1 的线性关系）
        assert result != parts, "高相关因子应被残差化"
        # a 不应变
        assert [r["a"] for r in result] == [p["a"] for p in parts]

    def test_preserves_structure(self):
        """去相关后保持相同 key 集合和顺序。"""
        parts = [
            {"a": 1, "b": 3, "c": 0.5},
            {"a": 2, "b": 5, "c": 0.8},
            {"a": 3, "b": 7, "c": 0.9},
        ]
        result = decorrelate_factors(parts, threshold=0.5)
        assert len(result) == len(parts)
        for r in result:
            assert set(r.keys()) == {"a", "b", "c"}

    def test_insufficient_samples_no_op(self):
        """样本 < 3 时不处理。"""
        parts = [{"a": 1, "b": 3}, {"a": 2, "b": 5}]
        result = decorrelate_factors(parts)
        assert result is parts  # 原对象返回


# ═══════════════════════════════════════════════════════════════
# 线性方程求解器测试
# ═══════════════════════════════════════════════════════════════


class TestSolveLinear:
    """高斯消元求解器测试。"""

    def test_simple_system(self):
        """解 2x2 线性方程组。"""
        # x + y = 3, x - y = 1 -> x=2, y=1
        A = [[1, 1], [1, -1]]
        b = [3, 1]
        x = _solve_linear(A, b, 2)
        assert x is not None
        assert abs(x[0] - 2) < 1e-6
        assert abs(x[1] - 1) < 1e-6

    def test_singular_returns_none(self):
        """奇异矩阵返回 None。"""
        A = [[1, 1], [1, 1]]  # 两行相同
        b = [1, 2]
        x = _solve_linear(A, b, 2)
        assert x is None
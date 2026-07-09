"""P2-05: 因子相关矩阵诊断工具测试。

仅验证 compute_factor_correlation_matrix 的数学正确性，
不做实际打分回归（属 v2.0.0 范畴）。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from strategies.factors.registry import compute_factor_correlation_matrix


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
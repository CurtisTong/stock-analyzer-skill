"""(#8) 分位数归一化测试。

覆盖：
- 大样本（>=30）分位数归一化
- 小样本（<30）MAD 降级
- 单股跳过
- 极值处理
- ties 处理
- 排序保持
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from business.screening_service import normalize_factors_batch  # noqa: E402


def _make_parts(n, quality_values=None):
    """构造 n 只股票的 parts_list，quality 用指定值，其余因子固定 50。"""
    if quality_values is None:
        quality_values = list(range(n))
    parts = []
    for i, q in enumerate(quality_values):
        parts.append(
            {
                "quality": float(q),
                "valuation": 50.0,
                "momentum": 50.0,
                "liquidity": 50.0,
                "volatility": 50.0,
                "dividend": 50.0,
            }
        )
    return parts


class TestQuantileNormalization:
    """大样本（>=30）分位数归一化。"""

    def test_large_sample_uses_quantile(self):
        """30 只股票使用分位数归一化，值映射到 [0, 100]。"""
        vals = list(range(30))  # 0, 1, ..., 29
        parts = _make_parts(30, vals)
        out = normalize_factors_batch(parts)
        # 最低分（0）应映射到接近 0，最高分（29）应映射到接近 100
        assert out[0]["quality"] < out[-1]["quality"]
        assert 0 < out[0]["quality"] < 10  # rank 1 / 31 * 100 = 3.2
        assert 90 < out[-1]["quality"] < 100  # rank 30 / 31 * 100 = 96.8

    def test_quantile_uniform_distribution(self):
        """分位数归一化后值均匀分散（不依赖分布假设）。"""
        # 构造一个偏态分布：90% 是 50，10% 是 100
        vals = [50] * 27 + [100] * 3
        parts = _make_parts(30, vals)
        out = normalize_factors_batch(parts)
        # Z-score 下 50 会被压缩到很窄范围，分位数下 50 仍均匀分散
        fifties = [o["quality"] for o in out[:27]]
        # 27 个相同值应取平均排名 (1+27)/2 = 14 -> 14/31*100 = 45.2
        assert all(abs(f - 14 / 31 * 100) < 0.1 for f in fifties)

    def test_quantile_preserves_order(self):
        """分位数归一化保持原始排序。"""
        vals = [10, 50, 90, 30, 70] * 6  # 30 个值，每 5 个重复
        parts = _make_parts(30, vals)
        out = normalize_factors_batch(parts)
        # 同一原始值应映射到同一归一化值（间隔 5 的索引相同）
        for i in range(5):
            # vals[i] == vals[i+5] == vals[i+10] == ...
            for j in range(1, 6):
                assert out[i]["quality"] == out[i + 5 * j]["quality"]

    def test_quantile_handles_ties(self):
        """ties（相同值）取平均排名。"""
        # 18 个 10 + 6 个 20 + 6 个 30
        vals = [10] * 18 + [20] * 6 + [30] * 6
        parts = _make_parts(30, vals)
        out = normalize_factors_batch(parts)
        # 所有 10 应有相同归一化值（平均排名 (1+18)/2 = 9.5 -> 9.5/31*100）
        ten_val = out[0]["quality"]
        for i in range(18):
            assert out[i]["quality"] == ten_val
        # 所有 20 应有相同值（平均排名 (19+24)/2 = 21.5）
        twenty_val = out[18]["quality"]
        for i in range(18, 24):
            assert out[i]["quality"] == twenty_val
        # 10 < 20 < 30
        assert ten_val < twenty_val < out[24]["quality"]


class TestMADFallback:
    """小样本（<30）MAD 降级。"""

    def test_small_sample_uses_mad(self):
        """3 只股票使用 MAD 标准化。"""
        vals = [80, 50, 20]
        parts = _make_parts(3, vals)
        out = normalize_factors_batch(parts)
        # median=50, MAD=30
        # z(80) = 30/(1.4826*30) = 0.6746 -> 50 + 10.12 = 60.12
        # z(50) = 0 -> 50
        # z(20) = -0.6746 -> 50 - 10.12 = 39.88
        assert abs(out[1]["quality"] - 50.0) < 0.1
        assert out[0]["quality"] > 50
        assert out[2]["quality"] < 50

    def test_mad_robust_to_outlier(self):
        """MAD 对极值稳健（不受单个异常值影响）。"""
        vals = [50, 50, 50, 50, 50, 10000]  # 一个极端异常值
        parts = _make_parts(6, vals)
        out = normalize_factors_batch(parts)
        # median=50, MAD=0 -> 回退到 1.0
        # 前 5 个 50 映射到 50，异常值映射到很高的正 z
        for i in range(5):
            assert out[i]["quality"] == 50.0
        assert out[5]["quality"] > 50

    def test_mad_all_same_returns_50(self):
        """所有值相同 -> MAD=0 -> 全部映射到 50。"""
        vals = [50] * 5
        parts = _make_parts(5, vals)
        out = normalize_factors_batch(parts)
        for o in out:
            assert o["quality"] == 50.0


class TestEdgeCases:
    """边界情况。"""

    def test_empty_returns_empty(self):
        assert normalize_factors_batch([]) == []

    def test_single_returns_copy(self):
        """单股跳过归一化，返回副本。"""
        parts = [{"quality": 80, "valuation": 30}]
        out = normalize_factors_batch(parts)
        assert out[0] == parts[0]
        out[0]["quality"] = 99
        assert parts[0]["quality"] == 80  # 副本独立

    def test_output_clamped_to_0_100(self):
        """归一化值 clamp 到 [0, 100]。"""
        vals = [0, 100]  # 2 只极端值
        parts = _make_parts(2, vals)
        out = normalize_factors_batch(parts)
        for o in out:
            assert 0.0 <= o["quality"] <= 100.0

    def test_does_not_mutate_input(self):
        """不修改输入 parts_list。"""
        parts = _make_parts(5, [10, 20, 30, 40, 50])
        original = [p["quality"] for p in parts]
        normalize_factors_batch(parts)
        assert [p["quality"] for p in parts] == original

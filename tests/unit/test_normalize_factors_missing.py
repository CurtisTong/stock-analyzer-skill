"""normalize_factors_batch 缺失值处理测试。

v1.24.0：缺 key / 值为 None 的因子不参与分布统计，归一化后填中性 50，
不再被排到最低分位（此前 p.get(k, 0) 把缺值当 0 分）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from business.screening_service import normalize_factors_batch


def _big_batch(n=30, override=None):
    """构造 n 只股票的因子分，全部因子同值便于控制单一变量。"""
    rows = []
    for i in range(n):
        row = {k: 60.0 + (i % 10) for k in ("quality", "valuation", "momentum")}
        if override:
            row.update(override(i))
        rows.append(row)
    return rows


class TestQuantilePath:
    def test_missing_key_gets_neutral_50_not_zero(self):
        rows = _big_batch(30, override=lambda i: {"quality": None} if i < 5 else {})
        normed = normalize_factors_batch(rows)
        # 前 5 只缺 quality：应得中性 50，而非被排到最低分位（≈0-13）
        for r in normed[:5]:
            assert r["quality"] == 50.0
        # 其余 25 只正常参与排序，且最低分位显著高于 0
        present = [r["quality"] for r in normed[5:]]
        assert min(present) > 0

    def test_none_value_does_not_crash_sort(self):
        # 此前 None 直接进 sorted 会 TypeError
        rows = _big_batch(35, override=lambda i: {"valuation": None} if i % 7 == 0 else {})
        normed = normalize_factors_batch(rows)
        assert len(normed) == 35
        for i, r in enumerate(normed):
            if i % 7 == 0:
                assert r["valuation"] == 50.0

    def test_present_ranks_span_full_range(self):
        rows = _big_batch(30)
        normed = normalize_factors_batch(rows)
        vals = [r["quality"] for r in normed]
        assert max(vals) > 90  # 最高分位接近 100
        assert min(vals) < 10  # 最低分位接近 0


class TestMadPath:
    def test_small_batch_missing_gets_neutral_50(self):
        rows = _big_batch(10, override=lambda i: {"momentum": None} if i == 0 else {})
        normed = normalize_factors_batch(rows)
        assert normed[0]["momentum"] == 50.0
        assert all(r["momentum"] != 50.0 or i != 0 for i, r in enumerate(normed[1:], 1))

    def test_all_missing_factor_fills_50(self):
        rows = _big_batch(10, override=lambda i: {"dividend": None})
        normed = normalize_factors_batch(rows)
        assert all(r["dividend"] == 50.0 for r in normed)

    def test_missing_key_small_batch(self):
        rows = [{k: 55.0 for k in ("quality", "valuation")} for _ in range(5)]
        normed = normalize_factors_batch(rows)
        for r in normed:
            assert r["momentum"] == 50.0

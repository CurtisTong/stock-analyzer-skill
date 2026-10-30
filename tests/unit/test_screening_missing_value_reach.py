"""v1.24.0 复审修复：选股缺值处理的生产路径可达性。

背景：v1.24.0 的 P0 第 7 项修复了 normalize_factors_batch 的"缺值当 0"
（缺值应填中性 50 分位），但调用方 screening_pipeline._apply_factor_normalization
用 `r.get(k, 0)` 预填缺失，且 build_result_row 只输出 7 个硬编码因子——
结果生产路径上 normalize 永远看不到缺失，修复不可达；有权重的 event 因子
被填 0 排到最低分位，区分度被抹平。
"""

from __future__ import annotations

import pytest


class TestBuildResultRowKeepsMissing:
    """build_result_row 不得把缺失伪装成 50。"""

    def _ctx(self, parts):
        from business.screening_service import ResultRowContext, build_result_row

        return build_result_row(
            ResultRowContext(
                code="sh600519",
                quote_dict={"name": "贵州茅台", "price": 1500.0},
                fin={},
                features={"ret20": 1.0, "rsi": 50, "macd_signal": 0, "vol_price_signal": 0, "trend": 0},
                industry="白酒",
                total=60.0,
                parts=parts,
                rejected=[],
            )
        )

    def test_missing_factor_is_none(self):
        row = self._ctx({"quality": 80.0, "valuation": 70.0})
        assert row["quality"] == 80.0
        # 缺失（key 不存在）保留 None，不再是 50
        assert row["momentum"] is None
        assert row["dividend"] is None

    def test_extra_factors_are_carried_through(self):
        """parts 里的 event 等因子必须带出（否则调用方会填 0）。"""
        row = self._ctx({"quality": 80.0, "event": 20.0, "analyst": 90.0})
        assert row["event"] == 20.0
        assert row["analyst"] == 90.0


class TestPipelineNormalizationReachesMissing:
    """生产调用链：缺失因子在归一化后必须是中性 50 分位，而非最低分位。"""

    def test_missing_factor_not_ranked_lowest(self):
        from business.screening_pipeline import _apply_factor_normalization

        # 30 只股：momentum 全有值且互不相同，quality 有一只缺失
        rows = []
        for i in range(30):
            r = {"code": f"sh60000{i}", "score": 50.0, "momentum": float(i)}
            if i == 0:
                r["quality"] = None  # 缺失
            else:
                r["quality"] = float(i)
            rows.append(r)

        _apply_factor_normalization(rows, "balanced")

        # 缺失的那只：momentum 有真实值（应按真实分位），quality 缺失 → 中性 50
        assert rows[0]["momentum"] > 0, "有真实值的因子不应被当作缺失"
        assert rows[0]["quality"] == pytest.approx(50.0, abs=0.5), rows[0]["quality"]

    def test_absent_factor_is_neutral_not_zero(self):
        """row 里完全没有该因子 → 归一化后为中性 50（不是 0 分位）。"""
        from business.screening_pipeline import _apply_factor_normalization

        rows = []
        for i in range(30):
            r = {"code": f"sh60000{i}", "score": 50.0, "quality": float(i), "momentum": float(i)}
            # event 因子完全不存在（有权重但未计算）
            rows.append(r)

        _apply_factor_normalization(rows, "balanced")

        for r in rows:
            assert r.get("event") == pytest.approx(50.0, abs=0.5), r.get("event")


class TestWeightedScoreHandlesNone:
    """compute_weighted_score 对 None 因子按中性 50 处理（不得 TypeError）。"""

    def test_none_factor_treated_as_neutral(self):
        from business.screening_service import compute_weighted_score

        score = compute_weighted_score({"quality": 80.0, "momentum": None}, "balanced")
        assert isinstance(score, float)
        assert score > 0

    def test_missing_key_and_none_equivalent(self):
        from business.screening_service import compute_weighted_score

        a = compute_weighted_score({"quality": 80.0, "momentum": None}, "balanced")
        b = compute_weighted_score({"quality": 80.0, "momentum": 50}, "balanced")
        assert a == pytest.approx(b, abs=1e-9)

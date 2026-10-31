"""P1-6 回归：quality 因子的累计口径报告期缩放。

季报 EPS/ROE 是年初至今**累计**值（三季报 = 前 9 个月）；与年度行业阈值
（roe_excellent）比较前按报告期折算，否则同一家公司三季报分数显著低于
年报分数（系统性偏差）。比值项（ocf/eps 等）同口径不受影响。
"""

from __future__ import annotations

import pytest


def _cumulative_scale(fin):
    from strategies.factors.quality import _cumulative_scale

    return _cumulative_scale(fin)


class TestCumulativeScale:
    def test_annual_is_one(self):
        assert _cumulative_scale({"report_date": "2025-12-31"}) == 1.0

    def test_q3_scales_to_annual(self):
        # 9 个月累计 → 12/9 = 4/3
        assert _cumulative_scale({"report_date": "2025-09-30"}) == pytest.approx(4 / 3)

    def test_q1_scales_four(self):
        assert _cumulative_scale({"report_date": "2025-03-31"}) == pytest.approx(4.0)

    def test_h1_scales_two(self):
        assert _cumulative_scale({"report_date": "2025-06-30"}) == pytest.approx(2.0)

    def test_missing_report_date_no_scale(self):
        assert _cumulative_scale({"eps": 2.0}) == 1.0

    def test_invalid_report_date_no_scale(self):
        assert _cumulative_scale({"report_date": "not-a-date"}) == 1.0


class TestQualityScorePeriodAgnostic:
    """同一业务、同一年度水平的公司，年报与三季报分数不应系统性偏差。"""

    def test_q3_vs_annual_roe_score_equal(self):
        """累计 ROE 17.1%（9 个月）≈ 年化 22.8%——与行业优秀值 20 比较后应相近。"""
        from strategies.factors.quality import quality_score

        q3_fin = {"report_date": "2025-09-30", "roe": 17.1, "eps": 1.5, "ocf_per_share": 2.0}
        annual_fin = {"report_date": "2025-12-31", "roe": 22.8, "eps": 2.0, "ocf_per_share": 2.0}
        # 其它字段一致 → 差值只来自 ROE 的累计口径
        s_q3 = quality_score(q3_fin, "默认")
        s_annual = quality_score(annual_fin, "默认")
        assert abs(s_q3 - s_annual) < 3.0, f"累计口径未缩放: Q3={s_q3}, 年报={s_annual}"

    def test_ocf_eps_ratio_unchanged(self):
        """比值项（cashflow/eps）同口径，不应被缩放影响。"""
        from strategies.factors.quality import quality_score

        # 两份财务只有 report_date 不同、比值相同 → 分数应相同
        a = quality_score({"report_date": "2025-09-30", "eps": 2.0, "ocf_per_share": 2.5}, "默认")
        b = quality_score({"report_date": "2025-12-31", "eps": 2.0, "ocf_per_share": 2.5}, "默认")
        assert a == pytest.approx(b)

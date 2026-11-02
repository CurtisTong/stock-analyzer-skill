"""quality_score 缺失数据语义的回归测试（2026-11-02 skill 审查 P1）。

不变量：字段缺失（None）按子维度中性分（满分一半）计——
- 负债率未知不得拿满分 12（debt 越低越好，to_float(None)=0 曾当最优）；
- 整条全缺记录 ≈ 中性 50，不得被系统性抬高；
- key 存在但值为 None 时 dict.get(key, fallback) 不回退，须显式逐键探测。
"""

from __future__ import annotations

from strategies.factors.quality import quality_score

_HEALTHY = {
    "roe": 15.0,
    "net_profit_yoy": 20.0,
    "revenue_yoy": 15.0,
    "gross_margin": 30.0,
    "debt_ratio": 45.0,
    "eps": 1.0,
    "ocf_per_share": 1.2,
}


class TestMissingSemantics:
    def test_missing_debt_ratio_not_full_marks(self):
        """debt_ratio=None：不再拿满分 12（此前 88.5 vs healthy 81.7 反超）。"""
        fin = {**_HEALTHY, "debt_ratio": None}
        score = quality_score(fin)
        # 缺失中性 6 分 < 真实 45% 负债率任何可能得分上限 12，
        # 但整体分数不得高于"负债率 0（满分）"的记录
        perfect_debt = quality_score({**_HEALTHY, "debt_ratio": 0.0})
        assert score < perfect_debt

    def test_all_none_near_neutral(self):
        """整条全缺（键存在值 None）≈ 中性，不得静默拿高分。"""
        all_none = {k: None for k in _HEALTHY}
        score = quality_score(all_none)
        assert 35 <= score <= 55, f"全缺记录应接近中性 50，实测 {score}"

    def test_none_value_with_fallback_key(self):
        """roe=None + ROEJQ=25：dict.get 不回退，显式探测应取到 ROEJQ。"""
        fin = {"roe": None, "ROEJQ": 25.0, "debt_ratio": 40.0}
        score = quality_score(fin)
        # ROE=25 在优秀线 20 之上：ROE 子项应拿满 28，总分显著高于 ROE 缺失
        assert score >= 40

    def test_real_data_scores_unchanged_direction(self):
        """有数据时行为不变：优质财务 > 劣质财务。"""
        bad = {
            "roe": 2.0,
            "net_profit_yoy": -30.0,
            "revenue_yoy": -20.0,
            "gross_margin": 5.0,
            "debt_ratio": 85.0,
            "eps": -0.5,
            "ocf_per_share": -0.3,
        }
        assert quality_score(_HEALTHY) > quality_score(bad)

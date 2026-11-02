"""dupont_analysis 杜邦分解的单元测试（此前零测试零调用方）。

覆盖：三因子数学、total_assets/net_assets 回退路径、数据完整性
warning、2pp 对账阈值行为（东财净利率基于营业收入、ROE 基于平均
净资产的口径差约 1-2pp，阈值取 2.0pp）。
"""

from __future__ import annotations

import pytest

from strategies.factors.dupont import RECONCILIATION_THRESHOLD_PP, dupont_analysis


class TestThreeFactorMath:
    def test_exact_reconstruction(self):
        """净利率 23.63% × 周转 0.533 次 × 乘数 1.862 ≈ 23.45%。"""
        fin = {
            "net_margin": 23.63,
            "total_revenue": 100.0,
            "total_assets": 187.6,
            "net_assets": 100.7,
            "roe": 23.45,
        }
        r = dupont_analysis(fin)
        assert r["asset_turnover"] == pytest.approx(0.533, abs=1e-3)
        assert r["equity_multiplier"] == pytest.approx(1.863, abs=1e-3)
        assert r["roe_reconstructed"] == pytest.approx(23.44, abs=0.05)
        assert r["reconciliation_ok"] is True
        assert r["warning"] == ""

    def test_reconciliation_fail_marks_warning(self):
        """重建 ROE 与原始偏差 > 2pp → warning 标注对账异常。"""
        fin = {
            "net_margin": 20.0,
            "total_revenue": 100.0,
            "total_assets": 100.0,
            "net_assets": 50.0,
            "roe": 40.0,  # 重建 = 20×1×2 = 40 → 巧合对账；改原始为 60
        }
        fin["roe"] = 60.0
        r = dupont_analysis(fin)
        assert r["reconciliation_ok"] is False
        assert "对账偏差" in r["warning"]
        assert r["reconciliation_error"] > RECONCILIATION_THRESHOLD_PP

    def test_threshold_is_2pp(self):
        assert RECONCILIATION_THRESHOLD_PP == 2.0


class TestFallbackPaths:
    def test_total_assets_from_liability_and_debt_ratio(self):
        """total_assets 缺失 → 负债/负债率 反推（负债 60 亿、负债率 60% → 100 亿）。"""
        fin = {
            "net_margin": 10.0,
            "total_revenue": 50.0,
            "total_liability": 60.0,
            "debt_ratio": 60.0,
            "roe": 20.0,
        }
        r = dupont_analysis(fin)
        assert r["total_assets"] == pytest.approx(100.0, abs=0.01)
        # net_assets 回退 = 总资产 - 负债 = 40 亿
        assert r["net_assets"] == pytest.approx(40.0, abs=0.01)
        # 重建 ROE = 10% × 0.5 × 2.5 = 12.5%
        assert r["roe_reconstructed"] == pytest.approx(12.5, abs=0.01)
        assert r["reconciliation_ok"] is False  # 与原始 20 差 7.5pp

    def test_explicit_net_assets_wins_over_fallback(self):
        """net_assets 已填充时不再用 总资产-负债 覆盖。"""
        fin = {
            "net_margin": 10.0,
            "total_revenue": 50.0,
            "total_assets": 100.0,
            "net_assets": 50.0,
            "total_liability": 30.0,
            "roe": 20.0,
        }
        r = dupont_analysis(fin)
        assert r["net_assets"] == 50.0


class TestDataCompleteness:
    def test_zero_revenue_warns(self):
        r = dupont_analysis({"net_margin": 10.0, "total_assets": 100.0, "net_assets": 50.0, "roe": 20.0})
        assert "营收为 0" in r["warning"]
        assert r["asset_turnover"] == 0.0

    def test_zero_assets_warns_twice(self):
        r = dupont_analysis({"net_margin": 10.0, "total_revenue": 50.0, "roe": 20.0})
        assert "总资产为 0" in r["warning"] and "净资产为 0" in r["warning"]
        assert r["roe_reconstructed"] == 0.0

    def test_empty_fin_degrades_without_crash(self):
        r = dupont_analysis({})
        assert r["roe_reconstructed"] == 0.0
        assert "营收为 0" in r["warning"]

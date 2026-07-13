"""杜邦三因子分解测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.factors.dupont import dupont_analysis


class TestDupontAnalysis:
    """dupont_analysis 三因子分解 + ROE 对账测试。"""

    def test_basic_decomposition(self):
        """宝丰能源 2025 年报数据：三因子正确分解。"""
        fin = {
            "net_margin": 23.63,
            "total_revenue": 480.38,
            "total_assets": 901.52,
            "net_assets": 483.90,
            "roe": 24.84,
        }
        result = dupont_analysis(fin)
        # 总资产周转率 = 480.38 / 901.52 ≈ 0.533（审查 #9 原报告错用 0.70）
        assert abs(result["asset_turnover"] - 0.5329) < 0.01
        # 权益乘数 = 901.52 / 483.90 ≈ 1.863
        assert abs(result["equity_multiplier"] - 1.863) < 0.01
        # 重建 ROE 应接近原始 ROE
        assert abs(result["roe_reconstructed"] - 23.46) < 0.5
        # 对账通过（偏差 < 2pp）
        assert result["reconciliation_ok"] is True

    def test_reconciliation_warning_when_mismatch(self):
        """重建 ROE 与原始 ROE 偏差超阈值时输出 warning。"""
        fin = {
            "net_margin": 30.0,  # 故意偏高，制造对账偏差
            "total_revenue": 480.38,
            "total_assets": 901.52,
            "net_assets": 483.90,
            "roe": 24.84,
        }
        result = dupont_analysis(fin)
        # 30.0 × 0.533 × 1.863 ≈ 29.8%，与 24.84% 偏差 > 2pp
        assert result["reconciliation_ok"] is False
        assert "对账偏差" in result["warning"]

    def test_fallback_total_assets_from_liability(self):
        """total_assets 为 0 时，用 负债/负债率 反推。"""
        fin = {
            "net_margin": 23.63,
            "total_revenue": 480.38,
            "total_liability": 417.62,
            "debt_ratio": 46.33,  # 417.62 / 901.52 × 100
            "net_assets": 483.90,
            "roe": 24.84,
            "total_assets": 0,  # 未填充，触发回退
        }
        result = dupont_analysis(fin)
        # 反推总资产 ≈ 417.62 / 0.4633 ≈ 901.5
        assert abs(result["total_assets"] - 901.5) < 2.0

    def test_fallback_net_assets_from_assets_minus_liability(self):
        """net_assets 为 0 时，用 总资产 - 负债 回退。"""
        fin = {
            "net_margin": 23.63,
            "total_revenue": 480.38,
            "total_assets": 901.52,
            "total_liability": 417.62,
            "roe": 24.84,
            "net_assets": 0,  # 未填充，触发回退
        }
        result = dupont_analysis(fin)
        assert abs(result["net_assets"] - 483.90) < 1.0

    def test_missing_revenue_warns(self):
        """营收为 0 时输出 warning。"""
        result = dupont_analysis({"net_margin": 20, "total_assets": 100, "net_assets": 60, "roe": 15})
        assert "营收为 0" in result["warning"]
        assert result["asset_turnover"] == 0.0

    def test_missing_assets_warns(self):
        """总资产和负债均为 0 时输出 warning。"""
        result = dupont_analysis({"net_margin": 20, "total_revenue": 100, "roe": 15})
        assert "总资产为 0" in result["warning"]

    def test_empty_input(self):
        """空输入不崩溃，返回全 0。"""
        result = dupont_analysis({})
        assert result["roe_reconstructed"] == 0.0
        assert result["reconciliation_ok"] is True  # 0 vs 0 无偏差

    def test_round_trip_consistency(self):
        """构造完美对账数据：净利率×周转率×乘数 恰好等于 ROE。"""
        # roe = 20 × 0.5 × 2.0 = 20%
        fin = {
            "net_margin": 20.0,
            "total_revenue": 500.0,
            "total_assets": 1000.0,
            "net_assets": 500.0,
            "roe": 20.0,
        }
        result = dupont_analysis(fin)
        assert abs(result["roe_reconstructed"] - 20.0) < 0.01
        assert result["reconciliation_error"] < 0.1
        assert result["warning"] == ""

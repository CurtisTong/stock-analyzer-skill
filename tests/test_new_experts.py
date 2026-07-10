"""
测试 v2.1.2 补盲区 scoring 函数：sector_specialist/institution/risk_manager。

每个函数的关键阈值：
- sector_specialist：行业 PE 分位 + 行业景气（ROE × 营收增速）
- institution：ROE 阶梯 + PEG 视角 + FCF 安全边际
- risk_manager：pe_percentile 周期位置 + 极端情绪反向
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts.scoring import (
    sector_specialist,
    institution,
    risk_manager,
)

# ═══════════════════════════════════════════════════════════════
# sector_specialist
# ═══════════════════════════════════════════════════════════════


class TestSectorSpecialist:
    """行业专家：行业景气 + PE 分位 + 竞争格局。"""

    def test_returns_dict(self):
        result = sector_specialist.score({"quote": {}, "finance": {}})
        assert isinstance(result, dict)
        assert "基本面" in result
        assert "估值" in result
        assert "风险" in result

    def test_in_range(self):
        result = sector_specialist.score({"quote": {}, "finance": {}})
        for v in result.values():
            assert 0 <= v <= 100

    def test_high_prosperity_high_score(self):
        """ROE≥20 + 营收增速≥15 = 行业景气高 = 基本面高分。
        v2.4.0 行业差异化阈值后，基本面 = roe_score×(1-rev_weight) + rev_score×rev_weight，
        default 类 rev_weight=0.3：80×0.7 + 95×0.3 = 84.5，故阈值调整为 ≥80。
        """
        result = sector_specialist.score(
            {
                "quote": {"pe": 20, "pe_percentile": 50},
                "finance": {"ROEJQ": 25, "TOTALOPERATEREVETZ": 20},
            }
        )
        assert result["基本面"] >= 80

    def test_low_prosperity_low_score(self):
        """ROE<10 = 行业衰退 = 基本面低分。"""
        result = sector_specialist.score(
            {
                "quote": {"pe": 20, "pe_percentile": 50},
                "finance": {"ROEJQ": 5, "TOTALOPERATEREVETZ": -5},
            }
        )
        assert result["基本面"] <= 30

    def test_low_pe_percentile_high_valuation(self):
        """PE 行业分位 ≤20% = 行业低估 = 估值高分。"""
        result = sector_specialist.score(
            {
                "quote": {"pe": 15, "pe_percentile": 10},
                "finance": {"ROEJQ": 15},
            }
        )
        assert result["估值"] >= 80

    def test_high_pe_percentile_low_valuation(self):
        """PE 行业分位 >80% = 行业高估 = 估值低分。
        v2.4.0 行业差异化阈值后，default 类 pe_pct_high=80，
        90% 落在 (80, 90] 区间得 35 分，故阈值调整为 ≤40。
        """
        result = sector_specialist.score(
            {
                "quote": {"pe": 50, "pe_percentile": 90},
                "finance": {"ROEJQ": 15},
            }
        )
        assert result["估值"] <= 40

    def test_competitive_moat_low_debt(self):
        """低负债 + 高 ROE = 龙头护城河 = 风险高分。"""
        result = sector_specialist.score(
            {
                "quote": {"pe_percentile": 50},
                "finance": {"ROEJQ": 20, "ZCFZL": 20},
            }
        )
        assert result["风险"] >= 80

    def test_high_debt_low_moat(self):
        """高负债 = 竞争劣势 = 风险低分。"""
        result = sector_specialist.score(
            {
                "quote": {"pe_percentile": 50},
                "finance": {"ROEJQ": 10, "ZCFZL": 80},
            }
        )
        assert result["风险"] <= 30


# ═══════════════════════════════════════════════════════════════
# institution
# ═══════════════════════════════════════════════════════════════


class TestInstitution:
    """机构派：ROE 阶梯 + PEG 视角 + FCF 安全边际。"""

    def test_returns_dict(self):
        result = institution.score({"quote": {}, "finance": {}})
        assert isinstance(result, dict)
        assert "基本面" in result
        assert "估值" in result
        assert "安全边际" in result

    def test_in_range(self):
        result = institution.score({"quote": {}, "finance": {}})
        for v in result.values():
            assert 0 <= v <= 100

    def test_high_roe_top_fundamental(self):
        """ROE≥25 = 顶级基本面。"""
        result = institution.score(
            {
                "quote": {"pe": 20},
                "finance": {"ROEJQ": 30, "PARENTNETPROFITTZ": 20, "XSMLL": 60},
            }
        )
        assert result["基本面"] >= 95

    def test_low_roe_rejected(self):
        """ROE<10 = 不达机构门槛。"""
        result = institution.score(
            {
                "quote": {"pe": 20},
                "finance": {"ROEJQ": 5},
            }
        )
        assert result["基本面"] <= 20

    def test_peg_below_one_high_valuation(self):
        """PEG<1 = 估值合理/低估。"""
        result = institution.score(
            {
                "quote": {"pe": 15},  # PE=15, growth=20 → PEG=0.75
                "finance": {"ROEJQ": 15, "PARENTNETPROFITTZ": 20},
            }
        )
        assert result["估值"] >= 70

    def test_peg_above_two_low_valuation(self):
        """PEG>2.5 = 估值泡沫。"""
        result = institution.score(
            {
                "quote": {"pe": 60},  # PE=60, growth=20 → PEG=3.0
                "finance": {"ROEJQ": 15, "PARENTNETPROFITTZ": 20},
            }
        )
        assert result["估值"] <= 25

    def test_negative_pe_low_valuation(self):
        """亏损股（PE<0）= 机构一般不投。"""
        result = institution.score(
            {
                "quote": {"pe": -5},
                "finance": {"ROEJQ": -10},
            }
        )
        assert result["估值"] <= 30

    def test_fcf_positive_low_debt_high_mos(self):
        """FCF>0 + 低负债 = 高安全边际。"""
        result = institution.score(
            {
                "quote": {"pe": 15},
                "finance": {"ROEJQ": 15, "ZCFZL": 20, "MGJYXJJE": 2},
            }
        )
        assert result["安全边际"] >= 80

    def test_tech_sentiment_data_driven(self):
        """技术面随趋势、情绪随机构持仓环比变化（不再恒中性）。"""
        # 缺数据：回退中性
        result = institution.score({"quote": {"pe": 50}, "finance": {"ROEJQ": 20}})
        assert result["技术面"] == 30  # 横盘
        assert result["情绪"] == 50  # 缺机构持仓环比
        # 上升趋势 -> 技术面 60
        result = institution.score(
            {
                "quote": {"pe": 50},
                "finance": {"ROEJQ": 20},
                "kline_features": {"trend": 1},
            }
        )
        assert result["技术面"] == 60
        # 机构加仓 -> 情绪 100
        result = institution.score(
            {"quote": {"pe": 50, "inst_holding_change": 6}, "finance": {"ROEJQ": 20}}
        )
        assert result["情绪"] == 100


# ═══════════════════════════════════════════════════════════════
# risk_manager
# ═══════════════════════════════════════════════════════════════


class TestRiskManager:
    """风险管理：周期位置 + 风险预算 + 极端情绪反向。"""

    def test_returns_dict(self):
        result = risk_manager.score({"quote": {}, "finance": {}})
        assert isinstance(result, dict)
        assert "风险" in result
        assert "估值" in result
        assert "情绪" in result

    def test_in_range(self):
        result = risk_manager.score({"quote": {}, "finance": {}})
        for v in result.values():
            assert 0 <= v <= 100

    def test_extreme_pe_percentile_top_warning(self):
        """PE 分位 ≥90% = 周期顶部警示。"""
        result = risk_manager.score(
            {
                "quote": {"pe_percentile": 95},
                "finance": {"ZCFZL": 30},
            }
        )
        assert result["估值"] <= 15  # 极端高估警示

    def test_low_pe_percentile_low_risk(self):
        """PE 分位 <20% = 低风险。"""
        result = risk_manager.score(
            {
                "quote": {"pe_percentile": 10},
                "finance": {"ZCFZL": 30},
            }
        )
        assert result["估值"] >= 75  # 低估=低风险

    def test_double_high_risk_critical(self):
        """高负债 + 高 PE 分位 = 双重风险。"""
        result = risk_manager.score(
            {
                "quote": {"pe_percentile": 80},
                "finance": {"ZCFZL": 80},
            }
        )
        assert result["风险"] <= 20  # 极端高风险

    def test_low_debt_low_pe_safe(self):
        """低负债 + 低 PE 分位 = 低风险。"""
        result = risk_manager.score(
            {
                "quote": {"pe_percentile": 30},
                "finance": {"ZCFZL": 20},
            }
        )
        assert result["风险"] >= 80

    def test_extreme_greed_warning(self):
        """情绪 ≥80 = 极端贪婪警示。"""
        result = risk_manager.score(
            {
                "quote": {},
                "finance": {},
                "market_features": {
                    "limit_up_count": 100,
                    "limit_down_count": 5,
                    "advance_ratio": 0.85,
                    "nh_nl_ratio": 2.0,
                },
            }
        )
        assert result["情绪"] <= 40

    def test_extreme_fear_opportunity(self):
        """情绪 <20 = 极端恐慌 = 逆向机会（高分，非警示）。"""
        result = risk_manager.score(
            {
                "quote": {},
                "finance": {},
                "market_features": {
                    "limit_up_count": 5,
                    "limit_down_count": 80,
                    "advance_ratio": 0.15,
                    "nh_nl_ratio": 0.2,
                },
            }
        )
        assert result["情绪"] >= 90  # 恐慌=机会（Howard Marks 逆向）

    def test_neutral_market(self):
        """中性市场情绪 = 中等分。"""
        result = risk_manager.score(
            {
                "quote": {},
                "finance": {},
                "market_features": {
                    "limit_up_count": 40,
                    "limit_down_count": 30,
                    "advance_ratio": 0.5,
                    "nh_nl_ratio": 1.0,
                },
            }
        )
        assert 35 <= result["情绪"] <= 65

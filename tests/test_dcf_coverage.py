"""DCF 估值模型覆盖测试（mock industry_beta / macro_indicators）。

覆盖 CAPM WACC 计算（成功/失败/约束区间）、行业字典 fallback、
用户传入折现率分支、各行业 capex_ratio、增长率自动推断与约束、
EV/EBITDA 多分支、评分函数分级。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import strategies.factors.dcf as dcf


# ═══════════════════════════════════════════════════════════════
# _compute_capm_wacc
# ═══════════════════════════════════════════════════════════════


class TestComputeCapmWacc:
    def test_success_normal_beta(self):
        """正常 beta + 宏观利率 -> CAPM WACC。"""
        with patch("industry_beta.compute_beta", return_value={"beta": 1.2}), patch(
            "macro_indicators.fetch_treasury_10y", return_value={"value": 2.5}
        ), patch("macro_indicators.fetch_erp_sh300", return_value={"value": 5.5}):
            result = dcf._compute_capm_wacc("sh600519")
        assert result is not None
        wacc, label = result
        # 0.025 + 1.2 * 0.055 = 0.091
        assert wacc == 0.091
        assert "CAPM" in label

    def test_beta_none_returns_none(self):
        """beta 为 None 时返回 None。"""
        with patch("industry_beta.compute_beta", return_value=None), patch(
            "macro_indicators.fetch_treasury_10y", return_value={"value": 2.5}
        ), patch("macro_indicators.fetch_erp_sh300", return_value={"value": 5.5}):
            assert dcf._compute_capm_wacc("sh600519") is None

    def test_beta_none_value_returns_none(self):
        """beta_result 存在但 beta 字段为 None。"""
        with patch("industry_beta.compute_beta", return_value={"beta": None}), patch(
            "macro_indicators.fetch_treasury_10y", return_value={"value": 2.5}
        ), patch("macro_indicators.fetch_erp_sh300", return_value={"value": 5.5}):
            assert dcf._compute_capm_wacc("sh600519") is None

    def test_wacc_clamped_to_min(self):
        """极低 beta -> WACC 被约束到下限 0.06。"""
        with patch("industry_beta.compute_beta", return_value={"beta": 0.1}), patch(
            "macro_indicators.fetch_treasury_10y", return_value={"value": 1.0}
        ), patch("macro_indicators.fetch_erp_sh300", return_value={"value": 1.0}):
            result = dcf._compute_capm_wacc("sh600519")
        assert result is not None
        assert result[0] == dcf._WACC_MIN

    def test_wacc_clamped_to_max(self):
        """极高 beta -> WACC 被约束到上限 0.20。"""
        with patch("industry_beta.compute_beta", return_value={"beta": 5.0}), patch(
            "macro_indicators.fetch_treasury_10y", return_value={"value": 5.0}
        ), patch("macro_indicators.fetch_erp_sh300", return_value={"value": 10.0}):
            result = dcf._compute_capm_wacc("sh600519")
        assert result is not None
        assert result[0] == dcf._WACC_MAX

    def test_treasury_none_uses_fallback(self):
        """treasury 为 None 时用 fallback 2.5%。"""
        with patch("industry_beta.compute_beta", return_value={"beta": 1.0}), patch(
            "macro_indicators.fetch_treasury_10y", return_value=None
        ), patch("macro_indicators.fetch_erp_sh300", return_value={"value": 5.5}):
            result = dcf._compute_capm_wacc("sh600519")
        assert result is not None
        # 0.025 + 1.0 * 0.055 = 0.08
        assert result[0] == 0.08

    def test_erp_none_uses_fallback(self):
        """ERP 为 None 时用 fallback 5.5%。"""
        with patch("industry_beta.compute_beta", return_value={"beta": 1.0}), patch(
            "macro_indicators.fetch_treasury_10y", return_value={"value": 2.5}
        ), patch("macro_indicators.fetch_erp_sh300", return_value=None):
            result = dcf._compute_capm_wacc("sh600519")
        assert result is not None
        assert result[0] == 0.08

    def test_exception_returns_none(self):
        """compute_beta 抛异常时返回 None。"""
        with patch("industry_beta.compute_beta", side_effect=RuntimeError("boom")):
            assert dcf._compute_capm_wacc("sh600519") is None


# ═══════════════════════════════════════════════════════════════
# _fallback_industry_discount
# ═══════════════════════════════════════════════════════════════


class TestFallbackIndustryDiscount:
    def test_known_industry(self):
        rate, label = dcf._fallback_industry_discount("科技")
        assert rate == 0.12
        assert "科技" in label

    def test_unknown_industry_uses_default(self):
        rate, label = dcf._fallback_industry_discount("未知行业")
        assert rate == 0.10  # 默认
        assert "未知行业" in label


# ═══════════════════════════════════════════════════════════════
# dcf_valuation - 折现率三级优先级
# ═══════════════════════════════════════════════════════════════


class TestDcfDiscountRatePriority:
    def test_user_supplied_rate(self):
        """用户显式传入 discount_rate（!= 0.10）-> '用户传入'。"""
        fin = {"eps": 5.0}
        result = dcf.dcf_valuation(100, fin, discount_rate=0.15)
        assert result["wacc_source"] == "用户传入"
        assert result["discount_rate"] == 15.0

    def test_capm_success(self):
        """传 stock_code 且 CAPM 成功 -> 'CAPM'。"""
        with patch("industry_beta.compute_beta", return_value={"beta": 1.2}), patch(
            "macro_indicators.fetch_treasury_10y", return_value={"value": 2.5}
        ), patch("macro_indicators.fetch_erp_sh300", return_value={"value": 5.5}):
            result = dcf.dcf_valuation(100, {"eps": 5.0}, stock_code="sh600519")
        assert "CAPM" in result["wacc_source"]

    def test_capm_fail_fallback_industry(self):
        """传 stock_code 但 CAPM 失败 -> 行业字典 fallback。"""
        with patch("industry_beta.compute_beta", return_value=None):
            result = dcf.dcf_valuation(100, {"eps": 5.0}, stock_code="sh600519", industry="科技")
        assert result["wacc_source"].startswith("行业字典")
        assert result["discount_rate"] == 12.0

    def test_no_stock_code_industry_dict(self):
        """未传 stock_code -> 直接用行业字典。"""
        result = dcf.dcf_valuation(100, {"eps": 5.0}, industry="医药")
        assert result["wacc_source"].startswith("行业字典")
        assert result["discount_rate"] == 10.0


# ═══════════════════════════════════════════════════════════════
# dcf_valuation - 增长率 / capex_ratio / 错误分支
# ═══════════════════════════════════════════════════════════════


class TestDcfValuationBranches:
    def test_growth_inferred_from_profit_yoy(self):
        """growth_rate=None 时用净利同比增速（上限 30%）。"""
        fin = {"eps": 5.0, "net_profit_yoy": 50.0}  # 50% -> capped to 30%
        result = dcf.dcf_valuation(100, fin)
        assert result["growth_rate"] == 30.0

    def test_growth_default_when_negative_yoy(self):
        """净利同比为负 -> 默认 5%。"""
        fin = {"eps": 5.0, "net_profit_yoy": -10.0}
        result = dcf.dcf_valuation(100, fin)
        assert result["growth_rate"] == 5.0

    def test_no_data_returns_error(self):
        """无 ocf 也无 eps -> error。"""
        result = dcf.dcf_valuation(100, {})
        assert result.get("error") == "无可用现金流数据"
        assert result["margin_of_safety"] == -100

    def test_industry_capex_ratio_heavy(self):
        """重资产行业 capex_ratio=0.5。"""
        fin = {"ocf_per_share": 10.0}
        result = dcf.dcf_valuation(100, fin, industry="重资产")
        assert result["fcf_per_share"] == 5.0  # 10 * 0.5

    def test_industry_capex_ratio_finance(self):
        """金融行业 capex_ratio=0.85。"""
        fin = {"ocf_per_share": 10.0}
        result = dcf.dcf_valuation(100, fin, industry="金融")
        assert result["fcf_per_share"] == 8.5  # 10 * 0.85

    def test_eps_fallback_when_no_ocf(self):
        """无 ocf 但有 eps -> 用 eps * capex_ratio。"""
        result = dcf.dcf_valuation(100, {"eps": 4.0})
        assert result["fcf_per_share"] == 2.8  # 4.0 * 0.7(默认)

    def test_price_zero_margin_zero(self):
        """price=0 -> margin_of_safety=0。"""
        result = dcf.dcf_valuation(0, {"eps": 5.0})
        assert result["margin_of_safety"] == 0


# ═══════════════════════════════════════════════════════════════
# dcf_score
# ═══════════════════════════════════════════════════════════════


class TestDcfScore:
    def test_error_returns_neutral(self):
        assert dcf.dcf_score(100, {}) == 50

    def test_high_margin_returns_90(self):
        """安全边际 > 50% -> 90 分。"""
        # 低 price 高内在价值
        with patch.object(dcf, "dcf_valuation", return_value={"margin_of_safety": 60}):
            assert dcf.dcf_score(10, {"eps": 100}) == 90

    def test_negative_margin_returns_20(self):
        """安全边际 < -20% -> 20 分。"""
        with patch.object(dcf, "dcf_valuation", return_value={"margin_of_safety": -30}):
            assert dcf.dcf_score(100, {"eps": 1}) == 20


# ═══════════════════════════════════════════════════════════════
# ev_ebitda_valuation
# ═══════════════════════════════════════════════════════════════


class TestEvEbitdaValuation:
    def test_operating_profit_path(self):
        """有营业利润 -> EBITDA = operating_profit * 1.3。"""
        fin = {"operating_profit": 100}
        quote = {"total_cap": 1300}
        result = dcf.ev_ebitda_valuation(50, fin, quote)
        assert result["ev_ebitda"] == 10.0  # 1300 / (100*1.3)
        assert result["ebitda"] == 130.0

    def test_eps_fallback_path(self):
        """无营业利润 -> 用 EPS * shares * 1.3。"""
        fin = {"eps": 5.0}
        quote = {"total_cap": 100}  # 100 亿
        result = dcf.ev_ebitda_valuation(50, fin, quote)
        # shares = 100e8 / 50 = 2e8; ebitda = 5 * 2e8 * 1.3 / 1e8 = 13
        assert result["ebitda"] == 13.0
        assert result["ev_ebitda"] == round(100 / 13.0, 2)

    def test_no_data_returns_error(self):
        """无营业利润也无 eps -> error。"""
        result = dcf.ev_ebitda_valuation(50, {}, {})
        assert result.get("error") == "无可用 EBITDA 数据"

    def test_no_quote_uses_zero_ev(self):
        """无 quote 时 ev=0，ev_ebitda=0。"""
        result = dcf.ev_ebitda_valuation(50, {"operating_profit": 100}, None)
        assert result["ev"] == 0
        assert result["ev_ebitda"] == 0.0

    def test_eps_fallback_no_total_cap(self):
        """无营业利润且无 total_cap -> error。"""
        result = dcf.ev_ebitda_valuation(50, {"eps": 5.0}, {"total_cap": 0})
        assert result.get("error") == "无可用 EBITDA 数据"


# ═══════════════════════════════════════════════════════════════
# ev_ebitda_score
# ═══════════════════════════════════════════════════════════════


class TestEvEbitdaScore:
    def test_error_returns_neutral(self):
        assert dcf.ev_ebitda_score(50, {}, {}) == 50

    def test_low_ratio_undervalued(self):
        """EV/EBITDA < low 阈值 -> 70 分。"""
        with patch.object(dcf, "ev_ebitda_valuation", return_value={"ev_ebitda": 5}):
            assert dcf.ev_ebitda_score(50, {"eps": 1}, {}) == 70

    def test_high_ratio_overvalued(self):
        """EV/EBITDA >= high 阈值 -> 20 分。"""
        with patch.object(dcf, "ev_ebitda_valuation", return_value={"ev_ebitda": 25}):
            assert dcf.ev_ebitda_score(50, {"eps": 1}, {}) == 20

    def test_zero_ratio_returns_neutral(self):
        """EV/EBITDA <= 0 -> 50 分。"""
        with patch.object(dcf, "ev_ebitda_valuation", return_value={"ev_ebitda": 0}):
            assert dcf.ev_ebitda_score(50, {"eps": 1}, {}) == 50

"""
FinanceRecord 字段映射测试（review#9+10）。
验证 _dict_to_finance 对东财原始字段名/标准化字段名的归一化能力。

WP1 (2026-07-21): 删除 7 个死字段后，本文件不再断言 dividend_yield 等。
仍保留 ESG/分红/治理 Tier 3 字段（consecutive_dividend_years / major_shareholder_reduction /
violation_penalty / audit_opinion）的映射测试，因 strategies/factors 仍在读取（读到的永远是 0）。
"""

import pytest


from data import _dict_to_finance  # noqa: E402


class TestDictToFinanceMapping:
    """_dict_to_finance 字段映射测试。"""

    def test_standardized_fields(self):
        """标准字段名直接透传。"""
        d = {
            "report_date": "2024-12-31",
            "eps": 5.5,
            "roe": 18.5,
            "revenue_yoy": 12.3,
            "net_profit_yoy": 20.1,
            "gross_margin": 45.0,
            "net_margin": 22.0,
            "debt_ratio": 35.0,
            "bps": 12.0,
            "ocf_per_share": 6.0,
        }
        r = _dict_to_finance(d)
        assert r.eps == 5.5
        assert r.roe == 18.5
        assert r.report_date == "2024-12-31"

    def test_eastmoney_raw_fields(self):
        """东财原始字段名通过映射归一化。"""
        d = {
            "REPORT_DATE": "2024-12-31",
            "EPSJB": "5.5",
            "ROEJQ": "18.5",
            "TOTALOPERATEREVETZ": "12.3",
            "PARENTNETPROFITTZ": "20.1",
            "XSMLL": "45.0",
            "XSJLL": "22.0",
            "ZCFZL": "35.0",
            "BPS": "12.0",
            "MGJYXJJE": "6.0",
        }
        r = _dict_to_finance(d)
        assert r.eps == 5.5
        assert r.roe == 18.5
        assert r.revenue_yoy == 12.3

    def test_esg_dividend_fields_default_zero(self):
        """ESG/分红字段缺省时为 0，不应报错（Tier 3 字段保留）。

        WP1 后 dividend_yield / fcf / ocf / gross_margin_qoq 等 Tier 2 字段
        已从 FinanceRecord 删除，本测试仅验证保留字段的 0 默认行为。
        """
        d = {"eps": 1.0, "roe": 10.0}
        r = _dict_to_finance(d)
        assert r.consecutive_dividend_years == 0
        assert r.major_shareholder_reduction == 0.0
        assert r.violation_penalty == 0.0
        assert r.audit_opinion == ""

    def test_esg_dividend_fields_populated(self):
        """Tier 3 字段在 fetcher 填充时被正确读取。"""
        d = {
            "eps": 1.0,
            "roe": 10.0,
            "CONSECUTIVE_DIVIDEND_YEARS": "8",  # 连续 8 年分红
            "MAJOR_SHAREHOLDER_REDUCTION": "2.5",  # 大股东减持 2.5%
            "VIOLATION_PENALTY": "1000000",  # 违规处罚 100 万
            "AUDIT_OPINION": "标准无保留意见",
        }
        r = _dict_to_finance(d)
        assert r.consecutive_dividend_years == 8
        assert r.major_shareholder_reduction == 2.5
        assert r.violation_penalty == 1000000
        assert r.audit_opinion == "标准无保留意见"

    def test_alternative_field_names(self):
        """支持中文字段名 fallback。"""
        d = {
            "eps": 1.0,
            "roe": 10.0,
            "连续分红年数": "5",
            "审计意见类型": "保留意见",
        }
        r = _dict_to_finance(d)
        assert r.consecutive_dividend_years == 5
        assert r.audit_opinion == "保留意见"

    def test_dash_and_empty_string_skipped(self):
        """'-' 和空字符串视为缺省（Tier 3 字段）。"""
        d = {
            "eps": 1.0,
            "CONSECUTIVE_DIVIDEND_YEARS": "",
            "AUDIT_OPINION": None,
        }
        r = _dict_to_finance(d)
        assert r.consecutive_dividend_years == 0
        assert r.audit_opinion == ""

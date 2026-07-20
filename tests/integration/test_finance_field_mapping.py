"""
FinanceRecord 字段映射测试（review#9+10）。
验证 _dict_to_finance 对东财原始字段名/标准化字段名的归一化能力。
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
        """ESG/分红字段缺省时为 0，不应报错。"""
        d = {"eps": 1.0, "roe": 10.0}
        r = _dict_to_finance(d)
        assert r.dividend_yield == 0.0
        assert r.consecutive_dividend_years == 0
        assert r.major_shareholder_reduction == 0.0
        assert r.violation_penalty == 0.0
        assert r.audit_opinion == ""

    def test_esg_dividend_fields_populated(self):
        """ESG/分红字段在 fetcher 填充时被正确读取。"""
        d = {
            "eps": 1.0,
            "roe": 10.0,
            "DIVIDENT_YIELD": "3.5",  # 股息率 3.5%
            "CONSECUTIVE_DIVIDEND_YEARS": "8",  # 连续 8 年分红
            "MAJOR_SHAREHOLDER_REDUCTION": "2.5",  # 大股东减持 2.5%
            "VIOLATION_PENALTY": "1000000",  # 违规处罚 100 万
            "AUDIT_OPINION": "标准无保留意见",
        }
        r = _dict_to_finance(d)
        assert r.dividend_yield == 3.5
        assert r.consecutive_dividend_years == 8
        assert r.major_shareholder_reduction == 2.5
        assert r.violation_penalty == 1000000
        assert r.audit_opinion == "标准无保留意见"

    def test_alternative_field_names(self):
        """支持中文字段名 fallback。"""
        d = {
            "eps": 1.0,
            "roe": 10.0,
            "股息率": "2.5",
            "连续分红年数": "5",
            "审计意见类型": "保留意见",
        }
        r = _dict_to_finance(d)
        assert r.dividend_yield == 2.5
        assert r.consecutive_dividend_years == 5
        assert r.audit_opinion == "保留意见"

    def test_dash_and_empty_string_skipped(self):
        """'-' 和空字符串视为缺省。"""
        d = {
            "eps": 1.0,
            "DIVIDENT_YIELD": "-",
            "CONSECUTIVE_DIVIDEND_YEARS": "",
            "AUDIT_OPINION": None,
        }
        r = _dict_to_finance(d)
        assert r.dividend_yield == 0.0
        assert r.consecutive_dividend_years == 0
        assert r.audit_opinion == ""

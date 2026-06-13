"""
财务字段映射测试：验证 akshare/efinance 中文字段名能正确映射到 FinanceRecord。
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from data import _dict_to_finance
from data.types import FinanceRecord


class TestDictToFinanceEastmoney:
    """东财原始字段名映射（原有功能）。"""

    def test_eastmoney_fields(self, sample_finance):
        rec = _dict_to_finance(sample_finance)
        assert rec.eps == 50.00
        assert rec.roe == 30.5
        assert rec.revenue_yoy == 15.2
        assert rec.net_profit_yoy == 18.3
        assert rec.gross_margin == 91.5
        assert rec.net_margin == 52.3
        assert rec.debt_ratio == 18.7
        assert rec.bps == 180.00
        assert rec.ocf_per_share == 55.00


class TestDictToFinanceAkshare:
    """akshare 中文字段名映射。"""

    def test_akshare_fields(self, sample_finance_akshare):
        rec = _dict_to_finance(sample_finance_akshare)
        assert rec.eps == 50.00
        assert rec.roe == 30.5
        assert rec.revenue_yoy == 15.2
        assert rec.net_profit_yoy == 18.3
        assert rec.gross_margin == 91.5
        assert rec.net_margin == 52.3
        assert rec.debt_ratio == 18.7
        assert rec.bps == 180.00
        assert rec.ocf_per_share == 55.00

    def test_akshare_report_date(self, sample_finance_akshare):
        rec = _dict_to_finance(sample_finance_akshare)
        assert rec.report_date == "2025-03-31"

    def test_akshare_alternative_field_names(self):
        """测试 akshare 可能的其他字段名变体。"""
        data = {
            "每股收益": "1.23",
            "加权净资产收益率": "15.5",
            "营业总收入同比增长率": "20.0",
            "归母净利润同比增长率": "25.0",
        }
        rec = _dict_to_finance(data)
        assert rec.eps == 1.23
        assert rec.roe == 15.5
        assert rec.revenue_yoy == 20.0
        assert rec.net_profit_yoy == 25.0


class TestDictToFinanceEfinance:
    """efinance 中文字段名映射。"""

    def test_efinance_fields(self, sample_finance_efinance):
        rec = _dict_to_finance(sample_finance_efinance)
        assert rec.eps == 50.00
        assert rec.roe == 30.5
        assert rec.revenue_yoy == 15.2
        assert rec.net_profit_yoy == 18.3
        assert rec.gross_margin == 91.5
        assert rec.net_margin == 52.3
        assert rec.debt_ratio == 18.7
        assert rec.bps == 180.00
        assert rec.ocf_per_share == 55.00

    def test_efinance_roe_variant(self):
        """测试 efinance ROE 字段名变体。"""
        data = {"ROE": "22.5", "每股收益": "3.14"}
        rec = _dict_to_finance(data)
        assert rec.roe == 22.5
        assert rec.eps == 3.14


class TestDictToFinanceEdgeCases:
    """边界情况测试。"""

    def test_empty_dict(self):
        """空 dict 应返回全零 FinanceRecord。"""
        rec = _dict_to_finance({})
        assert isinstance(rec, FinanceRecord)
        assert rec.eps == 0.0
        assert rec.roe == 0.0

    def test_none_values_skipped(self):
        """None 值应被跳过，使用候选字段。"""
        data = {"EPSJB": None, "基本每股收益": "2.50"}
        rec = _dict_to_finance(data)
        assert rec.eps == 2.50

    def test_empty_string_skipped(self):
        """空字符串应被跳过。"""
        data = {"EPSJB": "", "每股收益": "3.00"}
        rec = _dict_to_finance(data)
        assert rec.eps == 3.00

    def test_dash_skipped(self):
        """'-' 值应被跳过。"""
        data = {"ROEJQ": "-", "ROE": "18.0"}
        rec = _dict_to_finance(data)
        assert rec.roe == 18.0

    def test_mixed_field_sources(self):
        """混合不同数据源字段名。"""
        data = {
            "EPSJB": "1.00",  # 东财
            "净资产收益率": "20.0",  # akshare
            "毛利率": "60.0",  # efinance
        }
        rec = _dict_to_finance(data)
        assert rec.eps == 1.00
        assert rec.roe == 20.0
        assert rec.gross_margin == 60.0

    def test_priority_eastmoney_first(self):
        """东财字段名优先级更高（排在候选列表前面）。"""
        data = {"EPSJB": "1.00", "基本每股收益": "2.00", "每股收益": "3.00"}
        rec = _dict_to_finance(data)
        # EPSJB 排在最前面，应优先使用
        assert rec.eps == 1.00


class TestFinanceCompletenessCheck:
    """完整性校验测试（get_finance 中的 eps/roe 全零检查）。"""

    def test_all_zero_triggers_parse_error(self):
        """所有记录 eps==0 且 roe==0 应触发 ParseError。"""
        from common.exceptions import ParseError
        import data as data_mod
        from unittest.mock import MagicMock

        # Mock fetcher manager 返回全零数据
        zero_data = [
            {"基本每股收益": "0", "ROE": "0"},
            {"基本每股收益": "0", "ROE": "0"},
        ]

        mock_mgr = MagicMock()
        mock_mgr.fetch.return_value = zero_data
        original_mgr = data_mod._finance_manager
        original_loaded = data_mod._fetchers_loaded
        try:
            data_mod._finance_manager = mock_mgr
            data_mod._fetchers_loaded = True
            with pytest.raises(ParseError):
                data_mod.get_finance("test_code", use_cache=False)
        finally:
            data_mod._finance_manager = original_mgr
            data_mod._fetchers_loaded = original_loaded

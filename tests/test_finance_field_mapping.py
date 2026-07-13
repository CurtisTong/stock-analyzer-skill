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

    def test_goodwill_pledge_mapping(self):
        """商誉/质押比例字段应正确映射（之前遗漏导致恒为 0）。"""
        data = {
            "GOODWILL": "500000000",
            "PLEDGE_RATIO": "35.5",
            "GOODWILL_RATIO": "12.3",
        }
        rec = _dict_to_finance(data)
        assert rec.goodwill == 500000000.0
        assert rec.pledge_ratio == 35.5
        assert rec.goodwill_ratio == 12.3

    def test_goodwill_chinese_name_mapping(self):
        """商誉中文字段名也应映射。"""
        data = {"商誉": "300000000", "质押比例": "20.0"}
        rec = _dict_to_finance(data)
        assert rec.goodwill == 300000000.0
        assert rec.pledge_ratio == 20.0


class TestDictToFinanceAbsoluteValues:
    """绝对值字段映射 + 单位转换（审查 #1,2,7,8,12,13,15,19,20）。"""

    def test_revenue_absolute_value_yuan_to_yi(self):
        """营收绝对值：东财返回"元"，应 /1e8 转亿元。"""
        data = {"TOTALOPERATEREVE": "48037593136.78"}  # 480.38 亿
        rec = _dict_to_finance(data)
        assert abs(rec.total_revenue - 480.38) < 0.01

    def test_parent_net_profit_absolute_value(self):
        """归母净利润绝对值转亿元。"""
        data = {"PARENTNETPROFIT": "11350295509.65"}  # 113.50 亿
        rec = _dict_to_finance(data)
        assert abs(rec.parent_net_profit - 113.50) < 0.01

    def test_deducted_net_profit_absolute_value(self):
        """扣非净利润绝对值转亿元。"""
        data = {"KCFJCXSYJLR": "11519983716.43"}  # 115.20 亿
        rec = _dict_to_finance(data)
        assert abs(rec.deducted_net_profit - 115.20) < 0.01

    def test_total_liability_absolute_value(self):
        """负债总额绝对值转亿元。"""
        data = {"LIABILITY": "41762569552.36"}  # 417.63 亿
        rec = _dict_to_finance(data)
        assert abs(rec.total_liability - 417.63) < 0.01

    def test_fcf_absolute_value(self):
        """自由现金流绝对值转亿元。"""
        data = {"FCFF_FORWARD": "1304771372.42"}  # 13.05 亿
        rec = _dict_to_finance(data)
        assert abs(rec.fcf - 13.05) < 0.01


class TestDictToFinanceCalculatedFields:
    """计算字段：总资产/净资产反推（审查 #7,8）。"""

    def test_total_assets_from_liability_and_debt_ratio(self):
        """总资产 = 负债 / (负债率/100)。"""
        data = {
            "LIABILITY": "41762569552.36",  # 417.63 亿
            "ZCFZL": "46.33",  # 负债率 46.33%
        }
        rec = _dict_to_finance(data)
        # 417.63 / 0.4633 ≈ 901.5
        assert abs(rec.total_assets - 901.5) < 2.0

    def test_net_assets_from_assets_minus_liability(self):
        """净资产 = 总资产 - 负债。"""
        data = {
            "LIABILITY": "41762569552.36",
            "ZCFZL": "46.33",
        }
        rec = _dict_to_finance(data)
        # 901.5 - 417.63 ≈ 483.9
        assert abs(rec.net_assets - 483.9) < 2.0

    def test_no_liability_no_calculated_assets(self):
        """无负债数据时，总资产/净资产为 0。"""
        data = {"EPSJB": "1.0"}
        rec = _dict_to_finance(data)
        assert rec.total_assets == 0.0
        assert rec.net_assets == 0.0


class TestDictToFinanceRatiosAndQoQ:
    """偿债比率 + 季度环比字段（审查 #13,15）。"""

    def test_current_ratio_mapping(self):
        """流动比率 LD 字段映射。"""
        data = {"LD": "0.520272753675"}
        rec = _dict_to_finance(data)
        assert abs(rec.current_ratio - 0.52) < 0.01

    def test_quick_ratio_mapping(self):
        """速动比率 SD 字段映射。"""
        data = {"SD": "0.402057372501"}
        rec = _dict_to_finance(data)
        assert abs(rec.quick_ratio - 0.40) < 0.01

    def test_deducted_np_yoy_mapping(self):
        """扣非净利同比映射。"""
        data = {"KCFJCXSYJLRTZ": "30.9164239908"}
        rec = _dict_to_finance(data)
        assert abs(rec.deducted_np_yoy - 30.92) < 0.01

    def test_revenue_qoq_mapping(self):
        """营收季度环比映射。"""
        data = {"DJD_TOI_QOQ": "5.955975799133"}
        rec = _dict_to_finance(data)
        assert abs(rec.revenue_qoq - 5.96) < 0.01

    def test_profit_qoq_mapping(self):
        """净利季度环比映射。"""
        data = {"DJD_DPNP_QOQ": "52.502154334656"}
        rec = _dict_to_finance(data)
        assert abs(rec.profit_qoq - 52.50) < 0.01

    def test_gross_margin_qoq_mapping(self):
        """毛利率环比变动映射。"""
        data = {"XSMLL_TB": "5.772626239555"}
        rec = _dict_to_finance(data)
        assert abs(rec.gross_margin_qoq - 5.77) < 0.01

    def test_ratios_rounded_to_2_decimals(self):
        """比率字段保留 2 位小数。"""
        data = {"LD": "0.520272753675", "SD": "0.402057372501"}
        rec = _dict_to_finance(data)
        # round(0.520272..., 2) = 0.52
        assert rec.current_ratio == 0.52
        assert rec.quick_ratio == 0.4


class TestFinanceCompletenessCheck:
    """完整性校验测试（get_finance 中的 eps/roe 全零检查）。"""

    def test_all_zero_returns_records(self):
        """所有记录 eps==0 且 roe==0 应返回记录（新股无数据场景）而非抛异常。"""
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
            records = data_mod.get_finance("test_code", use_cache=False)
            assert len(records) == 2
            assert all(r.eps == 0 and r.roe == 0 for r in records)
        finally:
            data_mod._finance_manager = original_mgr
            data_mod._fetchers_loaded = original_loaded

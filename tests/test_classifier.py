"""
classifier.py 单元测试：覆盖 7 种个股类型分类逻辑。
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from classifier import classify_stock, TYPE_INDICATOR_MAP


class TestClassifyStock:
    """个股类型分类测试。"""

    def test_returns_required_fields(self, sample_quote, sample_finance, kline_uptrend):
        result = classify_stock(sample_finance, sample_quote, kline_uptrend)
        assert "type" in result
        assert "confidence" in result
        assert "reasons" in result
        assert "priority_indicators" in result
        assert "deprioritized" in result

    def test_valid_type(self, sample_quote, sample_finance, kline_uptrend):
        result = classify_stock(sample_finance, sample_quote, kline_uptrend)
        valid_types = {"题材股", "蓝筹股", "强成长股", "周期股", "稳成长股", "防御股", "普通股"}
        assert result["type"] in valid_types

    def test_valid_confidence(self, sample_quote, sample_finance, kline_uptrend):
        result = classify_stock(sample_finance, sample_quote, kline_uptrend)
        assert result["confidence"] in ("高", "中", "低")

    def test_reasons_is_list(self, sample_quote, sample_finance, kline_uptrend):
        result = classify_stock(sample_finance, sample_quote, kline_uptrend)
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) > 0


class TestThemeStock:
    """题材股分类。"""

    def test_small_cap_high_turnover(self):
        """小盘+高换手率 → 题材股"""
        quote = {"code": "sz300001", "circulating_cap": "50", "total_cap": "80", "turnover": "12"}
        result = classify_stock(None, quote, None)
        assert result["type"] == "题材股"
        assert result["confidence"] == "中"

    def test_small_cap_with_limit_streak(self):
        """小盘+连板 → 题材股（高置信度）"""
        # 构造连续涨停的 K 线数据（主板 10% 涨停）
        kline = []
        price = 10.0
        for i in range(12):
            kline.append({"close": str(round(price, 2)), "volume": "1000"})
            if i >= 8:  # 最后 4 根连续涨停 (~10%)
                price = round(price * 1.1, 2)
            else:
                price = round(price + 0.1, 2)

        # 使用主板代码 (sh600xxx) 以匹配 10% 涨停阈值
        quote = {"code": "sh600001", "circulating_cap": "50", "total_cap": "80", "turnover": "3"}
        result = classify_stock(None, quote, kline)
        assert result["type"] == "题材股"
        assert result["confidence"] == "高"


class TestBlueChipStock:
    """蓝筹股分类。"""

    def test_large_cap_with_roe(self):
        """大盘+ROE>10 → 蓝筹股"""
        quote = {"code": "sh600519", "circulating_cap": "2000", "total_cap": "22000", "turnover": "0.5"}
        fin = {"ROEJQ": "30", "PARENTNETPROFITTZ": "15", "XSMLL": "90", "ZCFZL": "20"}
        result = classify_stock(fin, quote, None)
        assert result["type"] == "蓝筹股"
        assert result["confidence"] == "高"

    def test_large_cap_no_finance(self):
        """大盘+无财务数据 → 蓝筹股（中置信度）"""
        quote = {"code": "sh600519", "circulating_cap": "2000", "total_cap": "22000", "turnover": "0.5"}
        result = classify_stock(None, quote, None)
        assert result["type"] == "蓝筹股"
        assert result["confidence"] == "中"


class TestGrowthStock:
    """强成长股分类。"""

    def test_high_growth_high_roe(self):
        """净利增速>30% + ROE>15% + 中小盘 → 强成长股"""
        quote = {"code": "sz002001", "circulating_cap": "200", "total_cap": "300", "turnover": "2"}
        fin = {"ROEJQ": "20", "PARENTNETPROFITTZ": "40", "XSMLL": "35", "ZCFZL": "45"}
        result = classify_stock(fin, quote, None)
        assert result["type"] == "强成长股"
        assert result["confidence"] == "高"


class TestCyclicalStock:
    """周期股分类。"""

    def test_high_volatility_low_margin(self):
        """增速波动大 + 毛利偏低 → 周期股"""
        quote = {"code": "sh600001", "circulating_cap": "300", "total_cap": "500", "turnover": "2"}
        fin = {"ROEJQ": "10", "PARENTNETPROFITTZ": "60", "XSMLL": "15", "ZCFZL": "55"}
        result = classify_stock(fin, quote, None)
        assert result["type"] == "周期股"
        assert result["confidence"] == "中"


class TestStableGrowthStock:
    """稳成长股分类。"""

    def test_moderate_growth_high_roe(self):
        """净利增速 15-30% + ROE>12% → 稳成长股"""
        quote = {"code": "sh600001", "circulating_cap": "300", "total_cap": "500", "turnover": "2"}
        fin = {"ROEJQ": "18", "PARENTNETPROFITTZ": "20", "XSMLL": "40", "ZCFZL": "45"}
        result = classify_stock(fin, quote, None)
        assert result["type"] == "稳成长股"
        assert result["confidence"] == "高"


class TestDefensiveStock:
    """防御股分类。"""

    def test_stable_growth_low_debt(self):
        """增速稳定 + 低负债 → 防御股"""
        quote = {"code": "sh600001", "circulating_cap": "300", "total_cap": "500", "turnover": "2"}
        fin = {"ROEJQ": "12", "PARENTNETPROFITTZ": "10", "XSMLL": "30", "ZCFZL": "35"}
        result = classify_stock(fin, quote, None)
        assert result["type"] == "防御股"
        assert result["confidence"] == "中"


class TestDefaultStock:
    """普通股分类。"""

    def test_no_distinguishing_features(self):
        """无明显特征 → 普通股"""
        quote = {"code": "sh600001", "circulating_cap": "300", "total_cap": "500", "turnover": "2"}
        fin = {"ROEJQ": "8", "PARENTNETPROFITTZ": "5", "XSMLL": "25", "ZCFZL": "65"}
        result = classify_stock(fin, quote, None)
        assert result["type"] == "普通股"

    def test_no_data_defaults_to_large_cap_blue_chip(self):
        """无数据+大盘 → 蓝筹股（中置信度）"""
        quote = {"code": "sh600519", "circulating_cap": "2000", "total_cap": "22000", "turnover": "0.5"}
        result = classify_stock(None, quote, None)
        assert result["type"] == "蓝筹股"
        assert result["confidence"] == "中"

    def test_no_data_small_cap_high_turnover(self):
        """无数据+小盘+高换手 → 题材股"""
        quote = {"code": "sz300001", "circulating_cap": "50", "total_cap": "80", "turnover": "6"}
        result = classify_stock(None, quote, None)
        assert result["type"] == "题材股"
        assert result["confidence"] == "低"

    def test_no_data_medium_cap(self):
        """无数据+中等市值 → 普通股"""
        quote = {"code": "sh600001", "circulating_cap": "200", "total_cap": "300", "turnover": "2"}
        result = classify_stock(None, quote, None)
        assert result["type"] == "普通股"
        assert result["confidence"] == "低"


class TestTypeIndicatorMap:
    """类型→指标映射测试。"""

    def test_all_types_have_mapping(self):
        expected_types = {"题材股", "蓝筹股", "强成长股", "周期股", "稳成长股", "防御股", "普通股"}
        assert set(TYPE_INDICATOR_MAP.keys()) == expected_types

    def test_each_type_has_priority_and_deprioritized(self):
        for stock_type, mapping in TYPE_INDICATOR_MAP.items():
            assert "priority" in mapping, f"{stock_type} 缺少 priority"
            assert "deprioritized" in mapping, f"{stock_type} 缺少 deprioritized"
            assert isinstance(mapping["priority"], list)
            assert isinstance(mapping["deprioritized"], list)
            assert len(mapping["priority"]) > 0, f"{stock_type} priority 为空"

    def test_priority_indicators_match_type(self, sample_quote, sample_finance, kline_uptrend):
        """分类结果的 priority_indicators 应与 TYPE_INDICATOR_MAP 一致。"""
        result = classify_stock(sample_finance, sample_quote, kline_uptrend)
        expected = TYPE_INDICATOR_MAP[result["type"]]
        assert result["priority_indicators"] == expected["priority"]
        assert result["deprioritized"] == expected["deprioritized"]

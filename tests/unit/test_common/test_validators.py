"""
输入验证器测试。
"""

import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from common.validators import (
    validate_code,
    normalize_code,
    validate_codes,
    resolve_code,
    NAME_TO_CODE,
    validate_date,
    validate_date_range,
    validate_positive,
    validate_in_range,
    ValidationError,
)


class TestValidateCode:
    """股票代码验证测试。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("sh600989", True),
            ("sz000807", True),
            ("600989", True),
            ("000807", True),
            ("bj430123", True),
            ("688123", True),
            ("300123", True),
            ("invalid", False),
            ("", False),
            ("12345", False),
            ("1234567", False),
            ("abc123", False),
        ],
    )
    def test_validate_code_formats(self, code, expected):
        """测试各种代码格式。"""
        assert validate_code(code) == expected


class TestNormalizeCode:
    """股票代码标准化测试。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("600989", "sh600989"),
            ("sh600989", "sh600989"),
            ("SH600989", "sh600989"),
            ("000807", "sz000807"),
            ("sz000807", "sz000807"),
            ("688123", "sh688123"),
            ("300123", "sz300123"),
            ("430123", "bj430123"),
        ],
    )
    def test_normalize_code(self, code, expected):
        """测试代码标准化。"""
        assert normalize_code(code) == expected

    def test_normalize_code_invalid(self):
        """测试无效代码抛出异常。"""
        with pytest.raises(ValidationError):
            normalize_code("invalid")

    def test_normalize_code_empty(self):
        """测试空代码抛出异常。"""
        with pytest.raises(ValidationError) as exc:
            normalize_code("")
        assert "不能为空" in exc.value.message


class TestValidateCodes:
    """批量代码验证测试。"""

    def test_validate_codes_valid(self):
        """测试有效代码列表。"""
        result = validate_codes(["sh600989", "sz000807", "600989"])
        assert result == ["sh600989", "sz000807", "sh600989"]

    def test_validate_codes_invalid(self):
        """测试无效代码抛出异常。"""
        with pytest.raises(ValidationError):
            validate_codes(["sh600989", "invalid"])

    def test_validate_codes_empty(self):
        """测试空列表抛出异常。"""
        with pytest.raises(ValidationError):
            validate_codes([])


class TestValidateDate:
    """日期验证测试。"""

    @pytest.mark.parametrize(
        "date,expected",
        [
            ("2024-01-01", True),
            ("2025-12-31", True),
            ("2024-1-1", False),
            ("2024-01-1", False),
            ("2024/01/01", False),
            ("", False),
        ],
    )
    def test_validate_date(self, date, expected):
        """测试日期格式验证。"""
        assert validate_date(date) == expected


class TestValidateDateRange:
    """日期范围验证测试。"""

    def test_validate_date_range_valid(self):
        """测试有效日期范围。"""
        assert validate_date_range("2024-01-01", "2024-12-31")

    def test_validate_date_range_same(self):
        """测试相同日期。"""
        assert validate_date_range("2024-01-01", "2024-01-01")

    def test_validate_date_range_invalid_order(self):
        """测试无效顺序。"""
        with pytest.raises(ValidationError):
            validate_date_range("2024-12-31", "2024-01-01")

    def test_validate_date_range_invalid_format(self):
        """测试无效格式。"""
        with pytest.raises(ValidationError):
            validate_date_range("2024/01/01", "2024-12-31")


class TestValidatePositive:
    """正数验证测试。"""

    def test_validate_positive_valid(self):
        """测试有效正数。"""
        assert validate_positive(10.5, "value") == 10.5

    def test_validate_positive_zero(self):
        """测试零值。"""
        assert validate_positive(0, "value", min_value=0) == 0

    def test_validate_positive_negative(self):
        """测试负数。"""
        with pytest.raises(ValidationError):
            validate_positive(-1, "value")

    def test_validate_positive_min(self):
        """测试最小值。"""
        assert validate_positive(5, "value", min_value=5) == 5

    def test_validate_positive_below_min(self):
        """测试低于最小值。"""
        with pytest.raises(ValidationError):
            validate_positive(4, "value", min_value=5)


class TestValidateInRange:
    """范围验证测试。"""

    def test_validate_in_range_valid(self):
        """测试有效范围内值。"""
        assert validate_in_range(5, "value", 0, 10) == 5

    def test_validate_in_range_boundary(self):
        """测试边界值。"""
        assert validate_in_range(0, "value", 0, 10) == 0
        assert validate_in_range(10, "value", 0, 10) == 10

    def test_validate_in_range_outside(self):
        """测试范��外值。"""
        with pytest.raises(ValidationError):
            validate_in_range(15, "value", 0, 10)


class TestResolveCode:
    """resolve_code 测试：接受代码或中文名 → 标准代码（PR-B 兑现 README 中文名输入承诺）。"""

    @pytest.mark.parametrize(
        "name,expected",
        [
            # 纯代码路径不破坏
            ("sh600989", "sh600989"),
            ("600989", "sh600989"),
            ("SH600519", "sh600519"),
            ("sz000807", "sz000807"),
            # 中文名精确匹配
            ("贵州茅台", "sh600519"),
            ("茅台", "sh600519"),
            ("中国平安", "sh601318"),
            ("招商银行", "sh600036"),
            ("招行", "sh600036"),
            ("宝丰能源", "sh600989"),
            # 中文名模糊匹配（用户输入前缀/后缀）
            ("贵州茅台股份", "sh600519"),
            ("平安", "sh601318"),
        ],
    )
    def test_resolve_code(self, name, expected):
        """代码 + 中文名统一入口。"""
        assert resolve_code(name) == expected

    def test_resolve_code_name_table_nonempty(self):
        """NAME_TO_CODE 表至少覆盖 README 重点示例。"""
        assert "贵州茅台" in NAME_TO_CODE
        assert "宝丰能源" in NAME_TO_CODE
        assert "中国平安" in NAME_TO_CODE

    def test_resolve_code_unknown_name(self):
        """未知中文名抛 ValidationError。"""
        with pytest.raises(ValidationError):
            resolve_code("不存在的虚拟股票xyz")

    def test_resolve_code_empty(self):
        """空值抛 ValidationError。"""
        with pytest.raises(ValidationError):
            resolve_code("")

    def test_resolve_code_non_string(self):
        """非字符串抛 ValidationError。"""
        with pytest.raises(ValidationError):
            resolve_code(123)


class TestCrossMarketCode:
    """跨市场代码（us:/hk:）校验与解析测试。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("us:spy", True),
            ("us:^gspc", True),
            ("US:SPY", True),
            ("hk:0700", True),
            ("HK:9988", True),
            ("hk:00700", True),
            ("us:", False),
            ("hk:", False),
            ("sh600989", True),
            ("invalid", False),
        ],
    )
    def test_validate_code_cross_market(self, code, expected):
        """跨市场代码格式校验。"""
        assert validate_code(code) == expected

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("us:spy", "us:spy"),
            ("US:SPY", "us:SPY"),
            ("hk:0700", "hk:0700"),
            ("HK:9988", "hk:9988"),
        ],
    )
    def test_resolve_code_cross_market(self, code, expected):
        """跨市场代码经 resolve_code 原样返回（小写前缀）。"""
        assert resolve_code(code) == expected

    def test_validate_codes_cross_market_mix(self):
        """批量校验混合 A 股 + 跨市场代码。"""
        result = validate_codes(["sh600519", "us:spy", "hk:0700"])
        assert result == ["sh600519", "us:spy", "hk:0700"]

    def test_resolve_code_cross_market_empty_symbol(self):
        """跨市场前缀但符号为空应抛错。"""
        with pytest.raises(ValidationError):
            resolve_code("us:")
        with pytest.raises(ValidationError):
            resolve_code("hk:")

    def test_resolve_code_chinese_name_hk_us(self):
        """港股/美股中文名映射。"""
        assert resolve_code("腾讯") == "hk:0700"
        assert resolve_code("腾讯控股") == "hk:0700"
        assert resolve_code("阿里") == "hk:9988"
        assert resolve_code("苹果") == "us:aapl"
        assert resolve_code("英伟达") == "us:nvda"

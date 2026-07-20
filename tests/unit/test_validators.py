"""
scripts/common/validators.py 的单元测试。

按 FRAMEWORK.md 规范：
- 测试类命名 TestXxxYyy（语义唯一）
- 测试方法 test_行为_期望
- parametrize 优先
- 无 sys.path.insert（依赖 pyproject.toml::pythonpath）
- 无 mock IO，纯函数
"""

from __future__ import annotations

import pytest

from common.exceptions import ValidationError
from common.validators import (
    NAME_TO_CODE,
    normalize_code,
    resolve_code,
    validate_code,
    validate_codes,
    validate_date,
    validate_date_range,
    validate_in_range,
    validate_positive,
)

# ═══════════════════════════════════════════════════════════════
# validate_code：纯 bool 返回值
# ═══════════════════════════════════════════════════════════════


class TestValidateCodeAccepts:
    """合法代码应返回 True。"""

    @pytest.mark.parametrize(
        "code",
        [
            "sh600519",  # 上证主板
            "sz000001",  # 深证主板
            "bj430047",  # 北交所
            "600519",  # 6 位纯数字
            "000001",
            "SH600519",  # 大写前缀（normalize 后验证）
            "sh688981",  # 科创板
            "sz300750",  # 创业板
            "us:aapl",  # 美股
            "hk:0700",  # 港股
            "US:SPY",  # 美股大写前缀
            "HK:9988",
        ],
    )
    def test_valid_codes(self, code):
        assert validate_code(code) is True


class TestValidateCodeRejects:
    """非法代码应返回 False。"""

    @pytest.mark.parametrize(
        "code",
        [
            "",  # 空
            "  ",  # 空白
            "sh12345",  # 5 位
            "sh1234567",  # 7 位
            "abc123",  # 含字母
            "xx600519",  # 未知前缀
            "us:",  # us: 符号为空
            "us:",  # 同上
            "hk:",
        ],
    )
    def test_invalid_codes(self, code):
        assert validate_code(code) is False

    def test_non_string_returns_false(self):
        """非字符串输入应优雅返回 False，不抛异常。"""
        for v in [None, 123, 600519, ["sh600519"], {"code": "sh600519"}]:
            assert validate_code(v) is False  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════
# normalize_code：返回标准化字符串，可能抛 ValidationError
# ═══════════════════════════════════════════════════════════════


class TestNormalizeCodeExchange:
    """按数字段推断交易所。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("600519", "sh600519"),
            ("000001", "sz000001"),
            ("300750", "sz300750"),
            ("688981", "sh688981"),
            ("430047", "bj430047"),
            ("510500", "sh510500"),  # 上证 ETF
            ("159915", "sz159915"),  # 深证 ETF
        ],
    )
    def test_exchange_by_digits(self, raw, expected):
        assert normalize_code(raw) == expected

    def test_always_corrections_wrong_prefix(self):
        """即使传错前缀也按数字段校正。"""
        # sh001330 应校正为 sz001330（深证）
        assert normalize_code("sh001330") == "sz001330"
        # sz600519 应校正为 sh600519（上证）
        assert normalize_code("sz600519") == "sh600519"


class TestNormalizeCodeErrors:
    """错误输入应抛 ValidationError。"""

    @pytest.mark.parametrize(
        "bad_input",
        ["", "abc", "12345", "1234567", "sh123", None],
    )
    def test_raises_validation_error(self, bad_input):
        with pytest.raises(ValidationError):
            normalize_code(bad_input)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════
# resolve_code：股票代码或中文名的统一入口
# ═══════════════════════════════════════════════════════════════


class TestResolveCodeDigit:
    """数字代码路径：走 normalize_code。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("600519", "sh600519"),
            ("SH600519", "sh600519"),
            ("sh600519", "sh600519"),
            (" 600519 ", "sh600519"),  # 前后空白
        ],
    )
    def test_normalize_path(self, raw, expected):
        assert resolve_code(raw) == expected


class TestResolveCodeCrossMarket:
    """跨市场代码（us:/hk:）原样返回（prefix 小写化，符号部分大小写保留）。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("us:aapl", "us:aapl"),
            ("US:AAPL", "us:AAPL"),  # prefix 小写，符号保留
            ("us:SPY", "us:SPY"),
            ("hk:0700", "hk:0700"),
            ("HK:9988", "hk:9988"),  # 港股数字本身就一致
        ],
    )
    def test_cross_market_returns_as_is(self, raw, expected):
        assert resolve_code(raw) == expected

    def test_prefix_always_lowercase(self):
        """不论大写小写输入，prefix 部分归一化为小写。"""
        assert resolve_code("US:aapl").startswith("us:")
        assert resolve_code("HK:0700").startswith("hk:")


class TestResolveCodeChinese:
    """中文名 → 代码映射（含模糊匹配）。"""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("贵州茅台", "sh600519"),
            ("茅台", "sh600519"),
            ("五粮液", "sz000858"),
            ("平安银行", "sz000001"),
            ("腾讯", "hk:0700"),
            ("腾讯控股", "hk:0700"),
            ("苹果", "us:aapl"),
            ("英伟达", "us:nvda"),
        ],
    )
    def test_exact_match(self, name, expected):
        assert resolve_code(name) == expected

    def test_fuzzy_match_substring(self):
        """模糊匹配：name 是 key 的子串。"""
        # "贵州茅台" 在 "贵州茅台(600519)" 里应被匹配
        # 这里通过 _try_resolve_chinese_name 的直接调用验证内部行为
        from common.validators import _try_resolve_chinese_name

        assert _try_resolve_chinese_name("贵州茅台有限公司") == "sh600519"


class TestResolveCodeErrors:
    """无法识别的输入应抛 ValidationError。"""

    @pytest.mark.parametrize(
        "bad",
        ["", "  ", "Unknown 公司", "xyz", None, "us:", "hk:"],
    )
    def test_raises(self, bad):
        with pytest.raises(ValidationError):
            resolve_code(bad)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════
# validate_codes：批量
# ═══════════════════════════════════════════════════════════════


class TestValidateCodes:
    def test_batch_normalizes_all(self):
        result = validate_codes(["600519", "000001", "688981"])
        assert result == ["sh600519", "sz000001", "sh688981"]

    def test_empty_list_raises(self):
        with pytest.raises(ValidationError):
            validate_codes([])

    def test_invalid_raises_with_first_bad(self):
        with pytest.raises(ValidationError):
            validate_codes(["sh600519", "abc"])

    def test_cross_market_preserved(self):
        result = validate_codes(["us:aapl", "hk:0700", "600519"])
        assert result == ["us:aapl", "hk:0700", "sh600519"]


# ═══════════════════════════════════════════════════════════════
# validate_date：YYYY-MM-DD 严格格式 + 真实有效性
# ═══════════════════════════════════════════════════════════════


class TestValidateDate:
    @pytest.mark.parametrize(
        "date_str,expected",
        [
            ("2026-07-20", True),
            ("2024-02-29", True),  # 闰年
            ("2023-02-29", False),  # 非闰年，不应通过
            ("2026-13-01", False),  # 非法月份
            ("2026-01-32", False),  # 非法日期
            ("2026-00-15", False),
            ("2026-01-00", False),
            ("26-07-20", False),  # 短年份
            ("2026/07/20", False),  # 错误分隔符
            ("2026-7-20", False),  # 非严格两位
            ("2026-07-20 ", False),  # 尾部空白
            ("", False),
            ("not a date", False),
        ],
    )
    def test_format_and_validity(self, date_str, expected):
        assert validate_date(date_str) is expected


# ═══════════════════════════════════════════════════════════════
# validate_date_range
# ═══════════════════════════════════════════════════════════════


class TestValidateDateRange:
    def test_valid_range(self):
        assert validate_date_range("2026-01-01", "2026-12-31") is True

    def test_same_day(self):
        assert validate_date_range("2026-07-20", "2026-07-20") is True

    def test_reversed_raises(self):
        with pytest.raises(ValidationError, match="开始日期必须早于"):
            validate_date_range("2026-12-31", "2026-01-01")

    def test_invalid_start(self):
        with pytest.raises(ValidationError):
            validate_date_range("not-a-date", "2026-12-31")

    def test_invalid_end(self):
        with pytest.raises(ValidationError):
            validate_date_range("2026-01-01", "bogus")


# ═══════════════════════════════════════════════════════════════
# validate_positive
# ═══════════════════════════════════════════════════════════════


class TestValidatePositive:
    def test_valid_returns_float(self):
        assert validate_positive("3.14", "price") == 3.14
        assert validate_positive(0, "price") == 0.0
        assert validate_positive(100, "size") == 100.0

    def test_negative_with_default_min(self):
        with pytest.raises(ValidationError, match="必须 >= 0"):
            validate_positive(-1.0, "price")

    def test_below_custom_min(self):
        with pytest.raises(ValidationError, match="必须 >= 10"):
            validate_positive(5, "score", min_value=10)

    def test_non_numeric_raises(self):
        with pytest.raises(ValidationError, match="必须为数字"):
            validate_positive("abc", "price")


# ═══════════════════════════════════════════════════════════════
# validate_in_range
# ═══════════════════════════════════════════════════════════════


class TestValidateInRange:
    def test_within_range(self):
        assert validate_in_range(50.0, "pct", 0, 100) == 50.0

    def test_at_boundary(self):
        """边界值（含端点）应通过。"""
        assert validate_in_range(0, "pct", 0, 100) == 0.0
        assert validate_in_range(100, "pct", 0, 100) == 100.0

    def test_below_min(self):
        with pytest.raises(ValidationError, match="必须在"):
            validate_in_range(-1, "pct", 0, 100)

    def test_above_max(self):
        with pytest.raises(ValidationError, match="必须在"):
            validate_in_range(101, "pct", 0, 100)

    def test_non_numeric_raises(self):
        with pytest.raises(ValidationError, match="必须为数字"):
            validate_in_range("foo", "pct", 0, 100)


# ═══════════════════════════════════════════════════════════════
# NAME_TO_CODE 表完整性
# ═══════════════════════════════════════════════════════════════


class TestNameToCodeTable:
    """NAME_TO_CODE 是手维护映射表，做结构性校验防止漂移。"""

    def test_all_values_are_strings(self):
        assert all(isinstance(v, str) for v in NAME_TO_CODE.values())

    def test_all_values_match_stock_code_format(self):
        """值要么是 sh/sz/bj + 6 位数字，要么是 us:/hk: 跨市场格式。"""
        import re

        pattern = re.compile(r"^(sh|sz|bj)\d{6}$|^(us|hk):[a-zA-Z0-9]+$")
        for k, v in NAME_TO_CODE.items():
            assert pattern.match(v), f"NAME_TO_CODE[{k!r}] = {v!r} 不符合代码格式"

    def test_no_empty_keys(self):
        assert all(k.strip() for k in NAME_TO_CODE.keys())

    def test_minimum_coverage(self):
        """至少覆盖 50 个常用标的，避免漂移到稀疏状态。"""
        assert (
            len(NAME_TO_CODE) >= 50
        ), f"NAME_TO_CODE 只有 {len(NAME_TO_CODE)} 个映射，少于预期"

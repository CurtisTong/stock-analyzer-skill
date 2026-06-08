"""
输入验证器模块。

提供股票代码、日期等输入的标准化和校验功能。
"""
import re
from typing import Optional, List
from .exceptions import ValidationError


# 股票代码正则
STOCK_CODE_PATTERN = re.compile(r"^(sh|sz|bj)?(\d{6})$", re.IGNORECASE)


def validate_code(code: str) -> bool:
    """
    验证股票代码格式。

    Args:
        code: 股票代码 (支持 sh600989, sz000807, 600989, 000807 等格式)

    Returns:
        是否有效
    """
    if not code or not isinstance(code, str):
        return False

    code = code.strip().lower()
    return bool(STOCK_CODE_PATTERN.match(code))


def normalize_code(code: str) -> str:
    """
    标准化股票代码为 sh/sz 前缀格式。

    Args:
        code: 原始代码

    Returns:
        标准化后的代码 (如 "sh600989")

    Raises:
        ValidationError: 代码格式无效
    """
    if not code:
        raise ValidationError("code", code, "不能为空")

    code = code.strip().lower()

    # 已经是标准格式
    if code.startswith(("sh", "sz", "bj")) and len(code) >= 8:
        return code

    # 提取纯数字
    digits = re.sub(r"\D", "", code)
    if len(digits) != 6:
        raise ValidationError("code", code, "必须为6位数字")

    # 根据代码段判断交易所
    if digits.startswith(("60", "68", "51", "56", "58")):
        return f"sh{digits}"
    elif digits.startswith(("00", "30", "15", "16", "18")):
        return f"sz{digits}"
    elif digits.startswith(("43", "83", "87", "88", "92")):
        return f"bj{digits}"
    else:
        # 默认根据前缀判断
        if code.startswith("sh"):
            return f"sh{digits}"
        elif code.startswith("sz"):
            return f"sz{digits}"
        elif code.startswith("bj"):
            return f"bj{digits}"
        # 未知格式，尝试返回
        return f"sh{digits}"


def validate_codes(codes: List[str]) -> List[str]:
    """
    批量验证并标准化股票代码。

    Args:
        codes: 股票代码列表

    Returns:
        标准化后的代码列表

    Raises:
        ValidationError: 任意代码格式无效
    """
    if not codes:
        raise ValidationError("codes", codes, "不能为空")

    result = []
    for code in codes:
        if not validate_code(code):
            raise ValidationError("code", code, "格式无效")
        result.append(normalize_code(code))

    return result


def validate_date(date_str: str) -> bool:
    """
    验证日期格式 (YYYY-MM-DD)。

    Args:
        date_str: 日期字符串

    Returns:
        是否有效
    """
    if not date_str:
        return False

    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    return bool(pattern.match(date_str))


def validate_date_range(start_date: str, end_date: str) -> bool:
    """
    验证日期范围。

    Args:
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        是否有效 (start <= end)

    Raises:
        ValidationError: 日期格式或范围无效
    """
    if not validate_date(start_date):
        raise ValidationError("start_date", start_date, "格式应为 YYYY-MM-DD")
    if not validate_date(end_date):
        raise ValidationError("end_date", end_date, "格式应为 YYYY-MM-DD")

    if start_date > end_date:
        raise ValidationError(
            "date_range",
            f"{start_date} - {end_date}",
            "开始日期必须早于或等于结束日期"
        )

    return True


def validate_positive(value: float, field_name: str, min_value: float = 0) -> float:
    """
    验证正数。

    Args:
        value: 待验证值
        field_name: 字段名称
        min_value: 最小允许值

    Returns:
        验证后的值

    Raises:
        ValidationError: 值无效
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValidationError(field_name, value, "必须为数字")

    if v < min_value:
        raise ValidationError(field_name, value, f"必须 >= {min_value}")

    return v


def validate_in_range(
    value: float,
    field_name: str,
    min_value: float,
    max_value: float
) -> float:
    """
    验证值在指定范围内。

    Args:
        value: 待验证值
        field_name: 字段名称
        min_value: 最小值
        max_value: 最大值

    Returns:
        验证后的值

    Raises:
        ValidationError: 值超出范围
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValidationError(field_name, value, "必须为数字")

    if not (min_value <= v <= max_value):
        raise ValidationError(
            field_name, value,
            f"必须在 {min_value} 到 {max_value} 之间"
        )

    return v


__all__ = [
    "validate_code",
    "normalize_code",
    "validate_codes",
    "validate_date",
    "validate_date_range",
    "validate_positive",
    "validate_in_range",
    "ValidationError",
]

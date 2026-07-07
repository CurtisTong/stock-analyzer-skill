"""
输入验证器模块。

提供股票代码、日期等输入的标准化和校验功能。
"""

import re
from typing import List
from .exceptions import ValidationError

# 股票代码正则
STOCK_CODE_PATTERN = re.compile(r"^(sh|sz|bj)?(\d{6})$", re.IGNORECASE)

# 常用 A 股中文名 → 代码映射（覆盖 README/user-guide 高频示例 + 板块龙头）
# v2.4.0: 扩充至 50+ 只，覆盖消费/科技/医药/周期/金融五大板块龙头
NAME_TO_CODE: dict = {
    # ── 消费 ──
    "贵州茅台": "sh600519",
    "茅台": "sh600519",
    "五粮液": "sz000858",
    "泸州老窖": "sz000568",
    "山西汾酒": "sh600809",
    "伊利股份": "sh600887",
    "海天味业": "sh603288",
    "美的集团": "sz000333",
    "格力电器": "sz000651",
    "海尔智家": "sh600690",
    # ── 金融 ──
    "中国平安": "sh601318",
    "平安银行": "sz000001",
    "招商银行": "sh600036",
    "招行": "sh600036",
    "工商银行": "sh601398",
    "建设银行": "sh601939",
    "中国银行": "sh601988",
    "农业银行": "sh601288",
    "中信证券": "sh600030",
    "东方财富": "sz300059",
    # ── 科技/制造 ──
    "宁德时代": "sz300750",
    "比亚迪": "sz002594",
    "隆基绿能": "sh601012",
    "通威股份": "sh600438",
    "北方华创": "sz002371",
    "中芯国际": "sh688981",
    "韦尔股份": "sh603501",
    "京东方A": "sz000725",
    "立讯精密": "sz002475",
    "海康威视": "sz002415",
    "科大讯飞": "sz002230",
    "中兴通讯": "sz000063",
    # ── 医药 ──
    "恒瑞医药": "sh600276",
    "迈瑞医疗": "sz300760",
    "药明康德": "sh603259",
    "片仔癀": "sh600436",
    "长春高新": "sz000661",
    "智飞生物": "sz300122",
    # ── 周期/资源 ──
    "宝丰能源": "sh600989",
    "云铝股份": "sz000807",
    "紫金矿业": "sh601899",
    "中国神华": "sh601088",
    "万华化学": "sh600309",
    "中国石油": "sh601857",
    "中国石化": "sh600028",
    "宝钢股份": "sh600019",
    "海螺水泥": "sh600585",
    # ── 港股/美股占位 ──
    "腾讯": "sh00700",
    "阿里巴巴": "us:baba",
}


def _try_resolve_chinese_name(name: str) -> str | None:
    """从 NAME_TO_CODE 表查中文名/模糊匹配，未命中返回 None。

    精确匹配优先，模糊匹配允许双向子串匹配，
    多个匹配时取最长键（最具体匹配）。
    """
    if not name:
        return None
    cleaned = name.strip()
    if cleaned in NAME_TO_CODE:
        return NAME_TO_CODE[cleaned]
    # 模糊匹配：双向子串，多匹配时取最长键
    matches = [(k, v) for k, v in NAME_TO_CODE.items() if k in cleaned or cleaned in k]
    if matches:
        # 多个匹配时取最长键（最具体），如"贵州茅台"优先于"茅台"
        best = max(matches, key=lambda kv: len(kv[0]))
        return best[1]
    return None


def resolve_code(name_or_code: str) -> str:
    """统一入口：接受股票代码或常用中文名，返回标准化代码。

    - 已合法代码（含 sh/sz/bj 前缀或纯 6 位数字）走 normalize_code 路径
    - 命中 NAME_TO_CODE 表（含模糊匹配）走中文名解析路径
    - 都未命中：抛 ValidationError

    Args:
        name_or_code: 股票代码或中文名称

    Returns:
        标准化股票代码（如 "sh600519"）

    Raises:
        ValidationError: 无法识别
    """
    if not name_or_code or not isinstance(name_or_code, str):
        raise ValidationError("name_or_code", name_or_code, "不能为空")

    s = name_or_code.strip()

    # 优先按代码处理（含纯 6 位数字 / 带前缀）
    if STOCK_CODE_PATTERN.match(s):
        return normalize_code(s)

    # 中文名 → 代码
    resolved = _try_resolve_chinese_name(s)
    if resolved:
        return resolved

    raise ValidationError(
        "name_or_code", name_or_code, "无法识别为股票代码或已收录的中文名"
    )


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
    标准化股票代码为 sh/sz/bj 前缀格式。

    始终根据数字段判断交易所前缀，即使输入已有前缀也会校正。
    例如 sh001330 → sz001330（00 开头为深市）。

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

    # 提取纯数字
    digits = re.sub(r"\D", "", code)
    if len(digits) != 6:
        raise ValidationError("code", code, "必须为6位数字")

    # 始终根据数字段判断交易所（校正错误前缀，如 sh001330 → sz001330）
    if digits.startswith(("60", "68", "51", "56", "58")):
        return f"sh{digits}"
    elif digits.startswith(("00", "30", "15", "16", "18")):
        return f"sz{digits}"
    elif digits.startswith(("43", "83", "87", "88", "92")):
        return f"bj{digits}"
    else:
        # 非标准数字段，回退到原始前缀判断
        if code.startswith("sz"):
            return f"sz{digits}"
        elif code.startswith("bj"):
            return f"bj{digits}"
        # 未知格式，默认 sh
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
    验证日期格式与有效性 (YYYY-MM-DD)。

    P1-31: 原仅用正则校验格式，2024-13-45 等非法日期会通过。
    改用 strptime 既校验格式又校验有效性。

    Args:
        date_str: 日期字符串

    Returns:
        是否有效
    """
    if not date_str:
        return False

    from datetime import datetime

    # 先校验严格格式 YYYY-MM-DD（两位月日），再校验日期有效性
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not pattern.match(date_str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


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
            "date_range", f"{start_date} - {end_date}", "开始日期必须早于或等于结束日期"
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
    value: float, field_name: str, min_value: float, max_value: float
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
            field_name, value, f"必须在 {min_value} 到 {max_value} 之间"
        )

    return v


__all__ = [
    "validate_code",
    "normalize_code",
    "validate_codes",
    "resolve_code",
    "NAME_TO_CODE",
    "validate_date",
    "validate_date_range",
    "validate_positive",
    "validate_in_range",
    "ValidationError",
]

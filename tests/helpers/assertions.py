"""领域断言：Quote / KLine / FinanceRecord / HolderData。

简单断言用 assert 即可；领域对象必须用本模块断言函数，保证：
1. 一致性：所有测试用同套校验规则
2. 失败定位：错误信息明确指出哪个字段不符合预期
3. 可演化：归一化字段变更时只改本模块
"""

from __future__ import annotations

from typing import Any

REQUIRED_QUOTE_FIELDS = {
    "code",
    "name",
    "price",
    "open",
    "high",
    "low",
    "volume",
    "amount",
}


def assert_valid_quote(
    quote: dict[str, Any], *, code: str | None = None, price_positive: bool = True
) -> None:
    """校验归一化后的行情数据。

    Args:
        quote: dict 含 code/name/price/open/high/low/volume/amount
        code: 期望的股票代码（不带 sh/sz/bj 前缀）
        price_positive: 是否要求 price > 0
    """
    missing = REQUIRED_QUOTE_FIELDS - set(quote.keys())
    assert not missing, f"Quote 缺少字段: {missing}"

    if code is not None:
        assert quote["code"].endswith(
            code
        ), f"期望 code 以 {code} 结尾，实际 {quote['code']}"

    if price_positive:
        assert float(quote["price"]) > 0, f"price 必须 > 0，实际 {quote['price']}"

    # 高低价关系
    high = float(quote["high"])
    low = float(quote["low"])
    open_ = float(quote["open"])
    price = float(quote["price"])
    assert low <= price <= high, f"价格 {price} 不在 [{low}, {high}] 范围内"
    assert low <= open_ <= high, f"开盘 {open_} 不在 [{low}, {high}] 范围内"

    # 成交额/量非负
    assert float(quote["volume"]) >= 0
    assert float(quote["amount"]) >= 0


REQUIRED_KLINE_FIELDS = {"day", "open", "high", "low", "close", "volume"}


def assert_kline_shape(bar: dict[str, Any]) -> None:
    """校验单根 K 线字段完整性 + OHLC 关系。"""
    missing = REQUIRED_KLINE_FIELDS - set(bar.keys())
    assert not missing, f"KLine 缺少字段: {missing}"

    high = float(bar["high"])
    low = float(bar["low"])
    open_ = float(bar["open"])
    close = float(bar["close"])
    assert low <= open_ <= high, f"open {open_} 越界 [{low}, {high}]"
    assert low <= close <= high, f"close {close} 越界 [{low}, {high}]"
    assert high >= low


REQUIRED_FINANCE_FIELDS = {
    "EPSJB",
    "ROEJQ",
    "TOTALOPERATEREVETZ",
    "PARENTNETPROFITTZ",
    "XSMLL",
    "XSJLL",
    "ZCFZL",
    "BPS",
}


def assert_valid_finance(finance: dict[str, Any]) -> None:
    """校验归一化后的财务数据（东财字段名）。"""
    missing = REQUIRED_FINANCE_FIELDS - set(finance.keys())
    assert not missing, f"Finance 缺少字段: {missing}"
    # 资产负债率应在 0-100
    assert 0 <= float(finance["ZCFZL"]) <= 100, f"资产负债率 {finance['ZCFZL']} 越界"

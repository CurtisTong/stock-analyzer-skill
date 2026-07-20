"""测试侧 dataclass 类型。

为常见领域对象提供显式类型，便于 type checker 和 IDE 跳转。
产品代码 `scripts/data/types.py` 已有 dataclass，本模块定义测试专用扩展。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteFixture:
    """行情数据 fixture 容器。"""

    code: str
    name: str
    price: float
    prev_close: float
    open: float
    change_pct: float
    change_amt: float
    high: float
    low: float
    volume: int  # 股
    amount: float  # 元
    turnover: float
    pe: float
    pb: float
    total_cap: float
    circulating_cap: float

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "price": str(self.price),
            "prev_close": str(self.prev_close),
            "open": str(self.open),
            "change_pct": str(self.change_pct),
            "change_amt": str(self.change_amt),
            "high": str(self.high),
            "low": str(self.low),
            "volume": str(self.volume),
            "amount": str(self.amount),
            "turnover": str(self.turnover),
            "pe": str(self.pe),
            "pb": str(self.pb),
            "total_cap": str(self.total_cap),
            "circulating_cap": str(self.circulating_cap),
        }


@dataclass(frozen=True)
class FinanceFixture:
    """财务数据 fixture 容器（东财字段名）。"""

    EPSJB: str
    ROEJQ: str
    TOTALOPERATEREVETZ: str
    PARENTNETPROFITTZ: str
    XSMLL: str
    XSJLL: str
    ZCFZL: str
    BPS: str
    MGJYXJJE: str

    def to_dict(self) -> dict:
        return {
            "EPSJB": self.EPSJB,
            "ROEJQ": self.ROEJQ,
            "TOTALOPERATEREVETZ": self.TOTALOPERATEREVETZ,
            "PARENTNETPROFITTZ": self.PARENTNETPROFITTZ,
            "XSMLL": self.XSMLL,
            "XSJLL": self.XSJLL,
            "ZCFZL": self.ZCFZL,
            "BPS": self.BPS,
            "MGJYXJJE": self.MGJYXJJE,
        }

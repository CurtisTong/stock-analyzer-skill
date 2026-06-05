"""统一数据类型定义。"""
from dataclasses import dataclass


@dataclass
class Quote:
    """统一行情数据结构。"""
    code: str = ""
    name: str = ""
    price: float = 0.0
    prev_close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    change_pct: float = 0.0
    change_amt: float = 0.0
    volume: int = 0          # 手
    amount: float = 0.0      # 万元
    turnover: float = 0.0    # %
    pe: float = 0.0
    pb: float = 0.0
    total_cap: float = 0.0   # 亿
    circulating_cap: float = 0.0
    source: str = ""

    def has_basic_data(self) -> bool:
        return self.price > 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class KlineBar:
    """统一 K 线数据结构。"""
    day: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0    # 手
    amount: float = 0.0
    pct_chg: float = 0.0
    source: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class FinanceRecord:
    """统一财务数据结构。"""
    report_date: str = ""
    eps: float = 0.0              # 每股收益
    roe: float = 0.0              # ROE(%)
    revenue_yoy: float = 0.0      # 营收同比(%)
    net_profit_yoy: float = 0.0   # 净利同比(%)
    gross_margin: float = 0.0     # 毛利率(%)
    net_margin: float = 0.0       # 净利率(%)
    debt_ratio: float = 0.0       # 负债率(%)
    bps: float = 0.0              # 每股净资产
    ocf_per_share: float = 0.0    # 每股经营现金流
    source: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()

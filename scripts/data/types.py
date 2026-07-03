"""统一数据类型定义。"""

from dataclasses import dataclass, asdict


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
    volume: int = 0  # 股（统一单位：腾讯手×100，新浪/东财原值）
    amount: float = 0.0  # 元（统一单位：腾讯万×10000，东财万×10000，新浪原值）
    turnover: float = 0.0  # %
    pe: float = 0.0
    pb: float = 0.0
    total_cap: float = 0.0  # 亿
    circulating_cap: float = 0.0
    source: str = ""
    fetch_time: str = ""  # 数据获取时间 ISO 格式

    def has_basic_data(self) -> bool:
        return self.price > 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class KlineBar:
    """统一 K 线数据结构。"""

    day: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0  # 股（统一单位）
    amount: float = 0.0
    pct_chg: float = 0.0
    source: str = ""
    fetch_time: str = ""  # 数据获取时间 ISO 格式

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinanceRecord:
    """统一财务数据结构。"""

    report_date: str = ""
    eps: float = 0.0  # 每股收益
    roe: float = 0.0  # ROE(%)
    revenue_yoy: float = 0.0  # 营收同比(%)
    net_profit_yoy: float = 0.0  # 净利同比(%)
    gross_margin: float = 0.0  # 毛利率(%)
    net_margin: float = 0.0  # 净利率(%)
    debt_ratio: float = 0.0  # 负债率(%)
    bps: float = 0.0  # 每股净资产
    ocf_per_share: float = 0.0  # 每股经营现金流
    goodwill: float = 0.0  # 商誉（亿元）
    pledge_ratio: float = 0.0  # 质押比例(%)
    source: str = ""
    fetch_time: str = ""  # 数据获取时间 ISO 格式
    goodwill_ratio: float = 0.0  # 商誉/总资产(%)
    consecutive_dividend_years: int = 0  # 连续分红年数
    major_shareholder_reduction: float = 0.0  # 大股东减持比例(%)
    violation_penalty: float = 0.0  # 违规处罚金额
    audit_opinion: str = ""  # 审计意见类型
    dividend_yield: float = 0.0  # 股息率(%)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MarginData:
    """融资融券数据结构。"""

    date: str = ""  # 日期
    code: str = ""  # 股票代码
    rzye: float = 0.0  # 融资余额（元）
    rqye: float = 0.0  # 融券余额（元）
    rzmre: float = 0.0  # 融资买入额
    rzche: float = 0.0  # 融资偿还额
    rzjme: float = 0.0  # 融资净买入额
    rqmcl: float = 0.0  # 融券卖出量
    rqchl: float = 0.0  # 融券偿还量
    rqjmg: float = 0.0  # 融券净卖出量
    rqyl: float = 0.0  # 融券余量

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HolderData:
    """股东户数数据结构。"""

    end_date: str = ""  # 截止日期
    code: str = ""  # 股票代码
    holder_num: int = 0  # 股东户数
    avg_amount: float = 0.0  # 户均持股（股）
    holder_num_change: float = 0.0  # 股东户数变化率(%)
    prev_holder_num: int = 0  # 上期股东户数
    concentration: str = ""  # 集中度评级（持续集中/提升/分散）

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TopHolderRecord:
    """十大流通股东数据结构。"""

    end_date: str = ""  # 截止日期
    rank: int = 0  # 排名
    holder_name: str = ""  # 股东名称
    holder_type: str = ""  # 股东类型（基金/QFII/社保/券商/一般法人/个人）
    hold_num: float = 0.0  # 持股数量（万股）
    hold_ratio: float = 0.0  # 持股比例(%)
    change: float = 0.0  # 变动（万股，正=增持）
    change_type: str = ""  # 变动类型（新进/增持/减持/不变）
    is_institution: bool = False  # 是否为机构

    def to_dict(self) -> dict:
        return asdict(self)


"""统一数据类型定义。"""

from dataclasses import dataclass, asdict, field
from typing import List, Optional


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
    # T23: 停牌/涨跌停标识（fetcher 可选填充，默认 False/0 表示未知或未停牌）
    is_suspended: bool = False  # 是否停牌
    limit_up: float = 0.0  # 涨停价（0 表示未知）
    limit_down: float = 0.0  # 跌停价（0 表示未知）
    # P2-13: 数据源返回的行业（fetcher 可选填充，默认空走 keyword 推断）
    industry: str = ""

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
    """统一财务数据结构。

    WP2 (2026-07-21): 数值字段从 ``float = 0.0`` 改为 ``Optional[float] = None``，
    区分"未披露"（None）与"披露了但确实为 0"（0.0）。
    业务层读取前必须 None-aware：None 时走"未知"分支（中性分/跳过判断/不显示）。
    """

    report_date: str = ""
    # 报告期类型（2026-07-23 宝丰能源 PE 误算复盘）：
    #   annual     = 年报（report_date -12-31）
    #   cumulative = 累计（中报 -06-30 / 三季报 -09-30）
    #   quarterly  = 单季（一季报 -03-31）
    #   ""         = 未标注（akshare 不返回 REPORT_TYPE / 旧数据）
    # 下游算 PE 前必须先看本字段：单季 EPS 不可直接做 price/eps。
    period_type: str = ""
    # 核心指标（None = 未披露/字段映射失败/数据源不返回）
    eps: Optional[float] = None  # 每股收益
    roe: Optional[float] = None  # ROE(%)
    revenue_yoy: Optional[float] = None  # 营收同比(%)
    net_profit_yoy: Optional[float] = None  # 净利同比(%)
    gross_margin: Optional[float] = None  # 毛利率(%)
    net_margin: Optional[float] = None  # 净利率(%)
    debt_ratio: Optional[float] = None  # 负债率(%)
    bps: Optional[float] = None  # 每股净资产
    ocf_per_share: Optional[float] = None  # 每股经营现金流
    goodwill: Optional[float] = None  # 商誉（亿元）
    pledge_ratio: Optional[float] = None  # 质押比例(%)
    source: str = ""
    fetch_time: str = ""  # 数据获取时间 ISO 格式
    goodwill_ratio: Optional[float] = None  # 商誉/总资产(%)
    consecutive_dividend_years: int = 0  # 连续分红年数
    major_shareholder_reduction: Optional[float] = None  # 大股东减持比例(%)
    violation_penalty: Optional[float] = None  # 违规处罚金额
    audit_opinion: str = ""  # 审计意见类型
    # 绝对值字段（亿元；东财返回"元"，mappers 层 /1e8 转亿元）
    total_revenue: Optional[float] = None  # 营业总收入(亿)
    parent_net_profit: Optional[float] = None  # 归母净利润(亿)
    deducted_net_profit: Optional[float] = None  # 扣非净利润(亿)
    total_liability: Optional[float] = None  # 负债总额(亿)
    total_assets: Optional[float] = None  # 总资产(亿，计算字段=负债/负债率)
    net_assets: Optional[float] = None  # 净资产(亿，计算字段=bps×股本)
    # 偿债能力 + 季度环比维度（东财主要指标已返回，原被丢弃）
    quick_ratio: Optional[float] = None  # 速动比率
    current_ratio: Optional[float] = None  # 流动比率
    deducted_np_yoy: Optional[float] = None  # 扣非净利同比(%)
    revenue_qoq: Optional[float] = None  # 营收季度环比(%)
    profit_qoq: Optional[float] = None  # 净利季度环比(%)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinanceMeta:
    """财务数据获取元信息（WP4 2026-07-21 新增）。

    与 FinanceRecord 列表一起返回，记录：
    - 数据来源（主源 / 降级源）
    - 期数完整性（实际 vs 请求）
    - 字段缺失降级列表
    - 是否缓存命中

    注：`is_stale` / `stale_reason` 字段为预留位，当前 `get_finance()` 尚未自动填充；
    调用方请使用 `scripts.business.finance_freshness.check_finance_freshness()`
    单独判定（见 WP6 board_overrides 板块差异化披露）。
    """

    source: str = ""  # 主源名（"eastmoney"）
    fallback_source: str = ""  # 降级源名（如 "akshare_finance"）
    requested_periods: int = 0  # 请求期数
    actual_periods: int = 0  # 实际返回期数
    is_periods_truncated: bool = False  # 实际 < 请求 → 触发降级告警
    is_degraded: bool = False  # 任一字段缺失/降级
    degraded_fields: List[str] = field(default_factory=list)  # 缺失字段名列表
    fetch_time: str = ""  # ISO 时间戳
    cache_hit: bool = False  # 缓存命中
    is_stale: bool = (
        False  # 预留位：财报过期；当前由 check_finance_freshness() 单独判定
    )
    stale_reason: str = ""  # 预留位：过期原因
    last_error: str = ""  # 最后一次异常描述

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

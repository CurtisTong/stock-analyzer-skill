"""财务字段映射表。

从 data/__init__.py 迁出，作为独立模块便于维护和测试。
映射东财 API 原始字段名 → FinanceRecord 标准字段名。
"""

# 财务字段映射表（模块级常量，避免每次调用重建）
FINANCE_FIELD_MAP = {
    "report_date": [
        "REPORT_DATE",
        "REPORTDATETIME",
        "NOTICE_DATE",
        "报告日期",
        "截止日期",
        "report_date",
    ],
    "eps": ["EPSJB", "基本每股收益", "每股收益", "eps"],
    "roe": ["ROEJQ", "净资产收益率", "加权净资产收益率", "ROE", "roe"],
    "revenue_yoy": [
        "TOTALOPERATEREVETZ",
        "营业收入同比",
        "营收同比",
        "营业总收入同比增长率",
        "营收同比(%)",
        "revenue_yoy",
    ],
    "net_profit_yoy": [
        "PARENTNETPROFITTZ",
        "归母净利润同比",
        "净利润同比",
        "归母净利润同比增长率",
        "净利润同比(%)",
        "net_profit_yoy",
    ],
    "gross_margin": [
        "XSMLL",
        "销售毛利率",
        "毛利率",
        "毛利率(%)",
        "销售毛利率(%)",
        "gross_margin",
    ],
    "net_margin": [
        "XSJLL",
        "销售净利率",
        "净利率",
        "净利率(%)",
        "销售净利率(%)",
        "net_margin",
    ],
    "debt_ratio": ["ZCFZL", "资产负债率", "资产负债率(%)", "debt_ratio"],
    "bps": ["BPS", "每股净资产", "bps"],
    "ocf_per_share": [
        "MGJYXJJE",
        "每股经营现金流",
        "每股现金流量净额",
        "ocf_per_share",
    ],
    # 商誉/质押字段：东财资产负债表和质押 API 可提供
    "goodwill": ["GOODWILL", "商誉", "商誉(元)", "goodwill"],
    "pledge_ratio": ["PLEDGE_RATIO", "质押比例", "股权质押比例", "pledge_ratio"],
    "goodwill_ratio": ["GOODWILL_RATIO", "商誉占比", "商誉/总资产", "goodwill_ratio"],
    # ESG/分红/治理字段
    "dividend_yield": ["DIVIDENT_YIELD", "股息率", "DY", "dividend_yield"],
    "consecutive_dividend_years": [
        "CONSECUTIVE_DIVIDEND_YEARS",
        "连续分红年数",
        "LXFHNX",
        "consecutive_dividend_years",
    ],
    "major_shareholder_reduction": [
        "MAJOR_SHAREHOLDER_REDUCTION",
        "大股东减持比例",
        "DSGJCP",
        "major_shareholder_reduction",
    ],
    "violation_penalty": [
        "VIOLATION_PENALTY",
        "违规处罚金额",
        "WGCFJE",
        "violation_penalty",
    ],
    "audit_opinion": [
        "AUDIT_OPINION",
        "审计意见类型",
        "SJYJ",
        "OPINION_TYPE",
        "audit_opinion",
    ],
    # 绝对值字段（东财返回"元"，__init__._dict_to_finance 层 /1e8 转亿元）
    "total_revenue": [
        "TOTALOPERATEREVE",
        "营业总收入",
        "营业收入",
        "total_revenue",
    ],
    "parent_net_profit": [
        "PARENTNETPROFIT",
        "归母净利润",
        "归属母公司净利润",
        "parent_net_profit",
    ],
    "deducted_net_profit": [
        "KCFJCXSYJLR",
        "扣非净利润",
        "扣除非经常性损益净利润",
        "deducted_net_profit",
    ],
    "total_liability": [
        "LIABILITY",
        "负债合计",
        "负债总额",
        "total_liability",
    ],
    "fcf": [
        "FCFF_FORWARD",
        "FCFF_BACK",
        "自由现金流",
        "fcf",
    ],
    # 偿债能力 + 季度环比维度
    "quick_ratio": ["SD", "速动比率", "quick_ratio"],
    "current_ratio": ["LD", "流动比率", "current_ratio"],
    "deducted_np_yoy": [
        "DJD_DEDUCTDPNP_YOY",
        "KCFJCXSYJLRTZ",
        "扣非净利同比",
        "扣除非经常性损益净利润同比增长率",
        "deducted_np_yoy",
    ],
    "revenue_qoq": ["DJD_TOI_QOQ", "营收环比", "营业收入环比", "revenue_qoq"],
    "profit_qoq": ["DJD_DPNP_QOQ", "净利环比", "归母净利润环比", "profit_qoq"],
    "gross_margin_qoq": [
        "XSMLL_TB",
        "毛利率环比",
        "毛利率同比",
        "gross_margin_qoq",
    ],
}

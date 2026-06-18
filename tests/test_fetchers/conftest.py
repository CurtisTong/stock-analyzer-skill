"""fetcher 测试共享 fixtures。"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ---------- 腾讯行情 mock 数据 ----------

TENCENT_RAW = (
    'v_sh600519="1~贵州茅台~600519~1800.00~1790.00~1795.00~12345~6000~6345~'
    "1800.50~100~1799.00~200~1799.50~150~1798.00~250~1798.50~180~"
    "15:00:03/1800.00/100/S/180000/12345|14:59:57/1799.50/50/B/89975/12340~"
    "20250612150003~10.00~0.56~1810.00~1790.00~1800.00/12345/2234567~"
    "12345~2234567.00~0.15~25.60~~1810.00~1790.00~1.12~22600.00~22600.00~"
    "8.20~2069.00~1611.00~1.00~2078.90~1603.10~"
    "1234567890~1234567890~1234567890~1234567890~1234567890~1234567890~"
    "1234567890~1234567890~1234567890~1234567890~1234567890~1234567890~"
    '1234567890~1234567890~1234567890~1234567890";'
)


def make_tencent_raw(**overrides):
    """生成腾讯行情 raw bytes，可覆盖任意字段。"""
    return TENCENT_RAW.encode("gbk")


# ---------- 腾讯 K 线 mock 数据 ----------

TENCENT_KLINE_RESP = {
    "code": 0,
    "data": {
        "sh600519": {
            "qfqday": [
                ["2025-06-10", "1790.00", "1800.00", "1810.00", "1785.00", "12345"],
                ["2025-06-11", "1800.00", "1805.00", "1815.00", "1795.00", "11000"],
                ["2025-06-12", "1805.00", "1800.00", "1810.00", "1790.00", "12345"],
            ]
        }
    },
}


def make_tencent_kline_raw(data=None):
    return json.dumps(data or TENCENT_KLINE_RESP).encode()


# ---------- 东方财富行情 mock 数据 ----------

EASTMONEY_QUOTE_RESP = {
    "rc": 0,
    "data": {
        "f57": "600519",
        "f58": "贵州茅台",
        "f43": 180000,
        "f60": 179000,
        "f46": 179500,
        "f170": 56,
        "f169": 1000,
        "f44": 181000,
        "f45": 179000,
        "f47": 12345,
        "f48": 22345670000,
        "f168": 15,
        "f162": 2560,
        "f167": 820,
        "f116": 2260000000000,
        "f117": 2260000000000,
    },
}


def make_eastmoney_quote_raw(data=None):
    return json.dumps(data or EASTMONEY_QUOTE_RESP).encode()


# ---------- 东方财富 K 线 mock 数据 ----------

EASTMONEY_KLINE_RESP = {
    "rc": 0,
    "data": {
        "klines": [
            "2025-06-10,1790.00,1800.00,1810.00,1785.00,12345,2234567,1.12,25.00,1.50,180000",
            "2025-06-11,1800.00,1805.00,1815.00,1795.00,11000,2000000,0.56,18.00,0.80,180500",
            "2025-06-12,1805.00,1800.00,1810.00,1790.00,12345,2234567,-0.28,25.00,1.12,180000",
        ],
    },
}


def make_eastmoney_kline_raw(data=None):
    return json.dumps(data or EASTMONEY_KLINE_RESP).encode()


# ---------- 东方财富财务 mock 数据 ----------

EASTMONEY_FINANCE_RESP = {
    "data": [
        {
            "REPORT_DATE": "2025-03-31",
            "EPSJB": "15.00",
            "ROEJQ": "8.5",
            "TOTALOPERATEREVETZ": "12.3",
            "PARENTNETPROFITTZ": "15.6",
        },
        {
            "REPORT_DATE": "2024-12-31",
            "EPSJB": "50.00",
            "ROEJQ": "30.5",
            "TOTALOPERATEREVETZ": "15.2",
            "PARENTNETPROFITTZ": "18.3",
        },
    ],
}


def make_eastmoney_finance_raw(data=None):
    return json.dumps(data or EASTMONEY_FINANCE_RESP).encode()


# ---------- 新浪行情 mock 数据 ----------

SINA_RAW = (
    'var hq_str_sh600519="贵州茅台,1795.00,1790.00,1800.00,1810.00,1790.00,'
    "1799.00,1800.50,1234500,2234567000.00,"
    "100,1799.00,200,1799.50,150,1798.00,250,1798.50,180,"
    "15:00:03,2025-06-12,01,10.00,0.56,1810.00,1790.00,1.12,22600.00,22600.00,"
    '8.20,2069.00,1611.00,1.00";'
)


def make_sina_raw():
    return SINA_RAW.encode("gbk")


# ---------- 新浪 K 线 mock 数据 ----------

SINA_KLINE_RESP = [
    {
        "day": "2025-06-10",
        "open": "1790.00",
        "high": "1810.00",
        "low": "1785.00",
        "close": "1800.00",
        "volume": "12345",
    },
    {
        "day": "2025-06-11",
        "open": "1800.00",
        "high": "1815.00",
        "low": "1795.00",
        "close": "1805.00",
        "volume": "11000",
    },
    {
        "day": "2025-06-12",
        "open": "1805.00",
        "high": "1810.00",
        "low": "1790.00",
        "close": "1800.00",
        "volume": "12345",
    },
]


def make_sina_kline_raw(data=None):
    return json.dumps(data or SINA_KLINE_RESP).encode()


# ---------- 雪球行情 mock 数据 ----------

XUEQIU_QUOTE_RESP = {
    "data": {
        "quote": {
            "symbol": "SH600519",
            "name": "贵州茅台",
            "current": 1800.00,
            "open": 1795.00,
            "high": 1810.00,
            "low": 1790.00,
            "last_close": 1790.00,
            "volume": 1234500,
            "amount": 2234567000.00,
            "turnover_rate": 0.15,
            "pe_ttm": 25.60,
            "pb": 8.20,
            "market_capital": 2260000000000,
        }
    }
}


def make_xueqiu_raw(data=None):
    return json.dumps(data or XUEQIU_QUOTE_RESP).encode()


# ---------- 同花顺行情 mock 数据 ----------

THS_RAW = '{"data":"2025-06-10,1790.00,1810.00,1785.00,1800.00,12345;2025-06-11,1800.00,1815.00,1795.00,1805.00,11000;2025-06-12,1805.00,1810.00,1790.00,1800.00,12345"}'


def make_ths_raw():
    return THS_RAW.encode("utf-8")


# ---------- 北向资金 mock 数据 ----------

NORTHBOUND_RESP = {
    "rc": 0,
    "data": {
        "s2n": [
            "2025-06-10,100000,50000,50000",
            "2025-06-11,120000,60000,60000",
        ],
        "n2s": [
            "2025-06-10,80000,40000,40000",
            "2025-06-11,90000,45000,45000",
        ],
    },
}


def make_northbound_raw(data=None):
    return json.dumps(data or NORTHBOUND_RESP).encode()


# ---------- 个股资金流向 mock 数据 ----------

STOCK_FLOW_RESP = {
    "rc": 0,
    "data": {
        "klines": [
            "2025-06-10,5000,10.5,3000,6.3,2000,4.2,1500,3.1,500,1.0",
            "2025-06-11,6000,12.0,4000,8.0,2000,4.0,1000,2.0,500,1.0",
        ],
    },
}


def make_stock_flow_raw(data=None):
    return json.dumps(data or STOCK_FLOW_RESP).encode()


# ---------- 龙虎榜 mock 数据 ----------

LHB_DETAIL_RESP = {
    "success": True,
    "result": {
        "data": [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "TRADE_DATE": "2025-06-12",
                "CLOSE_PRICE": 1800.00,
                "CHANGE_RATE": 0.56,
                "TURNOVERRATE": 0.15,
                "NET_BUY_AMT": 50000000,
                "BUY_AMT": 100000000,
                "SELL_AMT": 50000000,
                "EXPLANATION": "涨幅偏离值达7%的证券",
            },
        ],
    },
}


def make_lhb_detail_raw(data=None):
    return json.dumps(data or LHB_DETAIL_RESP).encode()


LHB_SEAT_RESP = {
    "success": True,
    "result": {
        "data": [
            {
                "BUYER_NAME": "机构专用",
                "BUY_AMT": 50000000,
                "BUY_AMT_RATIO": 10.5,
                "SELL_AMT": 0,
                "EXPLANATION": "涨幅偏离值达7%的证券",
            },
        ],
    },
}


def make_lhb_seat_raw(data=None):
    return json.dumps(data or LHB_SEAT_RESP).encode()


# ---------- 事件日历 mock 数据 ----------

EARNINGS_RESP = {
    "success": True,
    "result": {
        "data": [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "REPORT_DATE": "2025-03-31",
                "OP_DATE": "2025-04-30",
                "OP_CHANGE": "",
                "PREPLAN_DATE": "",
            },
        ],
    },
}


def make_earnings_raw(data=None):
    return json.dumps(data or EARNINGS_RESP).encode()


LOCKUP_RESP = {
    "success": True,
    "result": {
        "data": [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "FREE_DATE": "2025-07-01",
                "LIFT_NUM": 1000000,
                "LIFT_MARKET_CAP": 1800000000,
                "NEW_PRICE": 1800.00,
            },
        ],
    },
}


def make_lockup_raw(data=None):
    return json.dumps(data or LOCKUP_RESP).encode()


DIVIDEND_RESP = {
    "success": True,
    "result": {
        "data": [
            {
                "SECURITY_CODE": "600519",
                "SECURITY_NAME_ABBR": "贵州茅台",
                "EX_DIVIDEND_DATE": "2025-07-15",
                "PRETAX_BONUS_RMB": 50.00,
                "PLAN_NOTICE_DATE": "2025-06-01",
                "REG_DATE": "2025-07-14",
            },
        ],
    },
}


def make_dividend_raw(data=None):
    return json.dumps(data or DIVIDEND_RESP).encode()


# ---------- 融资融券 mock 数据 ----------

MARGIN_RESP = {
    "success": True,
    "result": {
        "data": [
            {
                "TRADE_DATE": "2025-06-12",
                "RZYE": 100000000,
                "RQYE": 5000000,
                "RZMRE": 20000000,
                "RZCHE": 15000000,
                "RZJME": 5000000,
                "RQMCL": 100000,
                "RQCHL": 80000,
                "RQJMG": 20000,
                "RQYL": 500000,
            },
        ],
    },
}


def make_margin_raw(data=None):
    return json.dumps(data or MARGIN_RESP).encode()


# ---------- 股东户数 mock 数据 ----------

HOLDER_RESP = {
    "gdrs": [
        {
            "END_DATE": "2025-03-31",
            "HOLDER_TOTAL_NUM": 50000,
            "AVG_FREE_SHARES": 10000,
            "TOTAL_NUM_RATIO": -5.2,
            "HOLD_FOCUS": "相对集中",
        },
    ],
}


def make_holder_raw(data=None):
    return json.dumps(data or HOLDER_RESP).encode()


# ---------- 十大流通股东 mock 数据 ----------

TOP_HOLDER_RESP = {
    "sdltgd": [
        {
            "END_DATE": "2025-03-31",
            "HOLDER_RANK": 1,
            "HOLDER_NAME": "中国证券金融股份有限公司",
            "SHARES_TYPE": "流通A股",
            "HOLD_NUM": 100000000,
            "HOLD_NUM_RATIO": 8.0,
            "HOLD_NUM_CHANGE": 5000000,
        },
        {
            "END_DATE": "2025-03-31",
            "HOLDER_RANK": 2,
            "HOLDER_NAME": "招商银行股份有限公司-某基金",
            "SHARES_TYPE": "流通A股",
            "HOLD_NUM": 50000000,
            "HOLD_NUM_RATIO": 4.0,
            "HOLD_NUM_CHANGE": -2000000,
        },
    ],
}


def make_top_holder_raw(data=None):
    return json.dumps(data or TOP_HOLDER_RESP).encode()

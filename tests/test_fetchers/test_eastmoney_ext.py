"""东方财富扩展数据源测试：资金流向 + 龙虎榜 + 事件日历 + 筹码。"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from fetchers.flow.eastmoney_flow import NorthboundFlowFetcher, StockFlowFetcher
from fetchers.lhb.eastmoney_lhb import LhbDetailFetcher, LhbSeatFetcher
from fetchers.event.eastmoney_event import (
    EarningsCalendarFetcher,
    LockupCalendarFetcher,
    DividendCalendarFetcher,
)
from fetchers.chip.eastmoney_chip import MarginFetcher, HolderFetcher, TopHolderFetcher
from common.exceptions import NetworkError

# ═══════════════════════════════════════════════════════════════
# 资金流向
# ═══════════════════════════════════════════════════════════════


class TestNorthboundFlowFetcher:
    def setup_method(self):
        self.fetcher = NorthboundFlowFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "northbound_flow"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
            "rc": 0,
            "data": {
                "s2n": ["2025-06-10,100000,50000,50000"],
                "n2s": ["2025-06-10,80000,40000,40000"],
            },
        }
        with patch(
            "fetchers.flow.eastmoney_flow.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is not None
        assert result["type"] == "northbound"
        assert len(result["days"]) == 1
        assert result["days"][0]["sh_net"] == 50000.0
        assert result["days"][0]["sz_net"] == 40000.0
        assert result["days"][0]["total_net"] == 90000.0

    def test_fetch_empty(self):
        with patch("fetchers.flow.eastmoney_flow.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("")
        assert result is None

    def test_fetch_invalid_json(self):
        with patch("fetchers.flow.eastmoney_flow.http_get", return_value=b"bad"):
            result = self.fetcher.fetch("")
        assert result is None

    def test_fetch_rc_not_zero(self):
        data = {"rc": -1}
        with patch(
            "fetchers.flow.eastmoney_flow.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is None

    def test_fetch_http_error(self):
        with patch(
            "fetchers.flow.eastmoney_flow.http_get",
            side_effect=NetworkError("url", "err", 3),
        ):
            with pytest.raises(NetworkError):
                self.fetcher.fetch("")


class TestStockFlowFetcher:
    def setup_method(self):
        self.fetcher = StockFlowFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "stock_flow"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
            "rc": 0,
            "data": {
                "klines": [
                    "2025-06-10,5000,10.5,3000,6.3,2000,4.2,1500,3.1,500,1.0",
                    "2025-06-11,6000,12.0,4000,8.0,2000,4.0,1000,2.0,500,1.0",
                ],
            },
        }
        with patch(
            "fetchers.flow.eastmoney_flow.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result["type"] == "stock_flow"
        assert result["code"] == "sh600519"
        assert len(result["days"]) == 2
        assert "summary" in result
        assert "main_net_5d" in result["summary"]

    def test_fetch_empty(self):
        with patch("fetchers.flow.eastmoney_flow.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_empty_klines(self):
        data = {"rc": 0, "data": {"klines": []}}
        with patch(
            "fetchers.flow.eastmoney_flow.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 龙虎榜
# ═══════════════════════════════════════════════════════════════


class TestLhbDetailFetcher:
    def setup_method(self):
        self.fetcher = LhbDetailFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "lhb_detail"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
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
                        "EXPLANATION": "涨幅偏离值达7%",
                    },
                ],
            },
        }
        with patch(
            "fetchers.lhb.eastmoney_lhb.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is not None
        assert result["type"] == "lhb_detail"
        assert len(result["items"]) == 1
        assert result["items"][0]["code"] == "600519"

    def test_fetch_filter_by_code(self):
        data = {
            "success": True,
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "茅台",
                        "TRADE_DATE": "2025-06-12",
                    },
                    {
                        "SECURITY_CODE": "000858",
                        "SECURITY_NAME_ABBR": "五粮液",
                        "TRADE_DATE": "2025-06-12",
                    },
                ],
            },
        }
        with patch(
            "fetchers.lhb.eastmoney_lhb.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result["items"]) == 1
        assert result["items"][0]["code"] == "600519"

    def test_fetch_empty(self):
        with patch("fetchers.lhb.eastmoney_lhb.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("")
        assert result is None

    def test_fetch_success_false(self):
        data = {"success": False}
        with patch(
            "fetchers.lhb.eastmoney_lhb.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is None


class TestLhbSeatFetcher:
    def setup_method(self):
        self.fetcher = LhbSeatFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "lhb_seat"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        buy_data = {
            "success": True,
            "result": {
                "data": [
                    {
                        "BUYER_NAME": "机构专用",
                        "BUY_AMT": 50000000,
                        "BUY_AMT_RATIO": 10.5,
                        "SELL_AMT": 0,
                    }
                ]
            },
        }
        sell_data = {
            "success": True,
            "result": {
                "data": [
                    {
                        "SELLER_NAME": "某券商",
                        "SELL_AMT": 30000000,
                        "SELL_AMT_RATIO": 6.3,
                        "BUY_AMT": 0,
                    }
                ]
            },
        }
        with patch(
            "fetchers.lhb.eastmoney_lhb.http_get",
            side_effect=[
                json.dumps(buy_data).encode(),
                json.dumps(sell_data).encode(),
            ],
        ):
            result = self.fetcher.fetch("sh600519", date="2025-06-12")
        assert result is not None
        assert result["type"] == "lhb_seat"
        assert len(result["buy_seats"]) == 1
        assert len(result["sell_seats"]) == 1

    def test_fetch_empty(self):
        with patch("fetchers.lhb.eastmoney_lhb.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519", date="2025-06-12")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 事件日历
# ═══════════════════════════════════════════════════════════════


class TestEarningsCalendarFetcher:
    def setup_method(self):
        self.fetcher = EarningsCalendarFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "earnings_calendar"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
            "success": True,
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "REPORT_DATE": "2025-03-31",
                        "OP_DATE": "2025-04-30",
                    },
                ],
            },
        }
        with patch(
            "fetchers.event.eastmoney_event.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is not None
        assert result["type"] == "earnings"
        assert len(result["items"]) == 1

    def test_fetch_empty(self):
        with patch("fetchers.event.eastmoney_event.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("")
        assert result is None

    def test_fetch_success_false(self):
        data = {"success": False}
        with patch(
            "fetchers.event.eastmoney_event.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is None


class TestLockupCalendarFetcher:
    def setup_method(self):
        self.fetcher = LockupCalendarFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "lockup_calendar"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
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
        with patch(
            "fetchers.event.eastmoney_event.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is not None
        assert result["type"] == "lockup"

    def test_fetch_empty(self):
        with patch("fetchers.event.eastmoney_event.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("")
        assert result is None


class TestDividendCalendarFetcher:
    def setup_method(self):
        self.fetcher = DividendCalendarFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "dividend_calendar"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
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
        with patch(
            "fetchers.event.eastmoney_event.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("")
        assert result is not None
        assert result["type"] == "dividend"
        assert result["items"][0]["bonus_per_share"] == 50.0

    def test_fetch_empty(self):
        with patch("fetchers.event.eastmoney_event.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 筹码（融资融券 + 股东户数 + 十大流通股东）
# ═══════════════════════════════════════════════════════════════


class TestMarginFetcher:
    def setup_method(self):
        self.fetcher = MarginFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "margin"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
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
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 1
        assert result[0]["date"] == "2025-06-12"
        assert result[0]["rzye"] == 100000000.0

    def test_fetch_empty(self):
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_success_false(self):
        data = {"success": False}
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_invalid_json(self):
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=b"bad"):
            result = self.fetcher.fetch("sh600519")
        assert result is None


class TestHolderFetcher:
    def setup_method(self):
        self.fetcher = HolderFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "holder"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
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
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 1
        assert result[0]["holder_num"] == 50000
        assert result[0]["concentration"] == "一般"

    def test_fetch_concentration_levels(self):
        """测试集中度评级。"""
        for focus, expected in [
            ("非常集中", "集中"),
            ("比较集中", "集中"),
            ("相对集中", "一般"),
            ("非常分散", "分散"),
            ("比较分散", "分散"),
        ]:
            data = {
                "gdrs": [
                    {
                        "END_DATE": "2025-03-31",
                        "HOLDER_TOTAL_NUM": 100,
                        "AVG_FREE_SHARES": 100,
                        "TOTAL_NUM_RATIO": 0,
                        "HOLD_FOCUS": focus,
                    }
                ]
            }
            with patch(
                "fetchers.chip.eastmoney_chip.http_get",
                return_value=json.dumps(data).encode(),
            ):
                result = self.fetcher.fetch("sh600519")
            assert result is not None
            assert result[0]["concentration"] == expected

    def test_fetch_empty_gdrs(self):
        data = {"gdrs": []}
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_no_gdrs_key(self):
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519")
        assert result is None


class TestTopHolderFetcher:
    def setup_method(self):
        self.fetcher = TopHolderFetcher()

    def test_name_and_priority(self):
        assert self.fetcher.name == "top_holder"
        assert self.fetcher.priority == 5

    def test_fetch_normal(self):
        data = {
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
            ],
        }
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert len(result) == 1
        assert result[0]["rank"] == 1
        assert result[0]["change_type"] == "增持"
        assert result[0]["is_institution"] is True

    def test_fetch_institution_detection(self):
        """机构识别。"""
        data = {
            "sdltgd": [
                {
                    "END_DATE": "2025-03-31",
                    "HOLDER_RANK": 1,
                    "HOLDER_NAME": "某基金有限公司",
                    "SHARES_TYPE": "流通A股",
                    "HOLD_NUM": 100000,
                    "HOLD_NUM_RATIO": 1.0,
                    "HOLD_NUM_CHANGE": 0,
                },
                {
                    "END_DATE": "2025-03-31",
                    "HOLDER_RANK": 2,
                    "HOLDER_NAME": "张三",
                    "SHARES_TYPE": "流通A股",
                    "HOLD_NUM": 50000,
                    "HOLD_NUM_RATIO": 0.5,
                    "HOLD_NUM_CHANGE": 0,
                },
            ],
        }
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result[0]["is_institution"] is True
        assert result[1]["is_institution"] is False

    def test_fetch_change_types(self):
        """变动类型：增持/减持/不变（通过数值推断）。"""
        data = {
            "sdltgd": [
                {
                    "END_DATE": "2025-03-31",
                    "HOLDER_RANK": 1,
                    "HOLDER_NAME": "A",
                    "SHARES_TYPE": "流通A股",
                    "HOLD_NUM": 100,
                    "HOLD_NUM_RATIO": 1.0,
                    "HOLD_NUM_CHANGE": 5000000,
                },
                {
                    "END_DATE": "2025-03-31",
                    "HOLDER_RANK": 2,
                    "HOLDER_NAME": "B",
                    "SHARES_TYPE": "流通A股",
                    "HOLD_NUM": 100,
                    "HOLD_NUM_RATIO": 1.0,
                    "HOLD_NUM_CHANGE": -2000000,
                },
                {
                    "END_DATE": "2025-03-31",
                    "HOLDER_RANK": 3,
                    "HOLDER_NAME": "C",
                    "SHARES_TYPE": "流通A股",
                    "HOLD_NUM": 100,
                    "HOLD_NUM_RATIO": 1.0,
                    "HOLD_NUM_CHANGE": 0,
                },
            ],
        }
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result[0]["change_type"] == "增持"
        assert result[1]["change_type"] == "减持"
        assert result[2]["change_type"] == "不变"

    def test_fetch_change_type_from_api_field(self):
        """变动类型：通过 API 的 CHANGE_TYPE 字段识别"新进"。"""
        data = {
            "sdltgd": [
                {
                    "END_DATE": "2025-03-31",
                    "HOLDER_RANK": 1,
                    "HOLDER_NAME": "A",
                    "SHARES_TYPE": "流通A股",
                    "HOLD_NUM": 100,
                    "HOLD_NUM_RATIO": 1.0,
                    "HOLD_NUM_CHANGE": 5000000,
                    "CHANGE_TYPE": "新进",
                },
                {
                    "END_DATE": "2025-03-31",
                    "HOLDER_RANK": 2,
                    "HOLDER_NAME": "B",
                    "SHARES_TYPE": "流通A股",
                    "HOLD_NUM": 100,
                    "HOLD_NUM_RATIO": 1.0,
                    "HOLD_NUM_CHANGE": 3000000,
                    "CHANGE_TYPE": "增持",
                },
            ],
        }
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is not None
        assert result[0]["change_type"] == "新进"
        assert result[1]["change_type"] == "增持"

    def test_fetch_empty_sdltgd(self):
        data = {"sdltgd": []}
        with patch(
            "fetchers.chip.eastmoney_chip.http_get", return_value=json.dumps(data).encode()
        ):
            result = self.fetcher.fetch("sh600519")
        assert result is None

    def test_fetch_no_sdltgd_key(self):
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=b"{}"):
            result = self.fetcher.fetch("sh600519")
        assert result is None

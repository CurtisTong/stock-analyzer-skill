"""lhb / event fetcher 单元测试。

覆盖龙虎榜与事件日历 fetcher 的关键路径，弥补此前零测试覆盖：

lhb（scripts/fetchers/lhb/eastmoney_lhb.py）：
  - LhbDetailFetcher：正常解析 / 日期 null（回归）/ 空结果 / JSON 解析失败 / 分页（回归）
  - LhbSeatFetcher：正常解析买卖席位 / 空结果

event（scripts/fetchers/event/eastmoney_event.py）：
  - EarningsCalendarFetcher：正常解析 / 日期 null / 空结果 / JSON 解析失败 / 分页
  - ShareholderChangeFetcher：正常解析 / 无 code 返回 None / 空结果

event/performance_forecast.py：
  - PerformanceForecastFetcher：正常解析 / 预告类型映射 / 无 code / 空结果 / 分页

设计：
- 用 monkeypatch 替换 fetcher 模块内导入的 http_get（from common import http_get
  后 http_get 是模块属性），返回模拟 JSON 字节，不依赖真实网络。
- 模拟 JSON 符合东财 datacenter 返回结构：
  {"success": True, "result": {"pages": N, "data": [...]}}
  （performance_forecast 不依赖 success 字段，用 "result" in data 判断）
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ═══════════════════════════════════════════════════════════════
# 辅助：构造 mock http_get
# ═══════════════════════════════════════════════════════════════


def _make_json_getter(response: Any):
    """构造返回固定 JSON 字节的 http_get 替身。

    response 可以是 dict（序列化为 JSON bytes）或 bytes（原样返回）。
    """

    def _http_get(url, timeout=10, max_retries=3):
        if isinstance(response, (bytes, bytearray)):
            return response
        return json.dumps(response).encode("utf-8")

    return _http_get


def _make_paged_getter(pages_response: list):
    """构造按调用次序返回不同页响应的 http_get 替身。

    pages_response[i] 对应第 i+1 次调用的返回（dict 或 bytes）。
    """

    state = {"idx": 0}

    def _http_get(url, timeout=10, max_retries=3):
        i = state["idx"]
        state["idx"] += 1
        resp = pages_response[i]
        if isinstance(resp, (bytes, bytearray)):
            return resp
        return json.dumps(resp).encode("utf-8")

    return _http_get


# ═══════════════════════════════════════════════════════════════
# LhbDetailFetcher
# ═══════════════════════════════════════════════════════════════


class TestLhbDetailFetcher:
    """龙虎榜明细数据源。"""

    def test_normal_parse(self, monkeypatch):
        """有效 JSON -> 正确解析字段（code/name/date/close/change_pct 等）。"""
        import fetchers.lhb.eastmoney_lhb as mod

        payload = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "TRADE_DATE": "2026-08-01T00:00:00",
                        "CLOSE_PRICE": "1800.50",
                        "CHANGE_RATE": "1.23",
                        "TURNOVERRATE": "0.15",
                        "NET_BUY_AMT": "5000000",
                        "BUY_AMT": "8000000",
                        "SELL_AMT": "3000000",
                        "EXPLANATION": "日涨幅偏离值达7%",
                    }
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.LhbDetailFetcher().fetch("")

        assert result is not None
        assert result["type"] == "lhb_detail"
        assert result["truncated"] is False
        item = result["items"][0]
        assert item["code"] == "600519"
        assert item["name"] == "贵州茅台"
        assert item["date"] == "2026-08-01"  # [:10] 截断
        assert item["close"] == 1800.5
        assert item["change_pct"] == 1.23
        assert item["turnover_rate"] == 0.15
        assert item["net_buy"] == 5000000.0
        assert item["buy_total"] == 8000000.0
        assert item["sell_total"] == 3000000.0
        assert item["reason"] == "日涨幅偏离值达7%"

    def test_null_date_returns_empty_string(self, monkeypatch):
        """回归：TRADE_DATE 为 null 时不崩溃，date 为 ''。

        历史 P0 bug：日期字段为 None 时 [:10] 报 TypeError。
        修复后用 (r.get(...) or "")[:10] 防御。
        """
        import fetchers.lhb.eastmoney_lhb as mod

        payload = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "TRADE_DATE": None,
                        "CLOSE_PRICE": "1800.5",
                    }
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.LhbDetailFetcher().fetch("")

        assert result is not None
        assert result["items"][0]["date"] == ""

    def test_empty_result_returns_none(self, monkeypatch):
        """result.data 为空列表 -> 返回 None。"""
        import fetchers.lhb.eastmoney_lhb as mod

        payload = {"success": True, "result": {"pages": 1, "data": []}}
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.LhbDetailFetcher().fetch("")

        assert result is None

    def test_json_decode_failure_returns_none(self, monkeypatch):
        """http_get 返回非 JSON -> JSONDecodeError 中断循环，无记录 -> None。"""
        import fetchers.lhb.eastmoney_lhb as mod

        monkeypatch.setattr(mod, "http_get", _make_json_getter(b"not json{"))

        result = mod.LhbDetailFetcher().fetch("")

        assert result is None

    def test_success_false_returns_none(self, monkeypatch):
        """success=False -> 中断抓取，返回 None。"""
        import fetchers.lhb.eastmoney_lhb as mod

        payload = {"success": False, "result": {"pages": 1, "data": [{"x": 1}]}}
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.LhbDetailFetcher().fetch("")

        assert result is None

    def test_pagination_accumulates_multiple_pages(self, monkeypatch):
        """回归：第一页 pages=2，第二页有更多数据，应累积两页记录。

        历史 P1 问题：分页循环未正确累积所有页。
        """
        import fetchers.lhb.eastmoney_lhb as mod

        page1 = {
            "success": True,
            "result": {
                "pages": 2,
                "data": [
                    {"SECURITY_CODE": "600519", "TRADE_DATE": "2026-08-01"},
                    {"SECURITY_CODE": "000001", "TRADE_DATE": "2026-08-01"},
                ],
            },
        }
        page2 = {
            "success": True,
            "result": {
                "pages": 2,
                "data": [
                    {"SECURITY_CODE": "600519", "TRADE_DATE": "2026-08-02"},
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_paged_getter([page1, page2]))

        result = mod.LhbDetailFetcher().fetch("")

        assert result is not None
        assert len(result["items"]) == 3
        codes = [i["code"] for i in result["items"]]
        assert codes == ["600519", "000001", "600519"]
        assert result["truncated"] is False

    def test_code_filter(self, monkeypatch):
        """指定 code 时只返回该股票的记录。"""
        import fetchers.lhb.eastmoney_lhb as mod

        payload = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {"SECURITY_CODE": "600519", "TRADE_DATE": "2026-08-01"},
                    {"SECURITY_CODE": "000001", "TRADE_DATE": "2026-08-01"},
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.LhbDetailFetcher().fetch("sh600519")

        assert result is not None
        assert len(result["items"]) == 1
        assert result["items"][0]["code"] == "600519"


# ═══════════════════════════════════════════════════════════════
# LhbSeatFetcher
# ═══════════════════════════════════════════════════════════════


class TestLhbSeatFetcher:
    """龙虎榜买卖席位数据源。"""

    def test_normal_parse_buy_and_sell_seats(self, monkeypatch):
        """正常解析买出席位与卖出席位。

        LhbSeatFetcher 内部对买入席位和卖出席位各发一次分页请求，
        mock 按次序返回买/卖两页。
        """
        import fetchers.lhb.eastmoney_lhb as mod

        buy_page = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {
                        "BUYER_NAME": "机构专用",
                        "BUY_AMT": "10000000",
                        "BUY_AMT_RATIO": "5.0",
                        "SELL_AMT": "2000000",
                        "EXPLANATION": "机构净买入",
                    }
                ],
            },
        }
        sell_page = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SELLER_NAME": "华泰证券",
                        "SELL_AMT": "8000000",
                        "SELL_AMT_RATIO": "4.0",
                        "BUY_AMT": "1000000",
                    }
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_paged_getter([buy_page, sell_page]))

        result = mod.LhbSeatFetcher().fetch("sh600519", date="2026-08-01")

        assert result is not None
        assert result["type"] == "lhb_seat"
        assert result["code"] == "600519"
        assert result["date"] == "2026-08-01"
        assert len(result["buy_seats"]) == 1
        assert result["buy_seats"][0]["name"] == "机构专用"
        assert result["buy_seats"][0]["buy_amt"] == 10000000.0
        assert result["buy_seats"][0]["buy_pct"] == 5.0
        assert len(result["sell_seats"]) == 1
        assert result["sell_seats"][0]["name"] == "华泰证券"
        assert result["sell_seats"][0]["sell_amt"] == 8000000.0

    def test_empty_buy_records_returns_none(self, monkeypatch):
        """买入席位无数据 -> 返回 None。"""
        import fetchers.lhb.eastmoney_lhb as mod

        buy_page = {"success": True, "result": {"pages": 1, "data": []}}
        monkeypatch.setattr(mod, "http_get", _make_json_getter(buy_page))

        result = mod.LhbSeatFetcher().fetch("sh600519", date="2026-08-01")

        assert result is None


# ═══════════════════════════════════════════════════════════════
# EarningsCalendarFetcher
# ═══════════════════════════════════════════════════════════════


class TestEarningsCalendarFetcher:
    """财报披露日历数据源。"""

    def test_normal_parse(self, monkeypatch):
        """有效 JSON -> 正确解析 report_date / disclosure_date / change。"""
        import fetchers.event.eastmoney_event as mod

        payload = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "REPORT_DATE": "2026-06-30T00:00:00",
                        "OP_DATE": "2026-08-01T00:00:00",
                        "OP_CHANGE": "提前",
                    }
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.EarningsCalendarFetcher().fetch("")

        assert result is not None
        assert result["type"] == "earnings"
        item = result["items"][0]
        assert item["code"] == "600519"
        assert item["name"] == "贵州茅台"
        assert item["report_date"] == "2026-06-30"
        assert item["disclosure_date"] == "2026-08-01"
        assert item["change"] == "提前"

    def test_null_date_fields_return_empty_string(self, monkeypatch):
        """回归：REPORT_DATE / OP_DATE 为 null -> 对应字段为 ''。"""
        import fetchers.event.eastmoney_event as mod

        payload = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {"SECURITY_CODE": "600519", "REPORT_DATE": None, "OP_DATE": None}
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.EarningsCalendarFetcher().fetch("")

        assert result is not None
        assert result["items"][0]["report_date"] == ""
        assert result["items"][0]["disclosure_date"] == ""

    def test_empty_result_returns_none(self, monkeypatch):
        """result.data 为空 -> 返回 None。"""
        import fetchers.event.eastmoney_event as mod

        payload = {"success": True, "result": {"pages": 1, "data": []}}
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.EarningsCalendarFetcher().fetch("")

        assert result is None

    def test_json_decode_failure_returns_none(self, monkeypatch):
        """非 JSON -> None。"""
        import fetchers.event.eastmoney_event as mod

        monkeypatch.setattr(mod, "http_get", _make_json_getter(b"<<<garbage"))

        result = mod.EarningsCalendarFetcher().fetch("")

        assert result is None

    def test_pagination_accumulates_pages(self, monkeypatch):
        """回归：pages=2，累积两页记录。"""
        import fetchers.event.eastmoney_event as mod

        page1 = {
            "success": True,
            "result": {
                "pages": 2,
                "data": [
                    {"SECURITY_CODE": "600519", "OP_DATE": "2026-08-01"},
                    {"SECURITY_CODE": "000001", "OP_DATE": "2026-08-02"},
                ],
            },
        }
        page2 = {
            "success": True,
            "result": {
                "pages": 2,
                "data": [{"SECURITY_CODE": "600519", "OP_DATE": "2026-08-03"}],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_paged_getter([page1, page2]))

        result = mod.EarningsCalendarFetcher().fetch("")

        assert result is not None
        assert len(result["items"]) == 3


# ═══════════════════════════════════════════════════════════════
# ShareholderChangeFetcher
# ═══════════════════════════════════════════════════════════════


class TestShareholderChangeFetcher:
    """大股东增减持数据源。"""

    def test_no_code_returns_none(self, monkeypatch):
        """无 code 时直接返回 None，不发请求。"""
        import fetchers.event.eastmoney_event as mod

        called = []

        def _no_call(url, timeout=10, max_retries=3):
            called.append(url)
            return b"{}"

        monkeypatch.setattr(mod, "http_get", _no_call)

        result = mod.ShareholderChangeFetcher().fetch("")

        assert result is None
        assert called == []  # 未发请求

    def test_normal_parse_increase(self, monkeypatch):
        """正常解析增持记录（change_num > 0 -> direction=increase）。"""
        import fetchers.event.eastmoney_event as mod

        payload = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "HOLDER_NAME": "茅台集团",
                        "END_DATE": "2026-08-01T00:00:00",
                        "CHANGE_NUM": "1000000",
                        "CHANGE_RATIO": "0.5",
                        "AVERAGE_PRICE": "1800.0",
                        "CHANGE_SHARES_AFTER": "2000000",
                    }
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.ShareholderChangeFetcher().fetch("sh600519")

        assert result is not None
        assert result["type"] == "shareholder"
        item = result["items"][0]
        assert item["holder_name"] == "茅台集团"
        assert item["end_date"] == "2026-08-01"
        assert item["change_num"] == 1000000.0
        assert item["direction"] == "increase"

    def test_decrease_direction(self, monkeypatch):
        """change_num < 0 -> direction=decrease。"""
        import fetchers.event.eastmoney_event as mod

        payload = {
            "success": True,
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "HOLDER_NAME": "某股东",
                        "END_DATE": "2026-08-01",
                        "CHANGE_NUM": "-500000",
                    }
                ],
            },
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.ShareholderChangeFetcher().fetch("sh600519")

        assert result is not None
        assert result["items"][0]["direction"] == "decrease"

    def test_empty_result_returns_none(self, monkeypatch):
        """无数据 -> 返回 None。"""
        import fetchers.event.eastmoney_event as mod

        payload = {"success": True, "result": {"pages": 1, "data": []}}
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.ShareholderChangeFetcher().fetch("sh600519")

        assert result is None


# ═══════════════════════════════════════════════════════════════
# PerformanceForecastFetcher
# ═══════════════════════════════════════════════════════════════


class TestPerformanceForecastFetcher:
    """业绩预告数据源（#10）。

    注意：该 fetcher 的 _fetch_all_pages 与 lhb/event 不同--
    用 "result" not in data 判断（而非 success 字段）。
    """

    def test_no_code_returns_none(self, monkeypatch):
        """无 code 时直接返回 None。"""
        import fetchers.event.performance_forecast as mod

        called = []

        def _no_call(url, timeout=10, max_retries=3):
            called.append(url)
            return b"{}"

        monkeypatch.setattr(mod, "http_get", _no_call)

        result = mod.PerformanceForecastFetcher().fetch("")

        assert result is None
        assert called == []

    def test_normal_parse_with_type_mapping(self, monkeypatch):
        """正常解析 + FORECASTTYPE 映射（预增 -> increase）。

        字段名与东财 RPT_PUBLIC_OP_PREDICT 实际返回一致：
        FORECASTTYPE / FORECASTL / FORECASTT / INCREASEL / INCREASET / YEAREARLIER
        （非早期猜测的 FORECAST_TYPE / PROFIT_MIN / PROFIT_MAX）。
        """
        import fetchers.event.performance_forecast as mod

        payload = {
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "NOTICE_DATE": "2026-08-01 00:00:00",
                        "REPORTDATE": "2026-06-30 00:00:00",
                        "FORECASTTYPE": "预增",
                        "FORECASTL": "1000000",
                        "FORECASTT": "1500000",
                        "INCREASEL": "10",
                        "INCREASET": "20",
                        "INCREASEJZ": "15",
                        "FORECASTJZ": "1250000",
                        "YEAREARLIER": "900000",
                        "FORECASTCONTENT": "预计归母净利润盈利",
                        "CHANGEREASONDSCRPT": "业绩增长",
                        "ISLATEST": "T",
                    }
                ],
            }
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.PerformanceForecastFetcher().fetch("sh600519")

        assert result is not None
        assert result["type"] == "forecast"
        item = result["items"][0]
        assert item["forecast_type"] == "increase"
        assert item["forecast_type_raw"] == "预增"
        assert item["profit_min"] == 1000000.0
        assert item["profit_max"] == 1500000.0
        assert item["change_min"] == 10.0
        assert item["change_max"] == 20.0
        assert item["change_midpoint"] == 15.0
        assert item["forecast_midpoint"] == 1250000.0
        assert item["pre_profit"] == 900000.0
        assert item["content"] == "预计归母净利润盈利"
        assert item["reason"] == "业绩增长"
        assert item["is_latest"] is True
        # notice_date / report_date 截断为日期
        assert item["notice_date"] == "2026-08-01"
        assert item["report_date"] == "2026-06-30"
        # code 保留原始入参（含前缀）
        assert item["code"] == "sh600519"

    def test_unknown_forecast_type_keeps_raw(self, monkeypatch):
        """未知 FORECASTTYPE -> forecast_type 等于原始值。"""
        import fetchers.event.performance_forecast as mod

        payload = {
            "result": {
                "pages": 1,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "FORECASTTYPE": "新类型",
                    }
                ],
            }
        }
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.PerformanceForecastFetcher().fetch("sh600519")

        assert result is not None
        assert result["items"][0]["forecast_type"] == "新类型"
        assert result["items"][0]["forecast_type_raw"] == "新类型"

    def test_empty_result_returns_none(self, monkeypatch):
        """result.data 为空 -> None。"""
        import fetchers.event.performance_forecast as mod

        payload = {"result": {"pages": 1, "data": []}}
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.PerformanceForecastFetcher().fetch("sh600519")

        assert result is None

    def test_no_result_key_returns_none(self, monkeypatch):
        """响应无 result 字段 -> None（与 lhb/event 的 success 检查不同）。"""
        import fetchers.event.performance_forecast as mod

        payload = {"success": True}
        monkeypatch.setattr(mod, "http_get", _make_json_getter(payload))

        result = mod.PerformanceForecastFetcher().fetch("sh600519")

        assert result is None

    def test_json_decode_failure_returns_none(self, monkeypatch):
        """非 JSON -> _fetch_all_pages 中断返回空列表 -> fetch 返回 None。

        注意：performance_forecast.fetch 用 except Exception 兜底返回 None，
        而非向上抛出（与 lhb/event 的 re-raise 行为不同）。
        """
        import fetchers.event.performance_forecast as mod

        monkeypatch.setattr(mod, "http_get", _make_json_getter(b"not json at all"))

        result = mod.PerformanceForecastFetcher().fetch("sh600519")

        assert result is None

    def test_pagination_accumulates_pages(self, monkeypatch):
        """回归：pages=2，累积两页记录。"""
        import fetchers.event.performance_forecast as mod

        page1 = {
            "result": {
                "pages": 2,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "FORECAST_TYPE": "预增",
                        "NOTICE_DATE": "2026-08-01",
                    },
                    {
                        "SECURITY_CODE": "600519",
                        "FORECAST_TYPE": "预增",
                        "NOTICE_DATE": "2026-08-02",
                    },
                ],
            }
        }
        page2 = {
            "result": {
                "pages": 2,
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "FORECAST_TYPE": "预增",
                        "NOTICE_DATE": "2026-08-03",
                    },
                ],
            }
        }
        monkeypatch.setattr(mod, "http_get", _make_paged_getter([page1, page2]))

        result = mod.PerformanceForecastFetcher().fetch("sh600519")

        assert result is not None
        assert len(result["items"]) == 3
        notice_dates = [i["notice_date"] for i in result["items"]]
        assert notice_dates == ["2026-08-01", "2026-08-02", "2026-08-03"]

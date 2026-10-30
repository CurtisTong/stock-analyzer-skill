"""大宗交易 / 涨停原因 fetcher 单元测试（v1.24.0 新数据域）。

mock 模式与 test_lhb_event_fetchers.py 一致：替换 fetcher 模块内
http_get，不依赖真实网络。

- BlockTradeFetcher（东财 RPT_DATA_BLOCKTRADE）：
  正常解析 / 溢价率 None 不伪装 0 / 个股过滤 / 空结果 / 网络异常透传
- LimitUpReasonFetcher（同花顺 limit_up_pool）：
  正常解析（原因/板型/回封/时间戳）/ 个股过滤无记录 / 非零 status_code /
  分页 / 网络异常透传
"""

from __future__ import annotations

import json

import pytest


def _make_json_getter(response):
    def _http_get(url, timeout=10, max_retries=3):
        if isinstance(response, (bytes, bytearray)):
            return response
        return json.dumps(response).encode("utf-8")

    return _http_get


def _page1_response():
    return {
        "success": True,
        "result": {
            "pages": 1,
            "data": [
                {
                    "SECURITY_CODE": "920765",
                    "SECURITY_NAME_ABBR": "美之高",
                    "TRADE_DATE": "2026-10-28 00:00:00",
                    "DEAL_PRICE": 9.7,
                    "CLOSE_PRICE": 9.88,
                    "CHANGE_RATE": 2.0661,
                    "DEAL_VOLUME": 286822,
                    "DEAL_AMT": 2782173.4,
                    "PREMIUM_RATIO": -0.018218,
                    "BUYER_NAME": "买方营业部",
                    "SELLER_NAME": "卖方营业部",
                },
                {
                    "SECURITY_CODE": "600519",
                    "SECURITY_NAME_ABBR": "贵州茅台",
                    "TRADE_DATE": "2026-10-28 00:00:00",
                    "DEAL_PRICE": 1500.0,
                    "CLOSE_PRICE": 1512.0,
                    "CHANGE_RATE": 0.8,
                    "DEAL_VOLUME": 100000,
                    "DEAL_AMT": 150000000.0,
                    "PREMIUM_RATIO": None,
                    "BUYER_NAME": "机构专用",
                    "SELLER_NAME": "卖方营业部",
                },
            ],
        },
    }


class TestBlockTradeFetcher:
    def _fetcher(self, monkeypatch, response):
        # _fetch_all_pages 复用自 lhb 模块，其 http_get 在 lhb 命名空间
        import fetchers.lhb.eastmoney_lhb as lhb_mod
        from fetchers.block_trade.eastmoney_block_trade import BlockTradeFetcher

        monkeypatch.setattr(lhb_mod, "http_get", _make_json_getter(response))
        return BlockTradeFetcher()

    def test_parse_fields(self, monkeypatch):
        f = self._fetcher(monkeypatch, _page1_response())
        result = f.fetch(days=7)
        assert result["type"] == "block_trade"
        assert len(result["items"]) == 2
        item = result["items"][0]
        assert item["code"] == "920765"
        assert item["date"] == "2026-10-28"
        assert item["deal_price"] == 9.7
        assert item["deal_volume_wan"] == 28.68  # 286822 股 → 28.68 万股
        assert item["premium_ratio"] == -1.82  # 比率 → 百分数
        assert item["buyer"] == "买方营业部"

    def test_none_premium_stays_none(self, monkeypatch):
        """溢价率缺失保持 None，不伪装成 0（0 溢价是有效语义）。"""
        f = self._fetcher(monkeypatch, _page1_response())
        result = f.fetch()
        moutai = next(i for i in result["items"] if i["code"] == "600519")
        assert moutai["premium_ratio"] is None

    def test_dash_premium_does_not_crash(self, monkeypatch):
        """东财空值 "-" 占位：必须安全转 None，不得 TypeError 炸掉整次查询。"""
        resp = _page1_response()
        resp["result"]["data"][0]["PREMIUM_RATIO"] = "-"
        f = self._fetcher(monkeypatch, resp)
        result = f.fetch()
        assert result["items"][0]["premium_ratio"] is None

    def test_string_premium_parsed(self, monkeypatch):
        """数值字符串溢价率（东财实际返回形态之一）正常解析。"""
        resp = _page1_response()
        resp["result"]["data"][0]["PREMIUM_RATIO"] = "-0.018218"
        f = self._fetcher(monkeypatch, resp)
        assert f.fetch()["items"][0]["premium_ratio"] == -1.82

    def test_provider_matches_yaml_key(self):
        from fetchers.block_trade.eastmoney_block_trade import BlockTradeFetcher

        assert BlockTradeFetcher().provider == "eastmoney"

    def test_code_filter(self, monkeypatch):
        f = self._fetcher(monkeypatch, _page1_response())
        result = f.fetch(code="sh600519", days=7)
        assert len(result["items"]) == 1
        assert result["items"][0]["code"] == "600519"

    def test_empty_result_returns_none(self, monkeypatch):
        f = self._fetcher(monkeypatch, {"success": True, "result": {"pages": 1, "data": []}})
        assert f.fetch() is None

    def test_network_error_propagates(self, monkeypatch):
        import fetchers.lhb.eastmoney_lhb as lhb_mod
        from fetchers.block_trade.eastmoney_block_trade import BlockTradeFetcher
        from common.exceptions import NetworkError

        def _boom(url, timeout=10, max_retries=3):
            raise NetworkError(url, "timeout")

        monkeypatch.setattr(lhb_mod, "http_get", _boom)
        with pytest.raises(NetworkError):
            BlockTradeFetcher().fetch()


class TestLimitUpReasonFetcher:
    def _fetcher(self, monkeypatch, response):
        from fetchers.limit_up.ths_limit_up import LimitUpReasonFetcher
        import fetchers.limit_up.ths_limit_up as mod

        monkeypatch.setattr(mod, "http_get", _make_json_getter(response))
        return LimitUpReasonFetcher()

    def _pool_response(self, items, total=None):
        return {
            "status_code": 0,
            "data": {"page": {"total": total if total is not None else len(items)}, "info": items},
        }

    def _pool_item(self, code="301525"):
        return {
            "code": code,
            "name": "儒竞科技",
            "change_rate": 19.995,
            "turnover_rate": 13.88,
            "reason_type": "机器人+数据中心温控",
            "limit_up_type": "换手板",
            "high_days": "首板",
            "open_num": 24,
            "is_again_limit": 1,
            "limit_up_suc_rate": 0.0,
            "first_limit_up_time": 1793163669,
            "last_limit_up_time": 1793170800,
            "order_amount": 1388826.6,
            "currency_value": 3431011800.0,
        }

    def test_parse_fields(self, monkeypatch):
        f = self._fetcher(monkeypatch, self._pool_response([self._pool_item()]))
        result = f.fetch(date="20261028")
        assert result["type"] == "limit_up_reason"
        assert result["date"] == "20261028"
        item = result["items"][0]
        assert item["code"] == "301525"
        assert item["reason_type"] == "机器人+数据中心温控"
        assert item["limit_up_type"] == "换手板"
        assert item["high_days"] == "首板"
        assert item["open_num"] == 24
        assert item["is_again_limit"] is True
        assert item["first_time"] == "13:01"  # epoch → HH:MM

    def test_code_filter_no_match_returns_none(self, monkeypatch):
        f = self._fetcher(monkeypatch, self._pool_response([self._pool_item()]))
        assert f.fetch(code="sh600519") is None

    def test_code_filter_match(self, monkeypatch):
        f = self._fetcher(monkeypatch, self._pool_response([self._pool_item("600519")]))
        result = f.fetch(code="sh600519")
        assert result["items"][0]["code"] == "600519"

    def test_bad_status_returns_none(self, monkeypatch):
        f = self._fetcher(monkeypatch, {"status_code": 500, "data": {}})
        assert f.fetch() is None

    def test_pagination_over_max_pages(self, monkeypatch):
        """total 超过 MAX_PAGES*100 时截断标记。"""
        from fetchers.limit_up.ths_limit_up import LimitUpReasonFetcher
        import fetchers.limit_up.ths_limit_up as mod

        items = [self._pool_item(f"30{i:04d}") for i in range(100)]

        def _http_get(url, timeout=10, max_retries=3):
            # page=2 起返回空列表（单 mock 模拟多页）
            page = int(dict(p.split("=") for p in url.split("?")[1].split("&"))["page"])
            if page > 1:
                info = []
            else:
                info = items
            resp = {"status_code": 0, "data": {"page": {"total": 900}, "info": info}}
            return json.dumps(resp).encode("utf-8")

        monkeypatch.setattr(mod, "http_get", _http_get)
        result = LimitUpReasonFetcher().fetch()
        assert result["truncated"] is True
        assert len(result["items"]) == 100  # 只取到第一页内容

    def test_again_limit_string_zero_not_flagged(self, monkeypatch):
        """接口回 "0" 字符串时不得误标回封（bool("0") is True 回归锚点）。"""
        item = self._pool_item()
        item["is_again_limit"] = "0"
        f = self._fetcher(monkeypatch, self._pool_response([item]))
        assert f.fetch()["items"][0]["is_again_limit"] is False

    def test_again_limit_string_one_flagged(self, monkeypatch):
        item = self._pool_item()
        item["is_again_limit"] = "1"
        f = self._fetcher(monkeypatch, self._pool_response([item]))
        assert f.fetch()["items"][0]["is_again_limit"] is True

    def test_provider_matches_yaml_key(self):
        from fetchers.limit_up.ths_limit_up import LimitUpReasonFetcher

        assert LimitUpReasonFetcher().provider == "ths"

    def test_network_error_propagates(self, monkeypatch):
        from fetchers.limit_up.ths_limit_up import LimitUpReasonFetcher
        import fetchers.limit_up.ths_limit_up as mod
        from common.exceptions import NetworkError

        def _boom(url, timeout=10, max_retries=3):
            raise NetworkError(url, "forbidden")

        monkeypatch.setattr(mod, "http_get", _boom)
        with pytest.raises(NetworkError):
            LimitUpReasonFetcher().fetch()

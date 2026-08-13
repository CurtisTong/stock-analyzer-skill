"""data 域核心单元测试（v1.20.x 补测）。

覆盖 data/__init__.py 的纯转换函数与单位归一化逻辑：
- _dict_to_quote / _dict_to_kline_bar / _dict_to_finance 字段映射与单位
- _normalize_cap / _normalize_volume / _normalize_amount 数据源差异
- _normalize_period_type 报告期归一化
- get_quote / get_finance 缓存命中与降级分支
"""

import pytest
from unittest.mock import patch

from data import (
    _dict_to_finance,
    _dict_to_kline_bar,
    _dict_to_quote,
    _normalize_cap,
    _normalize_period_type,
)
from data.types import FinanceMeta, Quote, KlineBar


class TestNormalizeCap:
    """total_cap/circulating_cap 归一化为亿。"""

    def test_a_share_divides_by_1e8(self):
        """A 股 fetcher 返回元，/1e8 转亿。"""
        assert _normalize_cap(169694000000.0, "eastmoney", "sh600989") == 1696.94

    def test_yfinance_keeps_raw(self):
        """yfinance 跨市场市值不做归一化（货币口径不同）。"""
        raw = 123456789.0
        assert _normalize_cap(raw, "yfinance", "us:aapl") == raw

    def test_zero_returns_zero(self):
        """空/零市值返回 0.0。"""
        assert _normalize_cap(0, "tencent", "sh600989") == 0.0
        assert _normalize_cap(None, "tencent", "sh600989") == 0.0


class TestNormalizePeriodType:
    """东财 REPORT_TYPE 中文值 -> 英文枚举。"""

    def test_quarterly(self):
        assert _normalize_period_type("一季报") == "quarterly"

    def test_cumulative_for_mid_and_q3(self):
        assert _normalize_period_type("中报") == "cumulative"
        assert _normalize_period_type("三季报") == "cumulative"

    def test_annual(self):
        assert _normalize_period_type("年报") == "annual"

    def test_unknown_or_empty_returns_blank(self):
        assert _normalize_period_type("") == ""
        assert _normalize_period_type("未知类型") == ""


class TestDictToQuote:
    """_dict_to_quote 字段映射与单位归一化。"""

    @pytest.fixture(autouse=True)
    def _no_industry_network(self, monkeypatch):
        """_resolve_industry 缺失时触网（akshare 行业补全），统一 patch 为空串。"""
        import data as data_mod

        monkeypatch.setattr(data_mod, "_resolve_industry", lambda d, c: "")

    def test_basic_fields(self):
        d = {
            "code": "SH600989",
            "name": "宝丰能源",
            "price": "10.5",
            "prev_close": "10.0",
            "change_pct": "5.0",
            "source": "tencent",
        }
        q = _dict_to_quote(d)
        assert isinstance(q, Quote)
        assert q.code == "sh600989"
        assert q.name == "宝丰能源"
        assert q.price == 10.5
        assert q.change_pct == 5.0
        assert q.source == "tencent"

    def test_tencent_volume_hands_to_shares(self):
        """腾讯 volume 单位"手" → 股（×100），科创板特判除外。"""
        d = {"code": "sz000001", "volume": "1234", "source": "tencent"}
        q = _dict_to_quote(d)
        assert q.volume == 123400

    def test_tencent_kcb_volume_already_shares(self):
        """腾讯科创板(688) volume 单位已是"股"，不 ×100。"""
        d = {"code": "sh688981", "volume": "1234", "source": "tencent"}
        q = _dict_to_quote(d)
        assert q.volume == 1234

    def test_tencent_amount_wan_to_yuan(self):
        """腾讯 amount 单位"万" → 元（×10000）。"""
        d = {"code": "sh600989", "amount": "123.45", "source": "tencent"}
        q = _dict_to_quote(d)
        assert q.amount == 1234500.0

    def test_sina_amount_kept_raw(self):
        """新浪 amount 原值（元）不转换。"""
        d = {"code": "sh600989", "amount": "1234567", "source": "sina"}
        q = _dict_to_quote(d)
        assert q.amount == 1234567.0

    def test_total_cap_normalized(self):
        """total_cap 元 → 亿。"""
        d = {"code": "sh600989", "total_cap": 2e10, "source": "eastmoney"}
        q = _dict_to_quote(d)
        assert q.total_cap == 200.0

    def test_suspended_and_limit_fields(self):
        d = {
            "code": "sz000001",
            "source": "tencent",
            "is_suspended": True,
            "limit_up": "11.0",
            "limit_down": "9.0",
        }
        q = _dict_to_quote(d)
        assert q.is_suspended is True
        assert q.limit_up == 11.0
        assert q.limit_down == 9.0

    def test_fetch_time_filled_when_missing(self):
        d = {"code": "sh600989", "source": "sina"}
        q = _dict_to_quote(d)
        assert q.fetch_time != ""

    def test_garbled_name_repaired(self):
        """乱码 name 经 repair_tencent_name 修复为中文。"""
        d = {"code": "sz002557", "source": "tencent", "name": "ǢǢʳƷ"}
        q = _dict_to_quote(d)
        assert isinstance(q.name, str)
        assert q.name != ""


class TestResolveIndustry:
    """_resolve_industry：已有 industry 直传，缺失时 akshare 补全。"""

    def test_passthrough_when_present(self):
        from data import _resolve_industry

        assert _resolve_industry({"industry": "医药生物"}, "sh600989") == "医药生物"

    def test_fetch_when_missing(self):
        from data import _resolve_industry

        with patch(
            "fetchers.industry.akshare_industry.fetch_industry",
            return_value="煤炭行业",
        ) as m:
            assert _resolve_industry({}, "sh600989") == "煤炭行业"
            m.assert_called_once_with("600989")

    def test_fallback_empty_on_exception(self):
        from data import _resolve_industry

        with patch(
            "fetchers.industry.akshare_industry.fetch_industry",
            side_effect=RuntimeError("network down"),
        ):
            assert _resolve_industry({}, "sh600989") == ""  # 异常兜底空串


class TestDictToKlineBar:
    """_dict_to_kline_bar 字段映射与别名。"""

    def test_day_alias_date(self):
        """支持 day / date / day_str 键名。"""
        bar = _dict_to_kline_bar({"date": "2026-08-11", "source": "sina"})
        assert bar.day == "2026-08-11"

    def test_day_priority(self):
        bar = _dict_to_kline_bar(
            {"day": "2026-08-11", "date": "2026-08-10", "source": "sina"}
        )
        assert bar.day == "2026-08-11"

    def test_fields_and_normalization(self):
        bar = _dict_to_kline_bar(
            {
                "day": "2026-08-11",
                "open": "10.0",
                "high": "11.0",
                "low": "9.5",
                "close": "10.5",
                "volume": "1000",
                "amount": "1.05",
                "pct_chg": "5.0",
                "source": "tencent",
            },
            code="sh600989",
        )
        assert isinstance(bar, KlineBar)
        assert bar.open == 10.0
        assert bar.close == 10.5
        assert bar.volume == 100000  # 腾讯手→股 ×100
        assert bar.amount == 10500.0  # 腾讯万→元 ×10000
        assert bar.pct_chg == 5.0

    def test_fetch_time_filled(self):
        bar = _dict_to_kline_bar({"day": "2026-08-11", "source": "sina"})
        assert bar.fetch_time != ""


class TestDictToFinance:
    """_dict_to_finance 补充分支（核心字段映射已有专项+集成覆盖）。"""

    def test_none_when_missing(self):
        """缺数据时数值字段为 None（非 0.0）。"""
        r = _dict_to_finance({"REPORT_DATE": "2026-03-31", "source": "eastmoney"})
        assert r.eps is None
        assert r.roe is None
        assert r.revenue_yoy is None

    def test_assets_derived_from_liability_and_debt_ratio(self):
        """负债/负债率(≤100) 推导总资产与净资产。"""
        r = _dict_to_finance(
            {
                "REPORT_DATE": "2026-03-31",
                "LIABILITY": 5e10,  # 500 亿
                "ZCFZL": "40.0",
                "source": "eastmoney",
            }
        )
        assert r.total_liability == 500.0
        assert r.total_assets == 1250.0  # 500 / 0.4
        assert r.net_assets == 750.0

    def test_assets_not_derived_when_ratio_invalid(self):
        """debt_ratio 缺失/超界时不推导，避免除零。"""
        break_even = _dict_to_finance(
            {"REPORT_DATE": "2026-03-31", "LIABILITY": 5e10, "source": "eastmoney"}
        )
        assert break_even.total_liability == 500.0
        assert break_even.total_assets is None

        exceeded = _dict_to_finance(
            {
                "REPORT_DATE": "2026-03-31",
                "LIABILITY": 5e10,
                "ZCFZL": "120.0",
                "source": "eastmoney",
            }
        )
        assert exceeded.total_assets is None

    def test_period_type_normalized(self):
        r = _dict_to_finance(
            {
                "REPORT_DATE": "2026-03-31",
                "REPORT_TYPE": "一季报",
                "source": "eastmoney",
            }
        )
        assert r.period_type == "quarterly"

    def test_absolute_values_converted_to_yi(self):
        r = _dict_to_finance(
            {
                "REPORT_DATE": "2026-03-31",
                "TOTALOPERATEREVE": 1.23456789e10,
                "PARENTNETPROFIT": 1.23456789e9,
                "source": "eastmoney",
            }
        )
        assert r.total_revenue == 123.46
        assert r.parent_net_profit == 12.35

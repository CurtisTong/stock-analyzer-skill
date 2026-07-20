"""
business 层单元测试：覆盖 ScreeningService 和 StockAnalysisService 的核心路径。
"""

import argparse
from unittest.mock import MagicMock, patch

import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from business.screening_service import (
    ScreeningService,
    _board_limit,
    _min_survival_cap,
    _goodwill_threshold,
    _pledge_threshold,
)  # noqa: E402


def _make_namespace(**kwargs):
    """构造一个 argparse-like 命名空间对象。"""
    defaults = {"min_amount": 5000, "min_cap": 40, "exclude_loss": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ═══════════════════════════════════════════════════════════════
# 1. 阈值辅助函数
# ═══════════════════════════════════════════════════════════════
class TestThresholdHelpers:
    """模块级阈值读取函数。"""

    def test_board_limit_known_boards(self):
        # P0-7: 涨跌停硬过滤改用精确阈值（非预警宽松阈值）
        assert _board_limit("主板") == 10.0
        assert _board_limit("创业板") == 20.0
        assert _board_limit("科创板") == 20.0
        assert _board_limit("北交所") == 30.0

    def test_board_limit_unknown_board(self):
        assert _board_limit("unknown") == 10.0

    def test_min_survival_cap_known_boards(self):
        assert _min_survival_cap("主板") == 5
        assert _min_survival_cap("创业板") == 3
        assert _min_survival_cap("北交所") == 2

    def test_goodwill_threshold_default(self):
        assert _goodwill_threshold() == 30

    def test_pledge_threshold_default(self):
        assert _pledge_threshold() == 70

    # P1-22: _st_prefixes 已删除，ST 检测统一使用 data.pool.is_st


# ═══════════════════════════════════════════════════════════════
# 2. ScreeningService 初始化
# ═══════════════════════════════════════════════════════════════
class TestScreeningServiceInit:
    def test_default_strategy(self):
        svc = ScreeningService()
        assert svc.default_strategy == "balanced"
        # v1.8: 线程池统一由 get_shared_executor 管理（DataConfig.max_workers）
        from common import get_shared_executor

        ex = get_shared_executor()
        assert ex._max_workers >= 4
        assert ex._max_workers <= 32


# ═══════════════════════════════════════════════════════════════
# 3. ScreeningService._hard_filter
# ═══════════════════════════════════════════════════════════════
class TestScreeningServiceHardFilter:
    def setup_method(self):
        self.svc = ScreeningService()
        self.filters = {"min_amount": 5000, "min_cap": 40, "exclude_loss": False}

    def test_st_stock_rejected(self):
        """ST 股票应被拒。"""
        quote = {"code": "sh600519", "name": "ST测试", "total_cap": 100, "amount": 1e8}
        fin = {"eps": 1, "roe": 10, "debt_ratio": 30}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert "ST风险" in reasons

    def test_normal_stock_passes(self):
        """正常股票应通过。"""
        quote = {
            "code": "sh600519",
            "name": "贵州茅台",
            "total_cap": 1000,
            "amount": 5e9,
            "change_pct": 1.0,
        }
        fin = {"eps": 10, "roe": 20, "debt_ratio": 30}
        assert self.svc._hard_filter(quote, fin, self.filters) == ([], [])

    def test_low_cap_rejected(self):
        quote = {
            "code": "sh600000",
            "name": "小盘",
            "total_cap": 5,
            "amount": 1e8,
            "change_pct": 0,
        }
        fin = {"eps": 1, "roe": 10}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert any("市值" in r for r in reasons)

    def test_loss_excluded_with_flag(self):
        """EPS<=0 + exclude_loss=True 应被拒。"""
        quote = {
            "code": "sh600000",
            "name": "亏损股",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": 0,
        }
        fin = {"eps": -1, "roe": -5}
        reasons, _ = self.svc._hard_filter(
            quote, fin, {**self.filters, "exclude_loss": True}
        )
        assert "EPS<=0" in reasons

    def test_loss_not_excluded_by_default(self):
        """EPS<=0 但 exclude_loss=False 应不被拒。"""
        quote = {
            "code": "sh600000",
            "name": "亏损股",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": 0,
        }
        fin = {"eps": -1, "roe": -5}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        # 仍然会因 EPS<0(亏损) 被标记，但不会被 exclude_loss 二次标记
        assert "EPS<=0" not in reasons

    def test_goodill_warning(self):
        """商誉>阈值应被拒。"""
        quote = {
            "code": "sh600000",
            "name": "高商誉",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": 0,
        }
        fin = {"eps": 1, "roe": 10, "goodwill_ratio": 50}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert any("商誉" in r for r in reasons)

    def test_pledge_warning(self):
        """质押率>阈值应被拒。"""
        quote = {
            "code": "sh600000",
            "name": "高质押",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": 0,
        }
        fin = {"eps": 1, "roe": 10, "pledge_ratio": 80}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert any("质押率" in r for r in reasons)

    def test_limit_up_rejected(self):
        """涨停应被拒（T+1 限制）。"""
        quote = {
            "code": "sh600000",
            "name": "涨停",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": 10,
        }
        fin = {"eps": 1, "roe": 10}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert "涨跌停限制" in reasons

    def test_limit_down_rejected(self):
        """跌停也应被拒。"""
        quote = {
            "code": "sh600000",
            "name": "跌停",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": -10,
        }
        fin = {"eps": 1, "roe": 10}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert "涨跌停限制" in reasons

    def test_donghu_prefix_rejected(self):
        """*ST 前缀应被拒。"""
        quote = {
            "code": "sh600000",
            "name": "*ST 测试",
            "total_cap": 100,
            "amount": 1e8,
        }
        fin = {"eps": 1, "roe": 10}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert "ST风险" in reasons

    def test_amount_too_low_rejected(self):
        """成交额<5000 万应被拒。"""
        quote = {
            "code": "sh600000",
            "name": "低成交",
            "total_cap": 100,
            "amount": 1e7,
            "change_pct": 0,
        }
        fin = {"eps": 1, "roe": 10}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert any("成交额" in r for r in reasons)

    def test_fin_field_aliases(self):
        """兼容东财原始字段名（EPSJB/ROEJQ）。"""
        quote = {
            "code": "sh600000",
            "name": "测试",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": 0,
        }
        fin = {"EPSJB": -1, "ROEJQ": 20, "ZCFZL": 30}
        reasons, _ = self.svc._hard_filter(quote, fin, self.filters)
        assert any("EPS" in r for r in reasons)

    def test_filters_dict_missing_keys(self):
        """filters dict 缺字段时回退到硬编码默认。"""
        quote = {
            "code": "sh600000",
            "name": "测试",
            "total_cap": 100,
            "amount": 1e8,
            "change_pct": 0,
        }
        fin = {"eps": 1, "roe": 10}
        # 空 filters dict -- P1-19: 返回 (reasons, warnings) 元组
        result = self.svc._hard_filter(quote, fin, {})
        assert isinstance(result, tuple)
        assert isinstance(result[0], list)


# ═══════════════════════════════════════════════════════════════
# 4. ScreeningService.screen 边界情况
# ═══════════════════════════════════════════════════════════════
class TestScreeningServiceScreenEdgeCases:
    def test_empty_codes(self):
        svc = ScreeningService()
        result = svc.screen([], strategy="balanced")
        assert result == []

    def test_invalid_strategy_falls_back(self, caplog):
        """未知策略回退到默认 balanced。"""
        svc = ScreeningService()
        # 不会抛异常，会用 balanced
        with patch("business.screening_service.get_quotes", return_value=[]):
            result = svc.screen(
                ["sh600000"], strategy="nonexistent_strategy", filters={}
            )
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# 5. _vol_price_signal_desc
# ═══════════════════════════════════════════════════════════════
class TestVolPriceSignalDesc:
    def test_positive_signal(self):
        assert ScreeningService._vol_price_signal_desc(1) == "配合"

    def test_negative_signal(self):
        assert ScreeningService._vol_price_signal_desc(-1) == "背离"

    def test_zero_signal(self):
        assert ScreeningService._vol_price_signal_desc(0) == "中性"


# ═══════════════════════════════════════════════════════════════
# 6. StockAnalysisService.analyze 数据来源元信息 (P0-02 / P1-17)
# ═══════════════════════════════════════════════════════════════


class _FakeFuture:
    """模拟 concurrent.futures.Future，直接持有结果或异常。"""

    def __init__(self, value=None, exc=None):
        self._value = value
        self._exc = exc

    def result(self, timeout=None):
        if self._exc:
            raise self._exc
        return self._value


class _FakeExecutor:
    """模拟 ThreadPoolExecutor.submit，按函数映射返回 FakeFuture。"""

    def __init__(self, handlers):
        # handlers: {(fn, args_tuple) -> FakeFuture}
        self._handlers = handlers
        self.calls = []

    def submit(self, fn, *args, **kwargs):
        # 把 kwargs 排序后追加到 args，确保调用方传 periods= 时 key 仍可匹配
        self.calls.append((fn, args, tuple(sorted(kwargs.items()))))
        # key 同时尝试带 kwargs 与不带 kwargs，兼容旧测试用例
        for k in ((fn, args), (fn, args, tuple(sorted(kwargs.items())))):
            if k in self._handlers:
                return self._handlers[k]
        # 默认返回 None
        return _FakeFuture(value=None)


def _make_quote(code="sh600519", source="tencent", fetch_time="2026-07-09T15:00:00"):
    """构造一个模拟 Quote 对象。"""
    from data.types import Quote

    return Quote(
        code=code,
        name="贵州茅台",
        price=1800.0,
        change_pct=1.5,
        source=source,
        fetch_time=fetch_time,
        pe=30,
        pb=10,
    )


def _make_index_quote():
    """构造上证指数模拟 Quote。"""
    from data.types import Quote

    return Quote(code="sh000001", name="上证指数", price=3000.0, change_pct=0.5)


def _make_kline(n=60, last_day="2026-07-09"):
    """构造模拟 KlineBar 列表。"""
    from data.types import KlineBar

    return [KlineBar(day=last_day, close=1800.0 + i, volume=10000) for i in range(n)]


def _make_finance():
    """构造模拟 FinanceRecord 列表。"""
    from data.types import FinanceRecord

    return [FinanceRecord(eps=50.0, roe=30.0, net_profit_yoy=20.0)]


class TestAnalyzeDataMetadata:
    """P0-02: analyze() 填充 data_sources / data_failed / data_time。"""

    def test_all_success_fills_sources_and_time(self):
        """三类数据全部成功 -> data_sources 含三项，data_time 取 quote.fetch_time。"""
        from business.stock_analysis import StockAnalysisService

        quote = _make_quote()
        index = _make_index_quote()
        kline = _make_kline()
        finance = _make_finance()

        svc = StockAnalysisService()
        fake_ex = _FakeExecutor(
            {
                (get_quote_fn, ("sh600519",)): _FakeFuture(value=quote),
                (get_kline_fn, ("sh600519", 240, 240)): _FakeFuture(value=kline),
                (get_finance_fn, ("sh600519",)): _FakeFuture(value=finance),
                (get_quote_fn, ("sh000001",)): _FakeFuture(value=index),
            }
        )

        with (
            patch("business.stock_analysis.get_shared_executor", return_value=fake_ex),
            patch(
                "business.stock_analysis.profile_stock", return_value={"type": "蓝筹股"}
            ),
            patch(
                "business.stock_analysis._analyze_technical",
                return_value={"ma": "多头"},
            ),
            patch("business.stock_analysis._analyze_chan", return_value={}),
        ):
            result = svc.analyze("sh600519")

        assert "行情" in result["data_sources"]
        assert "K线" in result["data_sources"]
        assert "财务" in result["data_sources"]
        assert result["data_failed"] == []
        assert result["data_time"] == "2026-07-09T15:00:00"

    def test_quote_failure_recorded_in_failed(self):
        """行情获取失败 -> data_failed 含'行情'，data_sources 不含'行情'。"""
        from business.stock_analysis import StockAnalysisService

        kline = _make_kline()
        finance = _make_finance()

        svc = StockAnalysisService()
        fake_ex = _FakeExecutor(
            {
                (get_quote_fn, ("sh600519",)): _FakeFuture(
                    exc=ConnectionError("timeout")
                ),
                (get_kline_fn, ("sh600519", 240, 240)): _FakeFuture(value=kline),
                (get_finance_fn, ("sh600519",)): _FakeFuture(value=finance),
                (get_quote_fn, ("sh000001",)): _FakeFuture(value=_make_index_quote()),
            }
        )

        with (
            patch("business.stock_analysis.get_shared_executor", return_value=fake_ex),
            patch(
                "business.stock_analysis.profile_stock", return_value={"type": "普通股"}
            ),
            patch(
                "business.stock_analysis._analyze_technical",
                return_value={"ma": "多头"},
            ),
            patch("business.stock_analysis._analyze_chan", return_value={}),
        ):
            result = svc.analyze("sh600519")

        assert "行情" in result["data_failed"]
        assert "行情" not in result["data_sources"]
        # 无 quote.fetch_time 时回退到 K线最后 day
        assert result["data_time"] == "2026-07-09"

    def test_finance_failure_recorded_in_failed(self):
        """财务获取失败 -> data_failed 含'财务'。"""
        from business.stock_analysis import StockAnalysisService

        quote = _make_quote()
        kline = _make_kline()

        svc = StockAnalysisService()
        fake_ex = _FakeExecutor(
            {
                (get_quote_fn, ("sh600519",)): _FakeFuture(value=quote),
                (get_kline_fn, ("sh600519", 240, 240)): _FakeFuture(value=kline),
                (get_finance_fn, ("sh600519",)): _FakeFuture(exc=RuntimeError("fail")),
                (get_quote_fn, ("sh000001",)): _FakeFuture(value=_make_index_quote()),
            }
        )

        with (
            patch("business.stock_analysis.get_shared_executor", return_value=fake_ex),
            patch(
                "business.stock_analysis.profile_stock", return_value={"type": "普通股"}
            ),
            patch(
                "business.stock_analysis._analyze_technical",
                return_value={"ma": "多头"},
            ),
            patch("business.stock_analysis._analyze_chan", return_value={}),
        ):
            result = svc.analyze("sh600519")

        assert "财务" in result["data_failed"]
        assert "财务" not in result["data_sources"]

    def test_index_quote_fetched_separately(self):
        """P1-17: 大盘指数行情独立拉取 sh000001，而非复用个股 quote。"""
        from business.stock_analysis import StockAnalysisService

        quote = _make_quote()
        kline = _make_kline()
        finance = _make_finance()
        index = _make_index_quote()

        svc = StockAnalysisService()
        fake_ex = _FakeExecutor(
            {
                (get_quote_fn, ("sh600519",)): _FakeFuture(value=quote),
                (get_kline_fn, ("sh600519", 240, 240)): _FakeFuture(value=kline),
                (get_finance_fn, ("sh600519",)): _FakeFuture(value=finance),
                (get_quote_fn, ("sh000001",)): _FakeFuture(value=index),
            }
        )

        with (
            patch("business.stock_analysis.get_shared_executor", return_value=fake_ex),
            patch(
                "business.stock_analysis.profile_stock", return_value={"type": "蓝筹股"}
            ),
            patch(
                "business.stock_analysis._analyze_technical",
                return_value={"ma": "多头"},
            ),
            patch("business.stock_analysis._analyze_chan", return_value={}),
            patch("business.stock_analysis._calculate_composite_score") as mock_score,
        ):
            mock_score.return_value = {"total": 75}
            svc.analyze("sh600519")

        # 确认 _calculate_composite_score 收到的是指数行情（sh000001），而非个股
        call_args = mock_score.call_args
        passed_index = call_args.kwargs.get("index_quote")
        assert passed_index is not None
        assert passed_index.code == "sh000001"

    def test_all_data_failure(self):
        """P1-26: quote/kline/finance 全失败 -> data_failed 含三项，data_sources 为空。"""
        from business.stock_analysis import StockAnalysisService

        svc = StockAnalysisService()
        fake_ex = _FakeExecutor(
            {
                (get_quote_fn, ("sh600519",)): _FakeFuture(
                    exc=ConnectionError("timeout")
                ),
                (get_kline_fn, ("sh600519", 240, 240)): _FakeFuture(
                    exc=ConnectionError("timeout")
                ),
                (get_finance_fn, ("sh600519",)): _FakeFuture(exc=RuntimeError("fail")),
                (get_quote_fn, ("sh000001",)): _FakeFuture(
                    exc=ConnectionError("timeout")
                ),
            }
        )

        with (
            patch("business.stock_analysis.get_shared_executor", return_value=fake_ex),
            patch(
                "business.stock_analysis.profile_stock", return_value={"type": "未知"}
            ),
            patch("business.stock_analysis._analyze_technical", return_value={}),
            patch("business.stock_analysis._analyze_chan", return_value={}),
        ):
            result = svc.analyze("sh600519")

        assert "行情" in result["data_failed"]
        assert "K线" in result["data_failed"]
        assert "财务" in result["data_failed"]
        assert result["data_sources"] == []

    def test_finance_periods_passed_to_get_finance(self):
        """finance_periods 参数应透传至 get_finance 调用。"""
        from business.stock_analysis import StockAnalysisService

        quote = _make_quote()
        kline = _make_kline()
        finance = _make_finance()

        svc = StockAnalysisService()
        fake_ex = _FakeExecutor(
            {
                (get_quote_fn, ("sh600519",)): _FakeFuture(value=quote),
                (get_kline_fn, ("sh600519", 240, 240)): _FakeFuture(value=kline),
                # get_finance 带 periods=8 kwargs
                (get_finance_fn, ("sh600519",), (("periods", 8),)): _FakeFuture(
                    value=finance
                ),
                (get_quote_fn, ("sh000001",)): _FakeFuture(value=_make_index_quote()),
            }
        )

        with (
            patch("business.stock_analysis.get_shared_executor", return_value=fake_ex),
            patch(
                "business.stock_analysis.profile_stock", return_value={"type": "蓝筹股"}
            ),
            patch(
                "business.stock_analysis._analyze_technical",
                return_value={"ma": "多头"},
            ),
            patch("business.stock_analysis._analyze_chan", return_value={}),
        ):
            svc.analyze("sh600519", finance_periods=8)

        # 确认 get_finance 被调用时带了 periods=8
        finance_calls = [call for call in fake_ex.calls if call[0] is get_finance_fn]
        assert len(finance_calls) == 1
        # _FakeExecutor.submit 记录 (fn, args, sorted_kwargs)
        assert finance_calls[0][2] == (("periods", 8),)


# 模块级引用，供 _FakeExecutor key 匹配
from data import (
    get_quote as get_quote_fn,
    get_kline as get_kline_fn,
    get_finance as get_finance_fn,
)  # noqa: E402

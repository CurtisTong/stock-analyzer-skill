"""stock_analysis 业务流程覆盖测试（mock get_quote / get_kline / get_finance）。

覆盖 _analyze 的数据降级分支：行情失败、K线失败/不足、财务失败、
数据时间戳提取、数据来源记录、预警列表、财务摘要、综合评分路径。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import business.stock_analysis as sa
from common.exceptions import ValidationError
from data.types import Quote, KlineBar, FinanceRecord


def _bar(day, close=10.0, high=11.0, low=9.0, volume=1000):
    return KlineBar(day=day, open=close, high=high, low=low, close=close, volume=volume)


def _uptrend_bars(n=30, start=10.0):
    """生成 n 根上升趋势 K 线（close 递增），满足技术分析所需。"""
    bars = []
    for i in range(1, n + 1):
        close = round(start + i * 0.3, 2)
        bars.append(
            _bar(
                f"2025-01-{i:02d}",
                close=close,
                high=close + 0.5,
                low=close - 0.5,
                volume=1000 + i * 50,
            )
        )
    return bars


def _quote(code="sh600519", price=1800.0, name="贵州茅台"):
    return Quote(
        code=code,
        name=name,
        price=price,
        prev_close=1790,
        change_pct=0.56,
        pe=25.6,
        pb=8.2,
        total_cap=22600,
        fetch_time="2025-01-01T10:00:00",
    )


def _finance():
    return FinanceRecord(eps=50.0, roe=30.0, net_profit_yoy=18.0, revenue_yoy=15.0)


class TestNormalizeCode:
    def test_invalid_code_raises_validation_error(self):
        with pytest.raises(ValidationError):
            sa._normalize_code("invalid-code!!")

    def test_valid_code_normalized(self):
        # sh600519 已是标准格式
        assert sa._normalize_code("sh600519") == "sh600519"


class TestAnalyzeDataDegradation:
    def test_quote_failure_records_warning(self):
        """行情获取失败 -> data_warnings 记录 + data_failed。"""
        with (
            patch.object(
                sa,
                "get_quote",
                side_effect=[RuntimeError("net"), _quote("sh000001", 3000, "上证")],
            ),
            patch.object(sa, "get_kline", return_value=[]),
            patch.object(sa, "get_finance", return_value=[]),
        ):
            result = sa.analyze("sh600519", include_technical=False, include_chan=False)
        assert any("行情数据获取失败" in w for w in result["data_warnings"])
        assert "行情" in result["data_failed"]

    def test_kline_failure_records_warning(self):
        """K线获取失败 -> data_warnings 记录技术面跳过。"""
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", side_effect=RuntimeError("net")),
            patch.object(sa, "get_finance", return_value=[]),
        ):
            result = sa.analyze("sh600519", include_finance=False, include_chan=False)
        assert any("K线数据获取失败" in w for w in result["data_warnings"])
        assert "K线" in result["data_failed"]

    def test_finance_failure_records_warning(self):
        """财务获取失败 -> data_warnings 记录基本面跳过。"""
        bars = _uptrend_bars(30)
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", side_effect=RuntimeError("net")),
        ):
            result = sa.analyze("sh600519", include_chan=False)
        assert any("财务数据获取失败" in w for w in result["data_warnings"])
        assert "财务" in result["data_failed"]

    def test_insufficient_kline_records_warning(self):
        """K线不足 10 根 -> warning + data_warnings。"""
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=[_bar("2025-01-01")]),
            patch.object(sa, "get_finance", return_value=[]),
        ):
            result = sa.analyze("sh600519", include_chan=False)
        assert result.get("warning") == "K线数据不足"
        assert any("K线数据不足" in w for w in result["data_warnings"])


class TestAnalyzeDataSources:
    def test_data_sources_recorded(self):
        """成功获取的数据记录到 data_sources。"""
        bars = _uptrend_bars(30)
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", return_value=[_finance()]),
        ):
            result = sa.analyze("sh600519", include_chan=False)
        assert "行情" in result["data_sources"]
        assert "K线" in result["data_sources"]
        assert "财务" in result["data_sources"]

    def test_data_time_from_quote_fetch_time(self):
        """quote.fetch_time 优先作为 data_time。"""
        bars = _uptrend_bars(30)
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", return_value=[]),
        ):
            result = sa.analyze("sh600519", include_finance=False, include_chan=False)
        assert result["data_time"] == "2025-01-01T10:00:00"

    def test_data_time_fallback_to_kline_day(self):
        """quote 无 fetch_time 时用 K线最后一根 day。"""
        q = _quote()
        q.fetch_time = ""
        bars = _uptrend_bars(30)
        with (
            patch.object(sa, "get_quote", side_effect=[q, _quote("sh000001", 3000)]),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", return_value=[]),
        ):
            result = sa.analyze("sh600519", include_finance=False, include_chan=False)
        assert result["data_time"] == "2025-01-30"


class TestAnalyzeFinanceSummary:
    def test_finance_summary_extracted(self):
        """财务数据成功时提取 finance 摘要。"""
        bars = _uptrend_bars(30)
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", return_value=[_finance()]),
        ):
            result = sa.analyze("sh600519", include_chan=False)
        assert "finance" in result
        assert result["finance"]["eps"] == 50.0

    def test_finance_unavailable_warning(self):
        """include_finance=True 但无财务数据 -> 警告。"""
        bars = _uptrend_bars(30)
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", return_value=[]),
        ):
            result = sa.analyze("sh600519", include_chan=False)
        assert any("财务数据不可用" in w for w in result["data_warnings"])


class TestAnalyzeCompositeScore:
    def test_composite_score_when_technical_and_profile_present(self):
        """technical + profile 同时存在时计算综合评分。"""
        bars = _uptrend_bars(30)
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", return_value=[_finance()]),
        ):
            result = sa.analyze("sh600519", include_chan=False)
        # technical 和 profile 都在时应触发 score 计算
        assert "technical" in result
        assert "profile" in result


class TestStockAnalysisService:
    def test_service_delegates_to_module_analyze(self):
        """StockAnalysisService.analyze 委托模块级 _analyze。"""
        bars = _uptrend_bars(30)
        with (
            patch.object(
                sa, "get_quote", side_effect=[_quote(), _quote("sh000001", 3000)]
            ),
            patch.object(sa, "get_kline", return_value=bars),
            patch.object(sa, "get_finance", return_value=[_finance()]),
        ):
            service = sa.StockAnalysisService()
            result = service.analyze("sh600519", include_chan=False)
        assert result["code"] == "sh600519"
        assert service.min_kline_days == 30

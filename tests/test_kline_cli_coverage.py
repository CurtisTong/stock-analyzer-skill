"""K 线 CLI 覆盖测试（mock get_kline）。

覆盖 kline.py 的 main()（--sources / 无 symbol 报错 / JSON 输出 / 表格输出）、
fetch()、aggregate_klines（week/month/空/异常日期）、render_table。
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import kline
from common.exceptions import DataError


class TestFetch:
    def test_fetch_returns_dicts(self):
        """fetch 调用 get_kline 并转换为 dict 列表。"""
        bar = MagicMock()
        bar.to_dict.return_value = {"day": "2025-01-01", "open": 10, "close": 11}
        with patch.object(kline, "get_kline", return_value=[bar]):
            result = kline.fetch("sh600519", 240, 5)
        assert result == [{"day": "2025-01-01", "open": 10, "close": 11}]
        bar.to_dict.assert_called_once()


class TestRenderTable:
    def test_empty_records(self):
        assert kline.render_table([]) == "(无数据)"

    def test_renders_lines(self):
        records = [
            {
                "day": "2025-01-01",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000,
            },
        ]
        out = kline.render_table(records)
        assert "2025-01-01" in out
        assert "O:" in out and "C:" in out


class TestAggregateKlines:
    def test_empty_returns_empty(self):
        assert kline.aggregate_klines([]) == []

    def test_week_aggregation(self):
        """同一 ISO 周的多根日 K 聚合为一根周 K。"""
        records = [
            {
                "day": "2025-01-06",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            },
            {
                "day": "2025-01-07",
                "open": 10.5,
                "high": 12,
                "low": 10,
                "close": 11.5,
                "volume": 200,
            },
            {
                "day": "2025-01-13",
                "open": 11.5,
                "high": 13,
                "low": 11,
                "close": 12.5,
                "volume": 150,
            },
        ]
        result = kline.aggregate_klines(records, period="week")
        assert len(result) == 2
        # 第一周：open=10, high=12, low=9, close=11.5, volume=300
        assert result[0]["open"] == 10
        assert result[0]["high"] == 12
        assert result[0]["low"] == 9
        assert result[0]["close"] == 11.5
        assert result[0]["volume"] == 300

    def test_month_aggregation(self):
        """按月聚合。"""
        records = [
            {
                "day": "2025-01-05",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            },
            {
                "day": "2025-02-03",
                "open": 10.5,
                "high": 12,
                "low": 10,
                "close": 11.5,
                "volume": 200,
            },
        ]
        result = kline.aggregate_klines(records, period="month")
        assert len(result) == 2
        assert result[0]["day"] == "2025-01-05"

    def test_invalid_date_fallback(self):
        """异常日期字符串时按前 8 位分组（不崩溃）。"""
        records = [
            {
                "day": "bad-date",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            },
        ]
        result = kline.aggregate_klines(records)
        assert len(result) == 1


class TestMain:
    def test_sources_flag(self, capsys):
        """--sources 打印可用数据源。"""
        fake_fetcher = MagicMock()
        fake_fetcher.name = "sina"
        fake_fetcher.priority = 10
        with (
            patch("sys.argv", ["kline.py", "--sources"]),
            patch("fetchers.get_kline_fetchers", return_value=[fake_fetcher]),
            patch("common.cache.cleanup_tmp_files"),
        ):
            kline.main()
        out = capsys.readouterr().out
        assert "可用 K 线数据源" in out
        assert "sina" in out

    def test_no_symbol_raises_error(self):
        """无 symbol 时调用 err 抛 DataError。"""
        with patch("sys.argv", ["kline.py"]), patch("common.cache.cleanup_tmp_files"):
            with pytest.raises(DataError):
                kline.main()

    def test_json_output(self, capsys):
        """-j 输出 JSON。"""
        records = [
            {
                "day": "2025-01-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            }
        ]
        with (
            patch("sys.argv", ["kline.py", "sh600519", "240", "5", "-j"]),
            patch("common.cache.cleanup_tmp_files"),
            patch.object(kline, "fetch", return_value=records),
        ):
            kline.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed == records

    def test_table_output(self, capsys):
        """默认表格输出。"""
        records = [
            {
                "day": "2025-01-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            }
        ]
        with (
            patch("sys.argv", ["kline.py", "sh600519", "240", "5"]),
            patch("common.cache.cleanup_tmp_files"),
            patch.object(kline, "fetch", return_value=records),
        ):
            kline.main()
        out = capsys.readouterr().out
        assert "2025-01-01" in out
        assert "O:" in out

    def test_default_scale_and_datalen(self, capsys):
        """仅传 symbol 时使用默认 scale=240 datalen=30。"""
        records = [
            {
                "day": "2025-01-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            }
        ]
        with (
            patch("sys.argv", ["kline.py", "sh600519"]),
            patch("common.cache.cleanup_tmp_files"),
            patch.object(kline, "fetch", return_value=records) as mock_fetch,
        ):
            kline.main()
        # 验证默认参数
        call_args = mock_fetch.call_args
        assert call_args[0][1] == 240  # scale
        assert call_args[0][2] == 30  # datalen

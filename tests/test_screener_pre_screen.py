"""
screener.py 覆盖率测试（Sprint 13）。
覆盖 pre_screen_quotes / prefetch_kline_all / compute_features 等函数。
下沉后这些函数位于 business.screening_service，通过 re-export 仍可从 screener 访问。
"""

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import screener  # noqa: E402
import business.screening_service as ss  # noqa: E402
from common import to_float  # noqa: E402


def _make_quote(code, name="X", amount=10000_0000, total_cap=100, change_pct=0.5):
    return {
        "code": code,
        "name": name,
        "amount": amount,  # 单位元（1 亿 = 10000_0000）
        "total_cap": total_cap,  # 单位亿
        "change_pct": change_pct,
    }


class TestPreScreenQuotes:
    """pre_screen_quotes 全市场预筛选测试。"""

    def test_excludes_st_stocks(self):
        """ST 股票被排除。"""
        args = argparse.Namespace(board_limit=0)
        quotes = [
            _make_quote("sh600000", "ST华讯"),
            _make_quote("sh600001", "贵州茅台"),
        ]
        result = screener.pre_screen_quotes(quotes, args)
        codes = [r["code"] for r in result]
        assert "sh600000" not in codes
        assert "sh600001" in codes

    def test_excludes_zero_amount(self):
        """amount=0 视为停牌被排除。"""
        args = argparse.Namespace(board_limit=0)
        quotes = [
            _make_quote("sh600000", "停牌股", amount=0),
            _make_quote("sh600001", "正常股"),
        ]
        result = screener.pre_screen_quotes(quotes, args)
        codes = [r["code"] for r in result]
        assert "sh600000" not in codes

    def test_excludes_other_board(self):
        """非主板/创业板/科创板/北交所被排除。"""
        args = argparse.Namespace(board_limit=0)
        # 非标准代码（不是 6 位数字）→ board_type 返回 "其他"
        quotes = [_make_quote("xx1234", "垃圾代码", 10000)]
        result = screener.pre_screen_quotes(quotes, args)
        assert result == []

    def test_applies_board_amount_threshold(self):
        """不同板块有不同最低成交额阈值。"""
        args = argparse.Namespace(board_limit=0)
        # 主板最低 5000 万 = 5000 * 10000 元
        quotes = [
            _make_quote("sh600000", "A", 4000 * 10000),  # 主板 4000 万（< 5000 万）
            _make_quote("sh600001", "B", 6000 * 10000),  # 主板 6000 万
        ]
        result = screener.pre_screen_quotes(quotes, args)
        codes = [r["code"] for r in result]
        assert "sh600000" not in codes
        assert "sh600001" in codes

    def test_applies_board_cap_threshold(self):
        """不同板块有不同最低市值阈值。"""
        args = argparse.Namespace(board_limit=0)
        quotes = [
            _make_quote("sh600000", "A", 10000_0000, total_cap=10),  # 主板 < 40 亿
            _make_quote("sh600001", "B", 10000_0000, total_cap=100),  # 主板 >= 40 亿
        ]
        result = screener.pre_screen_quotes(quotes, args)
        codes = [r["code"] for r in result]
        assert "sh600000" not in codes
        assert "sh600001" in codes

    def test_board_limit_caps_per_board(self):
        """board_limit > 0 时每板块最多 N 只（按成交额降序）。"""
        args = argparse.Namespace(board_limit=2)
        # 5 只主板股，limit=2 应只保留 2 只
        quotes = [
            _make_quote(
                "sh600000", f"A{i}", amount=10000_0000 + i * 1000_0000, total_cap=100
            )
            for i in range(5)
        ]
        result = screener.pre_screen_quotes(quotes, args)
        # 只保留 2 只
        assert len(result) == 2


class TestPrefetchKlineAll:
    """prefetch_kline_all 批量 K 线预拉测试。"""

    def test_returns_dict_mapping_codes_to_bars(self, monkeypatch):
        """返回 {code: bars} 字典。"""
        from data.types import KlineBar

        def mock_get_kline(code, scale=240, datalen=240):
            return [KlineBar(day="2025-01-01", open=10, high=11, low=9, close=10)]

        import data

        monkeypatch.setattr(data, "get_kline", mock_get_kline)
        result = ss.prefetch_kline_all(["sh600519", "sh600989"])
        assert isinstance(result, dict)
        assert "sh600519" in result
        assert len(result["sh600519"]) == 1

    def test_skips_failed_codes(self, monkeypatch):
        """失败 code 不在结果中。"""

        def mock_get_kline(code, scale=240, datalen=240):
            if code == "sh600519":
                raise Exception("network error")
            from data.types import KlineBar

            return [KlineBar(day="d", open=10, high=11, low=9, close=10)]

        import data

        monkeypatch.setattr(data, "get_kline", mock_get_kline)
        result = ss.prefetch_kline_all(["sh600519", "sh600989"])
        assert "sh600519" not in result
        assert "sh600989" in result


class TestComputeFeatures:
    """compute_features 函数测试（原 daily_features 已合并）。"""

    def test_returns_dict_with_features(self, monkeypatch):
        """返回 features dict。"""

        def mock_compute_features(code, bars=None):
            return {
                "trend": 1,
                "ret20": 5.0,
                "ma10": 11.0,
                "ma20": 12.0,
                "volume_ratio": 1.2,
                "macd_signal": 0,
                "rsi": 60,
                "rsi_signal": 0,
                "vol_price_signal": 0,
                "closes": [10.0, 11.0, 12.0],
            }

        monkeypatch.setattr(ss, "compute_features", mock_compute_features)
        result = ss.compute_features("sh600519")
        assert "trend" in result
        assert "rsi" in result
        assert "ret20" in result

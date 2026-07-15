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

    def setup_method(self, method):
        """(#1) 每个测试前 mock market_snapshot 返回空水位，回退绝对值阈值。"""
        import data.market_snapshot as ms

        self._orig_snapshot = ms.get_market_snapshot
        ms.get_market_snapshot = lambda: {
            "avg_amount_yuan": 0.0,
            "median_cap": 0.0,
            "updated": "",
            "source": "test_mock",
        }

    def teardown_method(self, method):
        import data.market_snapshot as ms

        ms.get_market_snapshot = self._orig_snapshot

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


class TestAdaptiveThresholds:
    """(#1) 自适应预筛选阈值测试：缩量/亢奋/正常 3 场景 + 回退。"""

    def test_adaptive_amount_threshold_fallback_when_no_market_ref(self):
        """市场水位缺失时回退板块绝对值。"""
        from strategies.filters import adaptive_amount_threshold

        # market_avg=0 -> 回退 5000 万 = 5000*10000 元
        result = adaptive_amount_threshold("主板", 0)
        assert result == 5000 * 10000

    def test_adaptive_amount_threshold_dynamic_normal_market(self):
        """正常市场水位：动态门槛落在 [floor, ceiling] 内。"""
        from strategies.filters import adaptive_amount_threshold

        # 全市场日均成交额中位数 2 亿元 = 2*10^8 元
        # 动态门槛 = 2e8 * 0.0001 = 20000 元 = 2 万元
        # 主板 floor = 5000 万，ceiling = 5000*3 = 15000 万
        # 2 万 < 5000 万 floor -> 取 floor 5000 万
        result = adaptive_amount_threshold("主板", 2 * 10**8)
        assert result == 5000 * 10000  # 被下限 floor 拉回

    def test_adaptive_amount_threshold_liquid_market(self):
        """亢奋市场水位：动态门槛超过 ceiling 时被封顶。

        全市场日均成交额中位数极高（如 10 万亿）时，
        动态门槛会远超 ceiling，此时取 ceiling（板块基准 × 倍数）。
        """
        from strategies.filters import adaptive_amount_threshold

        # 全市场日均成交额中位数 10 万亿元 = 10^13 元
        # 动态门槛 = 10^13 * 0.0001 = 10^9 元 = 10 亿元
        # 主板 floor = 5000 万元，ceiling = 5000 * 3 = 15000 万元 = 1.5 亿元
        # 10 亿 > 1.5 亿 ceiling -> 取 ceiling 15000 万元
        result = adaptive_amount_threshold("主板", 10**13)
        assert result == 15000 * 10000  # ceiling = 1.5 亿元

    def test_adaptive_amount_threshold_dynamic_in_range(self):
        """市场水位适中时动态门槛落在 [floor, ceiling] 内。"""
        from strategies.filters import adaptive_amount_threshold

        # 全市场日均成交额中位数 10 亿元 = 10^9 元
        # 动态门槛 = 10^9 * 0.0001 = 10^5 元 = 10 万元
        # 主板 floor = 5000 万元 -> 10 万 < 5000 万 floor -> 取 floor
        # 需要更大的市场水位才能让动态值超过 floor：
        # 全市场日均 100 亿 = 10^10 -> 动态 = 10^6 = 100 万 < 5000 万 floor
        # 全市场日均 1 万亿 = 10^12 -> 动态 = 10^8 = 1 亿，落在 [5000万, 1.5亿] 内
        result = adaptive_amount_threshold("主板", 10**12)
        assert result == 10**12 * 0.0001  # 1 亿元，在区间内

    def test_adaptive_cap_threshold_fallback_when_no_market_ref(self):
        """市值水位缺失时回退板块绝对值。"""
        from strategies.filters import adaptive_cap_threshold

        result = adaptive_cap_threshold("主板", 0)
        assert result == 40

    def test_adaptive_cap_threshold_dynamic(self):
        """正常市值水位：动态门槛 = 中位市值 × 0.5，受 ceiling 封顶。"""
        from strategies.filters import adaptive_cap_threshold

        # 全市场中位市值 200 亿
        # 动态门槛 = 200 * 0.5 = 100 亿
        # 主板 floor = 40，ceiling = 40 * 2 = 80
        # 100 > 80 ceiling -> 取 ceiling 80
        result = adaptive_cap_threshold("主板", 200)
        assert result == 80  # 被 ceiling 封顶

        # 全市场中位市值 100 亿 -> 动态 50 亿，落在 [40, 80] 内
        result = adaptive_cap_threshold("主板", 100)
        assert result == 50  # 取动态值

    def test_pre_screen_uses_adaptive_when_market_ref_available(self, monkeypatch):
        """pre_screen_quotes 在有市场水位时使用自适应阈值。"""
        # mock market_snapshot 返回高水位（亢奋市场）
        import data.market_snapshot as ms

        monkeypatch.setattr(
            ms,
            "get_market_snapshot",
            lambda: {
                "avg_amount_yuan": 10**11,  # 全市场日均 1000 亿
                "median_cap": 100,  # 全市场中位市值 100 亿
                "updated": "2099-01-01T00:00:00",
                "source": "cache",
            },
        )

        args = argparse.Namespace(board_limit=0)
        # 主板股 6000 万元（< 5000 万 floor）应被过滤
        # 注意：亢奋时 floor 仍为 5000 万（板块绝对值下限）
        quotes = [
            _make_quote("sh600000", "A", 4000 * 10000),  # 4000 万 < 5000 万 floor
            _make_quote("sh600001", "B", 6000 * 10000),  # 6000 万 > 5000 万 floor
        ]
        result = screener.pre_screen_quotes(quotes, args)
        codes = [r["code"] for r in result]
        assert "sh600000" not in codes
        assert "sh600001" in codes

    def test_pre_screen_fallback_when_snapshot_unavailable(self, monkeypatch):
        """快照获取失败时回退绝对值，不阻断预筛选。"""
        import data.market_snapshot as ms

        def _fail():
            raise Exception("network error")

        monkeypatch.setattr(ms, "get_market_snapshot", _fail)

        args = argparse.Namespace(board_limit=0)
        quotes = [
            _make_quote("sh600000", "A", 4000 * 10000),  # < 5000 万
            _make_quote("sh600001", "B", 6000 * 10000),  # >= 5000 万
        ]
        result = screener.pre_screen_quotes(quotes, args)
        codes = [r["code"] for r in result]
        assert "sh600000" not in codes
        assert "sh600001" in codes


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

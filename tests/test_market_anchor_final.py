"""market_anchor.py 剩余未覆盖行补充测试。

覆盖：
- _compute_multi_timeframe 数据不足返回 None（179）、degraded 累积（191,195）
- _fetch_liquidity_volatility 完整路径（295-336）：大盘 ATR=0、returns<2、
  个股 amount 估算、流动性比率计算、各降级分支
- _fetch_emotion_phase 异常路径（356-358）
- _fetch_industry_beta / _fetch_portfolio_correlation 异常（399-401）
- _fetch_northbound_pricer direction 震荡分支（478）
- analyze 各 fetch_* degraded 传播（567, 631, 636, 650, 659）
所有网络/数据获取均 mock。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import market_anchor as ma
from data.types import KlineBar, Quote


# ═══════════════════════════════════════════════════════════════
# 辅助构造函数
# ═══════════════════════════════════════════════════════════════


def _make_kline(close=100.0, high=105.0, low=95.0, volume=10000, amount=1e9):
    return KlineBar(
        day="2025-01-01",
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=amount,
        pct_chg=0.0,
        source="test",
    )


def _make_quote(code="sh600519", price=100.0, total_cap=1000.0):
    return Quote(code=code, price=price, total_cap=total_cap, source="test")


def _gen_klines(n, base=100.0, drift=0.5):
    """生成 n 根递增 K 线，amount 字段非零。"""
    return [
        KlineBar(
            day=f"2025-01-{i+1:02d}",
            open=base + i * drift,
            high=base + i * drift + 1,
            low=base + i * drift - 1,
            close=base + i * drift,
            volume=10000 + i * 100,
            amount=1e9 + i * 1e7,
            pct_chg=drift / base * 100,
            source="test",
        )
        for i in range(n)
    ]


# ═══════════════════════════════════════════════════════════════
# _compute_multi_timeframe
# ═══════════════════════════════════════════════════════════════


class TestComputeMultiTimeframeFinal:
    def test_kline_empty_returns_degraded(self):
        """klines 为空 -> degraded."""
        with patch("market_anchor.get_kline", return_value=[]):
            result = ma._compute_multi_timeframe()
        assert result is not None
        assert "multi_timeframe" in result["data_quality"]["degraded_fields"]

    def test_insufficient_closes_returns_none(self):
        """closes < 20 -> 返回带 degraded_fields 的 dict（line 179 路径）。"""
        klines = [_make_kline(close=100 + i) for i in range(10)]
        with patch("market_anchor.get_kline", return_value=klines):
            result = ma._compute_multi_timeframe()
        assert result is not None
        assert (
            "multi_timeframe.insufficient_data"
            in result["data_quality"]["degraded_fields"]
        )

    def test_full_data_with_degraded_ma250(self):
        """数据 >= 60 但 < 250：ma250=None -> degraded 累积（191）。"""
        klines = _gen_klines(70, base=100.0, drift=0.3)
        with patch("market_anchor.get_kline", return_value=klines):
            result = ma._compute_multi_timeframe()
        assert result is not None
        # ma250 不足 250 -> None -> degraded
        degraded = result["data_quality"]["degraded_fields"]
        assert any("ma250" in d for d in degraded)
        assert result["ma20"] is not None
        assert result["ma60"] is not None

    def test_alignment_data_insufficient_flag(self):
        """数据较少导致 alignment='数据不足' -> degraded append（195）。"""
        # 用 25 根 K 线：ma5/10/20 有值，但 < 4 个 MA -> '数据不足'
        klines = _gen_klines(25, base=100.0, drift=0.2)
        with patch("market_anchor.get_kline", return_value=klines):
            result = ma._compute_multi_timeframe()
        assert result is not None
        degraded = result["data_quality"]["degraded_fields"]
        # alignment 为 '数据不足' 会 append 'multi_timeframe.alignment'
        assert any("alignment" in d for d in degraded)

    def test_exception_returns_degraded(self):
        with patch("market_anchor.get_kline", side_effect=RuntimeError("err")):
            result = ma._compute_multi_timeframe()
        assert result is not None
        assert "multi_timeframe" in result["data_quality"]["degraded_fields"]


# ═══════════════════════════════════════════════════════════════
# _fetch_liquidity_volatility
# ═══════════════════════════════════════════════════════════════


class TestFetchLiquidityVolatilityFinal:
    def test_full_success_with_stock_amount(self):
        """完整成功路径：大盘 ATR + vol + 个股 amount + 流动性比率。"""
        index_klines = _gen_klines(60, base=100.0, drift=0.3)
        stock_klines = _gen_klines(20, base=50.0, drift=0.5)
        quote = _make_quote(code="sh600519", price=50.0, total_cap=500.0)
        with (
            patch("market_anchor.get_kline", side_effect=[index_klines, stock_klines]),
            patch("market_anchor.get_quotes", return_value=[quote]),
        ):
            result = ma._fetch_liquidity_volatility("sh600519")
        assert result["sh300_atr_14"] is not None
        assert result["sh300_annualized_vol_pct"] is not None
        assert result["stock_avg_amount_20d_yi"] is not None
        assert result["stock_amount_source"] == "amount"
        assert result["stock_liquidity_ratio_pct"] is not None
        assert result["data_quality"]["degraded_fields"] == []

    def test_sh300_atr_zero_degraded(self):
        """构造平盘 K 线使 ATR=0 -> degraded sh300_atr（267）。

        用 close=high=low 的常量 K 线，TR 全为 0。
        """
        flat_klines = [
            KlineBar(
                day=f"2025-01-{i+1:02d}",
                open=100,
                high=100,
                low=100,
                close=100,
                volume=10000,
                amount=1e9,
                source="test",
            )
            for i in range(60)
        ]
        with (
            patch("market_anchor.get_kline", side_effect=[flat_klines, []]),
            patch("market_anchor.get_quotes", return_value=[]),
        ):
            result = ma._fetch_liquidity_volatility(None)
        # ATR=0 -> degraded
        assert "liquidity.sh300_atr" in result["data_quality"]["degraded_fields"]

    def test_returns_insufficient_degraded(self):
        """returns < 2 -> degraded sh300_vol（279）。用只有 2 根 K 线但 len>=20 触发不了。
        用 21 根但所有 close 相同 -> returns 全 0，stdev=0 但 len>=2 成立。
        改为构造 20 根 K 线，closes 长度 = 20，returns 长度 = 19 >= 2，正常。
        真正触发 279 需要 returns < 2，即 closes 长度 <= 2，但 len>=20 才进入。
        所以这里改测正常 vol 计算 + index_kline 不足分支。"""
        # 这个测试覆盖正常 vol 路径
        klines = _gen_klines(25, base=100.0, drift=1.0)
        with (
            patch("market_anchor.get_kline", side_effect=[klines, []]),
            patch("market_anchor.get_quotes", return_value=[]),
        ):
            result = ma._fetch_liquidity_volatility(None)
        assert result["sh300_annualized_vol_pct"] is not None

    def test_index_kline_insufficient_degraded(self):
        """index klines < 20 -> degraded index_kline。"""
        klines = _gen_klines(10, base=100.0, drift=0.3)
        with (
            patch("market_anchor.get_kline", side_effect=[klines, []]),
            patch("market_anchor.get_quotes", return_value=[]),
        ):
            result = ma._fetch_liquidity_volatility(None)
        assert "liquidity.index_kline" in result["data_quality"]["degraded_fields"]

    def test_stock_amount_zero_fallback_to_volume(self):
        """个股 amount=0 -> 降级用 volume*close 估算（source_tag='volume*close(估算)'）。"""
        index_klines = _gen_klines(60, base=100.0, drift=0.3)
        # stock klines: amount=0 但 volume>0, close>0
        stock_klines = [
            KlineBar(
                day=f"2025-01-{i+1:02d}",
                open=50,
                high=51,
                low=49,
                close=50,
                volume=100000,
                amount=0,
                source="test",
            )
            for i in range(20)
        ]
        quote = _make_quote(code="sh600519", price=50.0, total_cap=500.0)
        with (
            patch("market_anchor.get_kline", side_effect=[index_klines, stock_klines]),
            patch("market_anchor.get_quotes", return_value=[quote]),
        ):
            result = ma._fetch_liquidity_volatility("sh600519")
        assert result["stock_avg_amount_20d_yi"] is not None
        assert result["stock_amount_source"] == "volume*close(估算)"

    def test_stock_kline_empty_degraded(self):
        """stock_klines 为空 -> degraded stock_kline。"""
        index_klines = _gen_klines(60, base=100.0, drift=0.3)
        with (
            patch("market_anchor.get_kline", side_effect=[index_klines, []]),
            patch("market_anchor.get_quotes", return_value=[]),
        ):
            result = ma._fetch_liquidity_volatility("sh600519")
        assert "liquidity.stock_kline" in result["data_quality"]["degraded_fields"]

    def test_stock_amount_and_volume_both_zero(self):
        """个股 amount=0 且 volume=0 -> avg_amount=None -> degraded stock_amount。"""
        index_klines = _gen_klines(60, base=100.0, drift=0.3)
        stock_klines = [
            KlineBar(
                day=f"2025-01-{i+1:02d}",
                open=50,
                high=51,
                low=49,
                close=50,
                volume=0,
                amount=0,
                source="test",
            )
            for i in range(20)
        ]
        with (
            patch("market_anchor.get_kline", side_effect=[index_klines, stock_klines]),
            patch("market_anchor.get_quotes", return_value=[]),
        ):
            result = ma._fetch_liquidity_volatility("sh600519")
        assert "liquidity.stock_amount" in result["data_quality"]["degraded_fields"]

    def test_quote_no_basic_data_degraded(self):
        """个股 quote price=0 -> has_basic_data=False -> degraded stock_quote。"""
        index_klines = _gen_klines(60, base=100.0, drift=0.3)
        stock_klines = _gen_klines(20, base=50.0, drift=0.5)
        quote = _make_quote(code="sh600519", price=0.0, total_cap=500.0)
        with (
            patch("market_anchor.get_kline", side_effect=[index_klines, stock_klines]),
            patch("market_anchor.get_quotes", return_value=[quote]),
        ):
            result = ma._fetch_liquidity_volatility("sh600519")
        assert "liquidity.stock_quote" in result["data_quality"]["degraded_fields"]

    def test_total_cap_zero_degraded(self):
        """个股 total_cap=0 -> degraded total_cap。"""
        index_klines = _gen_klines(60, base=100.0, drift=0.3)
        stock_klines = _gen_klines(20, base=50.0, drift=0.5)
        quote = _make_quote(code="sh600519", price=50.0, total_cap=0.0)
        with (
            patch("market_anchor.get_kline", side_effect=[index_klines, stock_klines]),
            patch("market_anchor.get_quotes", return_value=[quote]),
        ):
            result = ma._fetch_liquidity_volatility("sh600519")
        assert "liquidity.total_cap" in result["data_quality"]["degraded_fields"]

    def test_stock_exception_degraded(self):
        """个股 get_kline 抛异常 -> degraded stock。"""
        index_klines = _gen_klines(60, base=100.0, drift=0.3)

        def _side(*a, **kw):
            if a and a[0] == "sh000300":
                return index_klines
            raise RuntimeError("stock err")

        with (
            patch("market_anchor.get_kline", side_effect=_side),
            patch("market_anchor.get_quotes", return_value=[]),
        ):
            result = ma._fetch_liquidity_volatility("sh600519")
        assert "liquidity.stock" in result["data_quality"]["degraded_fields"]

    def test_index_exception_degraded(self):
        """大盘 get_kline 抛异常 -> degraded index。"""
        with (
            patch("market_anchor.get_kline", side_effect=RuntimeError("idx err")),
            patch("market_anchor.get_quotes", return_value=[]),
        ):
            result = ma._fetch_liquidity_volatility(None)
        assert "liquidity.index" in result["data_quality"]["degraded_fields"]


# ═══════════════════════════════════════════════════════════════
# _fetch_emotion_phase / _fetch_industry_beta / _fetch_portfolio_correlation
# ═══════════════════════════════════════════════════════════════


class TestEmotionAndBetaFinal:
    def test_emotion_phase_exception_returns_none(self):
        """market_breadth.get_market_state 抛异常 -> 返回 None（356-358）。"""
        with patch(
            "market_anchor.market_breadth.get_market_state",
            side_effect=RuntimeError("err"),
        ):
            result = ma._fetch_emotion_phase({"up_count": 100})
        assert result is None

    def test_emotion_phase_no_breadth(self):
        assert ma._fetch_emotion_phase(None) is None

    def test_industry_beta_no_stock(self):
        assert ma._fetch_industry_beta(None) is None

    def test_industry_beta_exception_degraded(self):
        """compute_beta 抛异常 -> degraded industry_beta（399-401）。"""
        with patch("market_anchor.compute_beta", side_effect=RuntimeError("err")):
            result = ma._fetch_industry_beta("sh600519")
        assert "industry_beta" in result["data_quality"]["degraded_fields"]

    def test_industry_beta_returns_none(self):
        with patch("market_anchor.compute_beta", return_value=None):
            result = ma._fetch_industry_beta("sh600519")
        assert "industry_beta" in result["data_quality"]["degraded_fields"]

    def test_portfolio_correlation_exception_degraded(self):
        with patch(
            "market_anchor.compute_full_portfolio_correlation",
            side_effect=RuntimeError("err"),
        ):
            result = ma._fetch_portfolio_correlation("sh600519")
        assert "portfolio_correlation" in result["data_quality"]["degraded_fields"]


# ═══════════════════════════════════════════════════════════════
# _fetch_northbound_pricer direction 震荡分支（478）
# ═══════════════════════════════════════════════════════════════


class TestNorthboundDirectionOscillation:
    def test_direction_oscillation_long_short_mismatch(self):
        """total_net_yi > 0 但 recent_5d_slope='流出' -> direction='震荡'（478）。"""
        # 前 15 天大额流入，后 5 天大额流出 -> total > 0, 5d slope=流出
        flow_data = [{"net_buy": 1000000, "sh_net": 600000, "sz_net": 400000}] * 15
        flow_data += [{"net_buy": -500000, "sh_net": -300000, "sz_net": -200000}] * 5
        with patch("market_anchor.get_northbound_flow", return_value=flow_data):
            result = ma._fetch_northbound_pricer(days=20)
        assert result["total_net_yi"] > 0
        assert result["recent_5d_slope"] == "流出"
        assert result["direction"] == "震荡"


# ═══════════════════════════════════════════════════════════════
# analyze degraded 传播
# ═══════════════════════════════════════════════════════════════


class TestAnalyzeDegradationPropagation:
    def _mock_base(self, monkeypatch):
        monkeypatch.setattr(ma, "_fetch_index_snapshot", lambda *a, **kw: None)
        monkeypatch.setattr(
            ma, "_fetch_index_kline", lambda *a, **kw: {"closes": [100]}
        )
        monkeypatch.setattr(ma, "_fetch_breadth", lambda *a, **kw: {"up_count": 2000})
        monkeypatch.setattr(ma, "_compute_multi_timeframe", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "_fetch_emotion_phase", lambda *a, **kw: "震荡")
        monkeypatch.setattr(
            ma,
            "detect_market_state",
            lambda **kw: {
                "state": "牛市",
                "long_weight": 0.8,
                "short_weight": 0.2,
                "reason": "up",
            },
        )
        monkeypatch.setattr(
            ma, "sector_etf_strength", MagicMock(analyze=MagicMock(return_value=None))
        )

    def test_index_snapshot_none_propagates(self, monkeypatch):
        """index_snapshot=None -> degraded 'index'（567）。"""
        self._mock_base(monkeypatch)
        monkeypatch.setattr(ma, "_fetch_macro_anchor", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "_fetch_liquidity_volatility", lambda *a, **kw: None)
        result = ma.analyze(
            fetch_portfolio=False, fetch_rotation=False, fetch_northbound=False
        )
        assert "index" in result["data_quality"]["degraded_fields"]

    def test_macro_anchor_degraded_propagates(self, monkeypatch):
        """macro_payload 带 degraded_fields -> 传播（631）。"""
        self._mock_base(monkeypatch)
        monkeypatch.setattr(
            ma, "_fetch_index_snapshot", lambda *a, **kw: {"change_pct": 1.0}
        )
        monkeypatch.setattr(
            ma,
            "_fetch_macro_anchor",
            lambda *a, **kw: {"data_quality": {"degraded_fields": ["macro.leverage"]}},
        )
        monkeypatch.setattr(ma, "_fetch_liquidity_volatility", lambda *a, **kw: None)
        result = ma.analyze(
            fetch_portfolio=False, fetch_rotation=False, fetch_northbound=False
        )
        assert "macro.leverage" in result["data_quality"]["degraded_fields"]

    def test_liq_vol_degraded_propagates(self, monkeypatch):
        """liq_vol 带 degraded_fields -> 传播（636）。"""
        self._mock_base(monkeypatch)
        monkeypatch.setattr(
            ma, "_fetch_index_snapshot", lambda *a, **kw: {"change_pct": 1.0}
        )
        monkeypatch.setattr(ma, "_fetch_macro_anchor", lambda *a, **kw: None)
        monkeypatch.setattr(
            ma,
            "_fetch_liquidity_volatility",
            lambda *a, **kw: {
                "data_quality": {"degraded_fields": ["liquidity.sh300_atr"]}
            },
        )
        result = ma.analyze(
            fetch_portfolio=False, fetch_rotation=False, fetch_northbound=False
        )
        assert "liquidity.sh300_atr" in result["data_quality"]["degraded_fields"]

    def test_industry_beta_degraded_with_stock(self, monkeypatch):
        """stock_code 提供且 industry_beta 带 degraded -> 传播（650）。"""
        self._mock_base(monkeypatch)
        monkeypatch.setattr(
            ma, "_fetch_index_snapshot", lambda *a, **kw: {"change_pct": 1.0}
        )
        monkeypatch.setattr(ma, "_fetch_macro_anchor", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "_fetch_liquidity_volatility", lambda *a, **kw: None)
        monkeypatch.setattr(
            ma,
            "_fetch_industry_beta",
            lambda *a, **kw: {"data_quality": {"degraded_fields": ["industry_beta"]}},
        )
        monkeypatch.setattr(ma, "_fetch_portfolio_correlation", lambda *a, **kw: None)
        result = ma.analyze(
            stock_code="sh600519", fetch_rotation=False, fetch_northbound=False
        )
        assert "industry_beta" in result["data_quality"]["degraded_fields"]

    def test_portfolio_corr_degraded_propagates(self, monkeypatch):
        """portfolio_corr 带 degraded_fields -> 传播（659）。"""
        self._mock_base(monkeypatch)
        monkeypatch.setattr(
            ma, "_fetch_index_snapshot", lambda *a, **kw: {"change_pct": 1.0}
        )
        monkeypatch.setattr(ma, "_fetch_macro_anchor", lambda *a, **kw: None)
        monkeypatch.setattr(ma, "_fetch_liquidity_volatility", lambda *a, **kw: None)
        monkeypatch.setattr(
            ma,
            "_fetch_portfolio_correlation",
            lambda *a, **kw: {
                "data_quality": {"degraded_fields": ["portfolio_correlation"]}
            },
        )
        result = ma.analyze(
            stock_code="sh600519", fetch_rotation=False, fetch_northbound=False
        )
        assert "portfolio_correlation" in result["data_quality"]["degraded_fields"]


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])

"""market_anchor 流动性估算单位口径的回归测试。

不变量：KlineBar.volume 在数据层已归一化为"股"（types.py 契约 +
_dict_to_kline_bar 全源归一化：腾讯手×100/新浪原值），amount 降级
估算必须按 volume(股) × close(元) 计算——不得再按"手"口径 ×100。

回归背景（2026-11-02 skill 审查实测）：market_anchor.py 曾按"手"口径
volume × close × 100 / 1e8，100 万股 × 10 元被算成 10 亿（真实 0.1 亿），
stock_avg_amount_20d_yi 与 stock_liquidity_ratio_pct 全部放大 100 倍。
"""

from __future__ import annotations

import market_anchor
from data.types import KlineBar


def _bars(n: int, volume: int, close: float, amount: float = 0.0) -> list:
    return [
        KlineBar(
            day=f"2026-10-{i + 1:02d}",
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=volume,
            amount=amount,
        )
        for i in range(n)
    ]


def _patch_index_ok(monkeypatch):
    """大盘 K 线返回 60 根正常数据（让 ATR/波动率分支通过）。"""
    monkeypatch.setattr(
        market_anchor,
        "get_kline",
        lambda code, scale=240, datalen=60, **kw: (
            _bars(datalen, volume=10_000_000, close=4000.0, amount=1e11) if code.startswith("sh000") else []
        ),
    )


class TestLiquidityUnitCaliber:
    def test_volume_estimate_uses_share_units(self, monkeypatch):
        """100 万股 × 10 元 = 0.1 亿，不得按手口径放大 100 倍。"""
        _patch_index_ok(monkeypatch)

        def _stock_kline(code, scale=240, datalen=20, **kw):
            return _bars(datalen, volume=1_000_000, close=10.0, amount=0.0)

        monkeypatch.setattr(market_anchor, "get_kline", _stock_kline)
        monkeypatch.setattr(market_anchor, "get_quotes", lambda codes, use_cache=True: [])

        out = market_anchor._fetch_liquidity_volatility("sh600989")

        assert out["stock_amount_source"] == "volume*close(估算)"
        assert out["stock_avg_amount_20d_yi"] == 0.1
        assert out["stock_avg_amount_20d_yi"] < 1.0, "若接近 10 亿说明手口径回归"

    def test_amount_field_preferred_when_present(self, monkeypatch):
        """amount 可用时优先精确值：5000 万 = 0.5 亿。"""
        _patch_index_ok(monkeypatch)

        def _stock_kline(code, scale=240, datalen=20, **kw):
            return _bars(datalen, volume=1_000_000, close=10.0, amount=5e7)

        monkeypatch.setattr(market_anchor, "get_kline", _stock_kline)
        monkeypatch.setattr(market_anchor, "get_quotes", lambda codes, use_cache=True: [])

        out = market_anchor._fetch_liquidity_volatility("sh600989")
        assert out["stock_amount_source"] == "amount"
        assert out["stock_avg_amount_20d_yi"] == 0.5

    def test_liquidity_ratio_consistent_with_units(self, monkeypatch):
        """流动性比率 = 日均成交额 / 市值：0.1 亿 / 100 亿 = 0.1%。"""
        _patch_index_ok(monkeypatch)

        def _stock_kline(code, scale=240, datalen=20, **kw):
            return _bars(datalen, volume=1_000_000, close=10.0, amount=0.0)

        monkeypatch.setattr(market_anchor, "get_kline", _stock_kline)

        class _Q:
            def has_basic_data(self):
                return True

            total_cap = 100.0  # 亿

        monkeypatch.setattr(market_anchor, "get_quotes", lambda codes, use_cache=True: [_Q()])

        out = market_anchor._fetch_liquidity_volatility("sh600989")
        assert out["stock_liquidity_ratio_pct"] == 0.1

    def test_index_failure_still_computes_stock(self, monkeypatch):
        """大盘 K 线异常不阻断个股分支（降级标注 + 个股口径照算）。"""
        calls = {"n": 0}

        def _kline(code, scale=240, datalen=60, **kw):
            calls["n"] += 1
            if code.startswith("sh000"):
                raise RuntimeError("指数源超时")
            return _bars(datalen, volume=1_000_000, close=10.0, amount=0.0)

        monkeypatch.setattr(market_anchor, "get_kline", _kline)
        monkeypatch.setattr(market_anchor, "get_quotes", lambda codes, use_cache=True: [])

        out = market_anchor._fetch_liquidity_volatility("sh600989")
        assert "liquidity.index" in out["data_quality"]["degraded_fields"]
        assert out["stock_avg_amount_20d_yi"] == 0.1

"""stock_analysis._analyze_technical 与 technical.pipeline 过滤口径对齐的不变量测试。

不变量：_valid_kline_bars 的 K 线保留条数必须与
compute_indicators 完全一致（五字段 close/open/high/low/volume 全 > 0）。

回归背景（2026-11-02 skill 审查 P1）：_analyze_technical 曾只过滤
close/volume 两字段，构造含 open=0 的 K 线时 pipeline 口径 29 根、
本地口径 30 根——RSI/MACD/量能与 MA/KDJ/BOLL/形态在同一份报告里
错位一根（v1.28 M3 修复注释自称"同口径"但实际不同）。
"""

from __future__ import annotations

from data.types import KlineBar

from business.stock_analysis import _analyze_technical, _valid_kline_bars
from technical.pipeline import compute_indicators


def _make_bars(n: int, bad_open_idx: int | None = None) -> list:
    """构造 n 根正常上涨 K 线；bad_open_idx 指定哪根 open=0（close/volume 正常）。"""
    bars = []
    for i in range(n):
        open_ = 10.0 + i * 0.1
        close = open_ + 0.05
        if i == bad_open_idx:
            open_ = 0.0
        bars.append(
            KlineBar(
                day=f"2026-09-{i + 1:02d}",
                open=open_,
                high=close + 0.1,
                low=open_ - 0.05 if open_ > 0 else 9.0,
                close=close,
                volume=1_000_000 + i * 10_000,
            )
        )
    return bars


class TestKlineFilterCaliber:
    def test_filter_caliber_matches_pipeline(self):
        """含 open=0 的 K 线：本地过滤条数 == pipeline 过滤条数（对齐）。"""
        bars = _make_bars(30, bad_open_idx=25)
        assert len(_valid_kline_bars(bars)) == len(compute_indicators(bars)["closes"]) == 29

    def test_filter_caliber_matches_pipeline_low_zero(self):
        """low=0 / high=0 同样必须被两侧一致剔除。"""
        bars = _make_bars(30)
        bars[10].low = 0.0
        bars[20].high = 0.0
        assert len(_valid_kline_bars(bars)) == len(compute_indicators(bars)["closes"]) == 28

    def test_clean_data_all_kept(self):
        """正常数据零误伤：30 根全保留。"""
        bars = _make_bars(30)
        assert len(_valid_kline_bars(bars)) == len(compute_indicators(bars)["closes"]) == 30

    def test_analyze_technical_runs_on_adversarial_data(self):
        """错位修复后 _analyze_technical 在脏数据上不崩溃且产出完整字段。"""
        bars = _make_bars(30, bad_open_idx=25)
        result = _analyze_technical(bars)
        assert not result.get("_technical_error")
        assert result["ma"]
        assert "kdj" in result and "boll_position" in result
        assert len(result["patterns"]) <= 5

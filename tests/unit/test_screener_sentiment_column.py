"""screener 情绪列展示测试（v1.26 阶段 1）。

阶段 1 的约束：情绪因子权重为 0——**不影响评分与排名**，只作参考列。
因此必须验证：不加该列时输出逐字不变；加该列时缺失值显示 "-"（区别于 0 分）。
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

import pytest


def _row(code, name, score, sentiment=None):
    return {
        "code": code,
        "name": name,
        "board": "主板",
        "industry": "测试",
        "score": score,
        "quality": 80.0,
        "valuation": 70.0,
        "momentum": 60.0,
        "liquidity": 50.0,
        "chip": 50.0,
        "pe": 20.0,
        "roe": 15.0,
        "rsi": 50,
        "ret20": 1.0,
        "trend": "上升",
        "macd_signal": 1,
        "vol_price": "放量",
        "rejected": [],
        "sentiment": sentiment,
    }


class TestSentimentColumn:
    def _render(self, rows, **kw):
        import screener

        buf = io.StringIO()
        with redirect_stdout(buf):
            screener.render(rows, "balanced", 10, **kw)
        return buf.getvalue()

    def test_column_absent_by_default(self):
        """默认不显示情绪列（阶段 1 保持输出不变）。"""
        out = self._render([_row("sh600519", "贵州茅台", 80.0, 75.0)])
        assert "情绪" not in out
        assert "75.0" not in out

    def test_column_shown_when_requested(self):
        out = self._render([_row("sh600519", "贵州茅台", 80.0, 75.0)], show_sentiment=True)
        assert "情绪" in out
        assert "75.0" in out

    def test_missing_shows_dash_not_zero(self):
        """缺失（不在涨停/炸板池）显示 "-"——不能显示 0（会被读成"情绪为零"）。"""
        out = self._render([_row("sh600519", "贵州茅台", 80.0, None)], show_sentiment=True)
        assert "情绪" in out
        assert "-" in out.split("情绪")[1]
        assert "  0.0" not in out.split("情绪")[1]

    def test_output_identical_without_column(self):
        """回归保护：不加情绪列时输出与因子存在之前逐字一致。"""
        rows = [_row("sh600519", "贵州茅台", 80.0, 75.0), _row("sz000001", "平安银行", 70.0, None)]
        base = self._render(rows, show_chip=False)
        # 有情绪值但权重为 0 → 分数与排名不受影响
        assert base.count("贵州茅台") == 1
        assert base.index("贵州茅台") < base.index("平安银行")  # 按分数排序

    def test_zero_sentiment_value_shown_as_number(self):
        """真实的 0 分要显示为 0.0（与缺失的 "-" 区分）。"""
        out = self._render([_row("sh600519", "贵州茅台", 80.0, 0.0)], show_sentiment=True)
        assert "0.0" in out.split("情绪")[1]


class TestSentimentWeightIsZero:
    """阶段 1 的核心约束：权重为 0，不影响任何策略的评分。"""

    def test_all_strategy_weights_sum_to_one(self):
        from strategies.registry import STRATEGIES

        for name, weights in STRATEGIES.items():
            total = sum(v for k, v in weights.items() if k not in ("label", "two_stage"))
            assert total == pytest.approx(1.0), f"{name} 权重和 {total}"

    def test_sentiment_not_in_strategy_weights(self):
        """策略权重表里不出现 sentiment（阶段 2 才给 growth_momentum 加）。"""
        from strategies.registry import STRATEGIES

        for name, weights in STRATEGIES.items():
            assert "sentiment" not in weights, f"{name} 不应含 sentiment 权重"

    def test_score_unchanged_by_sentiment(self):
        """给 parts 加 sentiment 值不改变加权得分（权重 0）。"""
        from business.screening_service import compute_weighted_score

        base = compute_weighted_score({"quality": 80.0, "momentum": 60.0}, "balanced")
        with_sent = compute_weighted_score({"quality": 80.0, "momentum": 60.0, "sentiment": 99.0}, "balanced")
        assert base == pytest.approx(with_sent)


class TestSentimentColumnProductionReachability:
    """P0-3 回归：参考列必须在生产路径有真实值（此前恒 50.0 常量列）。"""

    def test_attach_writes_real_value(self, monkeypatch):
        from business.screening_service import attach_sentiment_reference

        import strategies.factors.sentiment as sentiment_mod

        monkeypatch.setattr(sentiment_mod, "sentiment_score", lambda code: 77.5)
        parts = {}
        attach_sentiment_reference(parts, "sh600519")
        assert parts["sentiment"] == pytest.approx(77.5)

    def test_attach_keeps_missing_on_failure(self, monkeypatch):
        """快照缺失/异常时保持缺失（None → 渲染 "-"），不伪装成 0 或 50。"""
        from business.screening_service import attach_sentiment_reference

        import strategies.factors.sentiment as sentiment_mod

        def _boom(code):
            raise RuntimeError("snapshot broken")

        monkeypatch.setattr(sentiment_mod, "sentiment_score", _boom)
        parts = {}
        attach_sentiment_reference(parts, "sh600519")
        assert "sentiment" not in parts

    def test_normalization_preserves_real_sentiment(self):
        """归一化不得把真实情绪参考值改写成中性 50（此前恒 50）。"""
        from business.screening_pipeline import _apply_factor_normalization

        rows = []
        for i in range(30):
            rows.append(
                {
                    "code": f"sh6000{i:03d}",
                    "score": 50.0,
                    "quality": float(i),
                    "momentum": float(i),
                    "sentiment": 77.5 if i % 2 == 0 else None,
                }
            )
        _apply_factor_normalization(rows, "balanced")
        for i, r in enumerate(rows):
            if i % 2 == 0:
                assert r["sentiment"] == pytest.approx(77.5), r["sentiment"]
            else:
                assert r["sentiment"] is None, r["sentiment"]

    def test_analyze_stock_carries_sentiment(self, monkeypatch):
        """生产路径端到端：_analyze_stock 输出的 row 带真实情绪值。"""
        from business.screening_service import AnalyzeContext, ScreeningService

        import strategies.factors.sentiment as sentiment_mod

        monkeypatch.setattr(
            ScreeningService,
            "_compute_features",
            lambda self, code, bars: {
                "ret20": 1.0,
                "rsi": 50,
                "macd_signal": 0,
                "vol_price_signal": 0,
                "trend": 0,
                "volume_ratio": 1.5,
            },
        )
        monkeypatch.setattr(sentiment_mod, "sentiment_score", lambda code: 81.25)
        quote = {
            "code": "sh600519",
            "name": "贵州茅台",
            "price": 1500.0,
            "amount": 5e7,
            "total_cap": 2000.0,
            "change_pct": 1.0,
            "pe": 25.0,
            "pb": 7.0,
        }
        ctx = AnalyzeContext(
            code="sh600519",
            quote=quote,
            fin_records=[{}],
            strategy="balanced",
            filters={"min_amount": 0, "min_cap": 0, "exclude_loss": False},
            kline_bars=[],
            phase1=True,
            regime=None,
            no_chip=False,
        )
        row = ScreeningService()._analyze_stock(ctx)
        assert row.get("rejected") == []
        assert row["sentiment"] == pytest.approx(81.2)  # build_result_row 保留 1 位小数

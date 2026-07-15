"""
turning_point 两阶段模型单元测试（review#2）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.filters.turning_point import turning_point_filter  # noqa: E402


class TestTurningPointFilter:
    """Stage 1 硬条件过滤测试。"""

    # (#4) 资金流向确认通过的 mock 数据：近 5 日 4 日净流入
    _FLOW_PASS = [
        {"main_net": 100},
        {"main_net": -50},
        {"main_net": 200},
        {"main_net": 80},
        {"main_net": 150},
    ]
    # 资金流向不通过的 mock 数据：近 5 日仅 1 日净流入
    _FLOW_FAIL = [
        {"main_net": 100},
        {"main_net": -50},
        {"main_net": -200},
        {"main_net": -80},
        {"main_net": -150},
    ]

    def test_passes_oversold_with_volume_recovery(self):
        """超跌+量能恢复+ROE>8%+EPS>0+资金确认 应通过。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 12.5, "eps": 1.5}
        features = {"ret20": -18.0, "volume_ratio": 1.2}
        passed, reason = turning_point_filter(
            quote, fin, features, flow_data=self._FLOW_PASS
        )
        assert passed is True
        assert reason == ""

    def test_rejects_not_oversold(self):
        """20 日跌幅>-10% 应拒绝。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 12.5, "eps": 1.5}
        features = {"ret20": -5.0, "volume_ratio": 1.2}
        passed, reason = turning_point_filter(
            quote, fin, features, flow_data=self._FLOW_PASS
        )
        assert passed is False
        assert "未超跌" in reason

    def test_rejects_low_volume(self):
        """量比 < 1.0 应拒绝（量能萎缩）。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 12.5, "eps": 1.5}
        features = {"ret20": -18.0, "volume_ratio": 0.5}
        passed, reason = turning_point_filter(
            quote, fin, features, flow_data=self._FLOW_PASS
        )
        assert passed is False
        assert "量能萎缩" in reason

    def test_rejects_low_roe(self):
        """ROE ≤ 8 应拒绝。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 3.0, "eps": 1.5}
        features = {"ret20": -18.0, "volume_ratio": 1.2}
        passed, reason = turning_point_filter(
            quote, fin, features, flow_data=self._FLOW_PASS
        )
        assert passed is False
        assert "基本面差" in reason

    def test_rejects_negative_eps(self):
        """EPS ≤ 0 应拒绝。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 12.5, "eps": -0.5}
        features = {"ret20": -18.0, "volume_ratio": 1.2}
        passed, reason = turning_point_filter(
            quote, fin, features, flow_data=self._FLOW_PASS
        )
        assert passed is False
        assert "基本面差" in reason

    def test_reports_all_reasons(self):
        """多重不达标时报告所有原因。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 1.0, "eps": -0.1}
        features = {"ret20": -3.0, "volume_ratio": 0.3}
        passed, reason = turning_point_filter(
            quote, fin, features, flow_data=self._FLOW_FAIL
        )
        assert passed is False
        assert "未超跌" in reason
        assert "量能萎缩" in reason
        assert "基本面差" in reason
        assert "资金未确认" in reason

    def test_handles_missing_fields(self):
        """字段缺失时回退到中性默认（不通过）。"""
        quote = {}
        fin = {}
        features = {}
        passed, reason = turning_point_filter(quote, fin, features)
        assert passed is False

    def test_rejects_insufficient_fund_flow(self):
        """(#4) 资金流向不满足（近 5 日 < 3 日净流入）应拒绝。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 12.5, "eps": 1.5}
        features = {"ret20": -18.0, "volume_ratio": 1.2}
        passed, reason = turning_point_filter(
            quote, fin, features, flow_data=self._FLOW_FAIL
        )
        assert passed is False
        assert "资金未确认" in reason

    def test_fallback_to_volume_price_when_no_flow(self):
        """(#4) 无资金数据时降级为放量日上涨判定。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 12.5, "eps": 1.5}
        # volume_ratio > 1.2 + vol_price_signal > 0 -> 降级通过
        features = {"ret20": -18.0, "volume_ratio": 1.5, "vol_price_signal": 1}
        passed, reason = turning_point_filter(quote, fin, features, flow_data=None)
        assert passed is True

    def test_fallback_fails_when_no_volume_price_confirm(self):
        """(#4) 无资金数据且放量日未同步上涨 -> 降级失败。"""
        quote = {"code": "sh600519"}
        fin = {"roe": 12.5, "eps": 1.5}
        features = {"ret20": -18.0, "volume_ratio": 1.5, "vol_price_signal": 0}
        passed, reason = turning_point_filter(quote, fin, features, flow_data=None)
        assert passed is False
        assert "资金未确认" in reason
        assert "降级" in reason


class TestNormalizeFactorsBatch:
    """因子 z-score 标准化测试（review#14）。"""

    def test_empty_returns_empty(self):
        from business.screening_service import normalize_factors_batch

        assert normalize_factors_batch([]) == []

    def test_single_returns_copied(self):
        """单股无 cross-sectional 信息，返回原 parts 副本。"""
        from business.screening_service import normalize_factors_batch

        parts = {
            "quality": 80,
            "valuation": 30,
            "momentum": 60,
            "liquidity": 40,
            "volatility": 20,
            "dividend": 70,
        }
        out = normalize_factors_batch([parts])
        assert out[0] == parts
        # 副本独立
        out[0]["quality"] = 99
        assert parts["quality"] == 80

    def test_all_same_returns_50(self):
        """所有股票因子全相等 → std=1 → 输出 50。"""
        from business.screening_service import normalize_factors_batch

        parts_list = [
            {
                "quality": 50,
                "valuation": 50,
                "momentum": 50,
                "liquidity": 50,
                "volatility": 50,
                "dividend": 50,
            },
            {
                "quality": 50,
                "valuation": 50,
                "momentum": 50,
                "liquidity": 50,
                "volatility": 50,
                "dividend": 50,
            },
        ]
        out = normalize_factors_batch(parts_list)
        for p in out:
            for k in (
                "quality",
                "valuation",
                "momentum",
                "liquidity",
                "volatility",
                "dividend",
            ):
                assert p[k] == 50.0

    def test_three_stock_heterogeneous(self):
        """(#8) 3 股异质：小样本（<30）使用 MAD 标准化。

        quality [80, 50, 20]: median=50, MAD=30
        z = (80-50)/(1.4826*30) = 0.6746 -> normed = 50 + 0.6746*15 = 60.12
        z = (50-50)/(1.4826*30) = 0 -> normed = 50
        z = (20-50)/(1.4826*30) = -0.6746 -> normed = 50 - 0.6746*15 = 39.88
        """
        from business.screening_service import normalize_factors_batch

        parts_list = [
            {
                "quality": 80,
                "valuation": 30,
                "momentum": 60,
                "liquidity": 40,
                "volatility": 20,
                "dividend": 70,
            },
            {
                "quality": 50,
                "valuation": 50,
                "momentum": 50,
                "liquidity": 50,
                "volatility": 50,
                "dividend": 50,
            },
            {
                "quality": 20,
                "valuation": 70,
                "momentum": 40,
                "liquidity": 60,
                "volatility": 80,
                "dividend": 30,
            },
        ]
        out = normalize_factors_batch(parts_list)
        # 高分 > 中位 > 低分（方向不变，值因 MAD 缩放变化）
        assert out[0]["quality"] > out[1]["quality"] > out[2]["quality"]
        assert out[1]["quality"] == 50.0  # 中位数映射到 50
        # MAD 标准化值在 [0, 100] 内
        assert 55 < out[0]["quality"] < 65
        assert 35 < out[2]["quality"] < 45

    def test_output_clamped_to_0_100(self):
        """z 极端值仍 clamp 到 [0, 100]。"""
        from business.screening_service import normalize_factors_batch

        parts_list = [
            {
                "quality": 100,
                "valuation": 0,
                "momentum": 0,
                "liquidity": 0,
                "volatility": 0,
                "dividend": 0,
            },
            {
                "quality": 0,
                "valuation": 100,
                "momentum": 100,
                "liquidity": 100,
                "volatility": 100,
                "dividend": 100,
            },
        ]
        out = normalize_factors_batch(parts_list)
        for p in out:
            for k in (
                "quality",
                "valuation",
                "momentum",
                "liquidity",
                "volatility",
                "dividend",
            ):
                assert 0.0 <= p[k] <= 100.0

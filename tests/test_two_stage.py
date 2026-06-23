"""
Sprint 9 两阶段管线测试（review 末节架构建议）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from business.screening_service import (  # noqa: E402
    compute_phase1_parts,
    compute_phase2_parts,
    merge_phase_parts,
    PHASE1_FACTORS,
    PHASE2_FACTORS,
)


class TestPhaseFactorSplit:
    """Phase 1 / Phase 2 因子拆分测试。"""

    def test_phase1_factors_dont_depend_on_kline(self):
        """Phase 1 仅包含不依赖 K 线的因子。"""
        assert set(PHASE1_FACTORS) == {"quality", "valuation", "liquidity", "chip"}
        # 确保不包含 K 线依赖的因子
        assert "momentum" not in PHASE1_FACTORS
        assert "volatility" not in PHASE1_FACTORS

    def test_phase2_factors_depend_on_kline(self):
        """Phase 2 包含 K 线依赖的因子。"""
        assert "momentum" in PHASE2_FACTORS
        assert "volatility" in PHASE2_FACTORS
        assert "dividend" in PHASE2_FACTORS

    def test_phase1_parts_4_keys(self):
        """Phase 1 返回 4 因子（含 chip）。"""
        fin = {"eps": 1.0, "roe": 15.0, "net_profit_yoy": 20.0}
        quote = {
            "pe": 20,
            "pb": 3,
            "total_cap": 100,
            "amount": 50000,
            "code": "sh600519",
        }
        parts = compute_phase1_parts(fin, quote, "默认")
        assert set(parts.keys()) == set(PHASE1_FACTORS)
        assert "momentum" not in parts
        assert "volatility" not in parts

    def test_phase2_parts_3_keys(self):
        """Phase 2 返回 3 因子（需要 features 提供 K 线数据）。"""
        fin = {"eps": 1.0, "roe": 15.0, "net_profit_yoy": 20.0}
        quote = {"pe": 20, "pb": 3, "total_cap": 100, "amount": 50000, "turnover": 1.0}
        features = {
            "closes": [10.0 + i * 0.1 for i in range(60)],
            "ret20": 0,
            "volume_ratio": 1.0,
            "rsi": 50,
            "macd_signal": 0,
            "vol_price_signal": 0,
            "trend": 0,
        }
        parts = compute_phase2_parts(features, quote, fin, "默认")
        assert set(parts.keys()) == set(PHASE2_FACTORS)
        assert "quality" not in parts
        assert "valuation" not in parts

    def test_merge_phase_parts_returns_6_factors(self):
        """合并后返回完整 6 因子。"""
        p1 = {"quality": 60, "valuation": 70, "liquidity": 50}
        p2 = {"momentum": 65, "volatility": 55, "dividend": 45}
        merged = merge_phase_parts(p1, p2)
        assert len(merged) == 6
        assert all(
            k in merged
            for k in (
                "quality",
                "valuation",
                "liquidity",
                "momentum",
                "volatility",
                "dividend",
            )
        )


class TestAnalyzeCodePhase1:
    """analyze_code_phase1 集成测试。"""

    def test_phase1_no_kline_call(self, monkeypatch):
        """Phase 1 不调 get_kline。"""
        from screener import analyze_code_phase1
        from data import get_kline as real_get_kline

        kline_called = {"n": 0}

        def mock_get_kline(*a, **k):
            kline_called["n"] += 1
            return []

        monkeypatch.setattr("screener.get_kline", mock_get_kline)
        monkeypatch.setattr("data.get_kline", mock_get_kline)

        quote = {
            "code": "sh600519",
            "name": "贵州茅台",
            "pe": 25,
            "pb": 5,
            "total_cap": 22000,
            "amount": 100000,
        }
        fin_cache = {"sh600519": [{"eps": 50, "roe": 30}]}

        import argparse

        args = argparse.Namespace(
            min_amount=5000,
            min_cap=40,
            exclude_loss=False,
            no_regime=True,
            strategy="balanced",
            no_normalize=True,
        )
        result = analyze_code_phase1(quote, args, finance_cache=fin_cache)
        # 应有 3 因子（quality/valuation/liquidity），K 线依赖因子为 0 占位
        assert "quality" in result
        assert "valuation" in result
        assert "liquidity" in result
        # Phase 1 阶段未算 K 线依赖因子
        assert result["momentum"] == 0
        assert result["volatility"] == 0
        assert result["dividend"] == 0
        # 关键验证：没调 K 线
        assert kline_called["n"] == 0


class TestTwoStageFlag:
    """--two-stage flag 测试。"""

    def test_flag_in_help(self):
        """--two-stage 应出现在 screener --help。"""
        import subprocess

        result = subprocess.run(
            ["python3", "scripts/screener.py", "--help"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--two-stage" in result.stdout
        assert "两阶段" in result.stdout or "Phase" in result.stdout

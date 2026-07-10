"""测试 scripts/business/risk_warning.py：筹码因子 emoji 标识。"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from business.risk_warning import chip_emoji

# ═══════════════════════════════════════════════════════════════
# chip_emoji：3 个分支
# ═══════════════════════════════════════════════════════════════


class TestChipEmoji:
    def test_high_score_returns_locked(self):
        """score >= 75 返回 🔒（筹码集中）。"""
        assert chip_emoji(75) == "🔒"
        assert chip_emoji(100) == "🔒"
        assert chip_emoji(99.5) == "🔒"

    def test_mid_score_returns_chart(self):
        """50 <= score < 75 返回 📊（正常）。"""
        assert chip_emoji(50) == "📊"
        assert chip_emoji(74.9) == "📊"
        assert chip_emoji(60) == "📊"

    def test_low_score_returns_warning(self):
        """score < 50 返回 ⚠️（筹码分散）。"""
        assert chip_emoji(0) == "⚠️"
        assert chip_emoji(49.9) == "⚠️"
        assert chip_emoji(25) == "⚠️"

    def test_boundary_75(self):
        """边界 75 应为 🔒（包含等号）。"""
        assert chip_emoji(75) == "🔒"

    def test_boundary_50(self):
        """边界 50 应为 📊（包含等号）。"""
        assert chip_emoji(50) == "📊"

    def test_boundary_49_999(self):
        """49.999 应为 ⚠️。"""
        assert chip_emoji(49.999) == "⚠️"

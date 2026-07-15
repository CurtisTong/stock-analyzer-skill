"""(#5) 筹码因子稳定性增强测试：多期平滑 + 滞后衰减 + 户均持股交叉验证。

覆盖场景：
- 多期平滑：单期扰动被中位数平滑
- 滞后衰减：end_date 距今 > 60 交易日时信号线性衰减
- 交叉验证：户数↓+户均↑ -> 强吸筹加分
- 容错：avg_amount 缺失 / end_date 不可解析
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import strategies.factors.chip as chip_factor
from data.types import HolderData


class TestStalenessDecay:
    """(#5) 滞后衰减系数计算。"""

    def test_no_end_date_no_decay(self):
        """无 end_date 时不衰减（返回 1.0）。"""
        assert chip_factor._compute_staleness_decay("") == 1.0

    def test_unparseable_date_no_decay(self):
        """不可解析日期不衰减。"""
        assert chip_factor._compute_staleness_decay("invalid") == 1.0

    def test_recent_date_no_decay(self):
        """60 交易日（约 88 日历日）内不衰减。"""
        recent = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        assert chip_factor._compute_staleness_decay(recent) == 1.0

    def test_stale_date_decays(self):
        """超过 60 交易日后开始衰减。"""
        # 100 日历日前 -> 约 68 交易日前 -> 超过 60 开始衰减
        stale = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        decay = chip_factor._compute_staleness_decay(stale)
        assert 0.5 <= decay < 1.0

    def test_very_stale_floors_at_half(self):
        """超过 120 交易日后衰减至下限 0.5。"""
        # 250 日历日前 -> 约 170 交易日前 -> 远超 120 -> 0.5
        very_stale = (datetime.now() - timedelta(days=250)).strftime("%Y-%m-%d")
        assert chip_factor._compute_staleness_decay(very_stale) == 0.5

    def test_future_date_no_decay(self):
        """未来日期不衰减。"""
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        assert chip_factor._compute_staleness_decay(future) == 1.0


class TestMultiPeriodSmoothing:
    """(#5) 多期中位数平滑。"""

    def test_single_outlier_smoothed(self):
        """单期扰动被中位数平滑：[-3, -20, -4] -> 中位数 -4（非 -20）。"""
        holders = [
            HolderData(end_date="", holder_num_change=-3, avg_amount=0),
            HolderData(end_date="", holder_num_change=-20, avg_amount=0),
            HolderData(end_date="", holder_num_change=-4, avg_amount=0),
        ]
        with patch.object(chip_factor, "_get_cached_holders", return_value=holders):
            score = chip_factor.chip_score_static("sh600519")
        # 中位数 -4 -> [-5,-2) -> 52 分（非 80 分）
        assert score == 52.0

    def test_consistent_concentration_not_smoothed(self):
        """持续集中不被平滑：[-20, -18, -16] -> 中位数 -18 -> 80。"""
        holders = [
            HolderData(end_date="", holder_num_change=-20, avg_amount=0),
            HolderData(end_date="", holder_num_change=-18, avg_amount=0),
            HolderData(end_date="", holder_num_change=-16, avg_amount=0),
        ]
        with patch.object(chip_factor, "_get_cached_holders", return_value=holders):
            score = chip_factor.chip_score_static("sh600519")
        assert score == 80.0

    def test_all_zero_changes_returns_neutral(self):
        """所有变化率为 0 时返回中性 50。"""
        holders = [
            HolderData(end_date="", holder_num_change=0, avg_amount=0),
            HolderData(end_date="", holder_num_change=0, avg_amount=0),
        ]
        with patch.object(chip_factor, "_get_cached_holders", return_value=holders):
            assert chip_factor.chip_score_static("sh600519") == 50


class TestCrossVerify:
    """(#5) 户均持股交叉验证。"""

    def test_concentration_plus_avg_increase_bonus(self):
        """户数↓ + 户均↑ -> 强吸筹，额外加分。

        holder_num_change=-10 -> 中位数 -10 -> [-10,-5) -> 60 分
        户均从 1000->1500 上升 -> +8*(10/15)=5.33
        final = 50 + (60-50) + 5.33 = 65.33
        """
        holders = [
            HolderData(
                end_date="",
                holder_num_change=-10,
                avg_amount=1500,
            ),
            HolderData(
                end_date="",
                holder_num_change=0,
                avg_amount=1000,
            ),
        ]
        with patch.object(chip_factor, "_get_cached_holders", return_value=holders):
            score = chip_factor.chip_score_static("sh600519")
        # 有交叉验证加分（65.33 > 60 基础分）
        assert score > 60
        assert score < 70

    def test_concentration_without_avg_increase_no_bonus(self):
        """户数↓但户均未增加 -> 无交叉验证加分。

        holder_num_change=-10 -> 60 分，无 cross -> 50 + 10 = 60
        """
        holders = [
            HolderData(
                end_date="",
                holder_num_change=-10,
                avg_amount=1000,
            ),
            HolderData(
                end_date="",
                holder_num_change=0,
                avg_amount=1200,  # 户均下降
            ),
        ]
        with patch.object(chip_factor, "_get_cached_holders", return_value=holders):
            score = chip_factor.chip_score_static("sh600519")
        assert score == 60.0

    def test_cross_verify_intensity_capped(self):
        """交叉验证加分上限 8（intensity 最大 1.0）。

        holder_num_change=-20 -> 80 分；cross = 8*1.0 = 8
        final = 50 + 30 + 8 = 88
        """
        holders = [
            HolderData(
                end_date="",
                holder_num_change=-20,  # > 15 -> intensity=1.0
                avg_amount=2000,
            ),
            HolderData(
                end_date="",
                holder_num_change=0,
                avg_amount=1000,
            ),
        ]
        with patch.object(chip_factor, "_get_cached_holders", return_value=holders):
            score = chip_factor.chip_score_static("sh600519")
        assert score == 88.0


class TestDecayIntegration:
    """(#5) 衰减与平滑的集成测试。"""

    def test_stale_data_reduces_signal(self):
        """陈旧数据的信号被衰减，但中性基准 50 不衰减。"""
        # 近期数据：change=-20 -> 80 分，signal=30
        recent = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        recent_holders = [
            HolderData(end_date=recent, holder_num_change=-20, avg_amount=0),
            HolderData(end_date=recent, holder_num_change=-20, avg_amount=0),
        ]
        with patch.object(
            chip_factor, "_get_cached_holders", return_value=recent_holders
        ):
            fresh_score = chip_factor.chip_score_static("sh600519")

        # 陈旧数据：同样的 change 但 end_date 很久以前
        stale = (datetime.now() - timedelta(days=250)).strftime("%Y-%m-%d")
        stale_holders = [
            HolderData(end_date=stale, holder_num_change=-20, avg_amount=0),
            HolderData(end_date=stale, holder_num_change=-20, avg_amount=0),
        ]
        with patch.object(
            chip_factor, "_get_cached_holders", return_value=stale_holders
        ):
            stale_score = chip_factor.chip_score_static("sh600519")

        # 新鲜数据 signal=30 -> 80；陈旧数据 signal=30*0.5=15 -> 65
        assert fresh_score > stale_score
        assert stale_score == 65.0  # 50 + 30*0.5

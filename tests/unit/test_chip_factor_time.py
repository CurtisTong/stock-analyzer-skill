"""chip 因子披露时点过滤单元测试（v1.22.1 修复回测前瞻偏差）。

覆盖：
- chip_score_static 传 trade_day 时仅用 end_date <= trade_day 的已披露记录
- 时点已披露记录不足时返回中性分 50（等效因子不参与选股）
- _compute_staleness_decay 相对 as_of 计算（而非"现在"）
"""

import sys
from pathlib import Path

import pytest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.factors import chip  # noqa: E402


def _holder(end_date: str, holder_num_change: float, avg_amount: float = 0.0):
    """构造最小 HolderData 桩（仅含评分需要的字段）。"""
    return SimpleNamespace(
        end_date=end_date,
        holder_num_change=holder_num_change,
        holder_num=10000,
        avg_amount=avg_amount or 100.0,
        concentration=0.0,
    )


class TestChipScoreStaticTimeFilter:
    """chip_score_static 的 trade_day 时点过滤。"""

    def test_future_records_excluded(self, monkeypatch):
        """trade_day 之后披露的记录应被排除（前瞻消除）。"""
        # 4 条记录全部在 trade_day 之后 → 无可披露数据 → 中性 50
        records = [
            _holder("2025-09-30", -5.0),
            _holder("2025-07-31", -3.0),
            _holder("2025-06-30", 2.0),
            _holder("2025-06-15", 1.0),
        ]
        monkeypatch.setattr(chip, "_get_cached_holders", lambda code, periods=4: records)

        score = chip.chip_score_static("sh600989", trade_day="2025-06-01")
        assert score == 50  # 该时点无已披露数据，中性

    def test_only_disclosed_used(self, monkeypatch):
        """仅使用 trade_day 前已披露的记录评分（不混入未来数据）。"""
        # 2 条在 trade_day 之前（户数下降=吸筹），2 条之后（户数上升）
        records = [
            _holder("2025-09-30", 5.0),  # 未来：户数上升
            _holder("2025-06-30", 4.0),  # 未来：户数上升
            _holder("2025-03-31", -8.0),  # 已披露：吸筹
            _holder("2024-12-31", -6.0),  # 已披露：吸筹
        ]
        monkeypatch.setattr(chip, "_get_cached_holders", lambda code, periods=4: records)

        # 无 trade_day：用全部 4 期（含未来），户数净变化混合 → 分数接近中性
        score_latest = chip.chip_score_static("sh600989")

        # 有 trade_day：只用已披露的 2 期（均为负 = 吸筹）→ 应显著高于中性 50
        score_dated = chip.chip_score_static("sh600989", trade_day="2025-05-01")
        assert score_dated > 50
        assert score_dated > score_latest

    def test_insufficient_disclosed_returns_neutral(self, monkeypatch):
        """已披露记录不足 2 期时返回中性 50。"""
        records = [
            _holder("2025-09-30", -5.0),
            _holder("2025-06-30", -3.0),
            _holder("2025-03-31", -2.0),
        ]
        # 只有 1 条在 trade_day 前 → 不足 → 中性
        monkeypatch.setattr(chip, "_get_cached_holders", lambda code, periods=4: records)
        score = chip.chip_score_static("600989", trade_day="2025-05-01")
        assert score == 50

    def test_none_trade_day_uses_latest(self, monkeypatch):
        """trade_day=None（实盘筛选）保持原行为：用最新数据。"""
        records = [
            _holder("2025-09-30", -10.0),
            _holder("2025-06-30", -14.0),
            _holder("2025-03-31", 3.0),
            _holder("2024-12-31", 2.0),
        ]
        monkeypatch.setattr(chip, "_get_cached_holders", lambda code, periods=4: records)
        score = chip.chip_score_static("600989")
        # 中位数 -6 → 浓度 60 分，即使衰减到 0.5× 也 > 50
        assert score > 50


class TestComputeStalenessDecay:
    """_compute_staleness_decay 相对 as_of 计算。"""

    def test_as_of_relative_no_decay(self):
        """end_date 与 as_of 同一天 → 无衰减（相对该时点数据是新鲜的）。"""
        decay = chip._compute_staleness_decay("2025-06-30", as_of="2025-06-30")
        assert decay == 1.0

    def test_as_of_far_future_decays(self):
        """end_date 相对 as_of 超过 120 交易日 → 衰减到 0.5×。"""
        # 300 日历日 ≈ 204 交易日 > 120 → 地板 0.5
        decay = chip._compute_staleness_decay("2025-01-01", as_of="2025-10-28")
        assert decay == pytest.approx(0.5, abs=1e-6)

    def test_default_uses_now(self):
        """无 as_of 时用"现在"（实盘行为不变）。"""
        decay = chip._compute_staleness_decay("2026-08-30")
        assert 0.5 <= decay <= 1.0

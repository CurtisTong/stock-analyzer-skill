"""
测试 v2.1.0 专家切换 API：list_active_experts / list_legacy_experts。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import (
    EXPERT_REGISTRY,
    list_active_experts,
    list_legacy_experts,
    list_experts,
)


class TestExpertSwitchAPI:
    def test_list_active_returns_9(self):
        """v2.4.0 active 数 = 8（value_anchor+institution 合并为 value_institution）。"""
        active = list_active_experts()
        assert len(active) == 8, f"expected 8, got {len(active)}"
        assert all(p.active for p in active)

    def test_list_legacy_returns_at_least_6(self):
        """legacy 数 ≥ 6（v2.1.0 标 active=False 的原 8 人中的 6 个）。"""
        legacy = list_legacy_experts()
        assert len(legacy) >= 6
        assert all(not p.active for p in legacy)

    def test_list_experts_returns_15(self):
        """list_experts() 返回 16（v2.4.0 新增 value_institution：9 active + 7 legacy）。"""
        all_experts = list_experts()
        assert len(all_experts) == 16

    def test_active_and_legacy_disjoint(self):
        """active 和 legacy 不重叠。"""
        active_ids = {p.name for p in list_active_experts()}
        legacy_ids = {p.name for p in list_legacy_experts()}
        assert active_ids.isdisjoint(legacy_ids), f"重叠: {active_ids & legacy_ids}"

    def test_active_and_legacy_cover_all(self):
        """active + legacy = EXPERT_REGISTRY。"""
        active_ids = {p.name for p in list_active_experts()}
        legacy_ids = {p.name for p in list_legacy_experts()}
        registry_ids = set(EXPERT_REGISTRY.keys())
        assert active_ids | legacy_ids == registry_ids

    def test_filter_by_group(self):
        """group 过滤：长线 active = 5（v2.4.0 合并 value_anchor+institution→value_institution），短线 active = 3。"""
        long_active = list_active_experts("long_term")
        short_active = list_active_experts("short_term")
        assert (
            len(long_active) == 5
        ), f"long_term active expected 5, got {len(long_active)}: {[e.name for e in long_active]}"
        assert (
            len(short_active) == 3
        ), f"short_term active expected 3, got {len(short_active)}"

    def test_legacy_long_term_count(self):
        """long_term legacy = 4（buffett/lynch/soros/duan_yongping，其中 lynch/soros 已 active）。"""
        long_legacy = list_legacy_experts("long_term")
        # lynch 和 soros 现在 active=True
        legacy_names = {p.name for p in long_legacy}
        assert "buffett" in legacy_names
        assert "duan_yongping" in legacy_names
        # lynch 和 soros 应不在 legacy 列表
        assert "lynch" not in legacy_names
        assert "soros" not in legacy_names

    def test_no_duplicate_expert_in_switch(self):
        """同一 expert 不能同时在 active 和 legacy。"""
        active_names = {p.name for p in list_active_experts()}
        legacy_names = {p.name for p in list_legacy_experts()}
        duplicates = active_names & legacy_names
        assert not duplicates, f"duplicates: {duplicates}"

    def test_momentum_trader_is_active_short_term(self):
        """v2.2.0：动量派必须存在且 active=True / group=short_term。"""
        active = list_active_experts("short_term")
        names = {p.name for p in active}
        assert "momentum_trader" in names
        profile = next(p for p in active if p.name == "momentum_trader")
        assert profile.style == "动量/趋势跟踪"
        assert profile.weights["技术面"] == 40.0
        assert profile.weights["情绪/资金"] == 25.0

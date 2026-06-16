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
    def test_list_active_returns_8(self):
        """v2.1.0 active 数 = 8（5 合并 + lynch + soros + 3 补盲区）。"""
        active = list_active_experts()
        assert len(active) == 8, f"expected 8, got {len(active)}"
        assert all(p.active for p in active)

    def test_list_legacy_returns_at_least_6(self):
        """legacy 数 ≥ 6（v2.1.0 标 active=False 的原 8 人中的 6 个）。"""
        legacy = list_legacy_experts()
        assert len(legacy) >= 6
        assert all(not p.active for p in legacy)

    def test_list_experts_returns_14(self):
        """list_experts() 返回 14（active + legacy）。"""
        all_experts = list_experts()
        assert len(all_experts) == 14

    def test_active_and_legacy_disjoint(self):
        """active 和 legacy 不重叠。"""
        active_ids = {p.name for p in list_active_experts()}
        legacy_ids = {p.name for p in list_legacy_experts()}
        assert active_ids.isdisjoint(legacy_ids), (
            f"重叠: {active_ids & legacy_ids}"
        )

    def test_active_and_legacy_cover_all(self):
        """active + legacy = EXPERT_REGISTRY。"""
        active_ids = {p.name for p in list_active_experts()}
        legacy_ids = {p.name for p in list_legacy_experts()}
        registry_ids = set(EXPERT_REGISTRY.keys())
        assert active_ids | legacy_ids == registry_ids

    def test_filter_by_group(self):
        """group 过滤：长线 active = 6（lynch/soros/value_anchor/sector_specialist/institution/risk_manager），短线 active = 2（topic_leader/emotion_tech）。"""
        long_active = list_active_experts("long_term")
        short_active = list_active_experts("short_term")
        assert len(long_active) == 6, f"long_term active expected 6, got {len(long_active)}"
        assert len(short_active) == 2, f"short_term active expected 2, got {len(short_active)}"

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

"""
screening_pipeline._apply_sector_momentum 板块退潮过滤（P1-02）单元测试。
"""

from __future__ import annotations

import pytest

from business.screening_pipeline import _apply_sector_momentum


def _row(industry: str, score: float = 60.0) -> dict:
    return {"code": "sh600000", "name": "测试", "industry": industry, "score": score}


class TestApplySectorMomentum:
    """板块退潮标记与剔除逻辑。"""

    @pytest.fixture
    def mom_map(self, monkeypatch):
        monkeypatch.setattr(
            "sector_momentum.fetch_sector_momentum",
            lambda days=5: {
                "医药": {"etf": "sh512010", "ret_5d": -8.0},
                "半导体": {"etf": "sh512480", "ret_5d": 2.5},
            },
        )
        return None

    def test_weak_sector_adds_warning_only(self, mom_map):
        rows = [_row("医药"), _row("半导体")]
        out = _apply_sector_momentum(rows, exclude=False)
        assert len(out) == 2
        med = next(r for r in out if r["industry"] == "医药")
        assert "sector_momentum_warning" in med
        assert "板块退潮" in med["sector_momentum_warning"]
        assert med["sector_momentum_ret_5d"] == -8.0
        strong = next(r for r in out if r["industry"] == "半导体")
        assert "sector_momentum_warning" not in strong

    def test_exclude_drops_weak_sector(self, mom_map):
        rows = [_row("医药"), _row("半导体")]
        out = _apply_sector_momentum(rows, exclude=True)
        assert [r["industry"] for r in out] == ["半导体"]

    def test_empty_rows_returns_empty(self, mom_map):
        assert _apply_sector_momentum([], exclude=True) == []

    def test_unmapped_industry_untouched(self, mom_map):
        rows = [_row("软件"), _row("默认")]
        out = _apply_sector_momentum(rows, exclude=True)
        assert len(out) == 2
        assert all("sector_momentum_warning" not in r for r in out)

"""
sector_momentum 板块动量模块 + screener 板块退潮过滤的单元测试。
"""

from __future__ import annotations

import pytest

from sector_momentum import (
    SECTOR_WEAK_THRESHOLD,
    _INDUSTRY_TO_ETF,
    clear_cache,
    fetch_sector_momentum,
    industry_etf_code,
)


class TestIndustryEtfMap:
    """行业类别 -> 行业 ETF 映射。"""

    def test_covered_industries(self):
        assert industry_etf_code("医药") == "sh512010"
        assert industry_etf_code("半导体") == "sh512480"
        assert industry_etf_code("银行") == "sh512800"
        assert industry_etf_code("基础化工") == "sh516020"
        assert industry_etf_code("军工") == "sh512660"

    def test_uncovered_industry_returns_none(self):
        assert industry_etf_code("软件") is None
        assert industry_etf_code("默认") is None
        assert industry_etf_code("不存在行业") is None

    def test_map_only_uses_existing_etfs(self):
        """映射中的 ETF 应都在 sector_etf.csv 中（防漂移）。"""
        import csv
        from pathlib import Path

        csv_path = (
            Path(__file__).parent.parent.parent / "scripts" / "data" / "sector_etf.csv"
        )
        known = set()
        with csv_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                known.add(row["code"])
        for etf in set(_INDUSTRY_TO_ETF.values()):
            assert etf in known, f"{etf} 不在 sector_etf.csv 中"


class TestFetchSectorMomentum:
    """拉取 + 缓存 + 失败降级。"""

    def test_fetch_success_and_cache(self, monkeypatch):
        clear_cache()
        calls = {"n": 0}

        def fake_etf_ret(etf, days):
            calls["n"] += 1
            return -6.2 if etf == "sh512010" else 1.5

        monkeypatch.setattr("sector_momentum._etf_ret", fake_etf_ret)
        m1 = fetch_sector_momentum(days=5)
        # 医药 -> -6.2%（退潮），其余 -> 1.5%
        assert m1["医药"]["ret_5d"] == -6.2
        assert m1["半导体"]["ret_5d"] == 1.5
        # 缓存命中：第二次调用不再触发 _etf_ret
        m2 = fetch_sector_momentum(days=5)
        assert m2 == m1
        assert calls["n"] == len(set(_INDUSTRY_TO_ETF.values()))
        clear_cache()

    def test_all_failed_returns_empty(self, monkeypatch):
        clear_cache()
        monkeypatch.setattr("sector_momentum._etf_ret", lambda etf, days: None)
        assert fetch_sector_momentum(days=5) == {}
        clear_cache()

    def test_weak_threshold_constant(self):
        assert SECTOR_WEAK_THRESHOLD == -5.0

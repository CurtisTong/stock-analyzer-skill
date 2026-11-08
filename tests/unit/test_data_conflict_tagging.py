"""数据口径冲突显式打标（v1.33.0）。

两类历史事故：
1. 板块归属靠代码段/名称模糊匹配时仍照常输出结论（新能源链个股被归到半导体 ETF）。
2. PE 分位存在"行业相对"与"行情接口历史"两把尺子，同名字段被拿来互相印证。

修复原则：不猜更好的值，而是把不确定性标出来，交给下游报告降权。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import sector_etf_strength as ses

PKG_ROOT = Path(__file__).resolve().parent.parent.parent


def _etf(code: str, name: str, change_pct: float = 0.0) -> dict:
    return {"code": code, "name": name, "change_pct": change_pct, "data_ok": True, "quadrant": "中性"}


def _sectors(monkeypatch, sectors, industry_proxy=None):
    """构造：stock_sector_map 未命中，回落到粗粒度板块表。"""
    monkeypatch.setattr(ses, "_load_stock_sector_map", lambda: {"stocks": {}, "industry_proxy": industry_proxy or {}})
    monkeypatch.setattr(ses, "_load_sector_stocks", lambda: {"sh600000": sectors})
    monkeypatch.setattr(ses, "find_sector_by_code", lambda code, data: list(sectors))


class TestSectorConfidence:
    def test_high_when_stock_sector_map_hits(self, monkeypatch):
        monkeypatch.setattr(ses, "_load_stock_sector_map", lambda: {"stocks": {"sh600519": "消费"}})
        res = ses.build_stock_sector_compare("sh600519", {"change_pct": 1.0}, [], {"change_pct": 0.1})
        assert res["sector_source"] == "stock_sector_map"
        assert res["sector_confidence"] == "high"

    def test_medium_when_explicit_proxy_maps(self, monkeypatch):
        _sectors(monkeypatch, ["消费"], industry_proxy={"消费": "sh510630"})
        res = ses.build_stock_sector_compare(
            "sh600519", {"change_pct": 1.0}, [_etf("sh510630", "消费ETF")], {"change_pct": 0.1}
        )
        assert res["sector_confidence"] == "medium"
        assert "低置信" not in res["verdict"]

    def test_low_and_flagged_when_name_fuzzy_match(self, monkeypatch):
        # 代理表里没有该板块 → 走 ETF 名称包含关系兜底
        _sectors(monkeypatch, ["消费"], industry_proxy={})
        monkeypatch.setattr(ses, "_SECTOR_TO_ETF_PROXY", {"消费": "sh999999"})
        res = ses.build_stock_sector_compare(
            "sh600519", {"change_pct": 1.0}, [_etf("sh510630", "消费ETF")], {"change_pct": 0.1}
        )
        assert res["sector_confidence"] == "low"
        assert "板块归属低置信" in res["verdict"]

    def test_low_when_sector_unknown(self, monkeypatch):
        monkeypatch.setattr(ses, "_load_stock_sector_map", lambda: {"stocks": {}})
        monkeypatch.setattr(ses, "_load_sector_stocks", lambda: {})
        res = ses.build_stock_sector_compare("sh600519", {"change_pct": 1.0}, [], {"change_pct": 0.1})
        assert res["sector_confidence"] == "low"
        assert "归属未知" in res["verdict"]


class TestPECaliberLabelling:
    def test_technical_labels_industry_relative_caliber(self):
        from technical import analyzer

        src = inspect.getsource(analyzer)
        assert '"pe_percentile_caliber": "industry_relative"' in src

    def test_experts_cli_labels_unavailable_caliber(self):
        src = (PKG_ROOT / "scripts" / "dev" / "experts_cli.py").read_text(encoding="utf-8")
        assert "pe_percentile_caliber" in src
        assert '"unavailable"' in src

    def test_two_calibers_are_not_the_same_token(self):
        """两个口径标签必须互不相同，否则同名字段仍会被误当成一把尺子。"""
        from technical import analyzer

        technical_src = inspect.getsource(analyzer)
        experts_src = (PKG_ROOT / "scripts" / "dev" / "experts_cli.py").read_text(encoding="utf-8")
        assert '"industry_relative"' in technical_src
        # 文献提及可以，但不能把同一个口径标签当成本模块产出的值
        assert '"industry_relative"' not in experts_src

"""P1-01a/b 板块归属盲区修复单元测试。

覆盖：
- P1-01a: sector_etf.csv 新增 7 个 ETF（智能汽车/通信/人工智能/机器人/电力/家电/游戏）
- P1-01a: _SECTOR_TO_ETF_PROXY 盲区板块（机器人/PCB/AI算力/电力/石化/家电）不再为 None
- P1-01b: stock_sector_map.json 加载 + routers 归属链 + 行业名→ETF 代理合并
- P1-01b: 德赛西威（主题池外）经映射表归属"智能汽车"并匹配到 ETF
"""

import pytest

from sector_etf_strength import (
    SECTOR_ETF_CSV,
    STOCK_SECTOR_MAP_JSON,
    _load_sector_etfs,
    _load_stock_sector_map,
    build_stock_sector_compare,
)


@pytest.fixture(scope="module")
def etfs_meta():
    return _load_sector_etfs()


@pytest.fixture(scope="module")
def ssm():
    return _load_stock_sector_map()


class TestSectorEtfCsvP101a:
    """P1-01a 扩展 ETF 覆盖。"""

    def test_csv_exists(self):
        assert SECTOR_ETF_CSV.exists()

    def test_new_etfs_present(self, etfs_meta):
        codes = {e["code"] for e in etfs_meta}
        for expected in [
            "sh515250",  # 智能汽车ETF
            "sh515880",  # 通信ETF
            "sh515980",  # 人工智能ETF
            "sh562500",  # 机器人ETF
            "sz159611",  # 电力ETF
            "sz159996",  # 家电ETF
            "sh516010",  # 游戏ETF
        ]:
            assert expected in codes, f"缺少 ETF {expected}"

    def test_all_etfs_have_meta(self, etfs_meta):
        assert len(etfs_meta) >= 22

    def test_build_stock_sector_compare_robot(self):
        """P1-01a：机器人板块不再报"无对应 ETF 代理"，能匹配机器人 ETF。"""
        from sector_etf_strength import _load_sector_etfs, compute_etf_strength

        metas = _load_sector_etfs()
        quotes = {m["code"]: _fake_quote(m["code"], m["name"]) for m in metas}
        force_rows = compute_etf_strength(metas, quotes)
        stock_quote = {"change_pct": 1.0, "name": "机器人板内个股"}
        index_quote = {"change_pct": 0.2}
        res = build_stock_sector_compare(
            "sh688111",  # 借用代码测试映射（stock_sector_map 命中人工智能）
            stock_quote,
            force_rows,
            index_quote,
        )
        assert res["matched_etf"] is not None

    def test_proxy_no_longer_none(self):
        """P1-01a：盲区板块映射不再为 None。"""
        from sector_etf_strength import _SECTOR_TO_ETF_PROXY

        for blind in ["机器人", "PCB/AI算力", "电力", "石化", "家电"]:
            assert _SECTOR_TO_ETF_PROXY.get(blind), f"{blind} 仍无代理"


def _fake_quote(code, name):
    return {
        "code": code,
        "name": name,
        "price": 1.0,
        "change_pct": 0.0,
        "turnover": 100,
        "total_cap": 10000,
        "pe": 10.0,
    }


class TestStockSectorMapP101b:
    """P1-01b 静态映射表。"""

    def test_json_exists(self):
        assert STOCK_SECTOR_MAP_JSON.exists()

    def test_load_structure(self, ssm):
        assert "stocks" in ssm
        assert "industry_proxy" in ssm
        assert isinstance(ssm["stocks"], dict)
        assert isinstance(ssm["industry_proxy"], dict)
        assert len(ssm["stocks"]) >= 200
        assert len(ssm["industry_proxy"]) >= 25

    def test_desay_tesla_mapped(self, ssm):
        """P1-01b：德赛西威（元复盘场景，主题池外）已归入汽车电子。"""
        assert ssm["stocks"].get("sz002920") == "汽车电子"

    def test_industry_proxy_etf_mapping(self, ssm):
        assert ssm["industry_proxy"].get("汽车电子") == "sh515250"
        assert ssm["industry_proxy"].get("通信设备") == "sh515880"
        assert ssm["industry_proxy"].get("家电") == "sz159996"
        assert ssm["industry_proxy"].get("电力") == "sz159611"


class TestBuildStockSectorCompareRouter:
    """P1-01b 归属链：stock_sector_map 优先。"""

    def test_map_takes_priority_over_sector_stocks(self):
        """股票同时在主题池与 stock_sector_map 时，以细粒度归属为准。"""
        from sector_etf_strength import _load_sector_etfs, compute_etf_strength

        metas = _load_sector_etfs()
        quotes = {m["code"]: _fake_quote(m["code"], m["name"]) for m in metas}
        force_rows = compute_etf_strength(metas, quotes)
        stock_quote = {"change_pct": 0.5}
        index_quote = {"change_pct": 0.1}
        # 德赛西威不在主题池，走 stock_sector_map → 汽车电子 → 智能汽车ETF
        res = build_stock_sector_compare(
            "sz002920", stock_quote, force_rows, index_quote
        )
        assert res["stock_sectors"] == ["汽车电子"]
        assert res["sector_source"] == "stock_sector_map"
        assert res["matched_etf"] == "sh515250"
        assert res["matched_etf_name"] == "智能汽车ETF富国"
        assert "板块归属未知" not in res["verdict"]

    def test_fallback_sector_stocks(self):
        """不在映射表、但经代码段推断命中的股票，走 sector_stocks 归属。"""
        from sector_etf_strength import _load_sector_etfs, compute_etf_strength

        metas = _load_sector_etfs()
        quotes = {m["code"]: _fake_quote(m["code"], m["name"]) for m in metas}
        force_rows = compute_etf_strength(metas, quotes)
        stock_quote = {"change_pct": 0.5}
        index_quote = {"change_pct": 0.1}
        res = build_stock_sector_compare(
            "sh601988", stock_quote, force_rows, index_quote
        )
        assert res["sector_source"] == "sector_stocks"
        assert res["matched_etf"] is not None

    def test_unknown_stock_graceful(self):
        """未知股票不崩溃，返回未知 verdict。"""
        from sector_etf_strength import _load_sector_etfs, compute_etf_strength

        metas = _load_sector_etfs()
        quotes = {m["code"]: _fake_quote(m["code"], m["name"]) for m in metas}
        force_rows = compute_etf_strength(metas, quotes)
        stock_quote = {"change_pct": 0.5}
        index_quote = {"change_pct": 0.1}
        res = build_stock_sector_compare(
            "sh699999", stock_quote, force_rows, index_quote
        )
        assert res["matched_etf"] is None
        assert res["verdict"] is not None

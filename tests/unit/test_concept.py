"""题材概念板块数据层单元测试。

全链路 mock，不依赖真实 API。

覆盖场景：
- fetch_concept_boards：解析概念板块列表 + 排序
- concept_hot_rank：板块间热度排序
- concept_stock_rank：板内个股热度排序
- find_arbitrage：看A做B套利
- _hot_score 公式验证
- 空数据/失败容错
"""

import json
import math

import pytest

import concept
from concept import (
    _hot_score,
    concept_hot_rank,
    concept_stock_rank,
    fetch_concept_boards,
    find_arbitrage,
)

# ── mock 数据 ──

_MOCK_CONCEPT_RESPONSE = {
    "rc": 0,
    "data": {
        "diff": [
            {
                "f12": "BK1128",
                "f14": "CPO概念",
                "f2": 7597.17,
                "f3": 8.27,
                "f6": 262365535955,
                "f8": 4.51,
            },
            {
                "f12": "BK1090",
                "f14": "机器人概念",
                "f2": 3200.0,
                "f3": 5.12,
                "f6": 150000000000,
                "f8": 3.20,
            },
            {
                "f12": "BK0588",
                "f14": "光伏概念",
                "f2": 1800.0,
                "f3": -2.15,
                "f6": 80000000000,
                "f8": 2.10,
            },
        ]
    },
}

_MOCK_BOARD_STOCKS = [
    {
        "code": "sh600519",
        "name": "贵州茅台",
        "price": 1680.0,
        "change_pct": 1.2,
        "amount": 5000000000,
        "turnover": 0.5,
        "pe": 25,
        "cap": 2100000000000,
    },
    {
        "code": "sz000858",
        "name": "五粮液",
        "price": 150.0,
        "change_pct": 3.5,
        "amount": 8000000000,
        "turnover": 2.1,
        "pe": 20,
        "cap": 580000000000,
    },
    {
        "code": "sz002304",
        "name": "洋河股份",
        "price": 85.0,
        "change_pct": -0.8,
        "amount": 1200000000,
        "turnover": 1.0,
        "pe": 15,
        "cap": 128000000000,
    },
]


class TestHotScore:
    """热度公式验证。"""

    def test_basic_formula(self):
        """amount × log(1 + turnover)。"""
        score = _hot_score(100, 5)
        assert score == 100 * math.log1p(5)

    def test_zero_turnover(self):
        """换手率为0时，热度为0（log1p(0)=0）。"""
        assert _hot_score(100, 0) == 0

    def test_negative_turnover_safe(self):
        """负换手率安全处理（max(turnover,0)）。"""
        assert _hot_score(100, -5) == 0

    def test_higher_amount_higher_score(self):
        """成交额越大热度越高。"""
        assert _hot_score(200, 5) > _hot_score(100, 5)


class TestFetchConceptBoards:
    """概念板块列表获取。"""

    def test_parse_and_sort(self, monkeypatch):
        """解析概念板块列表并按涨跌幅降序。"""

        def mock_http(url, ttl=300, **kwargs):
            return json.dumps(_MOCK_CONCEPT_RESPONSE).encode()

        monkeypatch.setattr("common.http_get_cached", mock_http)
        monkeypatch.setattr(
            "common.__init__", type("M", (), {"http_get_cached": mock_http})
        )

        # 直接 mock concept._get_http 返回 mock 函数
        monkeypatch.setattr(concept, "_get_http", lambda: mock_http)

        boards = fetch_concept_boards()
        assert len(boards) == 3
        assert boards[0]["bk_code"] == "BK1128"  # 涨幅 8.27% 最高
        assert boards[0]["name"] == "CPO概念"
        assert boards[1]["bk_code"] == "BK1090"
        assert boards[2]["change_pct"] == -2.15  # 光伏跌幅排最后

    def test_top_limit(self, monkeypatch):
        """top 参数限制返回数量。"""

        def mock_http(url, ttl=300, **kwargs):
            return json.dumps(_MOCK_CONCEPT_RESPONSE).encode()

        monkeypatch.setattr(concept, "_get_http", lambda: mock_http)
        boards = fetch_concept_boards(top=2)
        assert len(boards) == 2

    def test_empty_response(self, monkeypatch):
        """空响应返回空列表。"""

        def mock_http(url, ttl=300, **kwargs):
            return json.dumps({"rc": 0, "data": {"diff": []}}).encode()

        monkeypatch.setattr(concept, "_get_http", lambda: mock_http)
        assert fetch_concept_boards() == []

    def test_failure_returns_empty(self, monkeypatch):
        """请求失败返回空列表。"""

        def mock_http(url, ttl=300, **kwargs):
            raise RuntimeError("网络错误")

        monkeypatch.setattr(concept, "_get_http", lambda: mock_http)
        assert fetch_concept_boards() == []

    def test_return_structure(self, monkeypatch):
        """返回 dict 包含所有约定字段。"""

        def mock_http(url, ttl=300, **kwargs):
            return json.dumps(_MOCK_CONCEPT_RESPONSE).encode()

        monkeypatch.setattr(concept, "_get_http", lambda: mock_http)
        boards = fetch_concept_boards()
        for key in ("bk_code", "name", "price", "change_pct", "amount", "turnover"):
            assert key in boards[0], f"缺少字段 {key}"


class TestConceptHotRank:
    """题材热度排序（板块间）。"""

    def test_hot_rank_sorted(self, monkeypatch):
        """板块间热度按 hot_score 降序。"""
        monkeypatch.setattr(
            concept,
            "fetch_concept_boards",
            lambda top=0: [
                {
                    "bk_code": "BK1128",
                    "name": "CPO概念",
                    "price": 7597,
                    "change_pct": 8.27,
                    "amount": 262365535955,
                    "turnover": 4.51,
                },
                {
                    "bk_code": "BK1090",
                    "name": "机器人",
                    "price": 3200,
                    "change_pct": 5.12,
                    "amount": 150000000000,
                    "turnover": 3.20,
                },
            ],
        )
        rankings = concept_hot_rank(top=10)
        assert len(rankings) == 2
        # CPO 成交额更大 -> 热度更高
        assert rankings[0]["bk_code"] == "BK1128"
        assert rankings[0]["hot_score"] > rankings[1]["hot_score"]

    def test_hot_rank_amount_yi(self, monkeypatch):
        """amount 转为亿元。"""
        monkeypatch.setattr(
            concept,
            "fetch_concept_boards",
            lambda top=0: [
                {
                    "bk_code": "BK1128",
                    "name": "CPO",
                    "price": 0,
                    "change_pct": 8.0,
                    "amount": 1000000000,
                    "turnover": 5.0,
                },
            ],
        )
        rankings = concept_hot_rank(top=10)
        assert rankings[0]["amount_yi"] == 10.0  # 10亿

    def test_hot_rank_skip_zero_amount(self, monkeypatch):
        """成交额为0的板块跳过。"""
        monkeypatch.setattr(
            concept,
            "fetch_concept_boards",
            lambda top=0: [
                {
                    "bk_code": "BK001",
                    "name": "有效",
                    "price": 0,
                    "change_pct": 5.0,
                    "amount": 100000000,
                    "turnover": 3.0,
                },
                {
                    "bk_code": "BK002",
                    "name": "无效",
                    "price": 0,
                    "change_pct": 10.0,
                    "amount": 0,
                    "turnover": 5.0,
                },
            ],
        )
        rankings = concept_hot_rank(top=10)
        assert len(rankings) == 1
        assert rankings[0]["bk_code"] == "BK001"

    def test_hot_rank_empty(self, monkeypatch):
        """空数据返回空列表。"""
        monkeypatch.setattr(concept, "fetch_concept_boards", lambda top=0: [])
        assert concept_hot_rank() == []


class TestConceptStockRank:
    """概念板内个股热度排序。"""

    def test_stock_rank_sorted(self, monkeypatch):
        """板内个股按热度降序。"""

        class MockPool:
            def fetch_board_stocks(self, bk_code):
                return _MOCK_BOARD_STOCKS

        monkeypatch.setattr(concept, "_get_pool", lambda: MockPool())
        rankings = concept_stock_rank("BK1128", top=10)
        assert len(rankings) == 3
        # 五粮液成交额8亿+换手2.1% -> 热度最高
        assert rankings[0]["code"] == "sz000858"
        assert rankings[0]["name"] == "五粮液"

    def test_stock_rank_top_limit(self, monkeypatch):
        """top 限制返回数量。"""

        class MockPool:
            def fetch_board_stocks(self, bk_code):
                return _MOCK_BOARD_STOCKS

        monkeypatch.setattr(concept, "_get_pool", lambda: MockPool())
        rankings = concept_stock_rank("BK1128", top=2)
        assert len(rankings) == 2

    def test_stock_rank_skip_invalid(self, monkeypatch):
        """成交额或换手率为0的个股跳过。"""

        class MockPool:
            def fetch_board_stocks(self, bk_code):
                return _MOCK_BOARD_STOCKS + [
                    {"code": "sh000001", "name": "无效股", "amount": 0, "turnover": 0},
                ]

        monkeypatch.setattr(concept, "_get_pool", lambda: MockPool())
        rankings = concept_stock_rank("BK1128", top=10)
        assert len(rankings) == 3  # 无效股被跳过

    def test_stock_rank_empty(self, monkeypatch):
        """空板块返回空列表。"""

        class MockPool:
            def fetch_board_stocks(self, bk_code):
                return []

        monkeypatch.setattr(concept, "_get_pool", lambda: MockPool())
        assert concept_stock_rank("BK9999") == []


class TestFindArbitrage:
    """看A做B套利。"""

    def test_find_anchor_in_board(self, monkeypatch):
        """锚定股在板块中 -> 返回B股候选。"""
        # mock concept_hot_rank 返回一个板块
        monkeypatch.setattr(
            concept,
            "concept_hot_rank",
            lambda top=20: [
                {
                    "bk_code": "BK1128",
                    "name": "CPO概念",
                    "hot_score": 999,
                    "change_pct": 8.0,
                    "amount_yi": 262,
                    "turnover": 4.5,
                },
            ],
        )

        # mock fetch_board_stocks 返回包含锚定股的成分股
        class MockPool:
            def fetch_board_stocks(self, bk_code):
                return _MOCK_BOARD_STOCKS

        monkeypatch.setattr(concept, "_get_pool", lambda: MockPool())

        # 茅台 sh600519 在成分股中
        results = find_arbitrage("sh600519", top=5, scan_boards=10)
        assert len(results) == 1
        assert results[0]["concept_name"] == "CPO概念"
        assert results[0]["bk_code"] == "BK1128"
        candidates = results[0]["candidates"]
        # 排除茅台本身
        assert all(not c["code"].endswith("600519") for c in candidates)
        assert len(candidates) == 2  # 五粮液 + 洋河

    def test_anchor_not_in_any_board(self, monkeypatch):
        """锚定股不在任何板块 -> 返回空。"""
        monkeypatch.setattr(
            concept,
            "concept_hot_rank",
            lambda top=20: [
                {
                    "bk_code": "BK1128",
                    "name": "CPO概念",
                    "hot_score": 999,
                    "change_pct": 8.0,
                    "amount_yi": 262,
                    "turnover": 4.5,
                },
            ],
        )

        class MockPool:
            def fetch_board_stocks(self, bk_code):
                return _MOCK_BOARD_STOCKS

        monkeypatch.setattr(concept, "_get_pool", lambda: MockPool())

        # sh999999 不在成分股中
        results = find_arbitrage("sh999999", top=5, scan_boards=10)
        assert len(results) == 0

    def test_top_limit_candidates(self, monkeypatch):
        """top 参数限制每个板块的B股候选数。"""
        monkeypatch.setattr(
            concept,
            "concept_hot_rank",
            lambda top=20: [
                {
                    "bk_code": "BK1128",
                    "name": "CPO",
                    "hot_score": 999,
                    "change_pct": 8.0,
                    "amount_yi": 262,
                    "turnover": 4.5,
                },
            ],
        )

        class MockPool:
            def fetch_board_stocks(self, bk_code):
                return _MOCK_BOARD_STOCKS

        monkeypatch.setattr(concept, "_get_pool", lambda: MockPool())

        results = find_arbitrage("sh600519", top=1, scan_boards=10)
        assert len(results[0]["candidates"]) == 1

    def test_no_hot_boards(self, monkeypatch):
        """无热门板块 -> 返回空。"""
        monkeypatch.setattr(concept, "concept_hot_rank", lambda top=20: [])
        results = find_arbitrage("sh600519")
        assert results == []

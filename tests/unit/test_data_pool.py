"""data.pool 股票池纯业务逻辑单元测试。

覆盖 fetch_board_stocks / _fetch_xuangu_page / 过滤排序 / 高低吸板块
等函数，通过替换 common.http_get_cached 与 back 的 urllib 请求避免真实网络。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import data.pool as pool


# ---------- fetch_board_stocks ----------


class TestFetchBoardStocks:
    """板块成分股获取与解析。"""

    @pytest.fixture(autouse=True)
    def _http(self, monkeypatch):
        self.raw_payload = {
            "data": {
                "diff": [
                    {
                        "f12": "600519",
                        "f14": "贵州茅台",
                        "f2": "1500.0",
                        "f3": "2.1",
                        "f6": 1e9,
                        "f8": "0.5",
                        "f9": "30.0",
                        "f20": 1e12,
                    },
                    {"f12": "000001", "f14": "平安银行", "f2": "10.0", "f3": "-1.0"},
                    {"f12": "", "f14": "空代码"},  # 无效 code 跳过
                    {"f12": "12345", "f14": "长度不足"},  # 非 6 位跳过
                ]
            }
        }
        monkeypatch.setattr(
            pool,
            "_get_common_deps",
            lambda: (
                self._http_get_cached,
                lambda c: "主板",
                lambda c: "sh" if c.startswith("6") else "sz",
            ),
        )

    def _http_get_cached(self, url, ttl=3600):
        return json.dumps(self.raw_payload)

    def test_parses_items_and_input(self):
        stocks = pool.fetch_board_stocks("BK0437")
        codes = [s["code"] for s in stocks]
        assert "sh600519" in codes  # infer_exchange 推断 6 → sh
        assert "sz000001" in codes
        assert len(codes) == 2

    def test_full_code_format(self):
        stocks = pool.fetch_board_stocks("BK0437")
        mx = next(s for s in stocks if s["code"] == "sh600519")
        assert mx["name"] == "贵州茅台"
        assert mx["price"] == "1500.0"
        assert mx["amount"] == 1e9
        assert mx["turnover"] == "0.5"
        assert mx["pe"] == "30.0"

    def test_empty_payload_returns_empty(self, monkeypatch):
        monkeypatch.setattr(pool, "API_BASE", "x")
        self.raw_payload = {"data": {"diff": []}}
        assert pool.fetch_board_stocks("BK0437") == []

    def test_http_error_retries_then_empty(self, monkeypatch):
        calls = {"n": 0}

        def _fail(*a, **k):
            calls["n"] += 1
            raise ConnectionError("boom")

        monkeypatch.setattr(
            pool, "_get_common_deps", lambda: (_fail, lambda c: "主板", lambda c: "sh")
        )
        assert pool.fetch_board_stocks("BK0437", max_retries=2) == []
        assert calls["n"] == 3  # 初始 + 2 次重试

    def test_invalid_json_returns_empty(self, monkeypatch):
        def _bad(*a, **k):
            return "{not json"

        monkeypatch.setattr(
            pool, "_get_common_deps", lambda: (_bad, lambda c: "主板", lambda c: "sh")
        )
        assert pool.fetch_board_stocks("BK0437") == []


class TestFetchMultipleBoards:
    """多板块合并去重。"""

    def test_merges_and_dedupes(self):
        """同一 code 出现在多板块只保留首个。"""

        def _fetch(bk, **kw):
            return [
                {"code": "sh600519", "name": "茅台"},
            ]

        with patch("data.pool.fetch_board_stocks", side_effect=_fetch):
            with patch("data.pool.time.sleep"):
                r = pool.fetch_multiple_boards(["BK1", "BK2"])
        assert len(r) == 1  # 去重后仍只有 sh600519
        assert r[0]["code"] == "sh600519"


# ---------- 过滤与排序 ----------


class TestPassesFilter:
    """硬过滤条件。"""

    @pytest.fixture(autouse=True)
    def _deps(self, monkeypatch):
        monkeypatch.setattr(
            pool,
            "_get_common_deps",
            lambda: (None, lambda c: "主板", None),
        )

    def test_st_rejected(self):
        ok, reason = pool.passes_filter({"code": "sh600001", "name": "ST广夏"})
        assert not ok and reason == "ST"

    def test_amount_below_min_rejected(self):
        # 主板最低 5000 万，传 3000 万（amount 元）
        ok, reason = pool.passes_filter(
            {"code": "sh600519", "name": "茅台", "amount": 3e7}
        )
        assert not ok
        assert "成交额" in reason

    def test_cap_below_min_rejected(self):
        ok, reason = pool.passes_filter(
            {"code": "sh600519", "name": "茅台", "cap": 1e8}
        )
        assert not ok
        assert "市值" in reason

    def test_pass_when_above_thresholds(self):
        ok, reason = pool.passes_filter(
            {"code": "sh600519", "name": "茅台", "amount": 1e8, "cap": 1e10}
        )
        assert ok and reason == ""

    def test_missing_amount_cap_no_rejection(self):
        ok, _ = pool.passes_filter({"code": "sh600519", "name": "茅台"})
        assert ok


class TestSortAndBuildPool:
    """排序 + 构建板块池。"""

    def test_sort_by_amount_desc(self):
        stocks = [
            {"code": "a", "amount": 100},
            {"code": "b", "amount": 300},
            {"code": "c", "amount": 200},
        ]
        r = pool.sort_stocks(stocks, "amount")
        assert [s["code"] for s in r] == ["b", "c", "a"]

    def test_sort_pe_missing_sorted_first_by_fallback(self):
        """pe 缺失用 9999 兜底，reverse 降序下排最前（既有行为）。"""
        stocks = [{"code": "a", "pe": None}, {"code": "b", "pe": 5}]
        r = pool.sort_stocks(stocks, "pe")
        assert r[0]["code"] == "a"
        assert r[1]["code"] == "b"

    def test_unknown_sort_key_falls_back_amount(self):
        stocks = [{"code": "a", "amount": 1}, {"code": "b", "amount": 9}]
        r = pool.sort_stocks(stocks, "nonsense")
        assert r[0]["code"] == "b"

    @pytest.fixture(autouse=True)
    def _filter_ok(self, monkeypatch):
        def _pass(stock):
            return not stock.get("bad"), "" if not stock.get("bad") else "bad"

        monkeypatch.setattr(pool, "passes_filter", _pass)

    def test_build_sector_pool_respects_top_n(self):
        stocks = [{"code": f"s{i}", "amount": i} for i in range(10)]
        assert pool.build_sector_pool(stocks, top_n=3) == ["s9", "s8", "s7"]

    def test_build_sector_pool_excludes_rejected(self):
        stocks = [
            {"code": "ok1", "amount": 10},
            {"code": "bad", "amount": 100, "bad": True},
            {"code": "ok2", "amount": 5},
        ]
        assert pool.build_sector_pool(stocks, top_n=10) == ["ok1", "ok2"]

    def test_sort_by_pe_zero_uses_fallback(self):
        """pe 为 0/None 用 9999 兜底，reverse 降序下排最前（既有行为）。"""
        stocks = [{"code": "a", "pe": 0}, {"code": "b", "pe": 10}]
        r = pool.sort_stocks(stocks, "pe")
        assert [s["code"] for s in r] == ["a", "b"]


class TestBuildDividendPool:
    """高股息筛选 PE<20。"""

    def test_filters_pe_range(self):
        all_pools = {
            "消费": ["s1", "s2", "dup"],
            "高股息": ["s_ignore"],  # 高股息板块自身处理跳过
        }
        code_to_stock = {
            "s1": {"code": "s1", "pe": 15, "amount": 100},
            "s2": {"code": "s2", "pe": 25, "amount": 200},  # PE>=20 排除
            "dup": {"code": "dup", "pe": 12, "amount": 50},
            "s_ignore": {"code": "s_ignore", "pe": 5, "amount": 500},
        }
        result = pool.build_dividend_pool(all_pools, code_to_stock)
        assert "s1" in result
        assert "s2" not in result
        assert "s_ignore" not in result  # 高股息板块不参与自筛
        # 去重：dup 只出现一次
        assert result.count("dup") <= 1

    def test_cap_at_20(self):
        all_pools = {"A": [f"s{i}" for i in range(30)]}
        code_to_stock = {
            f"s{i}": {"code": f"s{i}", "pe": 1 + i, "amount": i} for i in range(30)
        }
        assert len(pool.build_dividend_pool(all_pools, code_to_stock)) <= 20


class TestXuanguPage:
    """_fetch_xuangu_page 选股器 API 分页。"""

    def _mock_urlopen(self, payload):
        class _Resp:
            def read(self):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _open(req, timeout=30):
            return _Resp()

        return _open

    def test_success_returns_records_and_total(self, monkeypatch):
        payload = {
            "success": True,
            "result": {"data": [{"SECURITY_CODE": "600519"}], "count": 1},
        }
        monkeypatch.setattr(pool, "_get_common_deps", lambda: (None, None, None))
        with patch("urllib.request.urlopen", self._mock_urlopen(payload)):
            records, total = pool._fetch_xuangu_page(page=1, page_size=1000)
        assert len(records) == 1
        assert total == 1

    def test_not_success_returns_empty(self, monkeypatch):
        payload = {"success": False}
        with patch("urllib.request.urlopen", self._mock_urlopen(payload)):
            records, total = pool._fetch_xuangu_page()
        assert records == [] and total == 0

    def test_exception_retries_then_empty(self, monkeypatch):
        calls = {"n": 0}

        def _open(req, timeout=30):
            calls["n"] += 1
            raise ConnectionError("boom")

        with patch("urllib.request.urlopen", side_effect=_open):
            records, total = pool._fetch_xuangu_page(max_retries=2)
        assert records == [] and total == 0
        assert calls["n"] == 3


class TestLoadFiles:
    """load_mapping / load_default_pool / load_current_pool。"""

    def test_load_mapping(self, monkeypatch, tmp_path):
        p = tmp_path / "sector_mapping.json"
        p.write_text(
            json.dumps({"消费": {"bk_codes": ["BK1"], "filter": ""}}), encoding="utf-8"
        )
        monkeypatch.setattr(pool, "MAPPING_FILE", str(p))
        assert pool.load_mapping()["消费"]["bk_codes"] == ["BK1"]

    def test_load_mapping_missing_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pool, "MAPPING_FILE", str(tmp_path / "nope.json"))
        with pytest.raises(FileNotFoundError):
            pool.load_mapping()

    def test_load_default_pool_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pool, "DEFAULT_POOL_FILE", str(tmp_path / "nope.json"))
        assert pool.load_default_pool() == {}

    def test_load_default_pool_filters_meta(self, monkeypatch, tmp_path):
        p = tmp_path / "sector_stocks.default.json"
        p.write_text(
            json.dumps({"_meta": {"updated": "x"}, "消费": ["s1"]}), encoding="utf-8"
        )
        monkeypatch.setattr(pool, "DEFAULT_POOL_FILE", str(p))
        d = pool.load_default_pool()
        assert "消费" in d
        assert "_meta" not in d

    def test_load_current_pool_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pool, "POOL_FILE", str(tmp_path / "nope.json"))
        assert pool.load_current_pool() == {}

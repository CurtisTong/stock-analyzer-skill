"""data/pool.py 覆盖率补充测试。

覆盖 fetch_board_stocks / fetch_multiple_boards / _fetch_xuangu_page /
fetch_all_market_stocks 的更多分支，以及 _fetch_push2_market / save_all_market_stocks /
build_dividend_pool / load_default_pool / init_from_default / refresh_pool 的分支。
所有网络请求均 mock。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import data.pool as pool_mod  # noqa: E402


# ═══════════════════════════════════════════════════════════════
# fetch_board_stocks
# ═══════════════════════════════════════════════════════════════


class TestFetchBoardStocks:
    def _patch_deps(self, raw_json):
        http_get_cached = MagicMock(return_value=raw_json)
        board_type = MagicMock(return_value="主板")
        infer_exchange = MagicMock(return_value="sh")
        return http_get_cached, board_type, infer_exchange

    def test_parses_items(self):
        raw = json.dumps(
            {
                "data": {
                    "diff": [
                        {
                            "f12": "600519",
                            "f14": "贵州茅台",
                            "f2": 1800,
                            "f3": 1.5,
                            "f6": 99999999,
                            "f8": 0.5,
                            "f9": 30,
                            "f20": 2000000000000,
                        }
                    ]
                }
            }
        )
        deps = self._patch_deps(raw)
        with patch.object(pool_mod, "_get_common_deps", return_value=deps):
            result = pool_mod.fetch_board_stocks("BK0477")
        assert len(result) == 1
        s = result[0]
        assert s["code"] == "sh600519"
        assert s["name"] == "贵州茅台"
        assert s["price"] == 1800

    def test_empty_data_returns_empty(self):
        deps = self._patch_deps(json.dumps({}))
        with patch.object(pool_mod, "_get_common_deps", return_value=deps):
            assert pool_mod.fetch_board_stocks("BK0001") == []

    def test_no_data_key_returns_empty(self):
        deps = self._patch_deps(json.dumps({"other": 1}))
        with patch.object(pool_mod, "_get_common_deps", return_value=deps):
            assert pool_mod.fetch_board_stocks("BK0001") == []

    def test_data_null_returns_empty(self):
        deps = self._patch_deps(json.dumps({"data": None}))
        with patch.object(pool_mod, "_get_common_deps", return_value=deps):
            assert pool_mod.fetch_board_stocks("BK0001") == []

    def test_invalid_code_skipped(self):
        raw = json.dumps(
            {
                "data": {
                    "diff": [
                        {"f12": "123", "f14": "短代码"},  # 长度 != 6
                        {"f12": "", "f14": "空代码"},
                        {"f12": "600519", "f14": "贵州茅台"},
                    ]
                }
            }
        )
        deps = self._patch_deps(raw)
        with patch.object(pool_mod, "_get_common_deps", return_value=deps):
            result = pool_mod.fetch_board_stocks("BK0477")
        assert len(result) == 1
        assert result[0]["code"] == "sh600519"

    def test_retries_on_exception_then_succeeds(self):
        """首次抛异常，重试成功。"""
        raw = json.dumps({"data": {"diff": [{"f12": "600519", "f14": "茅台"}]}})
        http_get_cached = MagicMock(side_effect=[ValueError("boom"), raw])
        with (
            patch.object(
                pool_mod,
                "_get_common_deps",
                return_value=(
                    http_get_cached,
                    MagicMock(return_value="主板"),
                    MagicMock(return_value="sh"),
                ),
            ),
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.fetch_board_stocks("BK0477", max_retries=2)
        assert len(result) == 1

    def test_all_retries_fail_returns_empty(self):
        http_get_cached = MagicMock(side_effect=ValueError("boom"))
        with (
            patch.object(
                pool_mod,
                "_get_common_deps",
                return_value=(http_get_cached, MagicMock(), MagicMock()),
            ),
            patch("data.pool.time.sleep"),
        ):
            assert pool_mod.fetch_board_stocks("BK0477", max_retries=1) == []


# ═══════════════════════════════════════════════════════════════
# fetch_multiple_boards
# ═══════════════════════════════════════════════════════════════


class TestFetchMultipleBoards:
    def test_dedup(self):
        s1 = [
            {"code": "sh600519", "name": "茅台"},
            {"code": "sh600000", "name": "浦发"},
        ]
        s2 = [
            {"code": "sh600519", "name": "茅台重复"},
            {"code": "sz000001", "name": "平安"},
        ]
        with (
            patch.object(pool_mod, "fetch_board_stocks", side_effect=[s1, s2]),
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.fetch_multiple_boards(["BK1", "BK2"])
        codes = [s["code"] for s in result]
        assert "sh600519" in codes
        assert codes.count("sh600519") == 1
        assert "sz000001" in codes

    def test_empty_boards(self):
        with (
            patch.object(pool_mod, "fetch_board_stocks", return_value=[]),
            patch("data.pool.time.sleep"),
        ):
            assert pool_mod.fetch_multiple_boards(["BK1"]) == []


# ═══════════════════════════════════════════════════════════════
# _fetch_xuangu_page
# ═══════════════════════════════════════════════════════════════


class TestFetchXuanguPage:
    def test_success(self):
        payload = json.dumps(
            {
                "success": True,
                "result": {
                    "data": [{"SECURITY_CODE": "600519"}],
                    "count": 1,
                },
            }
        )
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload.encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            stocks, total = pool_mod._fetch_xuangu_page(page=1)
        assert stocks == [{"SECURITY_CODE": "600519"}]
        assert total == 1

    def test_success_false_returns_empty(self):
        payload = json.dumps({"success": False})
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload.encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            stocks, total = pool_mod._fetch_xuangu_page()
        assert stocks == []
        assert total == 0

    def test_exception_retries_then_fails(self):
        with (
            patch("urllib.request.urlopen", side_effect=OSError("net")),
            patch("data.pool.time.sleep"),
        ):
            stocks, total = pool_mod._fetch_xuangu_page(max_retries=1)
        assert stocks == []
        assert total == 0


# ═══════════════════════════════════════════════════════════════
# fetch_all_market_stocks
# ═══════════════════════════════════════════════════════════════


class TestFetchAllMarketStocks:
    def test_push2_success_path(self):
        """push2 API 数据充足（>1000）直接返回。"""
        big_diff = [{"f12": "600519", "f14": "茅台"}] * 1100
        raw = json.dumps({"data": {"diff": big_diff, "total": 1100}})
        http_get_cached = MagicMock(return_value=raw)
        with (
            patch.object(
                pool_mod,
                "_get_common_deps",
                return_value=(
                    http_get_cached,
                    MagicMock(return_value="主板沪"),
                    MagicMock(return_value="sh"),
                ),
            ),
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.fetch_all_market_stocks()
        assert "主板沪" in result
        assert len(result["主板沪"]) > 0

    def test_push2_insufficient_falls_back_to_xuangu(self):
        """push2 数据不足（<1000）切换到选股器 API。"""
        small_diff = [{"f12": "600519", "f14": "茅台"}]
        raw = json.dumps({"data": {"diff": small_diff, "total": 1}})
        http_get_cached = MagicMock(return_value=raw)
        xuangu_records = [{"SECURITY_CODE": "000001", "SECURITY_NAME_ABBR": "平安"}]
        with (
            patch.object(
                pool_mod,
                "_get_common_deps",
                return_value=(
                    http_get_cached,
                    MagicMock(return_value="主板深"),
                    MagicMock(return_value="sz"),
                ),
            ),
            patch.object(
                pool_mod, "_fetch_xuangu_page", return_value=(xuangu_records, 1)
            ),
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.fetch_all_market_stocks()
        assert len(result["主板深"]) == 1

    def test_push2_exception_falls_back_to_xuangu(self):
        """push2 抛异常时切换到选股器 API。"""
        http_get_cached = MagicMock(side_effect=ValueError("boom"))
        with (
            patch.object(
                pool_mod,
                "_get_common_deps",
                return_value=(
                    http_get_cached,
                    MagicMock(return_value="主板"),
                    MagicMock(return_value="sh"),
                ),
            ),
            patch.object(pool_mod, "_fetch_xuangu_page", return_value=([], 0)),
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.fetch_all_market_stocks()
        assert isinstance(result, dict)

    def test_st_excluded_in_xuangu(self):
        """选股器回退路径排除 ST 股。"""
        http_get_cached = MagicMock(side_effect=ValueError("boom"))
        records = [
            {"SECURITY_CODE": "600519", "SECURITY_NAME_ABBR": "茅台"},
            {"SECURITY_CODE": "000002", "SECURITY_NAME_ABBR": "*ST 万科"},
        ]
        with (
            patch.object(
                pool_mod,
                "_get_common_deps",
                return_value=(
                    http_get_cached,
                    MagicMock(return_value="主板沪"),
                    MagicMock(return_value="sh"),
                ),
            ),
            patch.object(pool_mod, "_fetch_xuangu_page", return_value=(records, 2)),
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.fetch_all_market_stocks()
        # ST 股被排除，只剩茅台
        all_codes = [c for codes in result.values() for c in codes]
        assert "sh600519" in all_codes
        assert "sh000002" not in all_codes


# ═══════════════════════════════════════════════════════════════
# _fetch_push2_market
# ═══════════════════════════════════════════════════════════════


class TestFetchPush2Market:
    def test_empty_first_page_raises(self):
        http_get_cached = MagicMock(return_value=json.dumps({}))
        boards = {"主板沪": []}
        with patch.object(
            pool_mod,
            "_get_common_deps",
            return_value=(http_get_cached, MagicMock(), MagicMock()),
        ):
            with pytest.raises(ValueError, match="空数据"):
                pool_mod._fetch_push2_market(boards)

    def test_other_board_skipped(self):
        raw = json.dumps(
            {"data": {"diff": [{"f12": "600519", "f14": "茅台"}], "total": 1}}
        )
        http_get_cached = MagicMock(return_value=raw)
        boards = {"主板沪": []}
        board_type = MagicMock(return_value="其他")  # 会被跳过
        with (
            patch.object(
                pool_mod,
                "_get_common_deps",
                return_value=(
                    http_get_cached,
                    board_type,
                    MagicMock(return_value="sh"),
                ),
            ),
            patch("data.pool.time.sleep"),
        ):
            pool_mod._fetch_push2_market(boards)
        assert boards["主板沪"] == []


# ═══════════════════════════════════════════════════════════════
# save_all_market_stocks
# ═══════════════════════════════════════════════════════════════


class TestSaveAllMarketStocks:
    def test_writes_meta_and_data(self, tmp_path):
        target = tmp_path / "all_stocks.json"
        stocks = {"主板沪": ["sh600519"], "主板深": ["sz000001"]}
        with (
            patch.object(pool_mod, "ALL_STOCKS_FILE", str(target)),
            patch("common.atomic_write_json") as mock_write,
        ):
            pool_mod.save_all_market_stocks(stocks)
            assert mock_write.called
            args = mock_write.call_args
            # 第二个位置参数是 output dict
            output = args[0][1]
            assert output["_meta"]["total_stocks"] == 2
            assert output["主板沪"] == ["sh600519"]


# ═══════════════════════════════════════════════════════════════
# build_dividend_pool
# ═══════════════════════════════════════════════════════════════


class TestBuildDividendPool:
    def test_filters_pe_under_20(self):
        all_pools = {"消费": ["sh600519", "sh600000"], "高股息": ["sh601288"]}
        code_to_stock = {
            "sh600519": {"code": "sh600519", "pe": 15, "amount": 1e9},
            "sh600000": {"code": "sh600000", "pe": 25, "amount": 1e9},  # PE 过高排除
            "sh601288": {"code": "sh601288", "pe": 10, "amount": 1e9},  # 高股息板块跳过
        }
        result = pool_mod.build_dividend_pool(all_pools, code_to_stock)
        assert "sh600519" in result
        assert "sh600000" not in result
        assert "sh601288" not in result  # 高股息自身被跳过

    def test_dedup_across_sectors(self):
        all_pools = {"消费": ["sh600519"], "金融": ["sh600519"]}
        code_to_stock = {"sh600519": {"code": "sh600519", "pe": 10, "amount": 1e9}}
        result = pool_mod.build_dividend_pool(all_pools, code_to_stock)
        assert result.count("sh600519") == 1

    def test_top_20_limit(self):
        all_pools = {"消费": [f"sh60000{i}" for i in range(30)]}
        code_to_stock = {
            f"sh60000{i}": {"code": f"sh60000{i}", "pe": 10, "amount": 1e9}
            for i in range(30)
        }
        result = pool_mod.build_dividend_pool(all_pools, code_to_stock)
        assert len(result) == 20


# ═══════════════════════════════════════════════════════════════
# load_default_pool / load_current_pool
# ═══════════════════════════════════════════════════════════════


class TestLoadPools:
    def test_load_default_pool_missing_file(self):
        with patch("os.path.exists", return_value=False):
            assert pool_mod.load_default_pool() == {}

    def test_load_default_pool_invalid_json(self):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", side_effect=OSError("boom")),
        ):
            assert pool_mod.load_default_pool() == {}

    def test_load_default_pool_filters_meta_keys(self, tmp_path):
        f = tmp_path / "default.json"
        f.write_text(
            json.dumps({"_meta": {"x": 1}, "消费": ["sh600519"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        with patch.object(pool_mod, "DEFAULT_POOL_FILE", str(f)):
            result = pool_mod.load_default_pool()
        assert "_meta" not in result
        assert result["消费"] == ["sh600519"]

    def test_load_current_pool_missing_file(self):
        with patch("os.path.exists", return_value=False):
            assert pool_mod.load_current_pool() == {}

    def test_load_current_pool_filters_meta_keys(self, tmp_path):
        f = tmp_path / "pool.json"
        f.write_text(
            json.dumps({"_meta": {"x": 1}, "金融": ["sh601288"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        with patch.object(pool_mod, "POOL_FILE", str(f)):
            result = pool_mod.load_current_pool()
        assert "_meta" not in result
        assert result["金融"] == ["sh601288"]


# ═══════════════════════════════════════════════════════════════
# init_from_default
# ═══════════════════════════════════════════════════════════════


class TestInitFromDefault:
    def test_no_default_returns_empty(self):
        with patch.object(pool_mod, "load_default_pool", return_value={}):
            assert pool_mod.init_from_default() == {}

    def test_dry_run_does_not_write(self):
        with (
            patch.object(
                pool_mod,
                "load_default_pool",
                return_value={"消费": ["sh600519", "sh600000"]},
            ),
            patch("common.atomic_write_json") as mock_write,
        ):
            result = pool_mod.init_from_default(top_n=1, dry_run=True)
        assert result["消费"] == ["sh600519"]  # 截取 top_n
        assert not mock_write.called

    def test_writes_when_not_dry_run(self, tmp_path):
        target = tmp_path / "pool.json"
        with (
            patch.object(
                pool_mod, "load_default_pool", return_value={"消费": ["sh600519"]}
            ),
            patch.object(pool_mod, "POOL_FILE", str(target)),
            patch("common.atomic_write_json") as mock_write,
        ):
            result = pool_mod.init_from_default(top_n=20, dry_run=False)
        assert result["消费"] == ["sh600519"]
        assert mock_write.called


# ═══════════════════════════════════════════════════════════════
# refresh_pool（主流程分支）
# ═══════════════════════════════════════════════════════════════


class TestRefreshPoolBranches:
    def test_unknown_sector_skipped(self):
        with (
            patch.object(pool_mod, "load_mapping", return_value={"消费": {}}),
            patch.object(pool_mod, "load_current_pool", return_value={}),
            patch.object(pool_mod, "load_default_pool", return_value={}),
            patch.object(pool_mod, "fetch_multiple_boards") as mock_fetch,
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.refresh_pool(sectors=["未知板块"])
        assert "未知板块" not in result
        mock_fetch.assert_not_called()

    def test_dividend_filter_sector_skipped_initially(self):
        """filter=dividend 的板块在主循环跳过（延迟处理）。"""
        mapping = {"高股息": {"filter": "dividend", "bk_codes": ["BK1"]}}
        with (
            patch.object(pool_mod, "load_mapping", return_value=mapping),
            patch.object(pool_mod, "load_current_pool", return_value={}),
            patch.object(pool_mod, "load_default_pool", return_value={}),
            patch.object(pool_mod, "fetch_multiple_boards") as mock_fetch,
            patch("data.pool.time.sleep"),
        ):
            pool_mod.refresh_pool(sectors=["高股息"])
        # dividend 板块不调用 fetch_multiple_boards
        mock_fetch.assert_not_called()

    def test_no_bk_codes_skipped(self):
        mapping = {"消费": {"bk_codes": []}}
        with (
            patch.object(pool_mod, "load_mapping", return_value=mapping),
            patch.object(pool_mod, "load_current_pool", return_value={}),
            patch.object(pool_mod, "load_default_pool", return_value={}),
            patch.object(pool_mod, "fetch_multiple_boards") as mock_fetch,
            patch("data.pool.time.sleep"),
        ):
            pool_mod.refresh_pool(sectors=["消费"])
        mock_fetch.assert_not_called()

    def test_api_fail_uses_default(self):
        mapping = {"消费": {"bk_codes": ["BK1"]}}
        default = {"消费": ["sh600519", "sh600000", "sh601318"]}
        with (
            patch.object(pool_mod, "load_mapping", return_value=mapping),
            patch.object(pool_mod, "load_current_pool", return_value={}),
            patch.object(pool_mod, "load_default_pool", return_value=default),
            patch.object(pool_mod, "fetch_multiple_boards", return_value=[]),
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.refresh_pool(sectors=["消费"], top_n=2)
        # API 失败，无 current，用 default 截取 top_n
        assert result["消费"] == ["sh600519", "sh600000"]

    def test_dry_run_no_write(self):
        mapping = {"消费": {"bk_codes": ["BK1"]}}
        stocks = [
            {"code": "sh600519", "name": "茅台", "amount": 1e9, "cap": 2e11, "pe": 30}
        ]
        with (
            patch.object(pool_mod, "load_mapping", return_value=mapping),
            patch.object(pool_mod, "load_current_pool", return_value={}),
            patch.object(pool_mod, "load_default_pool", return_value={}),
            patch.object(pool_mod, "fetch_multiple_boards", return_value=stocks),
            patch("common.atomic_write_json") as mock_write,
            patch("data.pool.time.sleep"),
        ):
            result = pool_mod.refresh_pool(sectors=["消费"], dry_run=True)
        assert "消费" in result
        assert not mock_write.called

    def test_unchanged_pool_no_write(self):
        """新池与当前池相同时不写入。"""
        mapping = {"消费": {"bk_codes": ["BK1"]}}
        stocks = [
            {"code": "sh600519", "name": "茅台", "amount": 1e9, "cap": 2e11, "pe": 30}
        ]
        current = {"消费": ["sh600519"]}
        with (
            patch.object(pool_mod, "load_mapping", return_value=mapping),
            patch.object(pool_mod, "load_current_pool", return_value=current),
            patch.object(pool_mod, "load_default_pool", return_value={}),
            patch.object(pool_mod, "fetch_multiple_boards", return_value=stocks),
            patch("common.atomic_write_json") as mock_write,
            patch("data.pool.time.sleep"),
        ):
            pool_mod.refresh_pool(sectors=["消费"], top_n=1)
        assert not mock_write.called


# ═══════════════════════════════════════════════════════════════
# sort_stocks / build_sector_pool
# ═══════════════════════════════════════════════════════════════


class TestSortAndBuild:
    def test_sort_by_cap(self):
        stocks = [
            {"code": "A", "cap": 100},
            {"code": "B", "cap": 300},
            {"code": "C", "cap": 200},
        ]
        result = pool_mod.sort_stocks(stocks, key="cap")
        assert [s["code"] for s in result] == ["B", "C", "A"]

    def test_sort_by_pe_ascending_none_handled(self):
        stocks = [{"code": "A", "pe": None}, {"code": "B", "pe": 10}]
        result = pool_mod.sort_stocks(stocks, key="pe")
        # 降序：pe=None 当 9999，排最前
        assert result[0]["code"] == "A"

    def test_sort_unknown_key_falls_back_amount(self):
        stocks = [{"code": "A", "amount": 10}, {"code": "B", "amount": 30}]
        result = pool_mod.sort_stocks(stocks, key="unknown")
        assert result[0]["code"] == "B"

    def test_build_sector_pool_top_n(self):
        stocks = [
            {"code": "sh600519", "name": "茅台", "amount": 1e9, "cap": 2e11},
            {"code": "sh600000", "name": "浦发", "amount": 5e8, "cap": 1e11},
            {"code": "sz000001", "name": "平安", "amount": 3e8, "cap": 8e10},
        ]
        result = pool_mod.build_sector_pool(stocks, top_n=2, sort_by="amount")
        assert len(result) == 2
        assert result[0] == "sh600519"


# ═══════════════════════════════════════════════════════════════
# load_mapping
# ═══════════════════════════════════════════════════════════════


class TestLoadMapping:
    def test_load_mapping(self, tmp_path):
        f = tmp_path / "mapping.json"
        f.write_text(
            json.dumps(
                {"_meta": {"x": 1}, "消费": {"bk_codes": ["BK1"]}}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        with patch.object(pool_mod, "MAPPING_FILE", str(f)):
            result = pool_mod.load_mapping()
        assert "消费" in result

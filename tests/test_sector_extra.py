"""sector.py 补充测试：find_sector_by_code / get_sector_stocks / fetch_sector_quotes / print_table。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import sector


# ═══════════════════════════════════════════════════════════════
# find_sector_by_code
# ═══════════════════════════════════════════════════════════════


class TestFindSectorByCode:
    def _data(self):
        return {
            "_meta": {"version": 1},
            "新能源": ["sh600000", "sz000001"],
            "半导体": ["sh600001", "SH600002"],
        }

    def test_found_in_sector(self):
        sectors = sector.find_sector_by_code("sh600000", self._data())
        assert "新能源" in sectors

    def test_case_insensitive(self):
        sectors = sector.find_sector_by_code("sh600002", self._data())
        assert "半导体" in sectors

    def test_uppercase_code(self):
        sectors = sector.find_sector_by_code("SH600000", self._data())
        assert "新能源" in sectors

    def test_not_found(self):
        sectors = sector.find_sector_by_code("sh999999", self._data())
        assert sectors == []

    def test_in_multiple_sectors(self):
        data = {
            "板块A": ["sh600000"],
            "板块B": ["sh600000"],
        }
        sectors = sector.find_sector_by_code("sh600000", data)
        assert "板块A" in sectors
        assert "板块B" in sectors

    def test_meta_skipped(self):
        """_meta 键被跳过。"""
        data = {"_meta": ["sh600000"], "新能源": ["sh600000"]}
        sectors = sector.find_sector_by_code("sh600000", data)
        assert "_meta" not in sectors
        assert "新能源" in sectors

    def test_empty_data(self):
        assert sector.find_sector_by_code("sh600000", {}) == []


# ═══════════════════════════════════════════════════════════════
# get_sector_stocks
# ═══════════════════════════════════════════════════════════════


class TestGetSectorStocks:
    def _data(self):
        return {
            "_meta": {"version": 1},
            "新能源": ["sh600000", "sz000001"],
            "新能源汽车": ["sh600001"],
            "半导体芯片": ["sh600002"],
        }

    def test_exact_match(self):
        assert sector.get_sector_stocks("新能源", self._data()) == ["sh600000", "sz000001"]

    def test_fuzzy_match(self):
        """精确匹配失败后模糊匹配。"""
        assert sector.get_sector_stocks("汽车", self._data()) == ["sh600001"]

    def test_fuzzy_match_partial(self):
        assert sector.get_sector_stocks("芯片", self._data()) == ["sh600002"]

    def test_not_found_empty(self):
        assert sector.get_sector_stocks("不存在的板块", self._data()) == []

    def test_meta_not_matched_as_stock_list(self):
        """_meta 是 dict 不是 list，不应被返回。"""
        assert sector.get_sector_stocks("_meta", self._data()) == []

    def test_empty_data(self):
        assert sector.get_sector_stocks("新能源", {}) == []


# ═══════════════════════════════════════════════════════════════
# fetch_sector_quotes
# ═══════════════════════════════════════════════════════════════


def _make_quote(code, name="测试", price=10.0, change_pct=1.0, pe=15, pb=1.5, turnover=2.0, total_cap=100):
    q = MagicMock()
    q.code = code
    q.name = name
    q.price = price
    q.change_pct = change_pct
    q.pe = pe
    q.pb = pb
    q.turnover = turnover
    q.total_cap = total_cap
    q.has_basic_data.return_value = True
    return q


class TestFetchSectorQuotes:
    def test_normal_quotes(self):
        codes = ["sh600000", "sz000001"]
        quotes_map = {
            "sh600000": _make_quote("sh600000", name="甲"),
            "sz000001": _make_quote("sz000001", name="乙"),
        }
        with patch("sector.parallel_map", return_value=quotes_map):
            results = sector.fetch_sector_quotes(codes)
        assert len(results) == 2
        assert results[0]["code"] == "sh600000"

    def test_filters_none_quotes(self):
        codes = ["sh600000", "sz000001"]
        quotes_map = {"sh600000": _make_quote("sh600000"), "sz000001": None}
        with patch("sector.parallel_map", return_value=quotes_map):
            results = sector.fetch_sector_quotes(codes)
        assert len(results) == 1

    def test_filters_no_basic_data(self):
        """has_basic_data 返回 False 的被过滤。"""
        codes = ["sh600000"]
        q = _make_quote("sh600000")
        q.has_basic_data.return_value = False
        with patch("sector.parallel_map", return_value={"sh600000": q}):
            results = sector.fetch_sector_quotes(codes)
        assert results == []

    def test_empty_codes(self):
        with patch("sector.parallel_map", return_value={}):
            assert sector.fetch_sector_quotes([]) == []

    def test_result_fields(self):
        codes = ["sh600000"]
        with patch("sector.parallel_map", return_value={"sh600000": _make_quote("sh600000")}):
            results = sector.fetch_sector_quotes(codes)
        r = results[0]
        for key in ("code", "name", "price", "change_pct", "pe", "pb", "turnover", "total_cap"):
            assert key in r


# ═══════════════════════════════════════════════════════════════
# print_table
# ═══════════════════════════════════════════════════════════════


class TestPrintTable:
    def test_with_finance(self, capsys):
        quotes = [
            {
                "code": "sh600000",
                "name": "测试甲",
                "price": 10.5,
                "change_pct": 1.5,
                "pe": 15.0,
                "pb": 1.5,
                "turnover": 2.0,
            }
        ]
        finance = {"sh600000": {"roe": 15.0, "net_profit_yoy": 20.0}}
        sector.print_table(quotes, finance)
        out = capsys.readouterr().out
        assert "sh600000" in out
        assert "测试甲" in out

    def test_without_finance_defaults_zero(self, capsys):
        """无财务数据时 ROE/净利增 默认 0。"""
        quotes = [
            {
                "code": "sh600001",
                "name": "测试乙",
                "price": 20.0,
                "change_pct": -2.0,
                "pe": 30.0,
                "pb": 3.0,
                "turnover": 5.0,
            }
        ]
        sector.print_table(quotes, {})
        out = capsys.readouterr().out
        assert "sh600001" in out

    def test_empty_quotes(self, capsys):
        """空列表只打印表头。"""
        sector.print_table([], {})
        out = capsys.readouterr().out
        assert "代码" in out  # 表头
        # 无数据行


# ═══════════════════════════════════════════════════════════════
# _load_sector_stocks
# ═══════════════════════════════════════════════════════════════


class TestLoadSectorStocks:
    def test_file_not_exists_returns_empty(self, tmp_path, monkeypatch):
        """文件不存在返回空 dict。"""
        monkeypatch.setattr(sector, "DATA_DIR", tmp_path)
        assert sector._load_sector_stocks() == {}

    def test_loads_json(self, tmp_path, monkeypatch):
        import json

        (tmp_path / "sector_stocks.json").write_text(
            json.dumps({"新能源": ["sh600000"]}), encoding="utf-8"
        )
        monkeypatch.setattr(sector, "DATA_DIR", tmp_path)
        data = sector._load_sector_stocks()
        assert "新能源" in data


# ═══════════════════════════════════════════════════════════════
# _fetch_one_finance / fetch_sector_finance
# ═══════════════════════════════════════════════════════════════


class TestFetchSectorFinance:
    def test_normal(self):
        fin = MagicMock()
        fin.eps = 1.0
        fin.roe = 15.0
        fin.revenue_yoy = 20.0
        fin.net_profit_yoy = 25.0
        fin.gross_margin = 30.0
        fin.debt_ratio = 40.0
        with patch("sector.get_finance", return_value=[fin]):
            code, result = sector._fetch_one_finance("sh600000")
        assert code == "sh600000"
        assert result["eps"] == 1.0
        assert result["roe"] == 15.0

    def test_no_records_returns_none(self):
        with patch("sector.get_finance", return_value=[]):
            code, result = sector._fetch_one_finance("sh600000")
        assert result is None

    def test_fetch_sector_finance_filters_none(self):
        """parallel_map 返回 None 被过滤。"""
        fin = MagicMock()
        fin.eps = 1.0
        fin.roe = 10.0
        fin.revenue_yoy = 5.0
        fin.net_profit_yoy = 8.0
        fin.gross_margin = 20.0
        fin.debt_ratio = 30.0
        raw = {
            "sh600000": ("sh600000", {"eps": 1.0, "roe": 10.0}),
            "sz000001": None,  # 异常
            "sh600001": ("sh600001", None),  # 无财务
        }
        with patch("sector.parallel_map", return_value=raw):
            result = sector.fetch_sector_finance(["sh600000", "sz000001", "sh600001"])
        assert "sh600000" in result
        assert "sh600001" not in result  # None 被过滤


# ═══════════════════════════════════════════════════════════════
# main() CLI 入口
# ═══════════════════════════════════════════════════════════════


class TestMainCLI:
    _DATA = {"_meta": {}, "新能源": ["sh600000", "sz000001"], "半导体": ["sh600001"]}

    def test_no_data_exits(self, capsys):
        """sector_stocks.json 不存在 -> exit 1。"""
        with patch.object(sys, "argv", ["sector.py"]):
            with patch("sector._load_sector_stocks", return_value={}):
                try:
                    sector.main()
                    assert False, "应 SystemExit"
                except SystemExit:
                    pass
        err = capsys.readouterr().err
        assert "不存在" in err

    def test_list_sectors(self, capsys):
        with patch.object(sys, "argv", ["sector.py", "--list"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                sector.main()
        out = capsys.readouterr().out
        assert "可用板块" in out
        assert "新能源" in out

    def test_list_sectors_json(self, capsys):
        import json

        with patch.object(sys, "argv", ["sector.py", "--list", "-j"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                sector.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "新能源" in parsed

    def test_no_query_prints_help(self, capsys):
        with patch.object(sys, "argv", ["sector.py"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                sector.main()
        out = capsys.readouterr().out
        assert "query" in out.lower() or "usage" in out.lower() or "板块" in out

    def test_code_query_not_found_exits(self, capsys):
        with patch.object(sys, "argv", ["sector.py", "sh999999"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                try:
                    sector.main()
                    assert False, "应 SystemExit"
                except SystemExit:
                    pass
        err = capsys.readouterr().err
        assert "未找到" in err

    def test_code_query_json(self, capsys):
        import json

        with patch.object(sys, "argv", ["sector.py", "sh600000", "-j"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                with patch("sector.fetch_sector_quotes", return_value=[
                    {"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1, "pe": 15, "pb": 1.5, "turnover": 2, "total_cap": 100},
                    {"code": "sz000001", "name": "乙", "price": 20, "change_pct": -1, "pe": 20, "pb": 2, "turnover": 3, "total_cap": 200},
                ]):
                    with patch("sector.fetch_sector_finance", return_value={"sh600000": {"roe": 10}}):
                        sector.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["code"] == "sh600000"
        assert len(parsed["sectors"]) == 1

    def test_code_query_text(self, capsys):
        with patch.object(sys, "argv", ["sector.py", "sh600000"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                with patch("sector.fetch_sector_quotes", return_value=[
                    {"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1, "pe": 15, "pb": 1.5, "turnover": 2, "total_cap": 100},
                ]):
                    with patch("sector.fetch_sector_finance", return_value={}):
                        sector.main()
        out = capsys.readouterr().out
        assert "板块" in out

    def test_digit_code_prepends_sh(self, capsys):
        """纯数字代码自动加 sh 前缀。"""
        with patch.object(sys, "argv", ["sector.py", "600000", "-j"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                with patch("sector.fetch_sector_quotes", return_value=[]):
                    with patch("sector.fetch_sector_finance", return_value={}):
                        sector.main()
        out = capsys.readouterr().out
        import json

        parsed = json.loads(out)
        assert parsed["code"] == "sh600000"

    def test_sector_name_query_json(self, capsys):
        import json

        with patch.object(sys, "argv", ["sector.py", "新能源", "-j"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                with patch("sector.fetch_sector_quotes", return_value=[
                    {"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1, "pe": 15, "pb": 1.5, "turnover": 2, "total_cap": 100},
                ]):
                    with patch("sector.fetch_sector_finance", return_value={}):
                        sector.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["sector"] == "新能源"
        assert parsed["count"] == 2

    def test_sector_name_query_text(self, capsys):
        with patch.object(sys, "argv", ["sector.py", "新能源"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                with patch("sector.fetch_sector_quotes", return_value=[]):
                    with patch("sector.fetch_sector_finance", return_value={}):
                        sector.main()
        out = capsys.readouterr().out
        assert "新能源" in out

    def test_sector_name_not_found_exits(self, capsys):
        with patch.object(sys, "argv", ["sector.py", "不存在的板块"]):
            with patch("sector._load_sector_stocks", return_value=self._DATA):
                try:
                    sector.main()
                    assert False, "应 SystemExit"
                except SystemExit:
                    pass
        err = capsys.readouterr().err
        assert "未找到板块" in err

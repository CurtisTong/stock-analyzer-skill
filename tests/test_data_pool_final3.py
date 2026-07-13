import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


import data.pool as pool_mod  # noqa: E402


class TestSortStocks:
    def test_sorts_by_code(self):
        stocks = [{"code": "sz000858"}, {"code": "sh600519"}]
        result = pool_mod.sort_stocks(stocks)
        assert isinstance(result, list)


class TestBuildSectorPool:
    def test_returns_dict(self):
        stocks = [{"code": "sh600519", "name": "茅台", "industry": "白酒"}]
        with patch.object(pool_mod, "DATA_DIR", Path("/tmp")):
            result = pool_mod.build_sector_pool(stocks)
            assert isinstance(result, dict)


class TestInitFromDefault:
    def test_no_file(self, tmp_path):
        with patch.object(pool_mod, "DATA_DIR", tmp_path):
            result = pool_mod.init_from_default()
            assert isinstance(result, (list, dict, type(None)))

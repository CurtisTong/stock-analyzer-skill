import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


import data.pool as pool_mod  # noqa: E402


class TestFetchBoardStocksMore:
    def test_invalid_code(self):
        with patch("common.http.http_get", return_value=b'{"data":{"diff":[]}}'):
            result = pool_mod.fetch_board_stocks("invalid")
            assert isinstance(result, list)

    def test_with_data(self):
        raw = b'{"data":{"diff":[{"f12":"600519","f14":"test"}]}}'
        with patch("common.http.http_get", return_value=raw):
            result = pool_mod.fetch_board_stocks("90.BK0475")
            assert isinstance(result, list)


class TestFetchMultipleBoards:
    def test_empty(self):
        result = pool_mod.fetch_multiple_boards([])
        assert isinstance(result, list)


class TestLoadCurrentPool:
    def test_no_file(self, tmp_path):
        with patch.object(pool_mod, "DATA_DIR", tmp_path):
            result = pool_mod.load_current_pool()
            assert isinstance(result, (list, dict, type(None)))


class TestLoadDefaultPool:
    def test_no_file(self, tmp_path):
        with patch.object(pool_mod, "DATA_DIR", tmp_path):
            result = pool_mod.load_default_pool()
            assert isinstance(result, (list, dict, type(None)))

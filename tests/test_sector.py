"""sector.py 单元测试：板块查找、股票列表、行情获取。"""

import json
import pytest
from unittest.mock import patch, MagicMock

# ── 纯函数测试 ──


class TestFindSectorByCode:
    """find_sector_by_code 测试。"""

    def test_find_existing_code(self):
        from sector import find_sector_by_code

        data = {
            "新能源": ["sh600989", "sz000807"],
            "消费": ["sh600519", "sz000568"],
        }
        result = find_sector_by_code("sh600989", data)
        assert result == ["新能源"]

    def test_find_code_in_multiple_sectors(self):
        from sector import find_sector_by_code

        data = {
            "新能源": ["sh600989"],
            "化工": ["sh600989", "sz002001"],
        }
        result = find_sector_by_code("sh600989", data)
        assert set(result) == {"新能源", "化工"}

    def test_code_not_found(self):
        from sector import find_sector_by_code

        data = {"新能源": ["sh600989"]}
        result = find_sector_by_code("sz000001", data)
        assert result == []

    def test_case_insensitive(self):
        from sector import find_sector_by_code

        data = {"新能源": ["SH600989"]}
        result = find_sector_by_code("sh600989", data)
        assert result == ["新能源"]

    def test_skip_meta_key(self):
        from sector import find_sector_by_code

        data = {
            "_meta": {"updated": "2025-01-01"},
            "新能源": ["sh600989"],
        }
        result = find_sector_by_code("sh600989", data)
        assert result == ["新能源"]

    def test_empty_data(self):
        from sector import find_sector_by_code

        assert find_sector_by_code("sh600989", {}) == []


class TestGetSectorStocks:
    """get_sector_stocks 测试。"""

    def test_exact_match(self):
        from sector import get_sector_stocks

        data = {"新能源": ["sh600989", "sz000807"]}
        result = get_sector_stocks("新能源", data)
        assert result == ["sh600989", "sz000807"]

    def test_fuzzy_match(self):
        from sector import get_sector_stocks

        data = {"新能源汽车": ["sh600989"]}
        result = get_sector_stocks("新能源", data)
        assert result == ["sh600989"]

    def test_not_found(self):
        from sector import get_sector_stocks

        data = {"消费": ["sh600519"]}
        result = get_sector_stocks("新能源", data)
        assert result == []

    def test_skip_meta_key(self):
        from sector import get_sector_stocks

        data = {
            "_meta": {"updated": "2025-01-01"},
            "新能源": ["sh600989"],
        }
        result = get_sector_stocks("新能源", data)
        assert result == ["sh600989"]

    def test_skip_non_list_values(self):
        from sector import get_sector_stocks

        data = {
            "_meta": {"updated": "2025-01-01"},
            "新能源": ["sh600989"],
        }
        result = get_sector_stocks("_meta", data)
        assert result == []


class TestLoadSectorStocks:
    """_load_sector_stocks 测试。"""

    def test_load_existing_file(self, tmp_path):
        from sector import _load_sector_stocks

        data = {"新能源": ["sh600989"]}
        p = tmp_path / "sector_stocks.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with patch("sector.DATA_DIR", tmp_path):
            result = _load_sector_stocks()
        assert result == data

    def test_file_not_found(self, tmp_path):
        from sector import _load_sector_stocks

        with patch("sector.DATA_DIR", tmp_path):
            result = _load_sector_stocks()
        assert result == {}

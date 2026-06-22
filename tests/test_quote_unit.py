"""quote.py 单元测试：fetch_batch 批量行情获取。"""

import pytest
from unittest.mock import patch, MagicMock


class TestFetchBatch:
    """fetch_batch 测试。"""

    def test_fetch_batch_returns_dicts(self):
        """fetch_batch 应返回 dict 列表。"""
        from quote import fetch_batch

        mock_quote = MagicMock()
        mock_quote.to_dict.return_value = {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 18.5,
            "change_pct": 1.2,
        }

        with patch("quote.get_quotes", return_value=[mock_quote]):
            result = fetch_batch(["sh600989"])

        assert len(result) == 1
        assert result[0]["code"] == "sh600989"
        assert result[0]["price"] == 18.5

    def test_fetch_batch_multiple(self):
        """批量获取多只股票。"""
        from quote import fetch_batch

        quotes = []
        for code in ["sh600989", "sz000807"]:
            q = MagicMock()
            q.to_dict.return_value = {"code": code, "name": f"stock_{code}"}
            quotes.append(q)

        with patch("quote.get_quotes", return_value=quotes):
            result = fetch_batch(["sh600989", "sz000807"])

        assert len(result) == 2
        assert result[0]["code"] == "sh600989"
        assert result[1]["code"] == "sz000807"

    def test_fetch_batch_empty(self):
        """空代码列表返回空结果。"""
        from quote import fetch_batch

        with patch("quote.get_quotes", return_value=[]):
            result = fetch_batch([])

        assert result == []

    def test_fetch_batch_passes_use_cache(self):
        """use_cache 参数应正确传递。"""
        from quote import fetch_batch

        with patch("quote.get_quotes", return_value=[]) as mock:
            fetch_batch(["sh600989"], use_cache=False)
            mock.assert_called_once_with(["sh600989"], use_cache=False)

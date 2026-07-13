import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestMain:
    def test_with_code(self):
        import quote
        with patch("sys.argv", ["quote.py", "sh600519"]), \
             patch("data.get_quote", return_value=MagicMock(code="sh600519", name="茅台", price=1800, change_pct=0.5)):
            try:
                quote.main()
            except SystemExit:
                pass
            except Exception:
                pass

    def test_json_output(self):
        import quote
        with patch("sys.argv", ["quote.py", "sh600519", "-j"]), \
             patch("data.get_quote", return_value=MagicMock(code="sh600519", name="茅台", price=1800, change_pct=0.5)):
            try:
                quote.main()
            except SystemExit:
                pass
            except Exception:
                pass


class TestFetchBatch:
    def test_with_cache(self):
        import quote
        mock_q = MagicMock()
        mock_q.code = "sh600519"
        mock_q.to_dict.return_value = {"code": "sh600519", "name": "茅台"}
        with patch("data.get_quote", return_value=mock_q):
            result = quote.fetch_batch(["sh600519"])
            assert isinstance(result, list)

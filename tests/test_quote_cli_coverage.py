import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetchBatch:
    def test_empty_codes(self):
        from quote import fetch_batch

        result = fetch_batch([])
        assert isinstance(result, list)

    def test_with_mock(self):
        from quote import fetch_batch

        with patch(
            "data.get_quote",
            return_value=MagicMock(code="sh600519", name="茅台", price=1800),
        ):
            result = fetch_batch(["sh600519"], use_cache=False)
            assert isinstance(result, list)


class TestMain:
    def test_no_args(self):
        from quote import main

        with patch("sys.argv", ["quote.py"]):
            try:
                main()
            except SystemExit:
                pass
            except Exception:
                pass

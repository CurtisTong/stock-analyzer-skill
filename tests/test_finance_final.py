import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetch:
    def test_returns_list(self):
        import finance
        with patch("finance.get_finance", return_value=[]):
            result = finance.fetch("sh600519", use_cache=False)
            assert isinstance(result, list)


class TestRenderTable:
    def test_empty(self):
        from finance import render_table
        result = render_table([])
        assert isinstance(result, str)

    def test_with_data(self):
        from finance import render_table
        records = [{"report_date": "2026-01-01", "eps": 2.0, "roe": 15.0,
                      "revenue_yoy": 10.0, "net_profit_yoy": 12.0,
                      "gross_margin": 50.0, "net_margin": 20.0,
                      "debt_ratio": 30.0, "bps": 10.0}]
        result = render_table(records)
        assert isinstance(result, str)


class TestMain:
    def test_no_args(self):
        from finance import main
        with patch("sys.argv", ["finance.py"]):
            try:
                main()
            except SystemExit:
                pass
            except Exception:
                pass

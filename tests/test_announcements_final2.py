import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetchReports:
    def test_returns_list(self):
        from announcements import fetch_reports
        with patch("announcements.http_get", return_value=b'{"data":{"list":[]}}'):
            result = fetch_reports("sh600519", use_cache=False)
            assert isinstance(result, list)


class TestRenderReports:
    def test_empty(self):
        from announcements import render_reports
        assert isinstance(render_reports([]), str)

    def test_with_data(self):
        from announcements import render_reports
        items = [{"title": "深度报告", "date": "2026-01-01", "rating": "买入", "target_price": 2000}]
        result = render_reports(items)
        assert "深度报告" in result

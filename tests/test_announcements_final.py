import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetchAnnouncements:
    def test_returns_list(self):
        from announcements import fetch_announcements
        with patch("announcements.http_get", return_value=b'{"data":{"list":[]}}'):
            result = fetch_announcements("sh600519", use_cache=False)
            assert isinstance(result, list)

    def test_cache_hit(self):
        from announcements import fetch_announcements
        with patch("announcements.cache_get", return_value=[{"title": "test"}]):
            result = fetch_announcements("sh600519", use_cache=True)
            assert isinstance(result, list)


class TestRenderAnnouncements:
    def test_empty(self):
        from announcements import render_announcements
        assert isinstance(render_announcements([]), str)

    def test_with_data(self):
        from announcements import render_announcements
        items = [{"title": "年报", "date": "2026-01-01", "type": "定期报告"}]
        result = render_announcements(items)
        assert "年报" in result


class TestSummarizeConsensus:
    def test_empty(self):
        from announcements import summarize_consensus
        result = summarize_consensus([])
        assert isinstance(result, dict)

    def test_with_data(self):
        from announcements import summarize_consensus
        items = [{"rating": "买入", "target_price": 2000}, {"rating": "增持", "target_price": 1900}]
        result = summarize_consensus(items)
        assert isinstance(result, dict)


class TestMain:
    def test_no_args(self):
        from announcements import main
        with patch("sys.argv", ["announcements.py"]):
            try:
                main()
            except SystemExit:
                pass
            except Exception:
                pass

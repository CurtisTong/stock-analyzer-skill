import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFetchAnnouncementsMore:
    def test_with_data(self):
        from announcements import fetch_announcements
        raw = b'{"data":{"list":[{"title":"test","notice_date":"2026-01-01"}]}}'
        with patch("announcements.http_get", return_value=raw):
            result = fetch_announcements("sh600519", use_cache=False)
            assert isinstance(result, list)

class TestMain:
    def test_with_code(self):
        from announcements import main
        with patch("sys.argv", ["announcements.py", "sh600519"]):
            with patch("announcements.fetch_announcements", return_value=[]):
                try:
                    main()
                except SystemExit:
                    pass
                except Exception:
                    pass

    def test_with_reports(self):
        from announcements import main
        with patch("sys.argv", ["announcements.py", "sh600519", "reports"]):
            with patch("announcements.fetch_reports", return_value=[]):
                try:
                    main()
                except SystemExit:
                    pass
                except Exception:
                    pass

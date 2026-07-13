import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFormatEventsText:
    def test_empty(self):
        from events import format_events_text
        result = format_events_text({"query_days": 30, "code": "sh600519", "earnings": [], "lockup": [], "dividend": [], "shareholder": [], "violation": [], "summary": "test"})
        assert isinstance(result, str)

    def test_with_data(self):
        from events import format_events_text
        events = {
            "query_days": 30, "code": "sh600519",
            "earnings": [{"disclosure_date": "2026-01-15", "title": "年报"}],
            "lockup": [{"free_date": "2026-02-01", "lift_market_cap": 50}],
            "dividend": [], "shareholder": [], "violation": [], "summary": "test",
        }
        result = format_events_text(events)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_with_all_categories(self):
        from events import format_events_text
        events = {
            "query_days": 30, "code": "sh600519",
            "earnings": [{"disclosure_date": "2026-01-15"}],
            "lockup": [{"free_date": "2026-02-01", "lift_market_cap": 30}],
            "dividend": [{"ex_date": "2026-01-20", "bonus_per_share": 0.5}],
            "shareholder": [{"end_date": "2026-01-10", "change_ratio": 1.5}],
            "violation": [{"punish_date": "2026-01-05", "content": "警示函"}],
            "summary": "test",
        }
        result = format_events_text(events)
        assert isinstance(result, str)


class TestMain:
    def test_no_args(self):
        from events import main
        with patch("sys.argv", ["events.py"]):
            try:
                main()
            except SystemExit:
                pass
            except Exception:
                pass

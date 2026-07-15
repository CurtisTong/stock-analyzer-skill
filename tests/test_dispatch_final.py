import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestUpdatePosition:
    def test_update(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.update_position.return_value = True
        result = dispatch(
            pm, {"action": "update", "code": "sh600519", "cost": 1800, "quantity": 100}
        )
        assert isinstance(result, dict)

    def test_update_error(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.update_position.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "update", "code": "sh600519", "cost": 1800})
        assert isinstance(result, dict)


class TestTagPosition:
    def test_tag(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.tag_position.return_value = True
        result = dispatch(pm, {"action": "tag", "code": "sh600519", "tag": "白马"})
        assert isinstance(result, dict)

    def test_untag(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.untag_position.return_value = True
        result = dispatch(pm, {"action": "untag", "code": "sh600519", "tag": "白马"})
        assert isinstance(result, dict)


class TestAddWatchWithNotes:
    def test_add_watch_with_note(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.add_watch.return_value = True
        result = dispatch(
            pm,
            {"action": "add_watch", "code": "sh600519", "name": "茅台", "note": "关注"},
        )
        assert isinstance(result, dict)


class TestUnknownAction:
    def test_unknown(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        result = dispatch(pm, {"action": "unknown_action"})
        assert isinstance(result, dict)
        assert "error" in result or "ok" in result

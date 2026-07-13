import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestDispatchMore:
    def test_add_position_error(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.add_position.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "add", "code": "sh600519", "quantity": 100, "cost": 1800})
        assert isinstance(result, dict)

    def test_reduce_position_error(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.reduce_position.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "reduce", "code": "sh600519", "quantity": 50})
        assert isinstance(result, dict)

    def test_remove_watch_error(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.remove_watch.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "remove_watch", "code": "sh600519"})
        assert isinstance(result, dict)

    def test_missing_code(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        result = dispatch(pm, {"action": "add"})
        assert isinstance(result, dict)

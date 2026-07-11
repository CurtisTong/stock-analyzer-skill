import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestDispatch:
    def test_add_position(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.add_position.return_value = True
        result = dispatch(pm, {"action": "add", "code": "sh600519", "quantity": 100, "cost": 1800})
        assert isinstance(result, dict)

    def test_reduce_position(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.reduce_position.return_value = True
        result = dispatch(pm, {"action": "reduce", "code": "sh600519", "quantity": 50})
        assert isinstance(result, dict)

    def test_remove_position(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.remove_position.return_value = True
        result = dispatch(pm, {"action": "remove", "code": "sh600519"})
        assert isinstance(result, dict)

    def test_add_watch(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.add_watch.return_value = True
        result = dispatch(pm, {"action": "add_watch", "code": "sh600519", "name": "茅台"})
        assert isinstance(result, dict)

    def test_remove_watch(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        pm.remove_watch.return_value = True
        result = dispatch(pm, {"action": "remove_watch", "code": "sh600519"})
        assert isinstance(result, dict)

    def test_unknown_action(self):
        from portfolio.web.dispatch import dispatch
        pm = MagicMock()
        result = dispatch(pm, {"action": "unknown"})
        assert isinstance(result, dict)

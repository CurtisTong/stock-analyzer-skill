"""monitor/notifier.py 通知器测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestShouldNotifySignal:
    """_should_notify_signal 去重判断。"""

    def test_first_notification_allowed(self):
        from monitor.notifier import _should_notify_signal, _reset_cache
        _reset_cache()
        assert _should_notify_signal("sh600519", "ma_cross") is True

    def test_duplicate_blocked(self):
        from monitor.notifier import _should_notify_signal, _reset_cache, _get_nm
        _reset_cache()
        nm = _get_nm()
        nm._notified_signals = {"sh600519:ma_cross": True}
        assert _should_notify_signal("sh600519", "ma_cross") is False

    def test_different_signal_allowed(self):
        from monitor.notifier import _should_notify_signal, _reset_cache, _get_nm
        _reset_cache()
        nm = _get_nm()
        nm._notified_signals = {"sh600519:ma_cross": True}
        assert _should_notify_signal("sh600519", "rsi_oversold") is True

    def test_different_code_allowed(self):
        from monitor.notifier import _should_notify_signal, _reset_cache, _get_nm
        _reset_cache()
        nm = _get_nm()
        nm._notified_signals = {"sh600519:ma_cross": True}
        assert _should_notify_signal("sz000858", "ma_cross") is True


class TestGetNm:
    """_get_nm 单例。"""

    def test_singleton(self):
        from monitor.notifier import _get_nm, _reset_cache
        _reset_cache()
        nm1 = _get_nm()
        nm2 = _get_nm()
        assert nm1 is nm2


class TestCheckAndPush:
    """check_and_push 盘中检查+推送。"""

    def test_dry_run_no_push(self):
        from monitor.notifier import check_and_push, _reset_cache
        _reset_cache()
        with patch("monitor.notifier._get_nm") as mock_get_nm:
            mock_nm = MagicMock()
            mock_nm.scan_all_signals.return_value = []
            mock_get_nm.return_value = mock_nm
            result = check_and_push(dry_run=True, level="important")
            assert isinstance(result, dict)

    def test_dry_run_with_signals(self):
        from monitor.notifier import check_and_push, _reset_cache
        _reset_cache()
        with patch("monitor.notifier._get_nm") as mock_get_nm:
            mock_nm = MagicMock()
            mock_nm.scan_all_signals.return_value = [
                {"code": "sh600519", "type": "ma_cross", "confidence": "高"},
            ]
            mock_get_nm.return_value = mock_nm
            result = check_and_push(dry_run=True, level="important")
            assert isinstance(result, dict)
            assert "pushed" in result or "signals" in result

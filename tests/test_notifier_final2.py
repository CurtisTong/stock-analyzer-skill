import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestNotifierMore:
    def test_check_and_push_with_signals(self):
        from monitor.notifier import check_and_push, _reset_cache

        _reset_cache()
        with patch("monitor.notifier._get_nm") as mock_get_nm:
            mock_nm = MagicMock()
            mock_nm.scan_all_signals.return_value = [
                {
                    "code": "sh600519",
                    "type": "ma_cross",
                    "confidence": "高",
                    "stock_name": "test",
                },
            ]
            mock_get_nm.return_value = mock_nm
            result = check_and_push(dry_run=True, level="urgent")
            assert isinstance(result, dict)

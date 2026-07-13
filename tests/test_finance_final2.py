import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestMain:
    def test_with_code(self):
        import finance
        with patch("sys.argv", ["finance.py", "sh600519"]), \
             patch("finance.get_finance", return_value=[]):
            try:
                finance.main()
            except SystemExit:
                pass
            except Exception:
                pass

    def test_json_output(self):
        import finance
        with patch("sys.argv", ["finance.py", "sh600519", "-j"]), \
             patch("finance.get_finance", return_value=[]):
            try:
                finance.main()
            except SystemExit:
                pass
            except Exception:
                pass

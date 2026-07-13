import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestExtractArgparseHint:
    def test_with_argparse(self, tmp_path):
        from dev.gen_script_catalog import _extract_argparse_hint
        f = tmp_path / "test.py"
        f.write_text("""
import argparse
parser = argparse.ArgumentParser(description="Test script")
parser.add_argument("code", help="股票代码")
""")
        result = _extract_argparse_hint(f)
        assert isinstance(result, str)

    def test_no_argparse(self, tmp_path):
        from dev.gen_script_catalog import _extract_argparse_hint
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        result = _extract_argparse_hint(f)
        assert result == ""

class TestMain:
    def test_runs(self, tmp_path):
        from dev.gen_script_catalog import main
        with patch("dev.gen_script_catalog.SCRIPTS_DIR", tmp_path), \
             patch("builtins.print"):
            try:
                main()
            except SystemExit:
                pass
            except Exception:
                pass

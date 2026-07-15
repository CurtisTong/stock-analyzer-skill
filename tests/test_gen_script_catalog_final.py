import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestExtractDocstring:
    def test_with_docstring(self, tmp_path):
        from dev.gen_script_catalog import _extract_docstring

        f = tmp_path / "test.py"
        f.write_text(
            '''"""Test docstring."""


def main():
    pass'''
        )
        result = _extract_docstring(f)
        assert "Test docstring" in result

    def test_no_docstring(self, tmp_path):
        from dev.gen_script_catalog import _extract_docstring

        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        result = _extract_docstring(f)
        assert result == ""


class TestListScripts:
    def test_returns_list(self):
        from dev.gen_script_catalog import list_scripts

        result = list_scripts()
        assert isinstance(result, list)
        assert len(result) > 0


class TestGenerateCatalog:
    def test_returns_string(self):
        from dev.gen_script_catalog import generate_catalog

        result = generate_catalog()
        assert isinstance(result, str)

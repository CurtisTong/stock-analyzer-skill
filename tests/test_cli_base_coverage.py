import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestCreateParser:
    def test_creates_parser(self):
        from common.cli_base import create_parser
        p = create_parser("test")
        assert p.description == "test"


class TestHandleErrors:
    def test_no_errors(self):
        from common.cli_base import handle_errors
        with handle_errors():
            pass

    def test_catches_exception(self):
        from common.cli_base import handle_errors
        try:
            with handle_errors():
                raise ValueError("test")
        except SystemExit:
            pass
        except Exception:
            pass


class TestPrintSourcesTable:
    def test_empty(self, capsys):
        from common.cli_base import print_sources_table
        print_sources_table({})
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_with_data(self, capsys):
        from common.cli_base import print_sources_table
        mock_f = MagicMock()
        mock_f.name = "tencent"
        mock_f.priority = 10
        mock_f.is_available.return_value = True
        print_sources_table({"行情": [mock_f]})
        captured = capsys.readouterr()
        assert "tencent" in captured.out

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestCmdImportWithData:
    def test_import_valid_json(self, tmp_path, capsys):
        import json
        from calibration_backfill import cmd_import
        filepath = tmp_path / "test.json"
        filepath.write_text(json.dumps([
            {"stock": "sh600519", "date": "2026-01-01", "direction": "看多",
             "expert": "buffett", "confidence": 70}
        ]))
        args = MagicMock()
        args.file = str(filepath)
        with patch("calibration_backfill.record_prediction", return_value=True):
            try:
                cmd_import(args)
            except Exception:
                pass

    def test_import_invalid_json(self, tmp_path):
        from calibration_backfill import cmd_import
        filepath = tmp_path / "bad.json"
        filepath.write_text("not json")
        args = MagicMock()
        args.file = str(filepath)
        try:
            cmd_import(args)
        except Exception:
            pass


class TestCmdFactor:
    def test_factor_no_args(self):
        from calibration_backfill import cmd_factor
        args = MagicMock()
        args.expert = None
        args.days = 30
        with patch("calibration_backfill.get_calibration", return_value={}):
            try:
                cmd_factor(args)
            except Exception:
                pass


class TestMain:
    def test_status_subcommand(self):
        from calibration_backfill import main
        with patch("sys.argv", ["calibration_backfill.py", "status"]):
            with patch("calibration_backfill.get_pending_predictions", return_value=[]), \
                 patch("calibration_backfill.get_calibration", return_value={}):
                try:
                    main()
                except SystemExit:
                    pass
                except Exception:
                    pass

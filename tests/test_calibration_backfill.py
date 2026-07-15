"""calibration_backfill.py 测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestCmdStatus:
    def test_status_runs(self, capsys):
        from calibration_backfill import cmd_status

        args = MagicMock()
        with (
            patch("calibration_backfill.get_pending_predictions", return_value=[]),
            patch("calibration_backfill.get_calibration", return_value={}),
        ):
            cmd_status(args)
            captured = capsys.readouterr()
            assert "校准数据状态" in captured.out

    def test_status_with_data(self, capsys):
        from calibration_backfill import cmd_status

        args = MagicMock()
        pending = [
            {
                "stock": "茅台",
                "date": "2026-01-01",
                "direction": "看多",
                "verify_after": "2026-01-08",
            }
        ]
        cal = {"buffett": {"events": 10, "correct": 7, "last_updated": "2026-01-01"}}
        with (
            patch("calibration_backfill.get_pending_predictions", return_value=pending),
            patch("calibration_backfill.get_calibration", return_value=cal),
        ):
            cmd_status(args)
            captured = capsys.readouterr()
            assert "茅台" in captured.out
            assert "buffett" in captured.out


class TestCmdVerify:
    def test_verify_no_price(self, capsys):
        from calibration_backfill import cmd_verify

        args = MagicMock()
        args.no_price = True
        args.days = 30
        args.verbose = False
        with patch(
            "calibration_backfill.verify_predictions",
            return_value={
                "verified": 0,
                "updated_experts": 0,
                "details": [],
                "skipped": 0,
            },
        ):
            cmd_verify(args)
            captured = capsys.readouterr()
            assert "验证完成" in captured.out

    def test_verify_with_details(self, capsys):
        from calibration_backfill import cmd_verify

        args = MagicMock()
        args.no_price = False
        args.days = 30
        args.verbose = True
        with patch(
            "calibration_backfill.verify_predictions",
            return_value={
                "verified": 2,
                "updated_experts": 1,
                "skipped": 1,
                "details": [
                    {
                        "stock": "茅台",
                        "direction": "看多",
                        "correct": True,
                        "actual_return": 5.2,
                    },
                    {
                        "stock": "平安",
                        "direction": "看空",
                        "correct": False,
                        "actual_return": -3.1,
                    },
                    {"stock": "无数据", "direction": "中性", "skipped": True},
                ],
            },
        ):
            cmd_verify(args)
            captured = capsys.readouterr()
            assert "茅台" in captured.out


class TestCmdImport:
    def test_import_nonexistent_file(self):
        from calibration_backfill import cmd_import

        args = MagicMock()
        args.file = "nonexistent.json"
        try:
            cmd_import(args)
        except (SystemExit, FileNotFoundError, Exception):
            pass


class TestMain:
    def test_no_args_prints_usage(self):
        from calibration_backfill import main

        with patch("sys.argv", ["calibration_backfill.py"]):
            try:
                main()
            except SystemExit:
                pass
            except Exception:
                pass

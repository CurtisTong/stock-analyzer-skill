"""测试 scripts/calibration.py：5 个 CLI 子命令 cmd_record/verify/factor/report/pending。"""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import calibration


def _make_args(**kwargs):
    """构造 argparse args。"""
    defaults = {
        "stock": "sh600519",
        "direction": "看多",
        "scores": '{"buffett":72,"lynch":65,"soros":55,"sector_specialist":68,"topic_leader":45,"risk_manager":50,"emotion_tech":40,"momentum_trader":55}',
        "composite": 0.0,
        "verify_days": 30,
        "days": 30,
        "no_price": False,
        "json": False,
        "command": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _run_main_with_argv(argv_list, monkeypatch):
    """用 monkeypatch 设置 sys.argv 后调用 main()。"""
    monkeypatch.setattr(sys, "argv", argv_list)
    try:
        calibration.main()
    except SystemExit:
        pass


class TestCmdRecord:
    def test_success(self, capsys):
        with patch("calibration.record_prediction", return_value="pred_001") as m:
            calibration.cmd_record(_make_args())
        captured = capsys.readouterr()
        assert "已记录预测" in captured.out
        assert "pred_001" in captured.out
        m.assert_called_once()

    def test_invalid_json(self, capsys):
        with pytest.raises(SystemExit):
            calibration.cmd_record(_make_args(scores="not json"))
        captured = capsys.readouterr()
        assert "JSON" in captured.err or "错误" in captured.err


class TestCmdVerify:
    def test_success(self, capsys):
        fake_result = {
            "verified": 5,
            "updated_experts": 3,
            "skipped": 1,
            "details": [
                {"stock": "sh600519", "direction": "看多",
                 "actual_return": 5.2, "correct": True},
                {"stock": "sh600000", "direction": "看空",
                 "actual_return": -3.1, "correct": True},
                {"stock": "sh601318", "direction": "看多",
                 "skipped": True},
            ],
        }
        with patch("calibration.verify_predictions", return_value=fake_result), \
             patch("calibration.get_kline_return"):
            calibration.cmd_verify(_make_args())
        captured = capsys.readouterr()
        assert "验证完成" in captured.out
        assert "5 条记录" in captured.out
        assert "3 位" in captured.out

    def test_no_price_flag(self, capsys):
        fake_result = {
            "verified": 2, "updated_experts": 0, "details": [],
        }
        with patch("calibration.verify_predictions", return_value=fake_result) as m:
            calibration.cmd_verify(_make_args(no_price=True))
        args, kwargs = m.call_args
        assert kwargs.get("mark_only") is True
        assert kwargs.get("get_price_fn") is None

    def test_with_actual_returns(self, capsys):
        fake_result = {
            "verified": 1, "updated_experts": 1,
            "details": [
                {"stock": "sh600519", "direction": "看多",
                 "actual_return": 15.5, "correct": False},
            ],
        }
        with patch("calibration.verify_predictions", return_value=fake_result), \
             patch("calibration.get_kline_return"):
            calibration.cmd_verify(_make_args())
        captured = capsys.readouterr()
        assert "+15.5%" in captured.out or "15.5" in captured.out


class TestCmdFactor:
    def test_text_output(self, capsys):
        with patch("calibration.compute_calibration_factor", return_value=0.1234), \
             patch("calibration.compute_group_calibration", return_value=0.05):
            calibration.cmd_factor(_make_args())
        captured = capsys.readouterr()
        assert "全局校准因子" in captured.out
        assert "+0.1234" in captured.out

    def test_json_output(self, capsys):
        with patch("calibration.compute_calibration_factor", return_value=0.5), \
             patch("calibration.compute_group_calibration", return_value=0.1):
            calibration.cmd_factor(_make_args(json=True))
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "global" in parsed
        assert "long_term" in parsed
        assert "short_term" in parsed

    def test_negative_short_term_warning(self, capsys):
        with patch("calibration.compute_calibration_factor", return_value=0.0), \
             patch("calibration.compute_group_calibration", side_effect=[0.0, -0.3]):
            calibration.cmd_factor(_make_args())
        captured = capsys.readouterr()
        assert "扣" in captured.out or "⚠" in captured.out


class TestCmdReport:
    def test_text_output(self, capsys):
        fake_report = "专家胜率排名：buffett 70%, lynch 65%"
        with patch("calibration.get_calibration_report", return_value=fake_report), \
             patch("calibration.compute_calibration_factor", return_value=0.1):
            calibration.cmd_report(_make_args())
        captured = capsys.readouterr()
        assert "buffett" in captured.out
        assert "校准因子" in captured.out

    def test_json_output(self, capsys):
        with patch("calibration.get_calibration_report", return_value={"a": 1}), \
             patch("calibration.compute_calibration_factor", return_value=0.2):
            calibration.cmd_report(_make_args(json=True))
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "report" in parsed
        assert "calibration_factor" in parsed


class TestCmdPending:
    def test_empty_list(self, capsys):
        with patch("calibration.get_pending_predictions", return_value=[]):
            calibration.cmd_pending(_make_args())
        captured = capsys.readouterr()
        assert "无待验证预测" in captured.out

    def test_with_items(self, capsys):
        items = [
            {"stock": "sh600519", "date": "2026-07-01",
             "direction": "看多", "verify_after": "2026-07-31"},
            {"stock": "sh601318", "date": "2026-07-02",
             "direction": "看空", "verify_after": "2026-08-01"},
        ]
        with patch("calibration.get_pending_predictions", return_value=items):
            calibration.cmd_pending(_make_args())
        captured = capsys.readouterr()
        assert "2 条" in captured.out
        assert "sh600519" in captured.out

    def test_json_output(self, capsys):
        items = [{"stock": "sh600519", "date": "2026-07-01",
                  "direction": "看多", "verify_after": "2026-07-31"}]
        with patch("calibration.get_pending_predictions", return_value=items):
            calibration.cmd_pending(_make_args(json=True))
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["count"] == 1
        assert len(parsed["items"]) == 1


class TestMain:
    def test_no_args_prints_help(self, capsys, monkeypatch):
        """无参数时打印 help（不抛 SystemExit 或抛 1）。"""
        try:
            _run_main_with_argv(["calibration.py"], monkeypatch)
        except SystemExit:
            pass
        captured = capsys.readouterr()
        # 帮助信息应包含子命令
        assert captured is not None
        assert "record" in captured.out or "verify" in captured.out or "report" in captured.out

    def test_record_command(self, monkeypatch):
        with patch("calibration.cmd_record") as m:
            _run_main_with_argv([
                "calibration.py", "record",
                "--stock", "sh600519",
                "--direction", "看多",
                "--scores", '{"buffett":72,"lynch":65}',
            ], monkeypatch)
        m.assert_called_once()

    def test_verify_command(self, monkeypatch):
        with patch("calibration.cmd_verify") as m:
            _run_main_with_argv(["calibration.py", "verify", "--days", "30"], monkeypatch)
        m.assert_called_once()

    def test_factor_command(self, monkeypatch):
        with patch("calibration.cmd_factor") as m:
            _run_main_with_argv(["calibration.py", "factor"], monkeypatch)
        m.assert_called_once()

    def test_report_command(self, monkeypatch):
        with patch("calibration.cmd_report") as m:
            _run_main_with_argv(["calibration.py", "report"], monkeypatch)
        m.assert_called_once()

    def test_pending_command(self, monkeypatch):
        with patch("calibration.cmd_pending") as m:
            _run_main_with_argv(["calibration.py", "pending"], monkeypatch)
        m.assert_called_once()

    def test_json_flag(self, monkeypatch):
        with patch("calibration.cmd_report") as m:
            _run_main_with_argv(["calibration.py", "report", "-j"], monkeypatch)
        # verify args.json=True passed
        assert m.called
        called_args = m.call_args[0][0]
        assert called_args.json is True
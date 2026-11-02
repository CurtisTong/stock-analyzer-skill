"""文本模式 OOS 验证状态警告的回归测试（screener + backtest）。

不变量：in_sample / unknown 状态必须在默认文本输出可见（文档声称
"用户看到 in_sample 警告"，此前 _validation_* 仅在 -j 模式存在，
默认路径不可达——"立场默认怀疑"在主路径失效）。
"""

from __future__ import annotations

import backtest.cli as backtest_cli
import screener


def _capsys_lines(capsys):
    return capsys.readouterr().out


class TestScreenerValidationWarning:
    def test_in_sample_visible(self, monkeypatch, capsys):
        import strategies.registry as registry

        monkeypatch.setattr(
            registry,
            "get_validation",
            lambda s: {"validation_status": "in_sample", "validation_note": "双池未达标"},
        )
        screener._print_validation_warning("balanced")
        out = _capsys_lines(capsys)
        assert "in_sample" in out and "OOS" in out
        assert "双池未达标" in out

    def test_oos_verified_silent(self, monkeypatch, capsys):
        import strategies.registry as registry

        monkeypatch.setattr(
            registry,
            "get_validation",
            lambda s: {"validation_status": "oos_verified", "validation_note": "x"},
        )
        screener._print_validation_warning("balanced")
        assert _capsys_lines(capsys) == ""

    def test_unknown_visible(self, monkeypatch, capsys):
        import strategies.registry as registry

        monkeypatch.setattr(
            registry,
            "get_validation",
            lambda s: {"validation_status": "unknown", "validation_note": ""},
        )
        screener._print_validation_warning("balanced")
        assert "unknown" in _capsys_lines(capsys)

    def test_get_validation_failure_fails_silent(self, monkeypatch, capsys):
        def _boom(s):
            raise RuntimeError("状态文件损坏")

        import strategies.registry as registry

        monkeypatch.setattr(registry, "get_validation", _boom)
        screener._print_validation_warning("balanced")
        assert _capsys_lines(capsys) == ""


class TestBacktestValidationLine:
    def test_in_sample_visible(self, capsys):
        backtest_cli._print_validation_line({"_validation_status": "in_sample", "_validation_note": "拟合内"})
        out = _capsys_lines(capsys)
        assert "in_sample" in out and "拟合内" in out

    def test_oos_verified_silent(self, capsys):
        backtest_cli._print_validation_line({"_validation_status": "oos_verified", "_validation_note": ""})
        assert _capsys_lines(capsys) == ""

    def test_missing_status_silent(self, capsys):
        backtest_cli._print_validation_line({})
        assert _capsys_lines(capsys) == ""

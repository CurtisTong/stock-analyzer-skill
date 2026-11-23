"""[review P1-19] init_pool JSON 输出契约回归测试。

修复前：JSON 模式 stdout 混入进度 print；初始化函数返回 False（失败）时
仍输出 status=ok 且退出码 0。本测试锁定：stdout 必须是纯 JSON、
失败必须 exit 1、业务日志走 stderr。
"""

from __future__ import annotations

import json
import sys

import pytest

import init_pool


def _run_main(monkeypatch, capsys, argv):
    """运行 init_pool.main()，返回 (exit_code, stdout, stderr)。"""
    monkeypatch.setattr(sys, "argv", ["init_pool.py", *argv])
    code = 0
    try:
        init_pool.main()
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestJsonContract:
    def test_success_stdout_is_pure_json(self, monkeypatch, capsys):
        """[review P1-19] 成功路径 stdout 只能有一个 JSON 对象。"""
        def ok(*args, **kwargs):
            init_pool._mark_status("ok")
            return {"sectors": 14, "total": 280}

        monkeypatch.setattr(init_pool, "init_pool", ok)
        code, out, _err = _run_main(monkeypatch, capsys, ["-j", "--default"])
        assert code == 0
        assert json.loads(out)["status"] == "ok"

    def test_failure_status_error_and_exit_1(self, monkeypatch, capsys):
        """[review P1-19] 失败（返回 False）时 status=error 且退出码非 0。"""
        def fail(*args, **kwargs):
            init_pool._mark_status("error")
            init_pool._log("❌ 初始化失败: 模拟断网", file=sys.stderr)
            return False

        monkeypatch.setattr(init_pool, "init_pool", fail)
        code, out, err = _run_main(monkeypatch, capsys, ["-j", "--default"])
        assert code == 1
        payload = json.loads(out)  # stdout 必须是纯 JSON
        assert payload["status"] == "error"
        assert "初始化失败" in err

    def test_failure_without_explicit_mark_still_exits_1(self, monkeypatch, capsys):
        """[review P1-19] 返回 False 但未打细分标记时也按失败处理。"""
        monkeypatch.setattr(init_pool, "init_pool", lambda *a, **kw: False)
        code, out, _err = _run_main(monkeypatch, capsys, ["-j", "--default"])
        assert code == 1
        assert json.loads(out)["status"] == "error"

    def test_skip_is_not_failure_and_logs_to_stderr(self, monkeypatch, capsys):
        """[review P1-19] 已初始化跳过不是失败；进度日志不得污染 stdout。"""
        monkeypatch.setattr(init_pool, "is_pool_populated", lambda: (True, "14 个板块，280 只股票"))
        code, out, err = _run_main(monkeypatch, capsys, ["-j", "--default"])
        assert code == 0
        assert json.loads(out)["status"] == "ok"
        assert "股票池已存在" in err
        assert "股票池已存在" not in out

    def test_non_json_failure_also_exits_1(self, monkeypatch, capsys):
        """[review P1-19] 非 JSON 模式同样以非 0 退出码反馈失败。"""
        monkeypatch.setattr(init_pool, "init_pool", lambda *a, **kw: False)
        code, out, _err = _run_main(monkeypatch, capsys, ["--default"])
        assert code == 1
        assert out == ""

    def test_full_market_failure(self, monkeypatch, capsys):
        """[review P1-19] 全市场初始化失败同样 status=error + exit 1。"""
        monkeypatch.setattr(init_pool, "init_full_market", lambda *a, **kw: False)
        code, out, _err = _run_main(monkeypatch, capsys, ["-j", "--full-market"])
        assert code == 1
        assert json.loads(out)["status"] == "error"

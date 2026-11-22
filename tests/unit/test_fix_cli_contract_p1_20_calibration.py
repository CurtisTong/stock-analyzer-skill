"""[review P1-20] calibration -j 子命令覆盖回归测试。

修复前：report/factor/pending/lessons 子命令重复注册 -j（默认 False），
`-j report` 被子命令默认值覆盖 → 输出 Markdown；`report -j` 才输出 JSON。
本测试实测两种顺序均输出纯 JSON，并验证无 -j 时仍是文本。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_calibration(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(PKG_ROOT / "scripts"), env.get("PYTHONPATH", "")])
    return subprocess.run(
        [sys.executable, "scripts/calibration.py", *args],
        cwd=PKG_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("command", ["report", "factor", "pending", "lessons"])
@pytest.mark.parametrize("order", ["global_first", "subcommand_last"])
def test_json_output_both_orders(command: str, order: str):
    """[review P1-20] -j 前置/后置都必须得到纯 JSON。"""
    argv = ["-j", command] if order == "global_first" else [command, "-j"]
    result = _run_calibration(*argv)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)  # 纯 JSON，无任何文本前缀
    assert isinstance(payload, dict)


def test_global_first_report_matches_subcommand_last():
    """[review P1-20] 两种顺序输出内容一致（回归原始 bug 的直接断言）。"""
    a = _run_calibration("-j", "report")
    b = _run_calibration("report", "-j")
    assert a.returncode == b.returncode == 0
    assert json.loads(a.stdout) == json.loads(b.stdout)


def test_plain_report_remains_text():
    """[review P1-20] 不带 -j 时保持人类可读 Markdown（向后兼容）。"""
    result = _run_calibration("report")
    assert result.returncode == 0, result.stderr
    assert "校准报告" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)

"""refresh_pool.py CLI 参数注册的回归测试。

不变量：main() 消费的每个 args.<attr> 都必须在 parser 上注册，
--full-market / --default 两条不联网路径可完整执行（mock 业务层）。

回归背景（2026-11-02 skill 审查 P1）：6e399c3（v1.22.1）把本地
argparse 换成 create_parser 时误删了 main() 仍消费的 6 个参数注册，
任何调用直接 `AttributeError: 'Namespace' object has no attribute
'full_market'`，自 v1.22.1 起该 CLI 完全不可用且无测试守护。
"""

from __future__ import annotations

import json

import refresh_pool


def test_help_registers_all_consumed_flags(capsys):
    """--help 输出必须覆盖 main() 消费的全部自定义参数。"""
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        [sys.executable, "scripts/refresh_pool.py", "--help"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=30,
    )
    assert r.returncode == 0
    for flag in (
        "--top",
        "--sort",
        "--dry-run",
        "--diff",
        "--default",
        "--full-market",
        "--sector",
    ):
        assert flag in r.stdout, f"--help 缺少 {flag}"


def test_main_full_market_mode_runs(monkeypatch, capsys):
    """--full-market 路径完整执行（回归点：args.full_market 曾不存在）。"""
    monkeypatch.setattr(refresh_pool, "fetch_all_market_stocks", lambda: ["a", "b"])
    monkeypatch.setattr(refresh_pool, "save_all_market_stocks", lambda ret: None)
    monkeypatch.setattr("sys.argv", ["refresh_pool.py", "--full-market", "-j"])

    refresh_pool.main()

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "ok"
    assert payload["mode"] == "full_market"
    assert payload["count"] == 2


def test_main_default_mode_runs(monkeypatch, capsys):
    """--default 路径完整执行（回归点：args.default 曾不存在）。"""
    monkeypatch.setattr(refresh_pool, "init_from_default", lambda top_n=20, dry_run=False: {"stub": True})
    monkeypatch.setattr("sys.argv", ["refresh_pool.py", "--default", "-j"])

    refresh_pool.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["mode"] == "default"

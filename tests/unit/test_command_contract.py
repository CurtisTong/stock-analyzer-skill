"""命令契约 commands.json 完整性测试（v1.24.0 复审修复）。

背景：v1.24.0 的 commands.json 只列前 5 个 flag、无 type/default，
且 thin-wrapper 命令（backtest）flags 为空——LLM 拿到的是残缺契约。
同时该产物不受任何 CI 校验，可无限期腐化。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACTS = PKG_ROOT / "skills" / "_shared" / "references" / "commands.json"


@pytest.fixture(scope="module")
def contract():
    return json.loads(CONTRACTS.read_text(encoding="utf-8"))


class TestContractCompleteness:
    def test_all_commands_have_params(self, contract):
        """每个 CLI 命令都要有参数契约（不能是空壳）。"""
        empty = [c["name"] for c in contract["commands"] if c.get("cli") and not c.get("params")]
        assert not empty, f"以下 CLI 命令参数为空: {empty}"

    def test_library_modules_marked_not_cli(self, contract):
        """纯库模块必须标注 cli=false（否则 LLM 会误以为"无参数=不接受输入"）。"""
        by_name = {c["name"]: c for c in contract["commands"]}
        for name in ("chan", "classifier", "portfolio_web", "sector_momentum"):
            assert by_name[name]["cli"] is False, name
        assert by_name["screener"]["cli"] is True

    def test_flags_not_truncated(self, contract):
        """flags 不得被截断到 5 个（v1.24.0 只列前 5 个）。"""
        by_name = {c["name"]: c for c in contract["commands"]}
        screener = by_name["screener"]
        assert len(screener["flags"]) > 5
        assert len(screener["params"]) > 5

    def test_thin_wrapper_has_params(self, contract):
        """thin-wrapper 命令（backtest）必须带上子包 parser 的参数。"""
        by_name = {c["name"]: c for c in contract["commands"]}
        backtest = by_name["backtest"]
        assert len(backtest["flags"]) > 5
        assert "--strategy" in backtest["flags"]

    def test_common_params_included(self, contract):
        """使用 create_parser 的命令必须带公共参数 -j/--json。"""
        by_name = {c["name"]: c for c in contract["commands"]}
        assert "--json" in by_name["quote"]["flags"]

    def test_params_carry_type_and_default(self, contract):
        """参数契约要带 type/default，否则 LLM 仍需猜参数。"""
        by_name = {c["name"]: c for c in contract["commands"]}
        screener_params = {p["flags"][0]: p for p in by_name["screener"]["params"]}
        top = screener_params.get("--top")
        assert top is not None
        assert "default" in top
        assert "type" in top


class TestContractGuard:
    """CI 守卫：契约与源码不一致时必须失败。"""

    def _run_check(self):
        return subprocess.run(
            [sys.executable, "scripts/dev/gen_script_catalog.py", "--check-json"],
            cwd=PKG_ROOT,
            capture_output=True,
            text=True,
        )

    def test_check_passes_on_clean_tree(self):
        r = self._run_check()
        assert r.returncode == 0, r.stdout + r.stderr

    def test_check_detects_drift(self, tmp_path):
        """篡改契约后 --check-json 必须失败（证明守卫有效）。"""
        original = CONTRACTS.read_text(encoding="utf-8")
        try:
            data = json.loads(original)
            data["commands"][0]["flags"] = ["--bogus"]
            CONTRACTS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            r = self._run_check()
            assert r.returncode == 1
            assert "不一致" in (r.stdout + r.stderr)
        finally:
            CONTRACTS.write_text(original, encoding="utf-8")

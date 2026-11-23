"""CI 门禁回归测试（修复 review 报告 P1-28~31 / P2 假绿项）。

这些测试直接读取 CI 配置与门禁脚本，防止“覆盖率命令吞退出码”“Release
不校验测试”“版本检查忽略 missing”“契约 CLI 无 schema 也通过”等假绿回归。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_coverage_steps_do_not_pipe_to_tail():
    """覆盖率门禁不得用 `| tail` 吞掉 pytest 退出码（默认 bash -e 无 pipefail）。"""
    ci = _read(".github/workflows/ci.yml")
    coverage_lines = [line for line in ci.splitlines() if "pytest --cov=" in line or "--cov-report=term" in line]
    assert coverage_lines, "未找到覆盖率门禁步骤"
    for line in coverage_lines:
        assert "| tail" not in line, f"覆盖率命令被 tail 吞退出码: {line}"


def test_release_gate_requires_test_and_publish():
    """创建 Release 前必须确认 test 与 publish 全部成功。"""
    release = _read(".github/workflows/release.yml")
    block = release.split("  github-release:")[1]
    assert "needs: [validate, test, publish]" in block
    condition = block.split("if: >-")[1].split("runs-on:")[0]
    assert "needs.test.result == 'success'" in condition
    assert "needs.publish.result == 'success'" in condition


def test_setup_test_installs_jsonschema():
    """契约 schema 校验依赖 jsonschema，setup-test 必须安装。"""
    action = _read(".github/actions/setup-test/action.yml")
    assert "jsonschema" in action


def test_coverage_config_does_not_omit_active_technical_modules():
    """活跃引用的 technical/sentiment.py 与 report.py 不得被覆盖率配置 omit。"""
    cov = _read(".coveragerc")
    assert "scripts/technical/sentiment.py" not in cov
    assert "scripts/technical/report.py" not in cov


def test_validate_contracts_fails_when_no_schema():
    """schema 被删光时 validate_contracts.py 必须返回非 0，而不是假绿。"""
    spec = importlib.util.spec_from_file_location(
        "validate_contracts", REPO_ROOT / "scripts" / "dev" / "validate_contracts.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mod.CONTRACTS_DIR = Path(tmp)
        assert mod.main() == 1


def test_smoke_test_assertions_do_not_force_zero_exit():
    """冒烟测试不得用 `$(cmd || true)` 后判 $?，该判断恒为真。"""
    smoke = _read("tests/smoke_test.sh")
    for name in ("snapshots.py list", "hot_rank.py --top 5"):
        for line in smoke.splitlines():
            if name in line and "output=$(" in line:
                assert "|| true" not in line, f"{name} 的退出码被 || true 吞掉"


def test_skill_metadata_contract_requires_version_field():
    """版本契约必须先断言 version 存在，防止删字段绕过。"""
    test = _read("tests/contracts/test_skill_metadata_sync.py")
    assert 'assert "version" in fm' in test


def test_nightly_network_collects_junit_to_detect_skips():
    """nightly 必须输出 junit xml 才能统计 skip，避免全 skip 伪装成成功。"""
    nightly = _read(".github/workflows/nightly-network.yml")
    assert "--junitxml=" in nightly
    assert "SKIPPED" in nightly


def test_sync_version_check_script_is_importable():
    """sync_version.py 的 --check 仍可执行（missing 现在也视为失败）。"""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "dev" / "sync_version.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr

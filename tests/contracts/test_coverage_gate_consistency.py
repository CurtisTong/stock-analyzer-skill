"""覆盖率门禁一致性（防止三重口径再次漂移）。

历史问题（2026-11-18 审计）：CI 传 `--cov-fail-under=21`、`.coveragerc` 写 30、
`tests/FRAMEWORK.md` 写 30，实测 50.3%——门禁比真实覆盖低 29 个点，大面积无测试
的新代码照样过。

本文件锁死"一个真相"：`.coveragerc` 的 fail_under 必须等于 ci/release 的
fail-under 调用值，且 `test-suite.yml` 默认值一致；核心目录则用
`.coveragerc-core`，ci 步骤必须真的引用它。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _coveragerc_fail_under(rel: str) -> int:
    m = re.search(r"^fail_under\s*=\s*(\d+)", _read(rel), re.M)
    assert m, f"{rel} 缺少 fail_under"
    return int(m.group(1))


def _workflow_fail_under(rel: str) -> list[int]:
    return [int(x) for x in re.findall(r"^\s*fail-under:\s*(\d+)", _read(rel), re.M)]


def _test_suite_default() -> int:
    m = re.search(r'fail-under:.*?default:\s*"(\d+)"', _read(".github/workflows/test-suite.yml"), re.S)
    assert m, "test-suite.yml 缺少 fail-under 默认值"
    return int(m.group(1))


class TestCoverageGateSingleSource:
    def test_coveragerc_matches_callers(self):
        gate = _coveragerc_fail_under(".coveragerc")
        assert gate == 48, f".coveragerc 门槛变了（{gate}）：改阈值必须同时改调用方与本用例"
        for wf in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
            values = _workflow_fail_under(wf)
            assert values, f"{wf} 没有 fail-under 调用值"
            assert set(values) == {gate}, f"{wf} 的 fail-under {values} 与 .coveragerc {gate} 不一致"

    def test_test_suite_default_matches(self):
        assert _test_suite_default() == _coveragerc_fail_under(".coveragerc")

    def test_core_gate_is_enforced(self):
        """核心目录阈值必须 >0 且 ci 步骤真的引用 .coveragerc-core。"""
        core = _coveragerc_fail_under(".coveragerc-core")
        assert core == 57, f"核心目录门槛变了（{core}）：改阈值必须同时改 ci 步骤注释与本用例"
        ci = _read(".github/workflows/ci.yml")
        assert "COVERAGE_RCFILE: .coveragerc-core" in ci, "核心目录步骤没有引用 .coveragerc-core，阈值不会生效"

    def test_docs_quote_same_number(self):
        doc = _read("tests/FRAMEWORK.md")
        gate = _coveragerc_fail_under(".coveragerc")
        assert f"--cov-fail-under={gate}" in doc
        assert f"fail_under={gate}" in doc

    def test_gate_is_not_below_measured_coverage(self):
        """门槛必须留出缓冲但不能低到失去意义：真实覆盖前两位应高于门槛。"""
        gate = _coveragerc_fail_under(".coveragerc")
        measured = 50.96  # 2026-11-19 实测 tests/unit 全仓
        assert measured - gate <= 5, "门槛比实测低太多，起不到防退化作用"
        assert gate <= measured, "门槛高于实测，CI 会直接红"

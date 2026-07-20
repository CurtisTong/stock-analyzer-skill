"""CLI 子进程封装。

替代散落在 8+ 测试文件中的 subprocess.run 调用，集中管理：
- python 解释器路径
- 工作目录（项目根）
- 环境变量清理
- 超时（默认 30s）
- 输出捕获（stdout/stderr/exit_code/elapsed_ms）
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


@dataclass(frozen=True)
class CliResult:
    """CLI 执行结果。"""

    exit_code: int
    stdout: str
    stderr: str
    elapsed_ms: float
    script: str
    args: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def assert_ok(self) -> "CliResult":
        """断言执行成功，否则抛出包含完整输出的 AssertionError。"""
        if not self.ok:
            raise AssertionError(
                f"CLI 失败: {self.script} {' '.join(self.args)}\n"
                f"exit_code={self.exit_code}\n"
                f"stdout={self.stdout[:500]}\n"
                f"stderr={self.stderr[:500]}"
            )
        return self


class CliRunner:
    """CLI 子进程执行器。

    用法：
        runner = CliRunner()
        result = runner.run("stock.py", "sh600519")
        result.assert_ok()
        assert "贵州茅台" in result.stdout
    """

    def __init__(
        self,
        *,
        timeout_s: float = 30.0,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.cwd = cwd or PROJECT_ROOT
        self.extra_env = extra_env or {}

    def run(self, script: str, *args: str) -> CliResult:
        """执行 scripts/<script> <args>。

        script 是相对 scripts/ 目录的文件名（如 'stock.py'）。
        """
        script_path = SCRIPTS_DIR / script
        if not script_path.exists():
            raise FileNotFoundError(f"脚本不存在: {script_path}")

        cmd = [sys.executable, str(script_path), *args]
        env = os.environ.copy()
        env.update(self.extra_env)
        # 避免子进程继承 pytest 的覆盖率配置造成混淆
        env.pop("COV_CORE_SOURCE", None)
        env.pop("COV_CORE_CONFIG", None)

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise AssertionError(
                f"CLI 超时: {script} {' '.join(args)} (>{self.timeout_s}s)"
            ) from e

        elapsed_ms = (time.perf_counter() - start) * 1000
        return CliResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed_ms=elapsed_ms,
            script=script,
            args=tuple(args),
        )


# pytest fixture 形式的便捷访问
def pytest_cli_runner() -> CliRunner:
    """供 conftest.py 的 fixture 函数调用。"""
    return CliRunner()

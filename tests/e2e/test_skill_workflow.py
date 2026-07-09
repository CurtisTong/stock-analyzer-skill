"""P1-27: skill 工作流入口端到端测试骨架。

验证 13 个 skill 引用的核心脚本入口可执行（--help 退出码 0）。
不跑真实网络命令，仅确认 argparse 已正确装配、脚本可被 Python 导入执行。
后续可逐步扩展为完整工作流测试（mock 数据源 → 验证输出结构）。
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# skill → 主入口脚本映射（13 skill 共用 15 个脚本，去重后参数化）
SKILL_ENTRY_SCRIPTS = [
    "announcements.py",
    "backtest.py",
    "calibration.py",
    "calibration_backfill.py",
    "events.py",
    "finance.py",
    "init_pool.py",
    "kline.py",
    "monitor.py",
    "portfolio_web.py",
    "quote.py",
    "refresh_pool.py",
    "screener.py",
    "stock.py",
    "technical.py",
]


@pytest.mark.parametrize("script", SKILL_ENTRY_SCRIPTS)
def test_script_help_exit_zero(script):
    """每个 skill 引用的脚本 --help 应退出码 0（argparse 装配正确）。"""
    script_path = PROJECT_ROOT / "scripts" / script
    assert script_path.exists(), f"脚本不存在: {script_path}"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        f"{script} --help 退出码 {result.returncode}\n"
        f"stderr: {result.stderr.decode()[:500]}"
    )
    # --help 输出应包含 usage 字样
    stdout = result.stdout.decode()
    assert "usage:" in stdout, f"{script} --help 未输出 usage 行"


def test_skill_count_matches():
    """确认 skill 目录数量 = 13（不含 _shared）。"""
    skills_dir = PROJECT_ROOT / "skills"
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir() and d.name != "_shared"]
    assert len(skill_dirs) == 13, f"期望 13 个 skill，实际 {len(skill_dirs)}: {[d.name for d in skill_dirs]}"

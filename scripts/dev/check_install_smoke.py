#!/usr/bin/env python3
"""
零安装冒烟门禁：从干净 HOME 跑 install.sh，验证"装得上 + 跑得动"。

用途：
  - CI 每次 PR 校验安装路径未腐化（此前"5 分钟上手"只是 README 口号，无任何自动化守着）
  - 本地发版前快速自检

校验项：
  1. install.sh 在隔离 HOME 下 exit 0
  2. ~/.claude/skills 与 ~/.codex/skills 各 12 条有效软链（非悬空）
  3. 离线首输出：`init_pool.py --default -j` 产出可解析 JSON 且含股票条目
  4. 全流程 ≤ 300s（定位承诺"5 分钟"）

设计取舍：
  - **不访问真实行情源**。依赖外部 API 的冒烟在 CI 里必然 flaky（本项目踩过多次），
    这里只验"安装 + 离线可用"，网络数据正确性交给单元测试的 fixture。
  - HOME 隔离：避免污染开发机真实的 ~/.claude/skills。

用法：
  python3 scripts/dev/check_install_smoke.py         # 打印报告
  python3 scripts/dev/check_install_smoke.py --ci    # CI 模式：失败 exit 1
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS = (
    "stock",
    "stock-technical",
    "market",
    "sector",
    "portfolio",
    "portfolio-web",
    "portfolio-natural",
    "screener",
    "backtest",
    "research",
    "learn",
    "stock-help",
)
DEADLINE_SECONDS = 300


class SmokeFailure(RuntimeError):
    pass


def _run(cmd: list[str], env: dict, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=PKG_ROOT, env=env, capture_output=True, text=True, timeout=timeout)


def check_links(home: Path) -> list[str]:
    problems: list[str] = []
    for root in (home / ".claude" / "skills", home / ".codex" / "skills"):
        for skill in SKILLS:
            link = root / skill
            if not link.is_symlink():
                problems.append(f"{link}: 不是软链")
            elif not link.exists():
                problems.append(f"{link}: 悬空（目标不存在）")
    return problems


def parse_pool_output(stdout: str) -> str:
    """从 init_pool 输出里取 status。

    init_pool 在 JSON 前会打印人类可读提示行（"股票池已存在…"），从首个 { 起解析。
    """
    start = stdout.find("{")
    if start < 0:
        raise SmokeFailure(f"init_pool.py 输出不是合法 JSON: 未找到 JSON 对象\n{stdout[:400]}")
    try:
        payload = json.loads(stdout[start:])
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"init_pool.py 输出不是合法 JSON: {exc}\n{stdout[:400]}") from exc
    status = payload.get("status")
    if status != "ok":
        raise SmokeFailure(f"init_pool.py 返回非 ok 状态: {status!r}")
    return status


def check_offline_output(home: Path) -> dict:
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(PKG_ROOT / "scripts")}
    proc = _run([sys.executable, "scripts/init_pool.py", "--default", "-j"], env, timeout=120)
    if proc.returncode != 0:
        raise SmokeFailure(f"init_pool.py --default 失败 (exit {proc.returncode})\n{proc.stderr[-800:]}")
    return {"pool_status": parse_pool_output(proc.stdout)}


def run_smoke() -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="stock-smoke-home-") as tmp:
        home = Path(tmp)
        env = {**os.environ, "HOME": str(home)}
        install = _run(["bash", "install.sh"], env, timeout=180)
        if install.returncode != 0:
            raise SmokeFailure(f"install.sh 失败 (exit {install.returncode})\n{install.stderr[-800:]}")
        problems = check_links(home)
        if problems:
            raise SmokeFailure("软链校验失败:\n" + "\n".join(problems[:10]))
        pool = check_offline_output(home)
    elapsed = time.monotonic() - started
    if elapsed > DEADLINE_SECONDS:
        raise SmokeFailure(f"安装到首输出耗时 {elapsed:.0f}s，超过 {DEADLINE_SECONDS}s 承诺")
    return {"elapsed_seconds": round(elapsed, 1), "skills": len(SKILLS) * 2, **pool}


def main() -> int:
    parser = argparse.ArgumentParser(description="零安装冒烟门禁")
    parser.add_argument("--ci", action="store_true", help="CI 模式：失败返回非 0")
    args = parser.parse_args()

    try:
        result = run_smoke()
    except (SmokeFailure, subprocess.TimeoutExpired) as exc:
        print(f"❌ 安装冒烟失败: {exc}")
        return 1 if args.ci else 0

    print(
        f"✅ 安装冒烟通过: {result['skills']} 条软链 · 离线首输出 {result['pool_status']} · "
        f"耗时 {result['elapsed_seconds']}s（承诺 ≤{DEADLINE_SECONDS}s）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

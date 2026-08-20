#!/usr/bin/env python3
"""CI ↔ pre-commit mypy 白名单同步校验工具。

docs/next-tasks.md 任务 D：ci.yml 与 .pre-commit-config.yaml 中 3 条 mypy 白名单
命令（scripts 目录层 / CLI 层 / experts 层）重复维护易漂移。
本工具解析两份文件，抽取每条 mypy 命令的 目标路径列表，逐条比对：
  - --check：仅检查。不一致时打印差异并 exit 1（CI/pre-commit 门禁用）。
  - 默认：同样只做检查（该工具无需写回——漂移时需手动补齐命令）。

对应关系（按 step/hook 名称匹配）：
  ci.yml step "mypy 类型检查"        ↔ pre-commit hook "mypy-allowlist"
  ci.yml step "mypy CLI 层类型检查"  ↔ pre-commit hook "mypy-cli-layer"
  ci.yml step "mypy experts 层类型检查" ↔ pre-commit hook "mypy-experts-layer"

用法：
  python3 scripts/dev/sync_ci_precommit.py --check
"""

import re
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent.parent

CI_FILE = PKG_ROOT / ".github" / "workflows" / "ci.yml"
PRE_COMMIT_FILE = PKG_ROOT / ".pre-commit-config.yaml"

# 目标路径形如 scripts/... 或 experts/（裸目录也可，如 experts/）
_RE_PATH = re.compile(r"^(scripts/|experts/)\S*$")

# ci.yml step name → pre-commit hook id 对应表
STEP_TO_HOOK = {
    "mypy 类型检查": "mypy-allowlist",
    "mypy CLI 层类型检查": "mypy-cli-layer",
    "mypy experts 层类型检查": "mypy-experts-layer",
}

try:
    import yaml  # PyYAML 为配置加载必需运行时依赖
except ImportError:  # pragma: no cover
    yaml = None


def _extract_paths(text: str) -> list[str]:
    """从命令文本中抽取所有形如 scripts/xxx 或 experts/ 的目标路径（保序）。

    需清洗两类噪声：
      - 注释行（ci.yml run 里以 # 开头的说明，会含 scripts/data/ 字样而误匹配）
      - entry 引号包裹（pre-commit `bash -c '... experts/'` 尾部 `'`）
    """
    paths = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for t in re.split(r"\s+", stripped):
            t = t.strip("'\"")
            t = t.rstrip("，。；：")
            if _RE_PATH.match(t):
                paths.append(t)
    return paths


def load_ci_mypy_steps() -> dict[str, list[str]]:
    """解析 ci.yml 中 3 个 mypy step → 其目标路径列表。"""
    assert yaml is not None, "需要 PyYAML"
    data = yaml.safe_load(CI_FILE.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = {}
    for job in data.get("jobs", {}).values():
        for step in job.get("steps", []):
            name = step.get("name")
            if name in STEP_TO_HOOK:
                result[name] = _extract_paths(step.get("run", ""))
    return result


def load_precommit_hooks() -> dict[str, list[str]]:
    """解析 .pre-commit-config.yaml 中 3 个 mypy hook → 其 entry 目标路径列表。"""
    assert yaml is not None, "需要 PyYAML"
    data = yaml.safe_load(PRE_COMMIT_FILE.read_text(encoding="utf-8"))
    hooks_by_id = {
        repo.get("hooks", [])[i].get("id"): repo["hooks"][i]
        for repo in data.get("repos", [])
        for i in range(len(repo.get("hooks", [])))
    }
    result: dict[str, list[str]] = {}
    for step_name, hook_id in STEP_TO_HOOK.items():
        hook = hooks_by_id.get(hook_id)
        if hook is not None:
            result[step_name] = _extract_paths(hook.get("entry", ""))
    return result


def check() -> int:
    """比对 3 条 mypy 命令目标路径一致性。返回 0 一致 / 1 不一致。"""
    ci_steps = load_ci_mypy_steps()
    pre_hooks = load_precommit_hooks()

    if not ci_steps:
        print("✗ 未在 ci.yml 找到 mypy step（名称不匹配？）", file=sys.stderr)
        return 1
    if not pre_hooks:
        print("✗ 未在 pre-commit 找到 mypy hook（id 不匹配？）", file=sys.stderr)
        return 1

    errors = []
    for step_name in STEP_TO_HOOK:
        ci_paths = ci_steps.get(step_name)
        pre_paths = pre_hooks.get(step_name)
        if ci_paths is None or pre_paths is None:
            errors.append(
                f"[{step_name}] 缺失: ci={'有' if ci_paths is not None else '无'} "
                f"pre-commit={'有' if pre_paths is not None else '无'}"
            )
            continue
        if ci_paths != pre_paths:
            only_ci = [p for p in ci_paths if p not in pre_paths]
            only_pre = [p for p in pre_paths if p not in ci_paths]
            diffs = []
            if only_ci:
                diffs.append(f"  仅 ci.yml 有: {only_ci}")
            if only_pre:
                diffs.append(f"  仅 pre-commit 有: {only_pre}")
            if not diffs:
                diffs.append(f"  顺序/重复不同: ci={ci_paths} pre={pre_paths}")
            errors.append(f"[{step_name}] 路径不一致:\n" + "\n".join(diffs) + "\n")

    if errors:
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print(
            "\n修复方法: 手动同步 ci.yml 相关 step 与 .pre-commit-config.yaml 对应 hook 的目标路径（docs/next-tasks.md 任务 D）",
            file=sys.stderr,
        )
        return 1

    for step_name in STEP_TO_HOOK:
        n = len(ci_steps[step_name])
        print(f"✓ {step_name} ↔ {STEP_TO_HOOK[step_name]}: {n} 个路径一致")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="仅检查，不修改（默认行为）"
    )
    args = parser.parse_args()

    if args.check:
        return check()
    # 该工具无写回语义，统一走 check 逻辑
    return check()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Lint: 阻止 production 代码新增裸 ``except Exception:``（v1.16.0 治理）。

v1.16.0 D: 新增 ``--strict`` 选项：
- 默认 (advisory)：列出所有无日志调用的吞错点，exit 0；
- ``--strict`` (blocking)：把列表作为 CI 阻断门禁，exit 1。

用法::

    python3 scripts/dev/lint_silent_excepts.py            # advisory
    python3 scripts/dev/lint_silent_excepts.py --strict   # CI blocking
    python3 scripts/dev/lint_silent_excepts.py --strict --dirs scripts/common,scripts/business,scripts/data
                                                          # 分批清零：只对已清零目录阻断
"""

import re
import sys
from pathlib import Path

# 豁免的合理位置（白名单）
LOW_RISK_ALLOWLIST = {
    "scripts/portfolio/_file_utils.py": "atomic write / cleanup rollback",
    "scripts/portfolio/web/app.py": "browser.open fallback (cosmetic)",
    "scripts/portfolio/web/dispatch.py": "code normalize passthrough",
    "scripts/common/version.py": "version detection (cosmetic)",
    "scripts/backtest/cli.py": "visualization failure non-fatal",
    "scripts/macro_indicators.py": "cache freshness fallback",
    "scripts/common/exceptions/silent_fallback.py": "元模块自身",
}


def check_file(path):
    """返回 ([], advisories) 列表。

    violations = 应修的高风险；advisories = 低风险建议但允许通过。
    """
    if not path.suffix == ".py":
        return [], []
    rel = str(path)
    if any(rel.endswith(a) for a in LOW_RISK_ALLOWLIST):
        return [], []
    if rel.endswith("silent_fallback.py"):
        return [], []
    if "/tests/" in rel or rel.startswith("tests/"):
        return [], []
    if "/__pycache__/" in rel or rel.endswith("__pycache__"):
        return [], []

    text = path.read_text(encoding="utf-8")
    advisories = []
    for m in re.finditer(r"^(\s*)except\s+Exception[\s:]", text, re.M):
        line_no = text[: m.start()].count("\n") + 1
        window = text[m.end() : m.end() + 4000]
        has_log = any(
            needle in window
            for needle in (
                "logger.warning(",
                "logger.error(",
                "logger.exception(",
                "log_silent_fallback(",
                "raise ",
                "pass  # ",
            )
        )
        msg = f"{rel}:{line_no} 裸 except Exception 缺日志"
        if has_log:
            continue
        advisories.append((line_no, msg))
    return [], advisories


def _parse_dirs(argv: list[str]) -> list[Path] | None:
    """--dirs a,b,c：只扫这些目录（P0-4c 分批清零用）。

    不给 --dirs 时保持原行为：scripts/ + experts/ 全扫（advisory）。
    """
    for i, arg in enumerate(argv):
        if arg == "--dirs":
            raw = argv[i + 1] if i + 1 < len(argv) else ""
            return [Path(d.strip()) for d in raw.split(",") if d.strip()]
        if arg.startswith("--dirs="):
            return [Path(d.strip()) for d in arg.split("=", 1)[1].split(",") if d.strip()]
    return None


def main():
    strict = "--strict" in sys.argv
    dirs = _parse_dirs(sys.argv)
    sys.argv = [a for a in sys.argv if a != "--strict"]
    if dirs is not None:
        # 去掉 --dirs 及其值，避免 argparse 之外残留
        cleaned: list[str] = []
        skip_next = False
        for arg in sys.argv:
            if skip_next:
                skip_next = False
                continue
            if arg == "--dirs":
                skip_next = True
                continue
            if arg.startswith("--dirs="):
                continue
            cleaned.append(arg)
        sys.argv = cleaned

    all_advisories = []
    if dirs is None:
        roots = [Path("scripts")] + [Path("experts")]
    else:
        missing = [d for d in dirs if not d.exists()]
        if missing:
            print(f"❌ --dirs 目录不存在: {', '.join(str(m) for m in missing)}", file=sys.stderr)
            return 2
        roots = dirs
    for root in roots:
        for p in root.rglob("*.py"):
            _, advisories = check_file(p)
            all_advisories.extend(advisories)

    if all_advisories:
        if strict:
            print(
                f"❌ {len(all_advisories)} 处裸 except Exception（strict 模式阻断）：",
                file=sys.stderr,
            )
            for ln, msg in all_advisories[:30]:
                print(f"  {msg}", file=sys.stderr)
            if len(all_advisories) > 30:
                print(
                    f"  ... 另 {len(all_advisories) - 30} 处省略",
                    file=sys.stderr,
                )
            return 1
        print(f"ℹ️  {len(all_advisories)} 处建议加 log_silent_fallback（advisory，非阻塞）：")
        for ln, msg in all_advisories[:30]:
            print(f"  {msg}")
        if len(all_advisories) > 30:
            print(f"  ... 另 {len(all_advisories) - 30} 处省略")
        print()
        print("说明：v1.16.0 Batch 3 仅就 11 处 HIGH/MEDIUM 风险做了治理；")
        print("      剩余约 100 处为 LOW 风险（atomic write / fallback 兜底等），")
        print("      列为 advisory 但不阻断 CI。后续按需治理。")
        print("      用 --strict 开启阻断模式（CI 推荐先用 advisory）")
        return 0
    print("✅ 全部 except Exception 已合规或豁免")
    return 0


if __name__ == "__main__":
    sys.exit(main())

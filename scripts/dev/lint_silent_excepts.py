#!/usr/bin/env python3
"""Lint: 阻止 production 代码新增裸 ``except Exception:``（v1.16.0 P1-2 治理）。

v1.16.0 D: 新增 ``--strict`` 选项：
- 默认 (advisory)：列出所有无日志调用的吞错点，exit 0；
- ``--strict`` (blocking)：把列表作为 CI 阻断门禁，exit 1。

用法::

    python3 scripts/dev/lint_silent_excepts.py            # advisory
    python3 scripts/dev/lint_silent_excepts.py --strict   # CI blocking
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


def main():
    strict = "--strict" in sys.argv
    sys.argv = [a for a in sys.argv if a != "--strict"]

    root = Path("scripts")
    all_advisories = []
    for p in root.rglob("*.py"):
        _, advisories = check_file(p)
        all_advisories.extend(advisories)
    for p in Path("experts").rglob("*.py"):
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
        print(
            f"ℹ️  {len(all_advisories)} 处建议加 log_silent_fallback（advisory，非阻塞）："
        )
        for ln, msg in all_advisories[:30]:
            print(f"  {msg}")
        if len(all_advisories) > 30:
            print(f"  ... 另 {len(all_advisories) - 30} 处省略")
        print()
        print("说明：v1.16.0 Batch 3 仅就 11 处 HIGH/MEDIUM 风险做了治理；")
        print("      剩余约 100 处为 LOW 风险（atomic write / fallback 兜底等），")
        print("      列为 advisory 但不阻断 CI。后续按需在 Phase 5/6 治理。")
        print("      用 --strict 开启阻断模式（CI 推荐先用 advisory）")
        return 0
    print("✅ 全部 except Exception 已合规或豁免")
    return 0


if __name__ == "__main__":
    sys.exit(main())

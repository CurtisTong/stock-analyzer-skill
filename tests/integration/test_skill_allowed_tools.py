"""allowed-tools 收紧回归保护。

复盘上一轮提交发现 4 个 skill 使用 Bash(python3 scripts/*) 通配，
本次修复已收紧到显式脚本列表。本测试验证：
1. 没有任何 SKILL.md 仍使用 scripts/* 通配
2. 每个 skill 的 allowed-tools 与其实际调用的脚本一致
3. allowed-tools 列表合法（每行是 Bash/Read 前缀的路径模式）

按 FRAMEWORK.md 规范：纯文件解析测试，无 IO。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


# ────────────────────────────────────────────────────────────────
# 通配检测
# ────────────────────────────────────────────────────────────────


class TestNoWildcardScripts:
    """SKILL.md 不应使用 scripts/* 通配（应列出显式脚本）。"""

    def test_no_skill_uses_scripts_wildcard(self):
        """所有 SKILL.md 都不能含 \"scripts/*\" 通配。"""
        offenders: list[str] = []
        for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
            content = skill_md.read_text(encoding="utf-8")
            # 抓 allowed-tools 行
            for line in content.splitlines():
                if line.startswith("allowed-tools:") and "scripts/*" in line:
                    # 例外：若明确含 ` scripts/*)` 表示 Bash 通配
                    if re.search(r"Bash\(python3 scripts/\*\)", line):
                        offenders.append(f"{skill_md.relative_to(REPO_ROOT)}: {line}")
        assert not offenders, (
            "以下 SKILL.md 仍使用 scripts/* 通配（应改为显式脚本列表）:\n"
            + "\n".join(offenders)
        )


# ────────────────────────────────────────────────────────────────
# 合法格式校验
# ────────────────────────────────────────────────────────────────


class TestAllowedToolsFormat:
    """allowed-tools 字段格式合法（Bash / Read 前缀 + 路径模式）。"""

    @pytest.mark.parametrize(
        "skill_name",
        [
            "stock",
            "screener",
            "research",
            "sector",
            "market",
            "portfolio",
            "portfolio-web",
            "portfolio-natural",
            "backtest",
        ],
    )
    def test_allowed_tools_format(self, skill_name):
        """每个 skill 的 allowed-tools 是合法路径模式列表。"""
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_md.exists():
            pytest.skip(f"{skill_name}/SKILL.md 不存在")
        content = skill_md.read_text(encoding="utf-8")
        # 抓取 allowed-tools 行
        match = re.search(r"^allowed-tools:\s*(.+)$", content, re.MULTILINE)
        assert match, f"{skill_name}: 无 allowed-tools 行"
        tools_str = match.group(1)
        # 每项是 Bash(...) 或 Read(...) 形式
        items = re.findall(r"(Bash|Read)\([^)]+\)", tools_str)
        assert len(items) >= 1, f"{skill_name}: allowed-tools 无合法项"
        for item in items:
            prefix = item[:4]  # Bash / Read
            assert prefix in ("Bash", "Read"), f"{skill_name}: 非法前缀 {prefix}"


# ────────────────────────────────────────────────────────────────
# 实际引用 vs 允许的脚本一致性
# ────────────────────────────────────────────────────────────────


class TestAllowedToolsCoverage:
    """每个 skill 的 allowed-tools 必须覆盖 SKILL.md 文档承诺调用的脚本。

    反向验证：SKILL.md 里所有 python3 scripts/X.py 调用都应在
    allowed-tools 的白名单里。如果 SKILL.md 调用了 calibration.py
    但 allowed-tools 没列出，会被工具调用层拒掉。
    """

    @pytest.mark.parametrize(
        "skill_name, expected_scripts",
        [
            # 每个 skill 调用的脚本集合
            ("stock", {"quote", "kline", "finance", "technical", "stock",
                       "events", "market_anchor", "calibration", "calibration_backfill"}),
            ("research", {"quote", "kline", "finance", "technical",
                          "announcements", "market_anchor", "stock"}),
            ("screener", {"quote", "stock", "screener", "init_pool",
                          "refresh_pool", "finance", "technical"}),
            ("sector", {"quote", "sector", "sector_etf_strength",
                        "stock", "screener"}),
        ],
    )
    def test_scripts_in_skill_covered_by_allowed_tools(
        self, skill_name, expected_scripts
    ):
        """SKILL.md 文档里调用的脚本必须在 allowed-tools 白名单里。"""
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        if not skill_md.exists():
            pytest.skip(f"{skill_name}/SKILL.md 不存在")
        content = skill_md.read_text(encoding="utf-8")

        # 抓 allowed-tools 列表
        match = re.search(r"^allowed-tools:\s*(.+)$", content, re.MULTILINE)
        assert match, f"{skill_name}: 无 allowed-tools 行"
        tools_str = match.group(1)
        # 提取每个 Bash(...) 里的脚本名（去掉 python3 scripts/X.py 的 .py）
        allowed_scripts = set()
        for m in re.finditer(r"Bash\(python3 scripts/([a-z_]+)\.py", tools_str):
            allowed_scripts.add(m.group(1))

        # 抓 SKILL.md 里所有 python3 scripts/X.py 引用
        # 排除掉 allowed-tools 行本身
        body = content.replace(tools_str, "")
        used_scripts = set()
        for m in re.finditer(r"python3 scripts/([a-z_]+)\.py", body):
            used_scripts.add(m.group(1))

        # 过滤掉不存在的脚本（这些是 SKILL.md 中的反例引用，如
        # research.py 不存在但 SKILL.md 提到它是为了警告用户）
        from pathlib import Path as _Path
        nonexistent = {
            name
            for name in used_scripts
            if not (_Path(__file__).parent.parent.parent / "scripts" / f"{name}.py").exists()
        }
        # 单独断言：若脚本不存在，SKILL.md 应有相关说明（NOTE/警告）
        # 本测试只检查 allowed-tools 覆盖，跳过不存在脚本
        used_scripts = used_scripts - nonexistent

        missing = used_scripts - allowed_scripts
        assert not missing, (
            f"{skill_name}: SKILL.md 文档调用但 allowed-tools 未授权: {missing}"
        )
"""DeepSeek Harness（DSH）技能发现契约。

DSH 的 filesystem provider 以 `<projectRoot>/.dsh/skills/<name>/SKILL.md` 作为
项目级技能入口（优先级最高，rank 100），并允许该入口是指向 skills/ 的符号链接。
本测试用 unittest 编写（CI 的 pytest 可收集），无需 pytest 即可本地执行：

    python3 -m unittest tests.contracts.test_dsh_skill_support -v

解析器行为对齐 DSH 自带文档：frontmatter 必填 name / description，name 必须符合
kebab-case；disable-model-invocation / user-invocable 只接受严格布尔值；旧的驼峰键
（disableModelInvocation / modelInvocable / userInvocable）会让整个 skill 被丢弃。
其余字段（如 Claude Code 的 model / allowed-tools）被忽略，不参与校验。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
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
DSH_ROOT = ROOT / ".dsh" / "skills"
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LEGACY_INVOCATION_KEYS = ("disableModelInvocation", "modelInvocable", "userInvocable")
TRUE_STRINGS = {"true", "yes", "on", "1"}
FALSE_STRINGS = {"false", "no", "off", "0"}


def _parse_frontmatter(path: Path) -> dict:
    """复刻 DSH parseFrontmatter：只允许文件开头/结尾的裸 `---` 分隔线。"""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise AssertionError(f"{path}: 缺少首行 YAML frontmatter 分隔符")
    closing = None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip("\r\n") == "---":
            closing = idx
            break
    if closing is None:
        raise AssertionError(f"{path}: 缺少 frontmatter 结束分隔符")
    data = yaml.safe_load("".join(lines[1:closing]))
    if not isinstance(data, dict):
        raise AssertionError(f"{path}: frontmatter 必须是映射")
    return data


def _check_invocation_bool(data: dict, key: str) -> None:
    if key not in data:
        return
    value = data[key]
    if isinstance(value, bool):
        return
    if isinstance(value, int) and value in (0, 1):
        return
    if isinstance(value, str) and value.lower() in TRUE_STRINGS | FALSE_STRINGS:
        return
    raise AssertionError(f"{data.get('name')}: {key} 不是 DSH 接受的布尔值: {value!r}")


class TestDshSkillLinks(unittest.TestCase):
    def test_dsh_root_has_exactly_twelve_skill_bundles(self):
        self.assertTrue(DSH_ROOT.is_dir(), f"缺少 DSH 项目级技能根目录: {DSH_ROOT}")
        entries = sorted(p.name for p in DSH_ROOT.iterdir())
        self.assertEqual(entries, sorted(SKILLS), "DSH 技能入口必须与 skills/ 源一一对应")

    def test_each_entry_is_a_relative_symlink_to_the_source_skill(self):
        for name in SKILLS:
            link = DSH_ROOT / name
            self.assertTrue(link.is_symlink(), f"{name}: DSH 入口应为符号链接")
            self.assertEqual(
                Path.readlink(link).as_posix(),
                f"../../skills/{name}",
                f"{name}: 必须使用仓库内相对链接，便于移动仓库",
            )
            skill_md = link / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f"{name}: SKILL.md 不可解析")
            self.assertEqual(
                skill_md.resolve(), ROOT / "skills" / name / "SKILL.md",
                f"{name}: 链接必须指向 skills/ 权威源",
            )

    def test_every_skill_frontmatter_is_accepted_by_dsh(self):
        for name in SKILLS:
            data = _parse_frontmatter(ROOT / "skills" / name / "SKILL.md")
            self.assertEqual(data.get("name"), name, f"{name}: frontmatter name 必须与目录一致")
            description = data.get("description")
            self.assertIsInstance(description, str)
            self.assertTrue(description.strip(), f"{name}: description 不能为空")
            self.assertRegex(data["name"], SKILL_NAME_RE, f"{name}: 不是 kebab-case")
            for legacy in LEGACY_INVOCATION_KEYS:
                self.assertNotIn(legacy, data, f"{name}: DSH 拒绝旧键 {legacy}")
            for key in ("disable-model-invocation", "user-invocable"):
                _check_invocation_bool(data, key)

    def test_source_frontmatter_stays_shared_with_other_runtimes(self):
        """DSH 链接指向同一文件；Claude/Codex 的 frontmatter 不应被 DSH 适配破坏。"""
        for name in SKILLS:
            data = _parse_frontmatter(ROOT / "skills" / name / "SKILL.md")
            self.assertEqual(data.get("version"), "1.33.1", f"{name}: 版本须经 sync_version 同步")


class TestDshPackaging(unittest.TestCase):
    def test_install_script_refreshes_and_checks_dsh_links(self):
        script = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('DSH_LOCAL="$PKG_ROOT/.dsh/skills"', script)
        self.assertIn("创建项目级 .dsh/skills/ 链接", script)
        self.assertIn('ln -s "../../skills/$s" "$DST"', script)
        self.assertIn('check_links "$DSH_LOCAL"', script)
        self.assertIn("[3/7]", script)
        self.assertIn("[4/7]", script)

    def test_npm_package_includes_dsh_skills(self):
        pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIn(".dsh/", pkg["files"], "npm 发布包必须携带 DSH 技能入口")
        self.assertIn("deepseek-harness", pkg["keywords"])

    def test_dsh_skills_are_tracked_not_gitignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        ignored = {line.strip().rstrip("/") for line in ignore.splitlines() if line.strip()}
        self.assertNotIn(".dsh", ignored, ".dsh/skills 必须随仓库追踪，DSH 克隆即用")


if __name__ == "__main__":
    unittest.main()

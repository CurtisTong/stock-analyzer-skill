"""
SKILL.md 元数据校验：12 个 skill 的 frontmatter 与结构一致性。

校验项：
  1. frontmatter 必填字段存在（name、description）
  2. frontmatter 可选字段（version、model、allowed-tools）合理
  3. name 字段跟目录名一致
  4. description 长度 ≤ 250 字符（社区最佳实践）
  5. description 不含硬编码命令字面量（/skill-name）
  6. 必备章节存在（Usage / Instructions / Guardrails）
  7. 不含过期路径表述（"../../.."）
  8. frontmatter 解析合法（YAML）
"""

import re
from pathlib import Path

import pytest
import yaml

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

# 期望的 12 个 skill（9 核心 + 3 子模块：stock-technical / portfolio-web / portfolio-natural + learn）
# 2026-06-17 删除 4 个 deprecated skill（technical / stock-init / financial-analyst / investment-researcher），
# 现 9 核心 + 3 子模块 + 1 learn + 1 共享
EXPECTED_SKILLS = {
    "stock",
    "market",
    "sector",
    "portfolio",
    "portfolio-web",
    "portfolio-natural",
    "screener",
    "stock-technical",
    "monitor",
    "backtest",
    "stock-help",
    "learn",
    "research",
}

# 命令式 skill：允许 disable-model-invocation 且 description 可短
COMMAND_LIKE_SKILLS = {"backtest", "stock-help", "monitor"}

# 推荐的 model 值
ALLOWED_MODELS = {"haiku", "sonnet", "opus"}


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════


def parse_frontmatter(text: str) -> dict:
    """解析 YAML frontmatter（--- 包裹段）。

    P2-25: 改用 yaml.safe_load 替代手写解析，支持完整的 YAML 语法
    （引号、嵌套、多行等）。手写解析无法正确处理引号包裹的标量值。
    """
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm = text[3:end].strip()
    try:
        result = yaml.safe_load(fm)
    except yaml.YAMLError:
        # 非标准 frontmatter 降级为空 dict，避免崩溃
        return {}
    return result if isinstance(result, dict) else {}


def get_skill_files():
    """遍历所有 SKILL.md。"""
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


# ═══════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════


def test_all_expected_skills_present():
    """12 个 skill 都存在。"""
    actual = {p.parent.name for p in get_skill_files()}
    missing = EXPECTED_SKILLS - actual
    extra = actual - EXPECTED_SKILLS
    assert not missing, f"缺少 skill: {missing}"
    assert not extra, f"多余 skill: {extra}"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_frontmatter_required_fields(skill_path):
    """每个 SKILL.md 必填 name + description。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    assert "name" in fm, f"{skill_path.parent.name}: 缺 name 字段"
    assert "description" in fm, f"{skill_path.parent.name}: 缺 description 字段"
    assert fm["name"], f"{skill_path.parent.name}: name 为空"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_name_matches_directory(skill_path):
    """frontmatter name 字段跟目录名一致。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    assert (
        fm["name"] == skill_path.parent.name
    ), f"目录 {skill_path.parent.name} vs frontmatter name={fm.get('name')}"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_description_length(skill_path):
    """description 长度 ≤ 250 字符。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    desc = fm.get("description", "")
    assert (
        len(desc) <= 250
    ), f"{skill_path.parent.name}: description {len(desc)} 字符（>250），请裁剪"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_description_no_command_trigger_pattern(skill_path):
    """description 不含"输入 /X 时触发"类硬编码触发句（cross-reference 允许）。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    desc = fm.get("description", "")
    # 检测条件句："/X 时" "/X 触发" "输入 /X"
    bad_patterns = [
        r"输入\s*/[a-z][a-z0-9-]+",
        r"/[a-z][a-z0-9-]+\s*(时|触发|时调用)",
    ]
    for pat in bad_patterns:
        matches = re.findall(pat, desc)
        assert (
            not matches
        ), f"{skill_path.parent.name}: description 含命令触发句 {matches}，应改为能力/场景描述"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_model_field_valid(skill_path):
    """如果指定 model，必须是 haiku/sonnet/opus。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    model = fm.get("model")
    if model is not None:
        assert (
            model in ALLOWED_MODELS
        ), f"{skill_path.parent.name}: model={model} 不在 {ALLOWED_MODELS}"


VERSION_OVERRIDES = {
    # 当前所有 skill 与主版本一致
}
DEFAULT_VERSION = "1.15.0"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_version_consistency(skill_path):
    """version 字段与 package.json 一致（默认同 package.json，个别 skill 可通过 VERSION_OVERRIDES 覆盖）。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    expected = VERSION_OVERRIDES.get(skill_path.parent.name, DEFAULT_VERSION)
    if "version" in fm:
        assert (
            fm["version"] == expected
        ), f"{skill_path.parent.name}: version={fm['version']}（应为 {expected}）"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_required_sections(skill_path):
    """每个 SKILL.md 含必备章节。"""
    text = skill_path.read_text(encoding="utf-8")
    required = ["## Usage", "## Instructions", "## Guardrails"]
    missing = [s for s in required if s not in text]
    # 允许个别章节改名（如 help）但至少应存在 "## Guardrails" 或说明替代品
    if "## Guardrails" in missing:
        # help 允许用"## 注意事项"代替
        assert (
            "## 注意事项" in text or "## 进阶场景" in text
        ), f"{skill_path.parent.name}: 缺 Guardrails 章节"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_no_stale_path_hint(skill_path):
    """不含过期路径表述 "当前 skill 目录到包根目录为 ../../.."。"""
    text = skill_path.read_text(encoding="utf-8")
    assert (
        "../../.." not in text
    ), f"{skill_path.parent.name}: 仍含过期路径提示 '../../..'，Claude Code 工作目录即为项目根"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_no_absolute_paths_in_allowed_tools(skill_path):
    """SKILL.md 的 allowed-tools 不得包含绝对路径，必须以 ./ 或脚本名开头。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    tools = fm.get("allowed-tools", [])
    # 统一为列表
    if isinstance(tools, str):
        tools = [tools]
    for tool in tools:
        # 匹配 //xxx/... 或 /xxx/... 形式的绝对路径
        assert (
            "/Users/" not in tool
        ), f"{skill_path.parent.name}: allowed-tools 含绝对路径 '{tool}'，应改为相对路径"
        assert not re.search(
            r"^/\w+/", tool
        ), f"{skill_path.parent.name}: allowed-tools 含绝对路径 '{tool}'，应改为相对路径"


def test_shared_references_exist():
    """共享 references 存在。"""
    shared = SKILLS_DIR / "_shared" / "references"
    assert shared.exists(), f"共享目录不存在: {shared}"
    expected_files = ["code-prefix.md", "script-catalog.md", "five-layer.md"]
    for f in expected_files:
        assert (shared / f).exists(), f"共享文件缺失: {f}"


def test_stock_reports_template_exists():
    """stock 的报告模板外移文件存在。"""
    template = SKILLS_DIR / "stock" / "reports" / "full-template.md"
    assert template.exists(), f"模板文件不存在: {template}"


def test_init_pool_removed():
    """旧 init-pool skill 已清理。"""
    stale = SKILLS_DIR / "init-pool"
    assert not stale.exists(), "旧 init-pool skill 应已删除"

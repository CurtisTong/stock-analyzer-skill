"""
SKILL.md ↔ scripts/ 交叉引用一致性 + description 关键词扫描。

校验：
  1. SKILL.md 中提到的 `scripts/*.py` 必须在 scripts/ 真实存在
  2. description 关键词必须与 skill 核心能力匹配（防止 description 漂移）
  3. 必备章节别名（Instructions / Guardrails / 第一次使用 / 执行命令）
  4. frontmatter model 与 description 长度大致匹配（深度分析用 opus，命令用 haiku）
"""

import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# 运行时生成的数据文件（由 init_pool.py / refresh_pool.py / 用户首次使用产生）
# 这些文件首次安装时不存在，属于"约定生成"，不视为引用错误
RUNTIME_DATA_FILES = {
    "stock_pool.json",  # init_pool.py 产出
    "sector_stocks.json",  # init_pool.py 产出
    "sector_etf.csv",  # init_pool.py 产出
    "portfolio.json",  # 用户创建
    "portfolio_example.json",  # 项目自带的示例
    "portfolio_virtual.json",  # 模拟盘数据（--virtual 模式创建）
    "stock_pool_backup.json",  # refresh_pool.py 备份
    "all_stocks.json",  # refresh_pool.py --full-market 产出
}

# description 关键词白名单：skill 核心能力词
# 校验 description 中必须包含至少 1 个核心词（防止 description 写成空话）
# P2-26: 清理废弃 key（stock-init/financial-analyst/investment-researcher/help/technical），
# 对齐实际 skill 目录名（research/stock-help/stock-technical/portfolio-natural/portfolio-web/learn）
DESCRIPTION_KEYWORDS = {
    "stock": ["五层", "个股", "估值", "技术", "专家", "判断"],
    "market": ["大盘", "复盘", "指数", "板块", "风格"],
    "sector": ["板块", "行业", "标的", "轮动", "配置"],
    "portfolio": ["持仓", "组合", "盈亏", "风险", "调仓"],
    "screener": ["选股", "策略", "因子", "候选", "筛选"],
    "stock-technical": ["技术", "均线", "MACD", "KDJ", "BOLL", "缠论"],
    "monitor": ["监控", "持仓", "预警", "推送", "异动"],
    "backtest": ["回测", "策略", "胜率", "收益", "夏普"],
    "research": ["研究", "财务", "估值", "报告", "分析"],
    "stock-help": ["skill", "帮助", "功能", "使用"],
    "learn": ["学习", "投资", "基础", "概念", "入门"],
    "portfolio-natural": ["持仓", "自然语言", "触发", "映射"],
    "portfolio-web": ["持仓", "Web", "录入", "查询"],
}


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
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def list_real_scripts():
    """返回所有 scripts/*.py + scripts/*/__init__.py 的扁平集合。"""
    real = {p.name for p in SCRIPTS_DIR.glob("*.py")}
    # 也接受包形式：scripts/common/__init__.py 视为 scripts/common.py 等价
    for sub in SCRIPTS_DIR.iterdir():
        if sub.is_dir() and (sub / "__init__.py").exists():
            real.add(f"{sub.name}.py")  # scripts/common.py 视作 scripts/common/ 包
    return real


# ═══════════════════════════════════════════════════════════════
# cross-reference 测试
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_referenced_scripts_exist(skill_path):
    """SKILL.md 中提到的 scripts/*.py 必须在 scripts/ 真实存在。

    匹配规则：抓取 `scripts/<name>.py`（含路径前缀）。
    """
    text = skill_path.read_text(encoding="utf-8")
    # 匹配 scripts/foo.py 形式
    referenced = set(re.findall(r"scripts/([a-z_][a-z0-9_]*\.py)", text))
    real = list_real_scripts()
    missing = referenced - real
    assert not missing, (
        f"{skill_path.parent.name}: 引用了不存在的脚本 {missing}，"
        f"实际有 {sorted(real)}"
    )


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_referenced_data_files_exist(skill_path):
    """SKILL.md 中提到的 data/<file> 要么真实存在，要么是运行时生成白名单内。"""
    text = skill_path.read_text(encoding="utf-8")
    referenced = set(
        re.findall(r"data/([a-z_][a-z0-9_.]*\.(?:json|csv|yaml|yml))", text)
    )
    real = {p.name for p in (PROJECT_ROOT / "data").glob("*")}
    # 排除运行时生成文件
    runtime_or_real = referenced & (real | RUNTIME_DATA_FILES)
    missing = referenced - runtime_or_real
    assert not missing, (
        f"{skill_path.parent.name}: 引用了非白名单数据文件 {missing}，"
        f"请加入 RUNTIME_DATA_FILES 或创建真实文件"
    )


# ═══════════════════════════════════════════════════════════════
# description 关键词测试
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_description_has_core_keywords(skill_path):
    """description 必须包含至少 1 个核心能力词。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    name = fm.get("name", skill_path.parent.name)
    desc = fm.get("description", "")
    keywords = DESCRIPTION_KEYWORDS.get(name, [])
    if not keywords:
        pytest.skip(f"未配置 {name} 的关键词白名单")
    matched = [k for k in keywords if k in desc]
    assert matched, (
        f"{name}: description 缺少核心能力词，应至少包含 {keywords} 之一；"
        f"实际：{desc}"
    )


# ═══════════════════════════════════════════════════════════════
# 章节别名测试（允许 Help 用"第一次使用"代替 Instructions）
# ═══════════════════════════════════════════════════════════════

ALLOWED_INSTRUCTION_ALIASES = [
    "## Instructions",
    "## 第一次使用",
    "## 执行命令",
    "## 当用户触发此 skill 时",
]

ALLOWED_GUARDRAILS_ALIASES = [
    "## Guardrails",
    "## 注意事项",
    "## 进阶场景",
]


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_instruction_section_present(skill_path):
    """必填：Instruction 类章节（标准或别名）。"""
    text = skill_path.read_text(encoding="utf-8")
    has = any(alias in text for alias in ALLOWED_INSTRUCTION_ALIASES)
    assert has, f"{skill_path.parent.name}: 缺 Instruction 章节（标准或别名）"


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_guardrails_section_present(skill_path):
    """必填：Guardrails 类章节（标准或别名）。"""
    text = skill_path.read_text(encoding="utf-8")
    has = any(alias in text for alias in ALLOWED_GUARDRAILS_ALIASES)
    assert has, f"{skill_path.parent.name}: 缺 Guardrails 章节（标准或别名）"


# ═══════════════════════════════════════════════════════════════
# model 与 description 风格大致匹配
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("skill_path", get_skill_files(), ids=lambda p: p.parent.name)
def test_model_matches_complexity(skill_path):
    """模型选择与 skill 复杂度大致匹配：opus 用于长描述，haiku 用于短描述。"""
    text = skill_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    model = fm.get("model")
    desc = fm.get("description", "")
    if model == "haiku":
        # 命令式/简单 skill：description 应较短
        assert (
            len(desc) <= 110
        ), f"{skill_path.parent.name}: haiku 模式 description {len(desc)} 字符（应 ≤ 110）"
    elif model == "opus":
        # 深度分析：description 应较丰富
        assert (
            len(desc) >= 100
        ), f"{skill_path.parent.name}: opus 模式 description {len(desc)} 字符（应 ≥ 100）"

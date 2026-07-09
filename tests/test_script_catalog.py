"""script-catalog.md 自动生成与一致性校验（P2-29）。

校验：
1. gen_script_catalog.py 能正常运行
2. 生成的 catalog 与 skills/_shared/references/script-catalog.md 一致
3. scripts/*.py 每个脚本都在 catalog 中（双向一致）
"""

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dev.gen_script_catalog import generate_catalog, list_scripts  # noqa: E402

CATALOG_PATH = PROJECT_ROOT / "skills" / "_shared" / "references" / "script-catalog.md"


def test_generator_produces_nonempty_catalog():
    """生成器应产出非空 catalog。"""
    content = generate_catalog()
    assert len(content) > 100
    assert "| 脚本 | 用途 |" in content


def test_catalog_contains_all_scripts():
    """每个 scripts/*.py 都应出现在 catalog 中（双向一致）。"""
    scripts = list_scripts()
    assert len(scripts) >= 20, f"脚本数量过少: {len(scripts)}"

    content = generate_catalog()
    for s in scripts:
        assert s["path"] in content, f"catalog 缺少脚本: {s['path']}"


def test_catalog_is_up_to_date():
    """CI: catalog 文件应与生成器输出一致。"""
    content = generate_catalog()
    existing = CATALOG_PATH.read_text(encoding="utf-8")
    assert existing.strip() == content.strip(), (
        "script-catalog.md 不是最新，请运行: python3 scripts/dev/gen_script_catalog.py"
    )


def test_scripts_have_docstrings():
    """每个 catalog 脚本应有模块 docstring（用于描述）。"""
    scripts_dir = PROJECT_ROOT / "scripts"
    excluded = {"__init__"}
    no_doc = []
    for py in sorted(scripts_dir.glob("*.py")):
        if py.stem in excluded or py.stem.startswith("_"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            doc = ast.get_docstring(tree)
            if not doc:
                no_doc.append(py.name)
        except SyntaxError:
            no_doc.append(py.name)
    assert not no_doc, f"以下脚本缺少模块 docstring: {no_doc}"

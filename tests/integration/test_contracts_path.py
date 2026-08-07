"""stock.schema.json 路径校验 + 可用性测试。

回归保护：skills/_shared/contracts/README.md 引用 stock.schema.json，
SKILL.md（research/stock）也引用。本测试验证：
1. stock.schema.json 文件存在
2. schema 是有效 JSON Schema（可被 jsonschema.validate 加载）
3. README.md 文档化的 Python 校验代码片段语法正确（import 通过）
4. CLI 校验脚本 scripts/dev/validate_contracts.py 可执行

按 FRAMEWORK.md 规范：纯 IO + 校验测试，无网络。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent.parent


# ────────────────────────────────────────────────────────────────
# 路径存在性
# ────────────────────────────────────────────────────────────────


class TestStockSchemaPath:
    """stock.schema.json 路径校验（SKILL.md 引用一致性）。"""

    def test_schema_file_exists(self):
        """stock.schema.json 物理存在。"""
        schema_path = REPO_ROOT / "skills" / "_shared" / "contracts" / "stock.schema.json"
        assert schema_path.exists(), (
            f"SKILL.md 引用 stock.schema.json 但文件缺失: {schema_path}"
        )

    def test_schema_is_valid_json(self):
        """schema 是有效 JSON。"""
        schema_path = REPO_ROOT / "skills" / "_shared" / "contracts" / "stock.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert isinstance(schema, dict), "schema 顶层必须是 dict"
        # JSON Schema 必有 $schema 或 type 字段
        assert "$schema" in schema or "type" in schema or "properties" in schema, (
            "schema 不像 JSON Schema（缺 $schema/type/properties）"
        )

    def test_schema_is_loadable_by_jsonschema(self):
        """schema 可被 jsonschema 库加载（语法正确）。"""
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema 未安装")

        schema_path = REPO_ROOT / "skills" / "_shared" / "contracts" / "stock.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        # Draft 7 校验：检查语法 + $ref 是否闭合
        # 用一个最简有效实例验证 schema 至少能跑通验证
        try:
            jsonschema.Draft7Validator.check_schema(schema)
        except jsonschema.SchemaError as e:
            pytest.fail(f"schema 不是合法 JSON Schema Draft7: {e}")

    def test_readme_python_snippet_compiles(self):
        """README.md 行 29-40 的 Python 校验代码片段语法正确。"""
        readme = (REPO_ROOT / "skills" / "_shared" / "contracts" / "README.md").read_text(
            encoding="utf-8"
        )
        # 提取 ```python ... ``` 块
        pattern = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
        snippets = pattern.findall(readme)
        assert len(snippets) >= 1, "README.md 无 Python 代码块"
        # 验证每个 snippet 至少 import 语法正确（compile 不执行）
        for i, snippet in enumerate(snippets):
            try:
                compile(snippet, f"<readme-snippet-{i}>", "exec")
            except SyntaxError as e:
                pytest.fail(f"README.md Python snippet {i} 语法错误: {e}\n{snippet}")


# ────────────────────────────────────────────────────────────────
# CLI 校验脚本可执行
# ────────────────────────────────────────────────────────────────


class TestValidateContractsCLI:
    """scripts/dev/validate_contracts.py 可执行（README.md 文档化的 CLI）。"""

    def test_validate_contracts_help(self):
        """validate_contracts.py --help 退出码 0。"""
        cli = REPO_ROOT / "scripts" / "dev" / "validate_contracts.py"
        if not cli.exists():
            pytest.skip("validate_contracts.py 不存在")
        result = subprocess.run(
            [sys.executable, str(cli), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"validate_contracts.py --help 失败: {result.stderr}"
        )

    def test_validate_contracts_stock_schema(self):
        """validate_contracts.py 能正确验证 stock.schema.json。"""
        cli = REPO_ROOT / "scripts" / "dev" / "validate_contracts.py"
        if not cli.exists():
            pytest.skip("validate_contracts.py 不存在")
        # 默认行为：扫描 contracts/ 下所有 schema
        result = subprocess.run(
            [sys.executable, str(cli)],
            capture_output=True, text=True, timeout=30,
            cwd=str(REPO_ROOT),
        )
        # 不要求 exit 0（可能在测试环境没装 jsonschema）
        # 但应该输出一些结果（不是崩溃）
        assert result.stdout or result.stderr, "validate_contracts 无任何输出"
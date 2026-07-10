"""测试 scripts/dev/validate_contracts.py：JSON Schema 契约校验工具。

策略：使用 tmp_path 构造测试用 contracts 目录，覆盖：
- collect_schemas：加载 *.schema.json
- _find_refs：递归查找 $ref
- check_references：$ref 闭合性检查
- check_top_level_keys：必备顶层字段检查
- main：CLI 入口（含失败/通过/警告三种分支）
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dev import validate_contracts

CONTRACTS_DIR = validate_contracts.CONTRACTS_DIR


# ═══════════════════════════════════════════════════════════════
# collect_schemas：加载所有 schema 文件
# ═══════════════════════════════════════════════════════════════


class TestCollectSchemas:
    def test_loads_real_schemas(self):
        """从真实 contracts 目录加载所有 schema（已有 stock/technical/market 等）。"""
        schemas = validate_contracts.collect_schemas(CONTRACTS_DIR)
        assert len(schemas) > 0
        assert "stock.schema.json" in schemas or any(
            "stock" in k for k in schemas.keys()
        )

    def test_empty_dir_returns_empty(self, tmp_path):
        """空目录返回空 dict。"""
        schemas = validate_contracts.collect_schemas(tmp_path)
        assert schemas == {}

    def test_skips_non_schema_files(self, tmp_path):
        """非 *.schema.json 文件应被跳过。"""
        (tmp_path / "stock.schema.json").write_text('{"type":"object"}')
        (tmp_path / "readme.md").write_text("# hello")
        schemas = validate_contracts.collect_schemas(tmp_path)
        assert "stock.schema.json" in schemas
        assert "readme.md" not in schemas


# ═══════════════════════════════════════════════════════════════
# _find_refs：递归查找 $ref
# ═══════════════════════════════════════════════════════════════


class TestFindRefs:
    def test_top_level_ref(self):
        """顶层 $ref 直接返回。"""
        obj = {"$ref": "./stock.schema.json"}
        assert validate_contracts._find_refs(obj) == ["./stock.schema.json"]

    def test_nested_ref_in_dict(self):
        """嵌套 dict 中的 $ref 应被找到。"""
        obj = {"properties": {"technical": {"$ref": "./technical.schema.json"}}}
        assert validate_contracts._find_refs(obj) == ["./technical.schema.json"]

    def test_refs_in_list(self):
        """list 中的 $ref 应被找到。"""
        obj = {"items": [{"$ref": "a.schema.json"}, {"$ref": "b.schema.json"}]}
        refs = validate_contracts._find_refs(obj)
        assert "a.schema.json" in refs
        assert "b.schema.json" in refs

    def test_no_refs_returns_empty(self):
        """无 $ref 时返回空列表。"""
        assert validate_contracts._find_refs({"type": "object"}) == []
        assert validate_contracts._find_refs(["a", "b"]) == []

    def test_deeply_nested(self):
        """深嵌套中的 $ref 应被找到。"""
        obj = {"a": {"b": {"c": {"$ref": "./deep.schema.json"}}}}
        assert validate_contracts._find_refs(obj) == ["./deep.schema.json"]


# ═══════════════════════════════════════════════════════════════
# check_references：$ref 闭合性
# ═══════════════════════════════════════════════════════════════


class TestCheckReferences:
    def test_closed_refs_pass(self, tmp_path):
        """$ref 指向已存在的 schema 时无 issue。"""
        schemas = {
            "stock.schema.json": {"$ref": "./technical.schema.json"},
            "technical.schema.json": {"type": "object"},
        }
        issues = validate_contracts.check_references(schemas, strict=False)
        assert issues == []

    def test_broken_ref_reported(self, tmp_path):
        """$ref 指向不存在的 schema 时应产生 issue。"""
        schemas = {
            "stock.schema.json": {"$ref": "./missing.schema.json"},
        }
        issues = validate_contracts.check_references(schemas, strict=False)
        assert len(issues) == 1
        assert "不存在" in issues[0]

    def test_external_relative_refs_resolved(self):
        """形如 './stock.schema.json' 和 'stock.schema.json' 都能解析。"""
        schemas = {
            "a.schema.json": {"$ref": "./b.schema.json"},
            "b.schema.json": {"type": "object"},
            "c.schema.json": {"$ref": "d.schema.json"},  # 无 ./
            "d.schema.json": {"type": "object"},
        }
        issues = validate_contracts.check_references(schemas, strict=False)
        assert issues == []


# ═══════════════════════════════════════════════════════════════
# check_top_level_keys：必备字段
# ═══════════════════════════════════════════════════════════════


class TestCheckTopLevelKeys:
    def test_complete_schema_passes(self):
        """包含全部必备字段的 schema 无 issue。"""
        schemas = {
            "good.schema.json": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "title": "Good Schema",
            }
        }
        assert validate_contracts.check_top_level_keys(schemas) == []

    def test_missing_schema_field(self):
        """缺 $schema 字段应报告警告。"""
        schemas = {"bad.schema.json": {"type": "object", "title": "Bad"}}
        issues = validate_contracts.check_top_level_keys(schemas)
        assert any("$schema" in i for i in issues)

    def test_missing_type_field(self):
        """缺 type 字段应报告警告。"""
        schemas = {"bad.schema.json": {"$schema": "x", "title": "Bad"}}
        issues = validate_contracts.check_top_level_keys(schemas)
        assert any("type" in i for i in issues)

    def test_missing_title_field(self):
        """缺 title 字段应报告警告。"""
        schemas = {"bad.schema.json": {"$schema": "x", "type": "object"}}
        issues = validate_contracts.check_top_level_keys(schemas)
        assert any("title" in i for i in issues)


# ═══════════════════════════════════════════════════════════════
# _short_name：文件名简化
# ═══════════════════════════════════════════════════════════════


class TestShortName:
    def test_strips_suffix(self):
        """stock.schema.json -> stock"""
        assert validate_contracts._short_name("stock.schema.json") == "stock"

    def test_other_names_unchanged(self):
        """不含 .schema.json 后缀的保持不变。"""
        assert validate_contracts._short_name("stock.json") == "stock.json"


# ═══════════════════════════════════════════════════════════════
# main：CLI 入口（成功/失败/警告）
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_clean_returns_0(self, capsys):
        """所有 schema 合法时 main 返回 0。"""
        with patch.object(validate_contracts, "CONTRACTS_DIR", CONTRACTS_DIR):
            code = validate_contracts.main()
        # 真实 contracts 目录应当无错误
        assert code == 0
        captured = capsys.readouterr()
        # 至少打印 "找到 N 个 schema"
        assert "schema" in captured.out

    def test_missing_dir_returns_1(self, capsys, monkeypatch):
        """contracts 目录不存在时返回 1。"""
        monkeypatch.setattr(validate_contracts, "CONTRACTS_DIR", Path("/nonexistent"))
        code = validate_contracts.main()
        assert code == 1
        captured = capsys.readouterr()
        assert "不存在" in captured.out

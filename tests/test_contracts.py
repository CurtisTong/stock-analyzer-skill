"""
测试 skills/_shared/contracts/ 下的 JSON Schema。

校验所有 schema 合法、引用闭合、核心必备字段存在。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = PROJECT_ROOT / "skills" / "_shared" / "contracts"
VALIDATOR = PROJECT_ROOT / "scripts" / "dev" / "validate_contracts.py"


class TestContractFiles:
    def test_contracts_dir_exists(self):
        """contracts 目录存在。"""
        assert CONTRACTS_DIR.exists(), f"Missing: {CONTRACTS_DIR}"

    def test_required_schemas_exist(self):
        """所有必备 schema 文件存在。"""
        required = [
            "stock.schema.json",
            "market.schema.json",
            "sector.schema.json",
            "portfolio.schema.json",
            "debate.schema.json",
            "technical.schema.json",
        ]
        for name in required:
            assert (CONTRACTS_DIR / name).exists(), f"Missing: {name}"

    def test_readme_exists(self):
        """contracts/README.md 存在。"""
        assert (CONTRACTS_DIR / "README.md").exists()

    def test_all_schemas_are_valid_json(self):
        """所有 *.schema.json 都是合法 JSON。"""
        for f in CONTRACTS_DIR.glob("*.schema.json"):
            data = json.loads(f.read_text())
            assert isinstance(data, dict), f"{f.name} is not a JSON object"
            assert "$schema" in data or "type" in data, f"{f.name} 缺顶层字段"

    def test_all_schemas_have_title(self):
        """所有 schema 应有 title 字段。"""
        for f in CONTRACTS_DIR.glob("*.schema.json"):
            data = json.loads(f.read_text())
            assert "title" in data, f"{f.name} 缺 title"


class TestContractValidator:
    def test_validator_exits_zero(self):
        """validate_contracts.py 退出码为 0。"""
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            capture_output=True,
            text=True,
        )
        assert (
            result.returncode == 0
        ), f"Validator failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

    def test_validator_finds_schemas(self):
        """validator 输出应包含找到的 schema。"""
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            capture_output=True,
            text=True,
        )
        assert "schema" in result.stdout
        # 应至少找到 5 个 schema
        assert result.stdout.count(".schema.json") >= 5


class TestStockSchema:
    """stock.schema.json 专项测试。"""

    @pytest.fixture
    def schema(self):
        return json.loads((CONTRACTS_DIR / "stock.schema.json").read_text())

    def test_required_top_level(self, schema):
        """stock.schema 顶层必备字段。"""
        assert schema["type"] == "object"
        required = set(schema.get("required", []))
        assert "code" in required
        assert "fundamental" in required
        assert "valuation" in required
        assert "position_plan" in required

    def test_direction_enum(self, schema):
        """position_plan.direction 枚举值。"""
        direction = schema["properties"]["position_plan"]["properties"]["direction"]
        assert "enum" in direction
        assert "看多" in direction["enum"]
        assert "看空" in direction["enum"]
        assert "中性" in direction["enum"]


class TestDebateSchema:
    """debate.schema.json 专项测试。"""

    @pytest.fixture
    def schema(self):
        return json.loads((CONTRACTS_DIR / "debate.schema.json").read_text())

    def test_experts_min_max(self, schema):
        """experts 数组应有 4-9 个元素（v2.2.0 起 9 人圆桌）。"""
        experts = schema["properties"]["experts"]
        assert experts.get("minItems") == 4
        assert experts.get("maxItems") == 9

    def test_group_enum(self, schema):
        """expert.group 枚举含 long_term 和 short_term。"""
        group = schema["properties"]["experts"]["items"]["properties"]["group"]
        assert "long_term" in group["enum"]
        assert "short_term" in group["enum"]

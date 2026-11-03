"""
测试 skills/_shared/contracts/ 下的 JSON Schema。

校验所有 schema 合法、引用闭合、核心必备字段存在。
"""

import json
import subprocess
import sys

import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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
        assert result.returncode == 0, f"Validator failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"

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
        """stock.schema 顶层必备字段（v1.31 向现实收：按 stock.py -j 真实输出）。"""
        assert schema["type"] == "object"
        required = set(schema.get("required", []))
        assert {"code", "name", "price", "score", "technical", "finance"} <= required

    def test_no_idealized_fields_required(self, schema):
        """回归护栏：生产端从未输出的理想化字段不得再进 required。

        fundamental.rating / valuation.view / position_plan 曾让 LLM 只能
        编造交付物（2026-11-02 审查 P1），v1.31 起五层语义由消费方从
        finance/score/technical 现有字段推导（见 five-layer.md）。
        """
        required = set(schema.get("required", []))
        assert not {"fundamental", "valuation", "position_plan", "sentiment"} & required

    def test_score_nested_required(self, schema):
        """score 子对象必备评分与评级档。"""
        score = schema["properties"]["score"]
        assert set(score.get("required", [])) == {"score", "grade"}

    def test_backtest_mutual_exclusivity_documented(self, schema):
        """--with-backtest 的成功/失败两个出口都有字段定义。"""
        props = schema["properties"]
        assert "backtest" in props and "backtest_error" in props


class TestDebateSchema:
    """debate.schema.json 专项测试。"""

    @pytest.fixture
    def schema(self):
        return json.loads((CONTRACTS_DIR / "debate.schema.json").read_text())

    def test_experts_min_max(self, schema):
        """experts 数组应有 4-8 个元素（v2.4.0 起 8 人圆桌：5 长线 + 3 短线）。"""
        experts = schema["properties"]["experts"]
        assert experts.get("minItems") == 4
        assert experts.get("maxItems") == 8

    def test_group_enum(self, schema):
        """expert.group 枚举含 long_term 和 short_term。"""
        group = schema["properties"]["experts"]["items"]["properties"]["group"]
        assert "long_term" in group["enum"]
        assert "short_term" in group["enum"]

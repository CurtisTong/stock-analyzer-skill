"""契约 schema 与 CLI 真实输出的一致性测试（v1.31"向现实收"）。

回归背景（2026-11-02 skill 审查 P1）：stock.schema.json 曾要求
fundamental.rating/valuation.view/position_plan 等生产端从未输出的
嵌套字段，technical.schema.json 要求顶层 trend/ma_alignment/support_levels[]
而 CLI 实际输出 {meta, score, features}——LLM 无法从真实输出映射出
合规交付物。v1.31 将两个 schema 按真实输出收拢并互相解耦
（stock.py 的 technical 摘要与 technical.py 的完整报告是两种结构）。

本测试用真实 CLI 输出 fixture（tests/fixtures/*_cli_output.json，
采集命令见各文件头部注释）断言 schema 的 required 键在真实输出中
全部存在——schema 漂移回"理想化字段"会立刻失败。
"""

from __future__ import annotations

import json
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[2] / "skills" / "_shared" / "contracts"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_required_present(schema: dict, instance: dict, label: str) -> None:
    """校验 schema required 键在实例中存在（required 语义的最小实现，
    不依赖未安装的 jsonschema 库）。"""
    for key in schema.get("required", []):
        assert key in instance, f"{label}: schema required 键 {key!r} 不在真实输出中"


class TestStockSchemaMatchesReality:
    def test_required_keys_present_in_real_output(self):
        schema = _load(CONTRACTS / "stock.schema.json")
        real = _load(FIXTURES / "stock_cli_output.json")
        _assert_required_present(schema, real, "stock")

    def test_nested_required_keys_present(self):
        schema = _load(CONTRACTS / "stock.schema.json")
        real = _load(FIXTURES / "stock_cli_output.json")
        # finance 无嵌套 required；score.required = [score, grade]
        _assert_required_present(schema["properties"]["score"], real.get("score", {}), "stock.score")

    def test_technical_summary_shape(self):
        """stock.py 的 technical 是五层摘要（ma/rsi/kdj 等标量），不是 features 字典。"""
        real = _load(FIXTURES / "stock_cli_output.json")
        tech = real["technical"]
        assert "ma" in tech and "rsi" in tech
        assert not isinstance(tech.get("ma"), dict)

    def test_optional_backtest_fields_documented(self):
        """--with-backtest 的两个互斥出口在 schema 中有定义。"""
        schema = _load(CONTRACTS / "stock.schema.json")
        assert "backtest" in schema["properties"]
        assert "backtest_error" in schema["properties"]


class TestTechnicalSchemaMatchesReality:
    def test_required_keys_present_in_real_output(self):
        schema = _load(CONTRACTS / "technical.schema.json")
        real = _load(FIXTURES / "technical_cli_output.json")
        _assert_required_present(schema, real, "technical")

    def test_top_level_is_meta_score_features(self):
        real = _load(FIXTURES / "technical_cli_output.json")
        assert set(real.keys()) >= {"meta", "score", "features"}
        # 旧 schema 的理想化字段不得再出现于顶层
        assert "trend" not in real and "ma_alignment" not in real

    def test_support_resistance_lives_in_features(self):
        """均线排列/支撑阻力在 features 下（旧 schema 曾把它们放到顶层）。"""
        real = _load(FIXTURES / "technical_cli_output.json")
        features = real["features"]
        assert "ma_system" in features
        assert "support_resistance" in features

    def test_no_cross_ref_to_stock_schema(self):
        """解耦：stock.schema 结构层不再 $ref 引用 technical.schema。

        （描述文字中提到 technical.schema.json 文件名属合法说明，
        检查对象是结构层 $ref 而非全文。）"""

        def _find_refs(o):
            refs = []
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("$ref", "\$ref"):
                        refs.append(v)
                    else:
                        refs += _find_refs(v)
            elif isinstance(o, list):
                for item in o:
                    refs += _find_refs(item)
            return refs

        stock_schema = _load(CONTRACTS / "stock.schema.json")
        assert _find_refs(stock_schema) == []

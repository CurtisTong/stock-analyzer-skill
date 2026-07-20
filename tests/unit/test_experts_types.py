"""
experts/types.py 的单元测试。

按 FRAMEWORK.md 规范：
- 测试类 TestXxxYyy（语义唯一）
- 测试方法 test_行为_期望
- parametrize 优先
- 无 sys.path.insert（依赖 pyproject.toml::pythonpath）
- 无 mock IO（纯 dataclass + 函数）

覆盖：
- ExpertProfile dataclass：frozen 行为、__post_init__ 权重校验、字段默认值
- direction_from_score：5 个阈值区间 + 边界
- normalize_dim：alias 映射 + 透传
- DIMENSION_ALIASES 表结构性校验
"""

from __future__ import annotations

import dataclasses

import pytest

from experts.types import (
    DIMENSION_ALIASES,
    DIRECTION_THRESHOLDS,
    ExpertProfile,
    direction_from_score,
    normalize_dim,
)

# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


def _make_profile(
    *,
    name: str = "test",
    weights: dict | None = None,
    **overrides,
) -> ExpertProfile:
    """构造测试用 ExpertProfile。"""
    defaults = {
        "display_name": "测试专家",
        "group": "long_term",
        "style": "value",
        "horizon": "年",
        "core_signal": "ROE",
        "weights": weights
        or {
            "fundamentals": 40,
            "valuation": 30,
            "technical": 20,
            "sentiment": 5,
            "risk": 5,
        },
    }
    defaults.update(overrides)
    return ExpertProfile(name=name, **defaults)


# ═══════════════════════════════════════════════════════════════
# ExpertProfile dataclass
# ═══════════════════════════════════════════════════════════════


class TestExpertProfileConstruction:
    def test_minimal_required_fields(self):
        """必填字段即可构造。"""
        p = ExpertProfile(
            name="buffett",
            display_name="巴菲特",
            group="long_term",
            style="价值投资",
            horizon="年",
            core_signal="ROE",
            weights={"fundamentals": 50, "valuation": 30, "technical": 20},
        )
        assert p.name == "buffett"
        assert p.display_name == "巴菲特"

    def test_defaults(self):
        """veto_conditions / md_path / active 默认值。"""
        p = _make_profile()
        assert p.veto_conditions == []
        assert p.md_path == ""
        assert p.active is True

    def test_custom_veto_conditions(self):
        """veto_conditions 可显式设置。"""
        p = _make_profile(veto_conditions=["连续3年亏损", "商誉占比>30%"])
        assert len(p.veto_conditions) == 2

    def test_inactive_profile(self):
        """active=False 表示 deprecated。"""
        p = _make_profile(active=False)
        assert p.active is False


class TestExpertProfileImmutability:
    """ExpertProfile 是 frozen=True，字段不可修改。"""

    def test_cannot_mutate_name(self):
        p = _make_profile()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.name = "changed"  # type: ignore[misc]

    def test_cannot_mutate_weights(self):
        p = _make_profile()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.weights = {"new": 100}  # type: ignore[misc]


class TestExpertProfileWeightValidation:
    """__post_init__ 校验权重和接近 100。"""

    def test_valid_weights_no_warning(self, caplog):
        """权重和 = 100 应不触发警告。"""
        import logging

        with caplog.at_level(logging.WARNING, logger="experts.types"):
            _make_profile(
                weights={
                    "fundamentals": 40,
                    "valuation": 30,
                    "technical": 20,
                    "sentiment": 5,
                    "risk": 5,
                }
            )
        # 不应有警告
        assert not any(
            "权重加和" in record.message or "weights" in record.message.lower()
            for record in caplog.records
        ), f"权重和=100 不应触发警告，但收到: {[r.message for r in caplog.records]}"

    def test_tolerance_within_0_5(self, caplog):
        """权重和偏离 100 在 ±0.5 内应不警告（浮点容差）。"""
        import logging

        with caplog.at_level(logging.WARNING, logger="experts.types"):
            _make_profile(
                weights={
                    "fundamentals": 40.1,
                    "valuation": 30.1,
                    "technical": 20.1,
                    "sentiment": 5,
                    "risk": 5,
                }
            )
        assert not any(
            "权重加和" in r.message or "weights" in r.message.lower()
            for r in caplog.records
        ), f"权重和=100.3（容差内）不应警告: {[r.message for r in caplog.records]}"

    def test_invalid_weights_logs_warning(self, caplog):
        """权重和偏离 100 > 0.5 应记录 warning。"""
        import logging

        with caplog.at_level(logging.WARNING, logger="experts.types"):
            _make_profile(
                weights={
                    "fundamentals": 40,
                    "valuation": 30,
                    "technical": 10,  # 和 = 80，偏离 20 > 0.5
                    "sentiment": 0,
                    "risk": 0,
                }
            )
        # 应有警告
        weight_warnings = [
            r
            for r in caplog.records
            if "权重加和" in r.message or "weights" in r.message.lower()
        ]
        assert weight_warnings, "权重和严重偏离 100 应记录 warning"


class TestExpertProfileEquality:
    """dataclass equality：同 fields 相等。"""

    def test_equal_profiles(self):
        p1 = _make_profile(name="a")
        p2 = _make_profile(name="a")
        assert p1 == p2

    def test_different_name_unequal(self):
        p1 = _make_profile(name="a")
        p2 = _make_profile(name="b")
        assert p1 != p2


# ═══════════════════════════════════════════════════════════════
# direction_from_score
# ═══════════════════════════════════════════════════════════════


class TestDirectionFromScore:
    """5 档方向判定：强烈看多 / 看多 / 中性 / 看空 / 强烈看空。"""

    @pytest.mark.parametrize(
        "score,expected",
        [
            (100, "强烈看多"),
            (71, "强烈看多"),
            (70, "强烈看多"),  # 边界
            (69, "看多"),
            (60, "看多"),  # 边界
            (59, "中性"),
            (45, "中性"),
            (40, "中性"),  # 边界
            (39, "看空"),
            (30, "看空"),  # 边界
            (29, "强烈看空"),
            (0, "强烈看空"),
        ],
    )
    def test_score_to_direction(self, score, expected):
        assert direction_from_score(score) == expected

    def test_thresholds_descending_order(self):
        """DIRECTION_THRESHOLDS 必须降序排列（高阈值在前）。"""
        thresholds = [t for t, _ in DIRECTION_THRESHOLDS]
        assert thresholds == sorted(
            thresholds, reverse=True
        ), f"DIRECTION_THRESHOLDS 不是降序: {thresholds}"

    def test_thresholds_cover_full_range(self):
        """DIRECTION_THRESHOLDS 阈值应覆盖 [0, 100]。"""
        thresholds = [t for t, _ in DIRECTION_THRESHOLDS]
        assert min(thresholds) == 0
        assert max(thresholds) <= 100


# ═══════════════════════════════════════════════════════════════
# normalize_dim + DIMENSION_ALIASES
# ═══════════════════════════════════════════════════════════════


class TestNormalizeDim:
    """别名归一化：长形式/变体 → 短标准名。"""

    @pytest.mark.parametrize(
        "alias,expected",
        [
            # 情绪族别名 → 情绪
            ("情绪/资金", "情绪"),
            ("资金/情绪", "情绪"),
            ("情绪/反身性", "情绪"),
            ("情绪/题材", "情绪"),
            # 估值族
            ("估值/质量", "估值"),
            # 质量族
            ("质量/估值", "质量"),
            # 技术族
            ("技术/趋势", "技术面"),
            ("趋势/技术", "技术面"),
            ("技术面/趋势", "技术面"),
        ],
    )
    def test_alias_resolves(self, alias, expected):
        assert normalize_dim(alias) == expected

    def test_unknown_name_passes_through(self):
        """未知名应原样返回（不抛异常）。"""
        assert normalize_dim("不存在的维度") == "不存在的维度"
        assert normalize_dim("fundamentals") == "fundamentals"

    def test_empty_string_returns_empty(self):
        """空字符串保持空。"""
        assert normalize_dim("") == ""


class TestDimensionAliasesTable:
    """DIMENSION_ALIASES 表结构性校验。"""

    def test_aliases_is_dict(self):
        assert isinstance(DIMENSION_ALIASES, dict)

    def test_all_keys_and_values_are_strings(self):
        for k, v in DIMENSION_ALIASES.items():
            assert isinstance(k, str), f"key {k!r} 不是字符串"
            assert isinstance(v, str), f"value {v!r} 不是字符串"

    def test_no_self_mapping(self):
        """别名不应映射到自身（无意义）。"""
        for k, v in DIMENSION_ALIASES.items():
            assert k != v, f"别名 {k!r} 映射到自身"

    def test_keys_unique(self):
        assert len(DIMENSION_ALIASES) == len(set(DIMENSION_ALIASES.keys()))

    def test_minimum_alias_coverage(self):
        """至少 10 个别名（防漂移到稀疏状态）。"""
        assert (
            len(DIMENSION_ALIASES) >= 10
        ), f"DIMENSION_ALIASES 只有 {len(DIMENSION_ALIASES)} 个映射，少于预期"

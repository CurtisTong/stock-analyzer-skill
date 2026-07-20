"""
experts/scoring/_utils.py 的单元测试。

按 FRAMEWORK.md 规范：
- 测试类 TestXxxYyy
- 测试方法 test_行为_期望
- parametrize 优先
- 无 sys.path.insert

覆盖：
- _safe_float：合法/None/非法输入
- score_from_dimensions：完整/缺维度/越界/别名
- dimension_breakdown：各维度加权贡献 + 缺维度
- _score_to_reason_label：5 档阈值 + 边界
- _score_fundamentals：空数据/有效数据
"""

from __future__ import annotations

import pytest

from experts.scoring._utils import (
    _safe_float,
    _score_fundamentals,
    _score_to_reason_label,
    dimension_breakdown,
    score_from_dimensions,
)
from experts.types import ExpertProfile

# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


def _make_profile(weights: dict | None = None) -> ExpertProfile:
    return ExpertProfile(
        name="test",
        display_name="测试",
        group="long_term",
        style="value",
        horizon="年",
        core_signal="ROE",
        weights=weights
        or {
            "fundamentals": 40,
            "valuation": 30,
            "technical": 20,
            "sentiment": 5,
            "risk": 5,
        },
    )


# ═══════════════════════════════════════════════════════════════
# _safe_float
# ═══════════════════════════════════════════════════════════════


class TestSafeFloat:
    @pytest.mark.parametrize(
        "val,expected",
        [
            ("3.14", 3.14),
            ("100", 100.0),
            (42, 42.0),
            (3.14, 3.14),
            (0, 0.0),
            (None, 0.0),  # default 0.0
            ("", 0.0),
        ],
    )
    def test_valid_values(self, val, expected):
        assert _safe_float(val) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "val,default",
        [
            ("abc", 0.0),
            ("xyz", 99.9),
            (["a", "b"], 50.0),
            ({"k": "v"}, 1.0),
        ],
    )
    def test_invalid_returns_default(self, val, default):
        assert _safe_float(val, default=default) == pytest.approx(default)


# ═══════════════════════════════════════════════════════════════
# score_from_dimensions
# ═══════════════════════════════════════════════════════════════


class TestScoreFromDimensions:
    def test_full_match(self):
        """profile.weights 与 dim_scores 完全对应时。"""
        p = _make_profile()
        scores = {
            "fundamentals": 80,
            "valuation": 60,
            "technical": 70,
            "sentiment": 50,
            "risk": 50,
        }
        # 80*0.4 + 60*0.3 + 70*0.2 + 50*0.05 + 50*0.05 = 32+18+14+2.5+2.5 = 69
        assert score_from_dimensions(p, scores) == 69.0

    def test_missing_dim_uses_50_fallback(self):
        """缺维度时用 50 中性分兜底。"""
        p = _make_profile()
        # 只传 fundamentals
        result = score_from_dimensions(p, {"fundamentals": 90})
        # 90*0.4 + 50*0.3 + 50*0.2 + 50*0.05 + 50*0.05 = 36+15+10+2.5+2.5 = 66
        assert result == 66.0

    def test_empty_scores(self):
        """空 dict → 全 50 兜底。"""
        p = _make_profile()
        assert score_from_dimensions(p, {}) == 50.0

    def test_score_clamped_to_0_100(self):
        """单维度分数超出 [0, 100] 时被钳制。"""
        p = _make_profile()
        # fundamentals=150 → 钳到 100；valuation=-10 → 钳到 0
        scores = {
            "fundamentals": 150,
            "valuation": -10,
            "technical": 70,
            "sentiment": 50,
            "risk": 50,
        }
        # 100*0.4 + 0*0.3 + 70*0.2 + 50*0.05 + 50*0.05 = 40+0+14+2.5+2.5 = 59
        assert score_from_dimensions(p, scores) == 59.0

    def test_total_clamped_to_0_100(self):
        """总分也钳制到 [0, 100]。"""
        p = _make_profile(
            weights={
                "fundamentals": 100,
                "valuation": 100,
                "technical": 100,
                "sentiment": 100,
                "risk": 100,
            }
        )
        # 100*5 = 500 → 钳到 100
        result = score_from_dimensions(
            p,
            {
                "fundamentals": 100,
                "valuation": 100,
                "technical": 100,
                "sentiment": 100,
                "risk": 100,
            },
        )
        assert result == 100.0

    def test_unknown_dim_ignored(self):
        """dim_scores 中多余维度不影响总分。"""
        p = _make_profile()
        scores = {
            "fundamentals": 80,
            "valuation": 60,
            "technical": 70,
            "sentiment": 50,
            "risk": 50,
            "unknown_dim": 99,
        }
        assert score_from_dimensions(p, scores) == 69.0  # 与 full_match 相同

    def test_alias_resolution_via_unnormalized_profile(self):
        """防御性归一化：profile.weights 含长别名时，dim_scores 用短标准名也能命中。

        实际场景：手动构造 ExpertProfile 而不通过 yaml_loader 时，weights 可能
        含未归一化的别名（如"情绪/资金"）。score_from_dimensions 应通过
        _normalize_dim_name(dim) 二次归一化查找 dim_scores。
        """
        # profile weights 用归一化前的长别名（手动构造）
        p = ExpertProfile(
            name="unnormalized",
            display_name="未归一化测试",
            group="short_term",
            style="测试",
            horizon="日",
            core_signal="情绪",
            weights={
                "情绪/资金": 30,  # → '情绪'
                "估值/质量": 30,  # → '估值'
                "技术/趋势": 20,  # → '技术面'
                "资金面": 10,  # → '资金'
                "质量": 10,
            },
        )
        # dim_scores 用归一化后的短标准名
        scores = {
            "情绪": 80,
            "估值": 60,
            "技术面": 70,
            "资金": 50,
            "质量": 50,
        }
        # 80*0.3 + 60*0.3 + 70*0.2 + 50*0.1 + 50*0.1 = 24+18+14+5+5 = 66
        assert score_from_dimensions(p, scores) == 66.0


# ═══════════════════════════════════════════════════════════════
# dimension_breakdown
# ═══════════════════════════════════════════════════════════════


class TestDimensionBreakdown:
    def test_full_match(self):
        """每个维度的加权贡献（保留 2 位小数）。"""
        p = _make_profile()
        scores = {
            "fundamentals": 80,
            "valuation": 60,
            "technical": 70,
            "sentiment": 50,
            "risk": 50,
        }
        result = dimension_breakdown(p, scores)
        assert result["fundamentals"] == 32.0  # 80 * 0.4
        assert result["valuation"] == 18.0  # 60 * 0.3
        assert result["technical"] == 14.0  # 70 * 0.2
        assert result["sentiment"] == 2.5  # 50 * 0.05
        assert result["risk"] == 2.5  # 50 * 0.05

    def test_missing_dim_uses_50(self):
        """缺维度用 50 兜底（在 breakdown 中）。"""
        p = _make_profile()
        result = dimension_breakdown(p, {"fundamentals": 90})
        # 90*0.4 + 50*0.3 + 50*0.2 + 50*0.05 + 50*0.05
        assert result["fundamentals"] == 36.0
        assert result["valuation"] == 15.0
        assert result["technical"] == 10.0
        assert result["sentiment"] == 2.5
        assert result["risk"] == 2.5

    def test_score_clamped(self):
        """输入分超界时被钳制。"""
        p = _make_profile()
        result = dimension_breakdown(
            p,
            {
                "fundamentals": 200,  # → 100
                "valuation": 60,
                "technical": 70,
                "sentiment": 50,
                "risk": 50,
            },
        )
        # 100*0.4 + ...
        assert result["fundamentals"] == 40.0

    def test_returns_all_profile_dims(self):
        """breakdown 应包含 profile.weights 的所有维度。"""
        p = _make_profile()
        result = dimension_breakdown(p, {})
        assert set(result.keys()) == set(p.weights.keys())


# ═══════════════════════════════════════════════════════════════
# _score_to_reason_label
# ═══════════════════════════════════════════════════════════════


class TestScoreToReasonLabel:
    @pytest.mark.parametrize(
        "score,expected_substr",
        [
            (100, "优秀"),
            (80, "优秀"),  # 边界
            (79, "良好"),
            (60, "良好"),  # 边界
            (59, "中性"),
            (40, "中性"),  # 边界
            (39, "较弱"),
            (20, "较弱"),  # 边界
            (19, "较差"),
            (0, "较差"),
        ],
    )
    def test_thresholds(self, score, expected_substr):
        """5 档阈值用子串匹配（emoji 前缀不影响核心语义）。"""
        label = _score_to_reason_label(score)
        assert expected_substr in label

    def test_labels_descending_quality(self):
        """高分标签应优于低分标签。"""
        # 优秀 > 良好 > 中性 > 较弱 > 较差
        labels = {
            _score_to_reason_label(90),
            _score_to_reason_label(70),
            _score_to_reason_label(50),
            _score_to_reason_label(30),
            _score_to_reason_label(10),
        }
        assert len(labels) == 5  # 5 档互不相同


# ═══════════════════════════════════════════════════════════════
# _score_fundamentals
# ═══════════════════════════════════════════════════════════════


class TestScoreFundamentals:
    def test_empty_returns_50(self):
        """空 fin 应返回 50 兜底。"""
        assert _score_fundamentals({}) == 50.0

    def test_none_returns_50(self):
        """None fin 应优雅返回 50，不抛异常。"""
        assert _score_fundamentals(None) == 50.0  # type: ignore[arg-type]

    def test_excellent_fundamentals(self):
        """高 ROE + 高增速 + 高毛利率 + 低负债 → 高分。

        公式：score = (roe*5 + (yoy+50) + (rev_yoy+50) + margin*2 + (100-debt)) / 5
        每个子项 min(100, ...)，总均值。
        roe=25 → 100, yoy=50 → 100, rev_yoy=50 → 100, margin=80→100 (×2=160→100), debt=30→70
        = (100+100+100+100+70)/5 = 94.0
        """
        fin = {
            "roe": 25,
            "net_profit_yoy": 50,
            "revenue_yoy": 50,
            "gross_margin": 80,
            "debt_ratio": 30,
        }
        assert _score_fundamentals(fin) == pytest.approx(94.0, rel=1e-3)

    def test_poor_fundamentals(self):
        """低 ROE + 负增速 + 高负债 → 低分。

        roe=5 → 25, yoy=-30 → 20, rev_yoy=-10 → 40, margin=30 → 60, debt=80 → 20
        = (25+20+40+60+20)/5 = 33.0
        """
        fin = {
            "roe": 5,
            "net_profit_yoy": -30,
            "revenue_yoy": -10,
            "gross_margin": 30,
            "debt_ratio": 80,
        }
        assert _score_fundamentals(fin) == pytest.approx(33.0, rel=1e-3)

    def test_zero_roe_negative_yoy(self):
        """roe=0、负 yoy → 子项接近 0。"""
        fin = {
            "roe": 0,  # → 0
            "net_profit_yoy": -60,  # → 0 (max(0, -10)=0)
            "revenue_yoy": -50,  # → 0
            "gross_margin": 0,  # → 0
            "debt_ratio": 100,  # → 0 (max(0, 0)=0)
        }
        # 所有子项 = 0
        assert _score_fundamentals(fin) == 0.0

    def test_accepts_eastmoney_field_aliases(self):
        """同时支持英文小写与东财大写字段名（向后兼容）。"""
        fin = {
            "ROEJQ": 20,  # 中文版字段名
            "PARENTNETPROFITTZ": 30,
            "TOTALOPERATEREVETZ": 30,
            "XSMLL": 70,
            "ZCFZL": 40,
        }
        score = _score_fundamentals(fin)
        # 不应抛异常，且返回 [0, 100] 范围内
        assert 0 <= score <= 100

    def test_partial_fields(self):
        """部分字段缺失时使用 0 兜底（不抛 KeyError）。"""
        fin = {"roe": 20}  # 只传 ROE
        score = _score_fundamentals(fin)
        assert 0 <= score <= 100

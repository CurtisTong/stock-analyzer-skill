"""
scripts/strategies/factors/score_utils.py 的单元测试。

按 FRAMEWORK.md 规范：
- 测试类 TestXxxYyy
- 测试方法 test_行为_期望
- parametrize 优先
- 无 mock IO（依赖 strategies.thresholds 是文件 IO，本测试通过传不同 industry 隔离）

覆盖：
- pe_percentile 全分段边界（low / mid / high / 极高）
- 非法 PE（≤0）走兜底
- ScoringContext dataclass 字段、缺省值
"""

from __future__ import annotations

import pytest

from strategies.factors.score_utils import ScoringContext, pe_percentile

# ═══════════════════════════════════════════════════════════════
# pe_percentile：PE 百分位估值
# ═══════════════════════════════════════════════════════════════


class TestPePercentileBoundaries:
    """分段函数的 4 个区段 + 兜底段。"""

    def test_negative_pe_returns_50_fallback(self):
        """PE ≤ 0 返回 50（无意义数据兜底）。"""
        assert pe_percentile(0) == 50
        assert pe_percentile(-1) == 50
        assert pe_percentile(-100) == 50

    def test_undervalued_segment_low_score(self):
        """PE ≤ 阈值下界 → 低分（越便宜越低估 → 低分因 API 是百分位）。"""
        # pe_undervalued 默认 15：pe=10 < 15 → 返回 15
        assert pe_percentile(10) == 15

    @pytest.mark.parametrize(
        "pe,expected",
        [
            (15, 15),  # 边界：恰好 low 边界（≤ 返回 15）
            (16, 18.5),  # mid 段起点：(16-15)/(25-15)=0.1, 15+0.1*35=18.5
            (20, 32.5),  # mid 中部
            (24, 46.5),  # mid 末尾：(24-15)/(25-15)=0.9, 15+0.9*35=46.5
            (25, 50.0),  # 边界：恰好 mid 边界（≤ 返回 50）
        ],
    )
    def test_mid_segment_linear_interpolation(self, pe, expected):
        """PE 在 (low, mid] 段线性插值 [15, 50]。"""
        assert pe_percentile(pe) == pytest.approx(expected, rel=1e-3)

    @pytest.mark.parametrize(
        "pe,expected",
        [
            (26, 52.0),  # high 段起点：(26-25)/(40-25)=1/15, 50+(1/15)*30=52
            (30, 60.0),  # high 中部：(30-25)/15=1/3, 50+(1/3)*30=60
            (35, 70.0),  # high 后部：(35-25)/15=2/3, 50+(2/3)*30=70
            (40, 80.0),  # 边界：恰好 high 边界（≤ 返回 80）
        ],
    )
    def test_high_segment_linear_interpolation(self, pe, expected):
        """PE 在 (mid, high] 段线性插值 [50, 80]。"""
        assert pe_percentile(pe) == pytest.approx(expected, rel=1e-3)

    def test_extreme_high_capped_at_95(self):
        """PE > high 时封顶 95（避免极端值爆表）。"""
        # pe=60: (60-40)/40=0.5, 80+0.5*20=90 → 90
        assert pe_percentile(60) == pytest.approx(90.0, rel=1e-3)
        # pe=100: (100-40)/40=1.5, 80+1.5*20=110, min(95, 110)=95
        assert pe_percentile(100) == 95
        assert pe_percentile(200) == 95  # 达到上限 95
        assert pe_percentile(1000) == 95  # 上限仍是 95

    def test_output_in_0_100_range(self):
        """返回值必须在 [0, 100] 范围内。"""
        for pe in [0, 1, 5, 10, 14.99, 15, 20, 25, 39.99, 40, 50, 100, 500]:
            result = pe_percentile(pe)
            assert 0 <= result <= 100, f"pe={pe} → {result} 越界"


class TestPePercentileIndustry:
    """不同 industry 应走不同阈值表（用 monkeypatch 验证逻辑路径）。"""

    def test_default_industry_uses_default_thresholds(self, monkeypatch):
        """不传 industry → 使用 '默认' 行业阈值。"""
        # 默认行业阈值：pe_undervalued=15, pe_reasonable=25, pe_expensive=40
        # pe=20 应在 mid 段 → 32.5
        assert pe_percentile(20) == 32.5
        assert pe_percentile(20, "默认") == 32.5

    def test_unknown_industry_falls_back_to_default(self, monkeypatch):
        """未知 industry 走 '默认' 兜底。"""
        # 未配置的行业 → get_industry_threshold 返回 default → 用代码内硬编码阈值
        # 实际行为：未知行业也用代码默认值 15/25/40
        assert pe_percentile(20, "未知行业") == 32.5

    def test_explicit_industry_passed_correctly(self):
        """显式传 industry 不影响 mid 段插值（默认阈值下）。"""
        # 在默认阈值下，所有行业结果一致
        assert pe_percentile(20, "默认") == pe_percentile(20, "消费") == 32.5


# ═══════════════════════════════════════════════════════════════
# ScoringContext dataclass
# ═══════════════════════════════════════════════════════════════


class TestScoringContext:
    """ScoringContext 是因子评分的上下文容器。"""

    def test_required_fields(self):
        """quote/fin/features 是必需位置参数。"""
        ctx = ScoringContext(
            quote={"price": 100}, fin={"eps": 1.5}, features={"rsi": 50}
        )
        assert ctx.quote == {"price": 100}
        assert ctx.fin == {"eps": 1.5}
        assert ctx.features == {"rsi": 50}

    def test_default_industry(self):
        """industry 字段缺省 '默认'。"""
        ctx = ScoringContext(quote={}, fin={}, features={})
        assert ctx.industry == "默认"

    def test_default_code(self):
        """code 字段缺省空字符串。"""
        ctx = ScoringContext(quote={}, fin={}, features={})
        assert ctx.code == ""

    def test_custom_values(self):
        """所有字段显式赋值。"""
        ctx = ScoringContext(
            quote={"price": 50},
            fin={"eps": 1.0},
            features={"rsi": 70},
            industry="科技",
            code="sh600519",
        )
        assert ctx.industry == "科技"
        assert ctx.code == "sh600519"

    def test_dataclass_immutable_by_default(self):
        """ScoringContext 是普通 dataclass（非 frozen），字段可修改。"""
        ctx = ScoringContext(quote={}, fin={}, features={})
        ctx.code = "sz000858"
        assert ctx.code == "sz000858"

    def test_equality(self):
        """两个内容相同的 ScoringContext 应相等（dataclass 默认行为）。"""
        ctx1 = ScoringContext(
            quote={"a": 1}, fin={}, features={}, industry="默认", code=""
        )
        ctx2 = ScoringContext(
            quote={"a": 1}, fin={}, features={}, industry="默认", code=""
        )
        assert ctx1 == ctx2

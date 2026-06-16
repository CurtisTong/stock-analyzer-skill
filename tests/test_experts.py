"""
experts/ 单元测试：覆盖人设一致性、方向阈值、一票否决、维度权重。

P4-3: 新增双向同步校验——registry.py 的 weights 必须与
experts/*.md §九 评分矩阵中的权重百分比一致（偏差 ≤2%）。
"""
import re
import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import (
    EXPERT_REGISTRY,
    ExpertProfile,
    get_expert,
    list_experts,
    list_long_term_experts,
    list_short_term_experts,
    direction_from_score,
    apply_veto,
    DIRECTION_THRESHOLDS,
)
from experts.scoring import (
    score_from_dimensions,
    dimension_breakdown,
    score_expert,
)


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _parse_md_weights(md_path: Path) -> dict:
    """解析 experts/*.md §九 维度权重表。

    查找 '## 九' 后面的 markdown 表格，提取 '维度 | 权重' 列。
    返回 {维度名: float}，如 {"基本面": 42.0, "估值": 28.0, ...}。
    """
    text = md_path.read_text(encoding="utf-8")

    # 找 §九 section（格式：## 九、评分矩阵 或 ## 九：评分矩阵）
    sec9_match = re.search(r"##\s*九[、：:]?\s*评分矩阵", text)
    if not sec9_match:
        return {}

    sec9_text = text[sec9_match.start():]

    # 找表头行（含"维度"和"权重"）—— 表头可能跨多行（markdown 表格续行）
    table_match = re.search(
        r"\|\s*维度\s*\|\s*权重\s*\|",
        sec9_text,
        re.IGNORECASE,
    )
    if not table_match:
        return {}

    # 解析表格行：从表头所在行开始，找到包含 '|' 的行
    weights = {}
    # 回溯到表头行的行首
    table_start_line = sec9_text[:table_match.start()].count("\n")
    in_table = False
    for line in sec9_text.splitlines()[table_start_line:]:
        line = line.strip()
        # 表头行包含"维度"时标记进入表格
        if "维度" in line and "权重" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if "---" in line:
            continue
        # 分割列
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) < 2:
            continue
        dim = cols[0].strip()
        weight_str = cols[1].strip()
        # 提取百分比数字
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", weight_str)
        if m:
            weights[dim] = float(m.group(1))
    return weights


# ═══════════════════════════════════════════════════════════════
# 1. EXPERT_REGISTRY 完整性
# ═══════════════════════════════════════════════════════════════
class TestRegistryIntegrity:
    def test_exactly_8_or_14_experts(self):
        """v2.1.0 起：8 legacy + 6 extended = 14。允许 8（仅 legacy）作过渡。"""
        assert len(EXPERT_REGISTRY) in (8, 14), (
            f"Expected 8 or 14 experts, got {len(EXPERT_REGISTRY)}"
        )

    def test_all_have_required_fields(self):
        for name, p in EXPERT_REGISTRY.items():
            assert p.name, f"{name}: missing name"
            assert p.display_name, f"{name}: missing display_name"
            assert p.group in ("long_term", "short_term"), f"{name}: bad group {p.group}"
            assert p.weights, f"{name}: missing weights"
            assert p.md_path, f"{name}: missing md_path"

    def test_weights_sum_to_100(self):
        for name, p in EXPERT_REGISTRY.items():
            total = sum(p.weights.values())
            assert abs(total - 100) < 0.5, (
                f"{name}: weights sum to {total}%, expected 100%"
            )

    def test_all_md_files_exist(self):
        for name, p in EXPERT_REGISTRY.items():
            md_path = PROJECT_ROOT / p.md_path
            assert md_path.exists(), (
                f"{name}: md_path {p.md_path} does not exist"
            )

    def test_expert_profile_is_frozen(self):
        """ExpertProfile 应不可变（dataclass frozen=True）。"""
        profile = get_expert("buffett")
        with pytest.raises(Exception):
            profile.name = "another"  # type: ignore


# ═══════════════════════════════════════════════════════════════
# 2. 双向同步校验（registry ↔ markdown §九）
# ═══════════════════════════════════════════════════════════════
class TestWeightSync:
    """P4-3: 确保 registry.py 的 weights 与 markdown §九 表格一致。"""

    @pytest.mark.parametrize("expert_name", list(EXPERT_REGISTRY.keys()))
    def test_weights_match_md(self, expert_name):
        """每位专家的维度权重与 markdown §九 表格一致（偏差 ≤2%）。"""
        profile = EXPERT_REGISTRY[expert_name]
        md_path = PROJECT_ROOT / profile.md_path

        if not md_path.exists():
            pytest.skip(f"Markdown file not found: {profile.md_path}")

        md_weights = _parse_md_weights(md_path)
        if not md_weights:
            pytest.skip(f"Could not parse weights from {profile.md_path}")

        for dim, registry_weight in profile.weights.items():
            md_weight = md_weights.get(dim)
            if md_weight is None:
                # 模糊匹配：去掉括号内容后比对
                dim_clean = re.sub(r"\s*\(.*?\)\s*", "", dim)
                for md_dim, md_val in md_weights.items():
                    md_dim_clean = re.sub(r"\s*\(.*?\)\s*", "", md_dim)
                    if dim_clean == md_dim_clean:
                        md_weight = md_val
                        break
            assert md_weight is not None, (
                f"{expert_name}: dimension '{dim}' in registry "
                f"but not found in {profile.md_path} §九 table"
            )
            assert abs(registry_weight - md_weight) <= 2.0, (
                f"{expert_name} '{dim}': registry={registry_weight}% "
                f"vs md={md_weight}% (delta={abs(registry_weight - md_weight):.1f}%)"
            )

    @pytest.mark.parametrize("expert_name", list(EXPERT_REGISTRY.keys()))
    def test_md_has_no_extra_dimensions(self, expert_name):
        """markdown §九 表格中的维度不应比 registry 多（防遗漏同步）。"""
        profile = EXPERT_REGISTRY[expert_name]
        md_path = PROJECT_ROOT / profile.md_path

        if not md_path.exists():
            pytest.skip(f"Markdown file not found: {profile.md_path}")

        md_weights = _parse_md_weights(md_path)
        if not md_weights:
            pytest.skip(f"Could not parse weights from {profile.md_path}")

        registry_dims = set(profile.weights.keys())
        # 模糊匹配
        registry_dims_clean = {re.sub(r"\s*\(.*?\)\s*", "", d): d for d in registry_dims}

        for md_dim in md_weights:
            md_dim_clean = re.sub(r"\s*\(.*?\)\s*", "", md_dim)
            assert md_dim_clean in registry_dims_clean, (
                f"{expert_name}: dimension '{md_dim}' in {profile.md_path} §九 "
                f"but not in registry (missing sync?)"
            )


# ═══════════════════════════════════════════════════════════════
# 3. get_expert / list_experts
# ═══════════════════════════════════════════════════════════════
class TestExpertLookup:
    def test_get_existing_expert(self):
        p = get_expert("buffett")
        assert p is not None
        assert p.display_name == "巴菲特"

    def test_get_nonexistent_returns_none(self):
        assert get_expert("nobody") is None

    def test_list_all_returns_8_or_14(self):
        """v2.1.0 起：list_experts() 返回 8 legacy 或 14 extended。"""
        assert len(list_experts()) in (8, 14)

    def test_list_long_term_returns_4_or_8(self):
        """v2.1.0：长线原 4 + value_anchor + sector_specialist + institution + risk_manager = 8。"""
        experts = list_long_term_experts()
        assert len(experts) in (4, 8), f"expected 4 or 8, got {len(experts)}"
        assert all(e.group == "long_term" for e in experts)

    def test_list_short_term_returns_4_or_5(self):
        """v2.1.0：短线原 4 + topic_leader + emotion_tech = 5/6（含原 4 与合并）。"""
        experts = list_short_term_experts()
        assert len(experts) in (4, 5, 6), f"expected 4/5/6, got {len(experts)}"
        assert all(e.group == "short_term" for e in experts)

    def test_list_by_group(self):
        lt = list_experts("long_term")
        st = list_experts("short_term")
        assert len(lt) + len(st) in (8, 14)


# ═══════════════════════════════════════════════════════════════
# 4. direction_from_score
# ═══════════════════════════════════════════════════════════════
class TestDirectionFromScore:
    def test_strong_buy(self):
        assert direction_from_score(80) == "强烈看多"
        assert direction_from_score(70) == "强烈看多"

    def test_buy(self):
        assert direction_from_score(65) == "看多"
        assert direction_from_score(60) == "看多"

    def test_neutral(self):
        assert direction_from_score(50) == "中性"
        assert direction_from_score(40) == "中性"

    def test_sell(self):
        assert direction_from_score(35) == "看空"
        assert direction_from_score(30) == "看空"

    def test_strong_sell(self):
        assert direction_from_score(20) == "强烈看空"
        assert direction_from_score(0) == "强烈看空"

    def test_thresholds_ordered(self):
        """阈值必须从高到低排列。"""
        for i in range(len(DIRECTION_THRESHOLDS) - 1):
            assert DIRECTION_THRESHOLDS[i][0] > DIRECTION_THRESHOLDS[i + 1][0]


# ═══════════════════════════════════════════════════════════════
# 5. apply_veto
# ═══════════════════════════════════════════════════════════════
class TestVeto:
    def test_apply_veto_no_results_returns_all(self):
        """veto_results=None 时返回全部条件列表。"""
        profile = get_expert("buffett")
        result = apply_veto(profile, {}, None)
        assert result == list(profile.veto_conditions)

    def test_apply_veto_with_results(self):
        profile = get_expert("buffett")
        veto_results = {
            "ROE < 10% 或负债率 > 70%（金融业除外）": True,
            "FCF 连续 2 年为负": False,
            "公司涉财务造假或管理层失信": False,
        }
        triggered = apply_veto(profile, {}, veto_results)
        assert len(triggered) == 1
        assert "ROE" in triggered[0]

    def test_apply_veto_none_triggered(self):
        profile = get_expert("buffett")
        veto_results = {c: False for c in profile.veto_conditions}
        triggered = apply_veto(profile, {}, veto_results)
        assert triggered == []


# ═══════════════════════════════════════════════════════════════
# 6. score_from_dimensions（按权重加总）
# ═══════════════════════════════════════════════════════════════
class TestScoreFromDimensions:
    def test_all_neutral_50_returns_50(self):
        profile = get_expert("buffett")
        score = score_from_dimensions(profile, {})
        assert 49 <= score <= 51

    def test_all_100_returns_100(self):
        profile = get_expert("buffett")
        dims = {dim: 100 for dim in profile.weights}
        score = score_from_dimensions(profile, dims)
        assert score == 100.0

    def test_all_0_returns_0(self):
        profile = get_expert("buffett")
        dims = {dim: 0 for dim in profile.weights}
        score = score_from_dimensions(profile, dims)
        assert score == 0.0

    def test_clamp_over_100(self):
        profile = get_expert("buffett")
        dims = {"基本面": 200, "估值": 100, "技术面": 100, "情绪": 100, "安全边际": 100}
        score = score_from_dimensions(profile, dims)
        assert score == 100.0

    def test_clamp_negative(self):
        profile = get_expert("buffett")
        dims = {"基本面": -50, "估值": 100, "技术面": 100, "情绪": 100, "安全边际": 100}
        score = score_from_dimensions(profile, dims)
        # 基本面钳制到 0，权重 42% → 贡献 0
        # 100*0.28 + 100*0.05 + 100*0.05 + 100*0.20 = 58
        assert score == 58.0

    def test_weighted_total(self):
        profile = get_expert("buffett")
        dims = {"基本面": 80, "估值": 60, "技术面": 40, "情绪": 50, "安全边际": 70}
        expected = 80 * 0.42 + 60 * 0.28 + 40 * 0.05 + 50 * 0.05 + 70 * 0.20
        score = score_from_dimensions(profile, dims)
        assert abs(score - expected) < 0.01


# ═══════════════════════════════════════════════════════════════
# 7. dimension_breakdown
# ═══════════════════════════════════════════════════════════════
class TestDimensionBreakdown:
    def test_returns_all_dimensions(self):
        profile = get_expert("buffett")
        dims = {dim: 80 for dim in profile.weights}
        breakdown = dimension_breakdown(profile, dims)
        assert set(breakdown.keys()) == set(profile.weights.keys())

    def test_breakdown_sums_to_total(self):
        profile = get_expert("buffett")
        dims = {dim: 80 for dim in profile.weights}
        breakdown = dimension_breakdown(profile, dims)
        total = sum(breakdown.values())
        score = score_from_dimensions(profile, dims)
        assert abs(total - score) < 0.1


# ═══════════════════════════════════════════════════════════════
# 8. score_expert（端到端）
# ═══════════════════════════════════════════════════════════════
class TestScoreExpert:
    def test_returns_complete_structure(self):
        result = score_expert(get_expert("buffett"), {})
        assert "score" in result
        assert "direction" in result
        assert "breakdown" in result
        assert "dim_scores" in result

    def test_empty_stock_data_neutral(self):
        result = score_expert(get_expert("buffett"), {})
        assert 49 <= result["score"] <= 51
        assert result["direction"] == "中性"

    def test_good_stock_buffett_score_high(self):
        stock = {
            "quote": {"pe": 12, "pb": 1.5, "change_pct": 0.5},
            "finance": {"roe": 25, "net_profit_yoy": 30, "revenue_yoy": 20,
                        "gross_margin": 60, "debt_ratio": 25},
            "kline_features": {"trend": 1, "rsi": 50, "macd_signal": 1},
        }
        result = score_expert(get_expert("buffett"), stock)
        assert result["score"] >= 60, f"Expected >= 60, got {result['score']}"
        assert result["direction"] in ("看多", "强烈看多")

    def test_bad_stock_buffett_score_low(self):
        stock = {
            "quote": {"pe": 80, "pb": 8, "change_pct": -5},
            "finance": {"roe": 2, "net_profit_yoy": -20, "revenue_yoy": -10,
                        "gross_margin": 5, "debt_ratio": 85},
            "kline_features": {"trend": -1, "rsi": 25, "macd_signal": -1},
        }
        result = score_expert(get_expert("buffett"), stock)
        assert result["score"] <= 40, f"Expected <= 40, got {result['score']}"
        assert result["direction"] in ("看空", "中性", "强烈看空")

    def test_different_experts_diverge_on_sentiment(self):
        stock = {
            "quote": {"pe": 18, "pb": 3, "change_pct": 8},
            "finance": {"roe": 12, "net_profit_yoy": 10, "revenue_yoy": 8,
                        "gross_margin": 35, "debt_ratio": 50},
            "kline_features": {"trend": 1, "rsi": 75, "macd_signal": 1},
            "market_features": {"limit_up_count": 70, "limit_down_count": 3},
        }
        long_term_scores = [
            score_expert(e, stock)["score"] for e in list_long_term_experts()
        ]
        short_term_scores = [
            score_expert(e, stock)["score"] for e in list_short_term_experts()
        ]
        long_avg = sum(long_term_scores) / len(long_term_scores)
        short_avg = sum(short_term_scores) / len(short_term_scores)
        assert short_avg > long_avg, (
            f"短线团 ({short_avg:.1f}) 应高于长线团 ({long_avg:.1f})"
        )

    def test_score_in_valid_range(self):
        weird_stocks = [
            {},
            {"quote": {"pe": -100, "pb": -10}, "finance": {"roe": -50}},
            {"quote": {"pe": 9999, "pb": 999}, "finance": {"roe": 9999, "debt_ratio": 0}},
        ]
        for stock in weird_stocks:
            result = score_expert(get_expert("buffett"), stock)
            assert 0 <= result["score"] <= 100
            assert result["direction"] in (
                "强烈看空", "看空", "中性", "看多", "强烈看多",
            )

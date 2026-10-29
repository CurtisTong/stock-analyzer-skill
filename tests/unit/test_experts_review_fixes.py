"""v1.24.0 复审修复的专家圆桌回归测试。

覆盖复审中发现的 P1：
- 整组弃权被误判为"两极分化"（把一致看多翻成中性观望）
- slugging 赔率对看空专家返回负数
- 仓位钳制后分步建仓指令仍按钳制前仓位生成（卡片自相矛盾）
- 单组模式完全绕过钳制与弃权过滤
"""

from __future__ import annotations

import pytest

from experts.vote_engine import aggregate_group_votes, aggregate_votes


def _expert(name: str, score: float, **kw) -> dict:
    return {
        "name": name,
        "display_name": kw.get("display_name", name),
        "score": score,
        "reason": kw.get("reason", ""),
    }


def _abstain(name: str) -> dict:
    """弃权专家：score 为 None（vote_engine 按此识别）且带 abstain 标记。"""
    return {
        "name": name,
        "display_name": name,
        "score": None,
        "reason": "数据不足，无法判定",
        "abstain": True,
    }


class TestAbstainNotExtreme:
    """弃权是"读不出来"，不是"看空"信号。"""

    def test_all_long_abstain_not_polarized(self):
        """长线组全弃权 + 短线一致看多 → 不得判为"两极分化→中性"。"""
        results = [
            _abstain("lynch"),
            _abstain("soros"),
            _abstain("value_institution"),
            _abstain("sector_specialist"),
            _abstain("risk_manager"),
            _expert("topic_leader", 85),
            _expert("emotion_tech", 80),
            _expert("momentum_trader", 82),
        ]
        r = aggregate_votes(results, horizon="short")
        notes = " ".join(r.get("notes", []))
        assert "两极分化" not in notes, r.get("notes")
        # 短线一致看多，长线弃权不应把方向翻成中性
        assert r["direction"] != "中性"

    def test_no_abstain_polarized_still_detected(self):
        """真实的极端分歧（长线全看多 + 短线全看空）仍必须识别。"""
        results = [
            _expert("lynch", 85),
            _expert("soros", 88),
            _expert("value_institution", 82),
            _expert("sector_specialist", 86),
            _expert("risk_manager", 84),
            _expert("topic_leader", 15),
            _expert("emotion_tech", 12),
            _expert("momentum_trader", 18),
        ]
        r = aggregate_votes(results, horizon="short")
        notes = " ".join(r.get("notes", []))
        assert "两极分化" in notes


class TestSluggingSign:
    """看空专家的赔率不得为负。"""

    def test_bear_expert_slugging_positive(self):
        from experts.calibration import _directional_return, _slugging_from_rec

        # 看空专家：赢 = 股价下跌 8%（原始 -8），输 = 股价上涨 5%（原始 +5）
        win = _directional_return(-8.0, "看空")
        loss = _directional_return(5.0, "看空")
        assert win == pytest.approx(8.0)
        assert loss == pytest.approx(-5.0)

        rec = {"slug_win_sum": win, "slug_win_n": 1, "slug_loss_sum": loss, "slug_loss_n": 1}
        slug = _slugging_from_rec(rec)
        assert slug is not None
        assert slug > 0

    def test_bull_expert_unchanged(self):
        from experts.calibration import _directional_return

        assert _directional_return(6.0, "看多") == pytest.approx(6.0)
        assert _directional_return(-4.0, "看多") == pytest.approx(-4.0)


class TestPositionClampConsistency:
    """仓位钳制后，卡片的仓位与分步建仓指令必须自洽。"""

    def test_steps_sum_matches_clamped_position(self):
        import re

        from experts.vote_engine import _build_steps

        pos = 20
        steps = _build_steps(pos)
        assert "20%" in steps
        # 不得出现超过钳制后仓位的分步额度
        for part in re.findall(r"(\d+)%", steps):
            assert int(part) <= pos

    def test_build_steps_zero(self):
        from experts.vote_engine import _build_steps

        assert _build_steps(0) == "-"

    def test_high_confidence_clamped_to_cap(self):
        """高信心看多 → 仓位被钳到 20%，且 steps 同步为 20% 口径。"""
        results = [
            _expert("lynch", 95),
            _expert("soros", 92),
            _expert("value_institution", 94),
            _expert("sector_specialist", 90),
            _expert("risk_manager", 93),
            _expert("topic_leader", 90),
            _expert("emotion_tech", 88),
            _expert("momentum_trader", 91),
        ]
        r = aggregate_votes(results, horizon="short")
        pos = r["position"]
        assert pos["position_pct"] <= 20
        # steps 不得暗示超过 20% 的总仓位
        assert "50%" not in pos["steps"]
        assert "70%" not in pos["steps"]


class TestGroupModeClampAndAbstain:
    """单组模式也必须遵守弃权规则与仓位上限。"""

    def test_group_all_abstain_is_neutral_not_bearish(self):
        results = [_abstain("lynch"), _abstain("soros"), _abstain("value_institution")]
        r = aggregate_group_votes(results, group="long_term")
        assert r["direction"] == "中性"
        assert r["position"]["position_pct"] == 0
        assert r.get("abstained") == 3

    def test_group_position_clamped_to_cap(self):
        """单组高信心看多 → 仓位不得突破 20% 上限（修复前可到 84%）。"""
        results = [
            _expert("lynch", 95),
            _expert("soros", 94),
            _expert("value_institution", 96),
            _expert("sector_specialist", 92),
            _expert("risk_manager", 93),
        ]
        r = aggregate_group_votes(results, group="long_term")
        assert r["position"]["position_pct"] <= 20
        assert r.get("clamp_events")

    def test_group_abstain_excluded_from_votes(self):
        results = [
            _expert("lynch", 85),
            _expert("soros", 82),
            _expert("value_institution", 80),
            _abstain("sector_specialist"),
            _abstain("risk_manager"),
        ]
        r = aggregate_group_votes(results, group="long_term")
        assert r["votes"]["total"] == 3
        assert r.get("abstained") == 2

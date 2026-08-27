"""剧烈轮动期操作建议（避免与分层建议错配）单元测试。"""

import pytest

import market_anchor


def _rotation_payload(strength: float) -> dict:
    payload = {
        "window": 5,
        "rotation_strength": strength,
        "rotation_std": 1.2,
        "biggest_risers": [["A", "半导体", 2.0]],
        "biggest_fallers": [["B", "煤炭", 1.5]],
        "interpretation": "测试",
    }
    # 与 _fetch_sector_rotation 包装一致：strength>3 → 保守建议
    if strength > 3:
        payload["advice"] = (
            "剧烈轮动期（主线切换中）：减少新增仓位，优先减仓弱势持仓，"
            "等待主线明确后再考虑进攻/分层配置"
        )
    else:
        payload["advice"] = "轮动强度适中：可维持现有配置，结合板块强弱做均衡布局"
    return payload


class TestFetchSectorRotationAdvice:
    """剧烈轮动 → 保守建议。"""

    def test_high_rotation_conservative(self, monkeypatch):
        monkeypatch.setattr(
            "market_anchor.sector_etf_strength.compute_rotation_strength",
            lambda window=5: _rotation_payload(4.13),
        )
        res = market_anchor._fetch_sector_rotation(window=5)
        assert res["rotation_strength"] == 4.13
        assert "减少新增仓位" in res["advice"]
        assert "减仓弱势持仓" in res["advice"]

    def test_medium_rotation_balanced(self, monkeypatch):
        monkeypatch.setattr(
            "market_anchor.sector_etf_strength.compute_rotation_strength",
            lambda window=5: _rotation_payload(2.0),
        )
        res = market_anchor._fetch_sector_rotation(window=5)
        assert "维持现有配置" in res["advice"]

    def test_exception_degrades(self, monkeypatch):
        def boom(window=5):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "market_anchor.sector_etf_strength.compute_rotation_strength", boom
        )
        res = market_anchor._fetch_sector_rotation(window=5)
        assert res.get("data_quality", {}).get("degraded_fields") == ["sector_rotation"]


def _base_payload() -> dict:
    """to_markdown 所需最小完整 payload。"""
    return {
        "regime_label_zh": "测试状态",
        "regime": "TEST",
        "regime_confidence": "中",
        "regime_reason": "测试原因",
        "index_change_pct": 0.5,
        "index_code": "sh000300",
        "as_of": "2026-08-12T10:00:00",
        "data_quality": {"degraded_fields": []},
    }


class TestRenderRotationAdvice:
    """to_markdown 渲染操作建议。"""

    def _render_with_rotation(self, strength):
        payload = _base_payload()
        payload["sector_rotation"] = _rotation_payload(strength)
        return market_anchor.to_markdown(payload)

    def test_render_high_rotation_advice(self):
        md = self._render_with_rotation(4.13)
        assert "操作建议" in md
        assert "减少新增仓位" in md

    def test_render_no_rotation_section(self):
        payload = _base_payload()
        payload["sector_rotation"] = None
        md = market_anchor.to_markdown(payload)
        assert "题材轮动强度" not in md

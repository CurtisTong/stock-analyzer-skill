"""情绪因子单元测试（v1.26 阶段 1）。

全部为数学锚点断言——档位是按 2026-10-30 实测分布校准的，
必须能用手算验证，不能只断言"字段存在"。
"""

from __future__ import annotations

import json

import pytest


class TestHeightScore:
    """连板高度分：lbc_score = 40 + 45 × (1 − 0.5^(lbc−1))"""

    def test_anchors(self):
        from strategies.factors.sentiment import _lbc_score

        assert _lbc_score(1) == pytest.approx(40.0)
        assert _lbc_score(2) == pytest.approx(62.5)
        assert _lbc_score(3) == pytest.approx(73.75)
        # 函数内保留 2 位小数：40 + 45×0.9375 = 79.375 → 79.38
        assert _lbc_score(4) == pytest.approx(79.38)
        assert _lbc_score(5) == pytest.approx(82.19)

    def test_marginal_decreasing(self):
        """边际递减：每多一板的增幅必须递减。"""
        from strategies.factors.sentiment import _lbc_score

        inc1 = _lbc_score(2) - _lbc_score(1)
        inc2 = _lbc_score(3) - _lbc_score(2)
        inc3 = _lbc_score(4) - _lbc_score(3)
        assert inc1 > inc2 > inc3

    def test_broken_stock_has_no_height(self):
        """炸板股无 lbc（从未封板）→ 中性 50，不享首板 40。"""
        from strategies.factors.sentiment import _lbc_score

        assert _lbc_score(None) == 50.0
        assert _lbc_score(0) == 50.0


class TestSealScore:
    def test_broken_tiers(self):
        """炸板次数分档（实测分布校准）。"""
        from strategies.factors.sentiment import _broken_score

        assert _broken_score(0) == 100.0
        assert _broken_score(1) == 75.0
        assert _broken_score(2) == 55.0
        assert _broken_score(4) == 35.0
        assert _broken_score(6) == 20.0
        assert _broken_score(None) == 50.0

    def test_seal_ratio_tiers(self):
        """封单占比分档（按实测 p50=0.22% / p75=1.36% / p90=3.47% 重设）。"""
        from strategies.factors.sentiment import _seal_ratio_score

        assert _seal_ratio_score(0.0) == 30.0
        assert _seal_ratio_score(0.05) == 50.0
        assert _seal_ratio_score(0.3) == 70.0
        assert _seal_ratio_score(1.0) == 85.0
        assert _seal_ratio_score(5.0) == 100.0
        assert _seal_ratio_score(None) == 50.0

    def test_seal_composite(self):
        """封板质量分 = 0.6×炸板分 + 0.4×封单强度分。"""
        from strategies.factors.sentiment import _seal_score

        entry = {"zbc": 0, "fund": 1e7, "ltsz": 1e9}  # 封单占比 1%
        # 0.6*100 + 0.4*85 = 94.0
        assert _seal_score(entry) == pytest.approx(94.0)

    def test_missing_fund_is_neutral_not_zero_seal(self):
        """fund 缺失 ≠ 没有封单：缺失按中性 50，不得按 0 封单扣分。"""
        from strategies.factors.sentiment import _seal_score

        missing = _seal_score({"zbc": 0, "fund": None, "ltsz": 1e9})
        zero = _seal_score({"zbc": 0, "fund": 0, "ltsz": 1e9})
        assert missing == pytest.approx(0.6 * 100 + 0.4 * 50)
        assert missing > zero  # 缺失比"真的没封单"得分高


class TestSectorScore:
    def test_strength_tiers(self):
        """板块当日强度分档（占比口径）。"""
        from strategies.factors.sentiment import _sector_strength_score

        assert _sector_strength_score(0.0) == 30.0
        assert _sector_strength_score(2.0) == 55.0
        assert _sector_strength_score(5.0) == 72.0
        assert _sector_strength_score(10.0) == 88.0
        assert _sector_strength_score(20.0) == 100.0
        assert _sector_strength_score(None) == 50.0


class TestActivityScore:
    def test_non_monotonic(self):
        """活跃度非线性：过低（无人问津）与过高（接力风险）都扣分。"""
        from strategies.factors.sentiment import _activity_score

        assert _activity_score(0.5) == 30.0
        assert _activity_score(3.0) == 55.0
        assert _activity_score(8.0) == 85.0
        assert _activity_score(20.0) == 70.0
        assert _activity_score(40.0) == 45.0
        assert _activity_score(None) == 50.0

    def test_peak_at_healthy_turnover(self):
        """健康接力区（5%~15%）得分最高。"""
        from strategies.factors.sentiment import _activity_score

        scores = [_activity_score(x) for x in (0.5, 3, 8, 20, 40)]
        assert max(scores) == scores[2]


class TestSentimentScoreEndToEnd:
    """端到端：构造快照 → 因子输出（可手算）"""

    @pytest.fixture
    def snapshot(self, tmp_path, monkeypatch):
        import data.sentiment_panel as panel

        path = tmp_path / "sentiment_snapshots.json"
        monkeypatch.setattr(panel, "_snapshot_path", lambda: path)

        snap = {
            "date": "2026-10-29",
            "limit_up_count": 10,
            "broken_count": 0,
            "max_height": 3,
            "height_distribution": {"1": 8, "2": 1, "3": 1},
            "median_chg_pct": 10.0,
            "sectors": {
                "专用设备": {"limit_up": 2, "broken": 0, "count": 2},
                "汽车零部": {"limit_up": 1, "broken": 0, "count": 1},
            },
            "stocks": {
                "sz002526": {
                    "code": "sz002526",
                    "name": "山东矿机",
                    "status": "limit_up",
                    "lbc": 3,
                    "zbc": 0,
                    "fund": 9.7105e7,
                    "ltsz": 5.8096e9,
                    "hs": 2.51,
                    "zdp": 10.07,
                    "sector": "专用设备",
                },
                "sh600519": {
                    "code": "sh600519",
                    "name": "贵州茅台",
                    "status": "limit_up",
                    "lbc": 1,
                    "zbc": 0,
                    "fund": 1.0e8,
                    "ltsz": 1.0e10,
                    "hs": 1.2,
                    "zdp": 10.0,
                    "sector": "汽车零部",
                },
            },
        }
        path.write_text(
            json.dumps({"version": 1, "snapshots": {"2026-10-29": snap}}, ensure_ascii=False),
            encoding="utf-8",
        )
        return snap

    def test_score_matches_manual_calculation(self, snapshot):
        """总分 = 0.30×高度 + 0.25×封板 + 0.25×板块 + 0.20×活跃度。"""
        from strategies.factors.sentiment import sentiment_score

        score = sentiment_score("sz002526")
        assert score is not None
        # 高度 lbc=3 → 73.75
        # 封板 zbc=0 → 100；封单占比 97105016/5809648956.64 = 1.6707% → 85
        #   → 0.6*100 + 0.4*85 = 94.0
        # 板块 专用设备 2/10 = 20% → 100（无历史，轮动 +0）
        # 活跃度 hs=2.51 → 55
        expected = 0.30 * 73.75 + 0.25 * 94.0 + 0.25 * 100 + 0.20 * 55
        assert score == pytest.approx(expected, abs=0.01)

    def test_stock_outside_pool_returns_none(self, snapshot):
        """不在涨停/炸板池 → None（缺失，不是 0 分）。"""
        from strategies.factors.sentiment import sentiment_score

        assert sentiment_score("sh601398") is None

    def test_details_exposes_components(self, snapshot):
        from strategies.factors.sentiment import sentiment_details

        d = sentiment_details("sz002526")
        assert d is not None
        assert set(d["components"]) == {"height", "seal", "sector", "activity"}
        assert d["components"]["height"] == pytest.approx(73.75)


class TestFactorRegistration:
    def test_registered_with_zero_weight(self):
        """情绪因子已注册但权重为 0（阶段 1：只作参考列）。"""
        from strategies.factors.registry import get_factor_keys

        assert "sentiment" in get_factor_keys()

    def test_strategy_weights_unchanged(self):
        """阶段 1 不改变任何策略权重（6 策略权重和仍为 1.0）。"""
        from strategies.registry import STRATEGIES

        for name, weights in STRATEGIES.items():
            total = sum(v for k, v in weights.items() if k not in ("label", "two_stage"))
            assert total == pytest.approx(1.0), f"{name} 权重和 {total}"


class TestSnapshotPersistence:
    def test_save_and_roll(self, tmp_path, monkeypatch):
        """快照写入 + 超出保留期自动滚动清理。"""
        import data.sentiment_panel as panel

        path = tmp_path / "sentiment_snapshots.json"
        monkeypatch.setattr(panel, "_snapshot_path", lambda: path)

        for i in range(panel.MAX_SNAPSHOT_DAYS + 5):
            panel.save_snapshot({"date": f"2026-01-{i + 1:02d}", "stocks": {}})

        snapshots = panel.load_snapshots()["snapshots"]
        assert len(snapshots) == panel.MAX_SNAPSHOT_DAYS
        # 保留的是最近的
        assert max(snapshots.keys()) == f"2026-01-{panel.MAX_SNAPSHOT_DAYS + 5:02d}"

    def test_corrupted_file_treated_as_empty(self, tmp_path, monkeypatch):
        """快照文件损坏 → 视为无历史，不抛错。"""
        import data.sentiment_panel as panel

        path = tmp_path / "sentiment_snapshots.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(panel, "_snapshot_path", lambda: path)
        assert panel.load_snapshots()["snapshots"] == {}

    def test_promotion_rate_none_without_history(self, tmp_path, monkeypatch):
        """无历史快照时晋级率不可算 → None（不是 0）。"""
        import data.sentiment_panel as panel

        path = tmp_path / "sentiment_snapshots.json"
        monkeypatch.setattr(panel, "_snapshot_path", lambda: path)
        panel.save_snapshot({"date": "2026-10-29", "stocks": {}})
        assert panel.get_promotion_rate() is None

    def test_promotion_rate_math(self, tmp_path, monkeypatch):
        """晋级率 = 昨日涨停 ∩ 今日涨停 ÷ 昨日涨停数。"""
        import data.sentiment_panel as panel

        path = tmp_path / "sentiment_snapshots.json"
        monkeypatch.setattr(panel, "_snapshot_path", lambda: path)

        prev = {
            "date": "2026-10-28",
            "stocks": {f"sh60000{i}": {"status": "limit_up", "lbc": 1} for i in range(10)},
        }
        today = {
            "date": "2026-10-29",
            "stocks": {
                **{f"sh60000{i}": {"status": "limit_up", "lbc": 2} for i in range(3)},
                **{f"sh60001{i}": {"status": "limit_up", "lbc": 1} for i in range(2)},
            },
        }
        panel.save_snapshot(prev)
        panel.save_snapshot(today)
        # 昨日 10 只，今日续板 3 只 → 0.3
        assert panel.get_promotion_rate() == pytest.approx(0.3)

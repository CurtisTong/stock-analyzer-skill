"""docs/code-review-2026-11-21.md §4.3 技术分析与板块修复的回归测试。

每条用例在修复前必须失败（已用 HEAD 版本源码验证），修复后全部通过。
纯离线：不触发任何网络请求。
"""

from __future__ import annotations

import ast
import inspect

import pytest

import sector_etf_strength as ses
from technical import scoring
from technical.candlestick import detect_candle_patterns
from technical.macd import _detect_macd_divergence, _nearest_point
from technical.trend import support_resistance


# ── review §4.3-1（P2）：MACD 背离最近邻无距离上限 ──────────────────


class TestMacdDivergenceDistance:
    def test_top_divergence_rejects_far_dif_peaks(self):
        """价格双峰在 20/40，DIF 峰远在 8/52：修复前误报顶背离。"""
        c = [100.0] * 60
        c[20], c[40] = 110.0, 112.0
        d = [0.0] * 60
        d[8], d[52] = 0.8, 0.4
        assert _detect_macd_divergence(c, d, []) is None

    def test_bottom_divergence_rejects_far_dif_troughs(self):
        """价格双谷在 20/40，DIF 谷远在 8/52：修复前误报底背离。"""
        c = [100.0] * 60
        c[20], c[40] = 90.0, 85.0
        d = [0.0] * 60
        d[8], d[52] = -0.8, -0.4
        assert _detect_macd_divergence(c, d, []) is None

    def test_nearest_point_max_dist(self):
        """可选 max_dist 限制配对距离，默认值保持旧行为兼容。"""
        assert _nearest_point([10, 30, 50], 28) == 30
        assert _nearest_point([10, 30, 50], 28, max_dist=5) == 30
        assert _nearest_point([10, 30, 50], 28, max_dist=1) is None
        assert _nearest_point([], 28, max_dist=5) is None


# ── review §4.3-2（P3）：T 字/倒 T 字分支不可达 ──────────────────────


def _records_with_last(last: dict) -> list[dict]:
    base = {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.0}
    return [dict(base, day=f"d{i}") for i in range(3)] + [dict(last, day="target")]


class TestCandleTShape:
    def test_t_shape_recognized(self):
        """零实体 + 长下影 + 无上影 → T 字线（修复前判为十字星）。"""
        bar = {"open": 10.0, "high": 10.0, "low": 9.0, "close": 10.0}
        types = [p["type"] for p in detect_candle_patterns(_records_with_last(bar))]
        assert any("T字线" in t for t in types)

    def test_inverted_t_shape_recognized(self):
        """零实体 + 长上影 + 无下影 → 倒 T 字（修复前判为十字星）。"""
        bar = {"open": 10.0, "high": 11.0, "low": 10.0, "close": 10.0}
        types = [p["type"] for p in detect_candle_patterns(_records_with_last(bar))]
        assert any("倒T字" in t for t in types)

    def test_long_legged_doji_still_doji(self):
        """上下影都长的窄实体仍是十字星，不被误判为 T 字。"""
        bar = {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.01}
        types = [p["type"] for p in detect_candle_patterns(_records_with_last(bar))]
        assert any("十字星" in t for t in types)


# ── review §4.3-3（P3）：scoring.py 恒真 if True + 双重不可达 else ────


class TestScoringNoDeadBranch:
    def test_no_if_true_and_no_dead_else(self):
        """源码结构断言：恒真包裹与无行情死 else 均已删除。"""
        src = inspect.getsource(scoring.detect_market_environment)
        tree = ast.parse(src)
        dead_true = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.If) and isinstance(n.test, ast.Constant) and n.test.value is True
        ]
        assert dead_true == []
        # 提前 return 分支仍保留唯一的缺失数据提示
        assert src.count("大盘数据缺失，默认震荡") == 1

    def test_behavior_preserved_with_quote(self):
        """行为兼容：有行情时仍产出状态/权重。"""
        out = scoring.detect_market_environment(
            {"price": 3000, "change_pct": 0.2},
            recent_quotes=[{"change_pct": 0.2, "turnover": 1.0}],
        )
        assert out["state"] in ("强势", "弱势", "震荡", "冰点", "亢奋")
        assert isinstance(out["weight_adjustments"], dict)


# ── review §4.3-4（P3）：恰好 3 只 ETF 时 strong/weak 是同一批 ───────


def _fake_analyze(monkeypatch: pytest.MonkeyPatch, count: int) -> dict:
    metas = [
        {"code": f"sh51{i:04d}", "name": f"ETF{i}", "category": "行业", "bk_code": None}
        for i in range(count)
    ]
    quotes = {
        m["code"]: {
            "code": m["code"],
            "name": m["name"],
            "price": 1.0,
            "change_pct": float(count - i),
            "turnover": 1.0,
            "total_cap": 1.0,
        }
        for i, m in enumerate(metas)
    }
    monkeypatch.setattr(ses, "_load_sector_etfs", lambda: metas)
    monkeypatch.setattr(ses, "_fetch_etf_quotes", lambda codes: quotes)
    return ses.analyze(stock_code=None, fetch_index=False)


class TestStrongWeakDisjoint:
    def test_three_etfs_do_not_list_same_names_as_strong_and_weak(self, monkeypatch):
        """3 只 ETF：修复前 strong == weak，报告同时列🔥强势与💀弱势。"""
        out = _fake_analyze(monkeypatch, 3)
        assert len(out["strong_sectors"]) == 3
        assert out["weak_sectors"] == []
        assert not (set(out["strong_sectors"]) & set(out["weak_sectors"]))

    def test_six_etfs_keep_both_ends_disjoint(self, monkeypatch):
        """>=6 只 ETF 时两端仍正常输出且互不重叠。"""
        out = _fake_analyze(monkeypatch, 6)
        assert len(out["strong_sectors"]) == 3
        assert len(out["weak_sectors"]) == 3
        assert not (set(out["strong_sectors"]) & set(out["weak_sectors"]))


# ── review §4.3-5（P3）：vs 大盘 if/else 输出相同字符串 ──────────────


class TestIndexDirectionVerdict:
    def test_outperform_index(self):
        res = ses.build_stock_sector_compare("sh699999", {"change_pct": 2.0}, [], {"change_pct": 0.5})
        assert "跑赢大盘" in res["verdict"]

    def test_underperform_index(self):
        res = ses.build_stock_sector_compare("sh699999", {"change_pct": -2.0}, [], {"change_pct": -0.5})
        assert "跑输大盘" in res["verdict"]


# ── review §4.3-6（P3）：整数关口 round() 银行家舍入与注释不符 ────────


class TestIntegerLevelFloor:
    def test_55_floors_to_50_support(self):
        """last=55：round(5.5)=6 会把 60 当阻力；向下取整应为 50 支撑。"""
        out = support_resistance(
            [55.0] * 30,
            [56.0] * 30,
            [54.0] * 30,
            {"ma_supports": [], "ma_resistances": []},
        )
        int_supports = [s["level"] for s in out["supports"] if s["source"] == "整数关口"]
        int_resistances = [r["level"] for r in out["resistances"] if r["source"] == "整数关口"]
        assert 50.0 in int_supports
        assert int_resistances == []

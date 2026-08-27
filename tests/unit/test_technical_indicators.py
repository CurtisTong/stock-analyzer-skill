"""技术分析模块单元测试（审查修复回归测试）。

覆盖修复项：
- H1: PE 分位统一（technical.py 路径与 strategies 路径一致）+ 估值评分极性
- H2: composite_score 缺失 features 归一化为中性（稀疏/完整路径一致）
- H3: pipeline 透传 macd bar_trend（金叉+红柱放大 15 分）
- M1: volume_analysis 缩量窗口 off-by-one
- M2: breakout_check 回踩确认逻辑可达
- M4: detect_market_environment 空 dict / 缺 turnover 不误判
- M5: _score_limit adj 仅应用一次
- L1: 技术指标模块基础单元覆盖（macd/kdj/rsi/boll/ma）
"""

import importlib.util
from pathlib import Path

import pytest

from data.types import KlineBar
from technical.boll import bollinger
from technical.kdj import kdj_full
from technical.macd import macd_full
from technical.moving_average import ma_system
from technical.pipeline import compute_indicators
from technical.rsi import rsi_features
from technical.scoring import (
    _score_limit,
    _score_macd,
    composite_score,
    detect_market_environment,
)
from technical.trend import breakout_check, support_resistance
from technical.volume import volume_analysis
from tests.helpers.market_data import generate_sideways

REPO_ROOT = Path(__file__).resolve().parents[2]
TECHNICAL_CLI = REPO_ROOT / "scripts" / "technical.py"


@pytest.fixture(scope="module")
def technical_cli():
    """加载 technical.py CLI 模块（脚本非包，需按路径加载）。"""
    spec = importlib.util.spec_from_file_location("technical_cli", TECHNICAL_CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _neutral_features():
    """全中性指标特征（无任何买卖信号）。"""
    return {
        "ma_system": {"alignment": "交叉震荡"},
        "macd": {"signal": 0, "divergence": "", "bar_trend": "绿柱缩小"},
        "kdj": {"signal": "正常"},
        "bollinger": {"position": 0.5, "bandwidth_desc": "正常带宽"},
        "rsi": {"rsi": 50},
        "volume": {"volume_price_signal": 0},
        "patterns": [],
        "valuation_score": 50,
    }


def _cli_input(technical_cli, quote, records=None):
    """构造 _compute_all 的 TechnicalInput。"""
    records = records or generate_sideways(80)
    closes, opens, highs, lows, volumes = technical_cli._parse_records(records)
    return technical_cli.TechnicalInput(
        closes=closes,
        opens=opens,
        highs=highs,
        lows=lows,
        volumes=volumes,
        records=records,
        board="主板",
        quote=quote,
    )


# ═══════════════════════════════════════════════════════════════
# M1: 缩量窗口 off-by-one
# ═══════════════════════════════════════════════════════════════


class TestVolumeShrinkWindow:
    """M1: 最多回溯 shrink_window=5 根，不得误报 6 日。"""

    def test_six_declining_days_reports_max_five(self):
        volumes = [100.0] * 25 + [60, 50, 40, 30, 20, 10]  # 6 日连续递减
        closes = [float(i) for i in range(1, 32)]
        r = volume_analysis(closes, volumes, shrink_window=5, shrink_min_days=3)
        assert r["shrink_signal"] == 1
        assert "连续5日缩量" in r["shrink_desc"]

    def test_exactly_five_declining_days(self):
        volumes = [100.0] * 25 + [60, 50, 40, 30, 20]  # 5 日连续递减
        closes = [float(i) for i in range(1, 31)]
        r = volume_analysis(closes, volumes, shrink_window=5, shrink_min_days=3)
        assert r["shrink_signal"] == 1
        assert "连续5日缩量" in r["shrink_desc"]

    def test_two_declining_days_no_signal(self):
        volumes = [100.0] * 28 + [50, 40]
        closes = [float(i) for i in range(1, 31)]
        r = volume_analysis(closes, volumes, shrink_window=5, shrink_min_days=3)
        assert r["shrink_signal"] == 0

    def test_small_window_no_crash(self):
        closes = [1.0, 2, 3, 4, 5, 6]
        volumes = [10.0, 9, 8, 7, 6, 5]
        r = volume_analysis(closes, volumes, shrink_window=5, shrink_min_days=3)
        assert r is not None
        assert r["shrink_signal"] in (0, 1)


# ═══════════════════════════════════════════════════════════════
# M2: breakout_check 回踩确认逻辑
# ═══════════════════════════════════════════════════════════════


class TestBreakoutCheck:
    """M2: 回踩确认中分支可达，语义正确。"""

    @staticmethod
    def _closes(n=24, base=10.0, step=0.05):
        return [base + i * step for i in range(n)]

    def test_breakout_maintain_after_cross(self):
        closes = self._closes()
        closes[22] = 11.6
        closes[23] = 11.6  # 已突破 11.5 后维持
        r = breakout_check(closes, closes, [1000] * 24, 11.5)
        assert r["status"] == "突破维持(回踩未破)"

    def test_pullback_confirmation_reachable(self):
        closes = self._closes()
        closes[22] = 11.6  # 此前突破过
        closes[23] = 11.47  # 今日回踩至阻力下方 1% 内
        r = breakout_check(closes, closes, [1000] * 24, 11.5)
        assert r["status"] == "回踩确认中"

    def test_never_broken(self):
        closes = [10.0] * 24  # 全在阻力下方
        r = breakout_check(closes, closes, [1000] * 24, 11.5)
        assert r["status"] == "未突破"

    def test_today_cross_with_volume_confirm(self):
        closes = self._closes()
        closes[23] = 11.6  # 今日首次站上（前一日 11.1 <= 阻力）
        volumes = [1000] * 23 + [3000]
        r = breakout_check(closes, closes, volumes, 11.5)
        assert r["status"] == "突破确认(放量)"

    def test_today_cross_without_volume_confirm(self):
        closes = self._closes()
        closes[23] = 11.6
        volumes = [1000] * 24
        r = breakout_check(closes, closes, volumes, 11.5)
        assert r["status"] == "突破待确认(缩量)"

    def test_integration_breakout_confirm(self):
        """全链路：前高 11.0 → 放量突破，support_resistance 提供 breakout_target。

        锁死"突破确认(放量)"经真实调用链可达（审查 P0-3 修复：
        原实现用 nearest_resistance（恒在现价上方）导致突破分支不可达）。
        """
        closes = (
            [10.0] * 10
            + [10.2, 10.4, 10.6, 10.8, 10.5] * 3
            + [11.0]  # 前高（摆动高点）
            + [10.3, 10.5, 10.7, 10.4, 10.6] * 4
            + [11.1, 11.6]  # 最后一根放量突破
        )
        highs = [c + 0.15 for c in closes]
        lows = [c - 0.15 for c in closes]
        volumes = [800.0] * (len(closes) - 2) + [800.0, 1800.0]

        sr = support_resistance(
            closes, highs, lows, {"ma_supports": [], "ma_resistances": []}
        )
        target = sr.get("breakout_target")
        assert target is not None  # 现价下方存在摆动高点
        r = breakout_check(closes, highs, volumes, target)
        assert r["status"] == "突破确认(放量)"

    def test_integration_no_swing_high_below(self):
        """无现价下方摆动高点（单调上涨）→ breakout_target 为 None，调用方跳过。"""
        closes = [10.0 + i * 0.1 for i in range(60)]
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes]
        sr = support_resistance(
            closes, highs, lows, {"ma_supports": [], "ma_resistances": []}
        )
        assert sr.get("breakout_target") is None


# ═══════════════════════════════════════════════════════════════
# H2: composite_score 缺失 features 归一化为中性
# ═══════════════════════════════════════════════════════════════


class TestCompositeScoreNeutral:
    """H2: 稀疏路径（stock_analysis.py 风格）与完整路径评分一致。"""

    def test_sparse_and_full_paths_agree(self):
        sparse = composite_score(dict(_neutral_features()), "普通股", "震荡")

        full = dict(_neutral_features())
        full["chan_theory"] = {"valid": False, "error": "未启用"}
        full["limit_analysis"] = {
            "streak_type": "无连板",
            "board_status": "正常交易",
            "streak_volume": "",
        }
        full["local_patterns"] = {"patterns": [], "summary": "未检测到形态"}
        full["chip"] = {"margin": {}, "holders": {}}
        full_score = composite_score(full, "普通股", "震荡")

        assert sparse["score"] == full_score["score"]

    def test_neutral_stock_is_neutral_grade(self):
        r = composite_score(dict(_neutral_features()), "普通股", "震荡")
        assert r["grade"] == "中性"
        assert 40 <= r["score"] < 55

    def test_limit_penalty_still_applies(self):
        features = dict(_neutral_features())
        features["limit_analysis"] = {
            "streak_type": "无连板",
            "board_status": "封跌停",
            "streak_volume": "",
        }
        penalized = composite_score(features, "普通股", "震荡")
        neutral = composite_score(dict(_neutral_features()), "普通股", "震荡")
        assert penalized["score"] < neutral["score"]

    def test_chan_buy_point_bonus_still_applies(self):
        features = dict(_neutral_features())
        features["chan_theory"] = {
            "valid": True,
            "maidian": {
                "buy_points": [{"type": "一买", "confidence": "高"}],
                "sell_points": [],
            },
            "beichi": {},
        }
        bonus = composite_score(features, "普通股", "震荡")
        neutral = composite_score(dict(_neutral_features()), "普通股", "震荡")
        assert bonus["score"] > neutral["score"]


# ═══════════════════════════════════════════════════════════════
# H3: macd bar_trend 透传（金叉+红柱放大 15 分）
# ═══════════════════════════════════════════════════════════════


class TestMacdBarTrend:
    """H3: bar_trend 缺失时金叉只能拿 10 分，补齐后 15 分。"""

    def test_golden_cross_with_amplifying_bar_scores_15(self):
        w = {"macd": 1.0}
        adj = {"divergence_bottom": 1.0, "overbought": 1.0}
        assert (
            _score_macd(
                {"signal": 1, "bar_trend": "红柱放大", "divergence": ""}, w, adj
            )
            == 15.0
        )

    def test_golden_cross_without_bar_trend_scores_10(self):
        w = {"macd": 1.0}
        adj = {"divergence_bottom": 1.0, "overbought": 1.0}
        assert _score_macd({"signal": 1, "divergence": ""}, w, adj) == 10.0

    def test_pipeline_exposes_macd_bar_trend(self):
        bars = [
            KlineBar(
                day=f"2026-01-{i + 1:02d}",
                open=10 + i * 0.1,
                high=10.2 + i * 0.1,
                low=9.8 + i * 0.1,
                close=10 + i * 0.1,
                volume=1000 + i * 50,
            )
            for i in range(60)
        ]
        ind = compute_indicators(bars)
        assert "macd_bar_trend" in ind
        assert ind["macd_bar_trend"] in ("红柱放大", "红柱缩小", "绿柱放大", "绿柱缩小")


# ═══════════════════════════════════════════════════════════════
# H1: PE 分位统一 + 估值评分极性
# ═══════════════════════════════════════════════════════════════


class TestPePercentileUnified:
    """H1: technical.py 路径与 strategies 路径同源，亏损股中性处理。"""

    def test_loss_making_stock_is_neutral_percentile(self):
        from strategies.factors.score_utils import pe_percentile

        assert pe_percentile(-5, "默认") == 50

    def test_technical_cli_path_uses_unified_percentile(self, technical_cli):
        features = technical_cli._compute_all(
            _cli_input(technical_cli, {"code": "sh600000", "pe": -5, "pb": 1.2})
        )
        assert features["valuation"]["pe_percentile"] == 50.0

    def test_valuation_polarity_cheap_higher_than_expensive(self, technical_cli):
        cheap = technical_cli._compute_all(
            _cli_input(
                technical_cli,
                {"code": "sh600000", "pe": 10, "pb": 1.5, "net_profit_yoy": 20},
            )
        )
        expensive = technical_cli._compute_all(
            _cli_input(
                technical_cli,
                {"code": "sh600000", "pe": 80, "pb": 8, "net_profit_yoy": 5},
            )
        )
        # 修复后：便宜股估值评分更高（原实现昂贵股反而得分更高）
        assert cheap["valuation_score"] > expensive["valuation_score"]


# ═══════════════════════════════════════════════════════════════
# M5: _score_limit adj 仅应用一次
# ═══════════════════════════════════════════════════════════════


class TestScoreLimit:
    """M5: 封涨停不再双重乘 adj.breakout。"""

    def test_breakout_adj_applied_once(self):
        adj_bull = {"breakout": 1.3, "divergence_bottom": 0.5}
        limit_data = {
            "streak_type": "首板",
            "board_status": "封涨停",
            "streak_volume": "缩量加速(强-惜售)",
        }
        # (5 + 3 + 3) × 1.3 = 14.3；原实现封涨停额外乘一次 1.3 → 15.47
        assert _score_limit(limit_data, {"limit": 1.0}, adj_bull) == pytest.approx(14.3)

    def test_no_signal_returns_zero(self):
        limit_data = {
            "streak_type": "无连板",
            "board_status": "正常交易",
            "streak_volume": "",
        }
        assert _score_limit(limit_data, {"limit": 1.0}, {}) == 0.0

    def test_limit_down_penalty_kept(self):
        limit_data = {
            "streak_type": "无连板",
            "board_status": "封跌停",
            "streak_volume": "",
        }
        assert _score_limit(limit_data, {"limit": 1.0}, {}) == -3.0


# ═══════════════════════════════════════════════════════════════
# M4: detect_market_environment 缺失数据
# ═══════════════════════════════════════════════════════════════


class TestMarketEnvironmentMissingData:
    """M4: 空 dict / 缺 turnover 不再误判。"""

    def test_empty_quote_is_missing_data(self):
        r = detect_market_environment({})
        assert r["state"] == "震荡"
        assert r["signals"] == ["大盘数据缺失，默认震荡"]

    def test_quote_without_turnover_no_ice_signal(self):
        r = detect_market_environment({"price": 3000, "change_pct": 0.2})
        assert not any("冰点" in s or "极度缩量" in s for s in r["signals"])

    def test_normal_quote_detects_bull(self):
        r = detect_market_environment(
            {"price": 3000, "change_pct": 1.8, "turnover": 3.0}
        )
        assert r["state"] == "强势"


# ═══════════════════════════════════════════════════════════════
# L1: 技术指标模块基础覆盖
# ═══════════════════════════════════════════════════════════════


class TestIndicatorBasics:
    """L1: 核心指标的基础正确性。"""

    def test_ma_system_bull_alignment(self):
        closes = [float(i) for i in range(1, 80)]  # 需 ≥60 根才有 MA5/10/20/60 四条均线
        ma = ma_system(closes)
        assert ma["alignment"] == "多头排列"
        assert ma["ma5"] is not None and ma["ma250"] is None

    def test_kdj_boll_rsi_basic(self):
        closes = [float(i) for i in range(1, 60)]
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        kdj = kdj_full(closes, highs, lows, board="主板")
        assert {"k", "d", "j"} <= kdj.keys()
        boll = bollinger(closes)
        assert boll["upper"] >= boll["mid"] >= boll["lower"]
        rsi = rsi_features(closes)
        assert 0 <= rsi["rsi"] <= 100

    def test_macd_full_basic(self):
        closes = [float(i) for i in range(1, 80)]
        macd = macd_full(closes)
        assert macd["signal"] in (0, 1, -1)
        assert macd["dif"] is not None

"""技术分析 P0 回归测试（v1.27.0）。

两个 P0：
1. **报告层 None 崩溃**：analyzer 把 `rsi_features(closes)`（数据不足时返回
   None）和 `support_resistance(...)`（数据不足时返回 None）原样写入 features，
   report 用 `features.get("rsi", {})` 取值——键存在但值为 None 时 get 返回
   None（默认值只在键缺失时生效），随后 `.get()` 抛 AttributeError。
   10~14 根 K 线的次新股/数据截断场景必崩。

2. **背驰方向丢失**：chan 的 beichi summary 只写"N个中枢盘整背驰"（方向全丢），
   scoring/signals 只对 summary 做字符串匹配 → 看跌的盘整背驰被当成看涨底背驰
   加 8 分并输出买入信号，顶背驰的卖出信号被 elif 挤掉（永不可达）。
"""

from __future__ import annotations

import pytest


class TestReportNoneSafety:
    """report 层不得因 features 子字段为 None 而崩溃。"""

    _META = {
        "code": "sh600000",
        "name": "测试",
        "price": 10.0,
        "date": "2026-11-01",
        "change_pct": 1.2,
        "board": "主板",
        "timestamp": "2026-11-01 15:00",
    }
    _SCORE = {"score": 50, "grade": "中性", "buy_signals": [], "sell_signals": []}

    @pytest.mark.parametrize(
        "feature_key",
        ["rsi", "support_resistance", "ma_system", "kdj", "macd", "bollinger", "volume", "wave"],
    )
    def test_none_feature_does_not_crash(self, feature_key):
        from technical.report import render_report

        lines = render_report({feature_key: None}, self._SCORE, {}, self._META)
        assert lines

    def test_empty_features_does_not_crash(self):
        from technical.report import render_report

        assert render_report({}, self._SCORE, {}, self._META)

    def test_analyzer_wraps_support_resistance(self):
        """analyzer 写入 features 前必须兜住 None（否则下一行 .get() 就崩）。"""
        import inspect

        from technical import analyzer

        src = inspect.getsource(analyzer)
        assert 'support_resistance(closes, highs, lows, features["ma_system"]) or {}' in src


class TestMarketEnvironmentAuthority:
    """市场状态判定：多日窗口不得覆盖 market_detector 的权威判定。

    market_detector 的判定层级：市场宽度 > K线 MA20/量比 > 单日涨跌幅。
    指数在 MA20 下方且量能萎缩（权威判定=熊市）时，不能仅因近 5 日均涨
    0.6% 就翻成"强势"——权重会随之从弱势调到强势，与判定完全相反。
    """

    def test_kline_authoritative_state_not_overridden(self):
        from technical.scoring import detect_market_environment

        recent = [{"change_pct": 0.6}] * 5
        env = detect_market_environment(
            {"price": 3000, "change_pct": 0.6},
            recent_quotes=recent,
            index_kline={"ma20": 3100, "volumes": [100] * 10 + [50] * 5},
        )
        # 权威判定为熊市 → 技术口径"弱势"
        assert env["state"] == "弱势"

    def test_fallback_path_uses_multi_day_meaning(self):
        """无 K 线（单日 fallback 路径）时，多日均值仍用于修正状态。"""
        from technical.scoring import detect_market_environment

        recent = [{"change_pct": 0.6}] * 5
        env = detect_market_environment({"price": 3000, "change_pct": 0.6}, recent_quotes=recent)
        assert env["state"] == "强势"

    def test_turnover_signal_reachable_in_multi_day_path(self):
        """换手率信号在多日窗口路径可达（此前恒为 0 → 永不触发）。"""
        from technical.scoring import detect_market_environment

        recent = [{"change_pct": 0.6} for _ in range(4)]
        recent.append({"change_pct": 0.6, "turnover": 6.5})
        env = detect_market_environment({"price": 3000, "change_pct": 0.6, "turnover": 6.5}, recent_quotes=recent)
        assert any("高换手率" in s for s in env["signals"])
        assert env["state"] == "亢奋"

    def test_turnover_not_diluted_by_missing_samples(self):
        """有值的换手率不得被无值样本稀释（0.57%/5 → 0.114% 会漏触发）。"""
        from technical.scoring import detect_market_environment

        recent = [{"change_pct": 0.1} for _ in range(4)]
        recent.append({"change_pct": 0.1, "turnover": 0.2})  # 极度缩量
        env = detect_market_environment({"price": 3000, "change_pct": 0.1, "turnover": 0.2}, recent_quotes=recent)
        assert any("极度缩量" in s for s in env["signals"])

    def test_no_turnover_data_means_no_turnover_signal(self):
        """无换手率数据时不产生换手率信号（不误触发冰点/亢奋）。"""
        from technical.scoring import detect_market_environment

        env = detect_market_environment({"price": 3000, "change_pct": 0.5}, recent_quotes=[{"change_pct": 0.5}] * 5)
        assert not any("换手率" in s or "缩量" in s for s in env["signals"])


class TestScoreNormalizationMonotonic:
    """可正可负子项的归一化必须单调，且与"无信号=中性 50"口径一致。

    原实现 raw==0 走中性 50 特例、raw>0 走连续映射，两套口径中性点不一致，
    导致"明确利好"得分低于"完全无信号"：
      limit 量程 [-3,15]：raw=5(首板) → 44.4 < 50
      chip  量程 [-5,10]：raw=2(融资净买入) → 46.7 < 50
    """

    @staticmethod
    def _normalize(key, val):
        from technical.scoring import _SCORE_NEGATIVE_MIN, _get_score_max, clamp

        max_val = _get_score_max()[key]
        neg_span = -_SCORE_NEGATIVE_MIN.get(key, 0)
        if neg_span > 0 and val <= 0:
            return clamp(50.0 + val / neg_span * 50.0, 0, 100)
        return clamp(50.0 + val / max_val * 50.0, 0, 100)

    @pytest.mark.parametrize("key", ["limit", "chip", "local"])
    def test_zero_is_neutral_anchor(self, key):
        assert self._normalize(key, 0) == pytest.approx(50.0)

    @pytest.mark.parametrize("key", ["limit", "chip", "local"])
    def test_monotonic_increasing(self, key):
        values = [self._normalize(key, v) for v in range(-5, 16)]
        assert all(b >= a for a, b in zip(values, values[1:]))

    def test_limit_first_limit_up_beats_no_signal(self):
        """首板(+5) 必须高于无信号(0)。"""
        assert self._normalize("limit", 5) > self._normalize("limit", 0)

    def test_chip_margin_buy_beats_no_signal(self):
        """chip 融资净买入(+2) 必须高于无信号(0)。"""
        assert self._normalize("chip", 2) > self._normalize("chip", 0)

    def test_negative_still_below_neutral(self):
        """看跌形态（负分）必须低于中性。"""
        assert self._normalize("local", -5) < 50
        assert self._normalize("limit", -3) < 50


class TestPatternAndLocalScoring:
    """形态评分与本土战法评分的口径修复（v1.27.0）。"""

    @staticmethod
    def _pat(name, ptype="看涨", date="2026-11-01", position="T-0", **kw):
        d = {"name": name, "type": ptype, "date": date, "position": position}
        d.update(kw)
        return d

    def test_pattern_score_order_independent(self):
        """同一组形态换个顺序，评分不得改变。"""
        from technical.scoring import _score_patterns

        bull = {"type": "早晨之星(底部反转)", "date": "2026-11-01", "position": "T-2~0"}
        bear = {"type": "黄昏之星(顶部反转)", "date": "2026-11-01", "position": "T-2~0"}
        tw = {"pattern": 1.0}
        assert _score_patterns([bull, bear], tw, {}) == _score_patterns([bear, bull], tw, {})

    def test_newer_pattern_wins_regardless_of_type(self):
        """更新的形态胜出（旧的看涨 vs 新的看跌 → 看跌）。"""
        from technical.scoring import _score_patterns

        old_bull = {"type": "早晨之星", "date": "2026-10-30", "position": "T-0"}
        new_bear = {"type": "黄昏之星", "date": "2026-11-01", "position": "T-2~0"}
        assert _score_patterns([old_bull, new_bear], {"pattern": 1.0}, {}) == 3.0

    def test_complete_pattern_beats_single_bar_same_day(self):
        """同日同位置时，跨度大的完整形态优先（三根形态 > 单根形态）。"""
        from technical.scoring import _score_patterns

        star = {"type": "早晨之星", "date": "2026-11-01", "position": "T-2~0"}
        hammer = {"type": "倒锤子", "date": "2026-11-01", "position": "T-0"}
        # 三根看涨（13）vs 单根看跌（3）→ 完整形态胜
        assert _score_patterns([star, hammer], {"pattern": 1.0}, {}) == 13.0

    def test_local_same_pattern_counted_once(self):
        """同名形态多次触发只计一次（与 signals 层 dedup 口径一致）。"""
        from technical.scoring import _score_local

        one = {"patterns": [self._pat("老鸭头", confidence="中")]}
        three = {"patterns": [self._pat("老鸭头", confidence="中")] * 3}
        assert _score_local(three) == _score_local(one)

    def test_local_different_patterns_still_accumulate(self):
        """不同形态仍累加（老鸭头 + 美人肩）。"""
        from technical.scoring import _score_local

        s = _score_local({"patterns": [self._pat("老鸭头"), self._pat("美人肩")]})
        assert s > _score_local({"patterns": [self._pat("老鸭头")]})

    def test_turtle_breakout_not_scored_zero(self):
        """海龟突破此前 _score_local 恒 0（无对应分支）→ 现在按 strength 计分。"""
        from technical.scoring import _score_local

        assert _score_local({"patterns": [self._pat("海龟突破", strength=5)]}) > 0
        assert _score_local({"patterns": [self._pat("海龟突破", strength=3)]}) > 0


class TestBeichiDirection:
    """背驰方向必须传递到评分与信号层。"""

    @staticmethod
    def _chan(trend=None, ranges=None, buy_points=None):
        return {
            "valid": True,
            "maidian": {"buy_points": buy_points or [], "sell_points": []},
            "beichi": {
                "trend_beichi": trend,
                "range_beichi": ranges or [],
                "summary": "x",
            },
        }

    def test_bearish_range_beichi_not_scored_as_bullish(self):
        """看跌的盘整背驰不得加看涨分。"""
        from technical.scoring import _score_chan

        chan = self._chan(ranges=[{"type": "盘整背驰(看跌)"}])
        assert _score_chan(chan, {"chan": 1.0}, {}) == 0.0

    def test_bullish_range_beichi_scored(self):
        from technical.scoring import _score_chan

        chan = self._chan(ranges=[{"type": "盘整背驰(看涨)"}])
        assert _score_chan(chan, {"chan": 1.0}, {}) > 0

    def test_top_beichi_produces_sell_signal(self):
        """顶背驰必须产出卖出信号（此前被 elif 永久挤掉）。"""
        from technical.signals import _generate_signals

        chan = self._chan(trend="顶背驰(看跌)")
        buy, sell, _structured = _generate_signals({"chan_theory": chan})
        assert any("顶背驰" in s for s in sell)
        assert not any("底背驰" in s for s in buy)

    def test_bearish_range_beichi_produces_sell_not_buy(self):
        from technical.signals import _generate_signals

        chan = self._chan(ranges=[{"type": "盘整背驰(看跌)"}])
        buy, sell, _structured = _generate_signals({"chan_theory": chan})
        assert any("顶背驰" in s for s in sell)
        assert not any("底背驰" in s for s in buy)

    def test_bullish_range_beichi_produces_buy(self):
        from technical.signals import _generate_signals

        chan = self._chan(ranges=[{"type": "盘整背驰(看涨)"}])
        buy, sell, _structured = _generate_signals({"chan_theory": chan})
        assert any("底背驰" in s for s in buy)
        assert not any("顶背驰" in s for s in sell)

    def test_beichi_summary_keeps_direction(self):
        """chan 的 summary 必须带方向信息（供人读与字符串消费方）。"""
        from chan.beichi import chan_beichi

        closes = [100.0] * 40
        c = 100.0
        for _ in range(15):
            c -= 1.0
            closes.append(round(c, 3))
        for i in range(22):
            c = 85.0 + (8.0 if i % 4 < 2 else 0.0)
            closes.append(round(c, 3))
        c = 90.0
        for _ in range(18):
            c -= 0.45
            closes.append(round(c, 3))

        def _bi(direction, s, e, s_low, s_high, e_low, e_high):
            def _fx(t, h, low, idx):
                return {
                    "type": t,
                    "bar": {"high": h, "low": low, "date": f"d{idx}", "idx": idx},
                    "idx": idx,
                }

            return {
                "start": _fx("底" if direction == "up" else "顶", s_high, s_low, s),
                "end": _fx("顶" if direction == "up" else "底", e_high, e_low, e),
                "direction": direction,
                "high": max(s_high, e_high),
                "low": min(s_low, e_low),
                "start_idx": s,
                "end_idx": e,
            }

        n = len(closes)
        bis = [
            _bi("up", 20, 39, 99, 101, 100, 102),
            _bi("down", 39, 55, 85, 100, 100, 101),
            _bi("up", 55, 62, 85, 86, 92, 92.5),
            _bi("down", 62, 70, 85.5, 86, 92, 92.5),
            _bi("up", 70, 77, 85.5, 86, 90, 90.5),
            _bi("down", 77, n - 1, 82.0, 89.5, 90, 90.5),
        ]
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx={f"d{i}": i for i in range(len(closes))})
        for rb in r["range_beichi"]:
            direction = "看涨" if "看涨" in rb["type"] else "看跌"
            assert direction in r["summary"]

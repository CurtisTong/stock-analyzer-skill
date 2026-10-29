"""market_detector 市场状态判定单测。

2026-10-29 修复（回测报告 §6 开放问题 #2）引入：
- 无 breadth_data + 有 kline_data 时退化判定（MA20/量比），此前宽度默认值
  0.5/1.0 卡在所有阈值外导致结果恒为震荡；
- fallback / 退化路径的 reason 如实标注判定依据（此前 fallback 返回
  "指数在均线上方，量能放大"等与实际依据不符的文案）。
有宽度数据时的完整判定路径保持不变（回归锚点锁定）。
"""

from experts.market_detector import classify_market_state, detect_market_state

PRICE_ABOVE = {"price": 10.5, "change_pct": 0.3}
PRICE_BELOW = {"price": 9.5, "change_pct": -0.3}
MA20 = 10.0


def _kline(vol_pattern: str) -> dict:
    """构造 kline_data。vol_pattern: heavy(1.33) / light(0.67) / mild(0.85)。"""
    patterns = {
        "heavy": [1000] * 10 + [2000] * 5,  # recent/base = 2000/1500
        "light": [2000] * 10 + [1000] * 5,  # 1000/1500
        "mild": [2000] * 10 + [1478] * 5,  # ≈0.85
    }
    return {"ma20": MA20, "volumes": patterns[vol_pattern]}


def _breadth(advance=0.5, high_low=1.0, limit_down=0, margin=0) -> dict:
    return {
        "advance_ratio": advance,
        "new_high_low_ratio": high_low,
        "limit_down_count": limit_down,
        "margin_ratio": margin,
    }


class TestFullBreadthUnchanged:
    """有宽度数据时完整判定路径行为不变（回归锚点）。"""

    def test_bull_full_conditions(self):
        r = detect_market_state(
            index_quote=PRICE_ABOVE,
            kline_data=_kline("heavy"),
            breadth_data=_breadth(advance=0.7, high_low=2.0),
        )
        assert r["state"] == "牛市"
        assert r["reason"] == "指数在均线上方，量能放大，市场宽度良好"

    def test_bear_full_conditions(self):
        r = detect_market_state(
            index_quote=PRICE_BELOW,
            kline_data=_kline("light"),
            breadth_data=_breadth(advance=0.3, high_low=0.3),
        )
        assert r["state"] == "熊市"

    def test_ice_full_conditions(self):
        r = detect_market_state(
            index_quote=PRICE_ABOVE,
            kline_data=_kline("light"),
            breadth_data=_breadth(advance=0.1, high_low=0.1, limit_down=80),
        )
        assert r["state"] == "冰点"

    def test_mania_full_conditions(self):
        quote = {**PRICE_ABOVE, "pe_percentile": 95}
        r = detect_market_state(
            index_quote=quote,
            kline_data=_kline("heavy"),
            breadth_data=_breadth(advance=0.8, margin=15),
        )
        assert r["state"] == "亢奋"

    def test_below_ma20_bull_conditions_not_bull(self):
        """宽度数据在位时，MA20 位置不满足则牛市分支不触发。"""
        r = detect_market_state(
            index_quote=PRICE_BELOW,
            kline_data=_kline("heavy"),
            breadth_data=_breadth(advance=0.7, high_low=2.0),
        )
        assert r["state"] == "震荡"


class TestDegradedNoBreadth:
    """无宽度数据 + 有 kline_data：退化判定（MA20/量比），修复前恒为震荡。"""

    def test_above_ma20_heavy_volume_bull(self):
        r = detect_market_state(index_quote=PRICE_ABOVE, kline_data=_kline("heavy"))
        assert r["state"] == "牛市"
        assert r["reason"].startswith("MA20/量比退化判定（无宽度数据）")

    def test_below_ma20_light_volume_bear(self):
        r = detect_market_state(index_quote=PRICE_BELOW, kline_data=_kline("light"))
        assert r["state"] == "熊市"

    def test_below_ma20_mild_volume_defensive(self):
        r = detect_market_state(index_quote=PRICE_BELOW, kline_data=_kline("mild"))
        assert r["state"] == "防御型"

    def test_above_ma20_light_volume_range(self):
        r = detect_market_state(index_quote=PRICE_ABOVE, kline_data=_kline("light"))
        assert r["state"] == "震荡"

    def test_below_ma20_heavy_volume_range(self):
        r = detect_market_state(index_quote=PRICE_BELOW, kline_data=_kline("heavy"))
        assert r["state"] == "震荡"


class TestFallbackReason:
    """无 kline_data 时涨跌幅简易判定，reason 如实标注判定依据。"""

    def test_fallback_bull_reason_honest(self):
        r = detect_market_state(index_quote={"price": 10.0, "change_pct": 1.0}, allow_price_fallback=True)
        assert r["state"] == "牛市"
        assert "涨跌幅简易判定" in r["reason"]
        assert "+1.0%" in r["reason"]

    def test_fallback_bear(self):
        r = detect_market_state(index_quote={"price": 10.0, "change_pct": -1.0}, allow_price_fallback=True)
        assert r["state"] == "熊市"

    def test_fallback_range(self):
        r = detect_market_state(index_quote={"price": 10.0, "change_pct": 0.1}, allow_price_fallback=True)
        assert r["state"] == "震荡"

    def test_no_data_defaults_defensive_with_original_reason(self):
        r = detect_market_state()
        assert r["state"] == "防御型"
        assert r["reason"] == "指数偏弱，低波/价值品种抗跌，成长品种承压，结构性分化"

    def test_no_fallback_allowed_defaults_defensive(self):
        r = detect_market_state(index_quote={"price": 10.0, "change_pct": 3.0})
        assert r["state"] == "防御型"


class TestClassifyMarketState:
    """classify_market_state 统一入口路由。"""

    def test_full_data_routes_to_detect(self):
        assert classify_market_state(index_quote=PRICE_ABOVE, kline_data=_kline("heavy")) == "牛市"

    def test_change_pct_routes_to_fallback(self):
        assert classify_market_state(change_pct=1.0) == "牛市"

    def test_limit_down_routes_to_ice(self):
        assert classify_market_state(limit_down=80) == "冰点"

    def test_nothing_routes_to_defensive(self):
        assert classify_market_state() == "防御型"


class TestDetectMarketEnvironmentPassthrough:
    """technical.scoring.detect_market_environment 透传 index_kline。"""

    def test_index_kline_drives_state(self):
        from technical.scoring import detect_market_environment

        r = detect_market_environment(
            index_quote={"price": 10.5, "change_pct": 0.3},
            index_kline=_kline("heavy"),
        )
        assert r["state"] == "强势"  # 牛市 → 技术口径映射
        assert any("牛市" in s for s in r["signals"])

    def test_without_index_kline_falls_back_to_change_pct(self):
        from technical.scoring import detect_market_environment

        r = detect_market_environment(
            index_quote={"price": 10.5, "change_pct": -2.5},
        )
        assert r["state"] == "弱势"
        assert any("涨跌幅简易判定" in s for s in r["signals"])

    def test_missing_quote_defaults_range(self):
        from technical.scoring import detect_market_environment

        r = detect_market_environment(index_quote={})
        assert r["state"] == "震荡"

"""T8 信号/评分一致性修复回归测试。

T8-a(P2)：KDJ 中性区金叉的字符串层 buy 与结构化层 ``kdj_golden_cross``
语义不一致（buy=[] 但结构化 True），现补弱参考买点使两层一致。

T8-b(P3)：MACD n=34 时 DEA 序列只有 1 个点，原实现用当前 dif 冒充
prev_dea，使 prev_bar 衡量 DIF 自身涨跌，输出伪造的"红柱放大"。
现无前值 DEA 时 bar_trend 直接置"数据不足"，金叉/死叉门控保持不变。
"""

from __future__ import annotations


def _generate(kdj_signal, dunhua=False, **extra_features):
    """构造最小 features 并调用信号汇总。"""
    from technical.signals import _generate_signals

    features = {"kdj": {"signal": kdj_signal, "钝化": dunhua}}
    features.update(extra_features)
    return _generate_signals(features)


class TestT8ANeutralGoldenCross:
    """中性区金叉两层语义一致；字段名与返回结构保持不变。"""

    def test_neutral_golden_cross_two_layers_consistent(self):
        """K 在中性区(20~80)金叉：结构化 True 时字符串层必须也报买点。"""
        buy, sell, structured = _generate("金叉")

        assert structured["kdj_golden_cross"] is True, "原始金叉事实应保留"
        assert "KDJ金叉(中性区,参考弱)" in buy, "两层语义冲突：结构化报金叉但 buy 为空"
        assert "KDJ超卖区金叉" not in buy, "中性区金叉不应复用超卖措辞"

    def test_oversold_golden_cross_regression(self):
        """真正的超卖金叉仍按原有强买点上报，不被弱买点重复替代。"""
        buy, sell, structured = _generate("金叉+超卖")

        assert "KDJ超卖区金叉" in buy
        assert "KDJ金叉(中性区,参考弱)" not in buy
        assert structured["kdj_golden_cross"] is True

    def test_dunhua_and_overbought_not_mislabeled_as_neutral(self):
        """钝化金叉两层仍暂停；超买金叉仍走卖出侧，不误标为中性区弱买。"""
        buy_dunhua, _, structured_dunhua = _generate("金叉", dunhua=True)
        assert buy_dunhua == []
        assert structured_dunhua["kdj_golden_cross"] is False

        buy_over, sell_over, _ = _generate("金叉+超买")
        assert "KDJ金叉(中性区,参考弱)" not in buy_over
        assert "KDJ金叉+超买" in sell_over

    def test_return_structure_stable(self):
        """下游依赖的返回结构与键集合不变。"""
        buy, sell, structured = _generate("金叉")
        assert isinstance(buy, list) and isinstance(sell, list) and isinstance(structured, dict)
        for key in ("kdj_golden_cross", "kdj_death_cross", "kdj_oversold", "kdj_overbought",
                    "macd_golden_cross", "macd_death_cross", "is_downtrend"):
            assert key in structured


# n=34 的确定性上涨序列：修复前 bar_trend 被伪造为"红柱放大"（signal=0）。
_N34_RISING_CLOSES = [
    100.0, 103.1971, 103.3262, 104.7471, 105.9161, 109.8163, 113.5319,
    118.5965, 119.112, 121.6248, 121.806, 123.1376, 126.249, 126.4165,
    127.6733, 131.822, 135.4137, 136.9063, 140.94, 146.644, 146.6917,
    152.602, 157.9289, 160.6157, 161.8643, 169.6112, 172.4657, 173.2655,
    174.1034, 181.481, 186.9592, 194.5042, 201.601, 207.0062,
]


def _patch_dif_dea(monkeypatch, dif_series, dea_series):
    """让 macd_full 使用手控 DIF/DEA 序列（dea 长度>=2）。"""
    import technical.macd as macd_mod

    n = len(dif_series)
    fake26 = [0.0] * n

    def fake_ema(values, period):
        if period == 12:
            return [dif_series[i] + fake26[i] for i in range(n)]
        if period == 26:
            return fake26
        if period == 9:
            return list(dea_series)
        raise AssertionError(f"unexpected period {period}")

    monkeypatch.setattr(macd_mod, "_ema_series", fake_ema)


class TestT8BMacdBarTrend:
    """n=34 无前值 DEA 时不伪造柱趋势；n>=35 行为不变。"""

    def test_n34_bar_trend_is_insufficient_data(self):
        """修复前该序列输出伪造的"红柱放大"，现应降级为"数据不足"。"""
        from technical.macd import macd_full

        out = macd_full(_N34_RISING_CLOSES)

        assert out["bar_trend"] == "数据不足"
        assert out["signal"] == 0, "金叉/死叉前值门控不得被破坏"

    def test_n34_returns_keys_unchanged(self):
        """降级描述字段不改变 macd_full 的返回键。"""
        from technical.macd import macd_full

        out = macd_full(_N34_RISING_CLOSES)
        assert set(out) == {
            "dif", "dea", "macd_bar", "signal", "signal_desc", "bar_trend", "divergence",
        }

    def test_n35_bar_trend_normal(self):
        """n>=35（有前值 DEA）时 bar_trend 仍为正常四态之一。"""
        from technical.macd import macd_full

        closes = _N34_RISING_CLOSES + [212.0]
        out = macd_full(closes)

        assert out["bar_trend"] in ("红柱放大", "红柱缩小", "绿柱放大", "绿柱缩小")
        assert out["bar_trend"] != "数据不足"

    def test_bar_trend_branch_with_prev_dea_preserved(self, monkeypatch):
        """有前值 DEA 时柱状图趋势分支计算与金叉信号不受影响。"""
        from technical.macd import macd_full

        _patch_dif_dea(monkeypatch, [0.1, 0.1, 1.0], [0.5, 0.5, 0.5])
        out = macd_full([float(i) for i in range(35)])

        assert out["signal"] == 1
        assert out["bar_trend"] == "红柱放大"

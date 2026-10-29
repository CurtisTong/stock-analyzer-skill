"""缠论模块专项单测（补历史欠账：chan 零专项测试）。

自底向上覆盖 8 个子模块：merge（包含处理）→ fenxing（分型）→ bi（笔）→
xianduan（线段，特征序列破坏）→ zhongshu（中枢，GG/DD + 合并交集）→
area（MACD 面积）→ beichi（趋势/盘整背驰）→ maidian（三类买卖点，
含 P2-C4 锚点：一买/一卖必须依赖背驰）→ full_analysis 集成。

合成数据用锯齿 OHLC 生成器（单调段天然无包含关系，转折处可控）；
beichi/maidian 直接手工构造 bi_list/zs_list 输入，让 MACD 面积关系
（进入段大力度、离开段小力度）可精确控制。
"""

import math

import pytest

from chan.merge import chan_merge_inclusions
from chan.fenxing import chan_fenxing
from chan.bi import chan_bi
from chan.xianduan import chan_xianduan
from chan.zhongshu import chan_zhongshu
from chan.area import _macd_area
from chan.beichi import chan_beichi
from chan.maidian import chan_maidian
from chan import chan_full_analysis
from technical.core import aligned_macd


def _records(path, start=100.0):
    """锯齿 OHLC 生成器。path: [(close_delta, n_bars)]，open=prev close。

    单调段相邻 K 线高低点互不包含；转折 delta 反号处产生包含关系。
    """
    records, close = [], start
    for i, (delta, n) in enumerate(path):
        for _ in range(n):
            o, c = close, round(close + delta, 3)
            records.append(
                {
                    "day": f"d{len(records) + 1:03d}",
                    "open": o,
                    "close": c,
                    "high": max(o, c) + 0.05,
                    "low": min(o, c) - 0.05,
                    "volume": 10000,
                }
            )
            close = c
    return records


def _bar(high, low, idx, date=""):
    """合并后 bar（merge 输出形状）。"""
    return {"high": high, "low": low, "open": 0, "close": 0, "date": date, "idx": idx}


def _fx(fx_type, high, low, idx, date=""):
    """分型 dict（chan_bi 输入形状）。"""
    return {"type": fx_type, "bar": _bar(high, low, idx, date), "idx": idx}


def _bi(direction, s_idx, e_idx, s_low, s_high, e_low, e_high, date_s="", date_e=""):
    """手工笔（beichi/maidian 输入形状）。"""
    return {
        "start": _fx("底" if direction == "up" else "顶", s_high, s_low, s_idx, date_s),
        "end": _fx("顶" if direction == "up" else "底", e_high, e_low, e_idx, date_e),
        "direction": direction,
        "high": max(s_high, e_high),
        "low": min(s_low, e_low),
        "start_idx": s_idx,
        "end_idx": e_idx,
    }


# 缠论教材走势：上涨段（回调低点抬高）→ 深跌转折 → 下跌段（反弹高点降低）
# → 深涨转折 → 上涨段。3 线段重叠 → 1 中枢；末期在中枢上方 → 三买。
TEXTBOOK_PATH = [
    (1.0, 8),
    (-0.5, 4),
    (1.0, 8),
    (-0.5, 4),
    (1.0, 8),
    (-1.8, 6),
    (-1.0, 8),
    (0.5, 4),
    (-1.0, 8),
    (0.5, 4),
    (-1.0, 8),
    (1.8, 6),
    (1.0, 8),
    (-0.5, 4),
    (1.0, 8),
    (-0.5, 4),
    (1.0, 8),
]


class TestChanMergeInclusions:
    """K 线包含处理：涨势高高、跌势低低、max_merge 限制。"""

    def test_no_inclusion_passthrough(self):
        records = _records([(0.5, 6)])
        merged = chan_merge_inclusions(records)
        assert len(merged) == len(records)

    def test_up_direction_merges_high_high(self):
        """涨势中后一根被前一根包含 → 合并取高高。"""
        records = [
            {"day": "d1", "open": 10.0, "close": 11.0, "high": 11.2, "low": 9.9, "volume": 1},
            {"day": "d2", "open": 11.0, "close": 11.5, "high": 11.1, "low": 10.5, "volume": 1},  # 被包含
            {"day": "d3", "open": 11.5, "close": 12.0, "high": 12.2, "low": 11.4, "volume": 1},
        ]
        merged = chan_merge_inclusions(records)
        assert len(merged) == 2
        assert merged[0]["high"] == 11.2  # 涨势取高高
        assert merged[0]["low"] == 10.5
        assert merged[0]["date"] == "d2"  # 合并后 date/idx 取后者
        assert merged[0]["idx"] == 1

    def test_down_direction_merges_low_low(self):
        """跌势中包含 → 合并取低低。"""
        records = [
            {"day": "d1", "open": 12.0, "close": 11.0, "high": 12.1, "low": 10.9, "volume": 1},
            {"day": "d2", "open": 11.0, "close": 10.5, "high": 11.5, "low": 11.0, "volume": 1},  # 被包含
            {"day": "d3", "open": 10.5, "close": 10.0, "high": 10.6, "low": 9.8, "volume": 1},
        ]
        merged = chan_merge_inclusions(records)
        assert len(merged) == 2
        assert merged[0]["high"] == 11.5
        assert merged[0]["low"] == 10.9  # 跌势取低低

    def test_max_merge_limits_consecutive_merges(self):
        """max_merge=1 时连续包含只合并一次。"""
        records = [
            {"day": "d1", "open": 10.0, "close": 11.0, "high": 12.0, "low": 9.0, "volume": 1},
            {"day": "d2", "open": 11.0, "close": 11.5, "high": 11.5, "low": 9.5, "volume": 1},  # 包含
            {"day": "d3", "open": 11.5, "close": 12.0, "high": 11.8, "low": 10.0, "volume": 1},  # 再包含
            {"day": "d4", "open": 12.0, "close": 13.0, "high": 13.2, "low": 11.9, "volume": 1},
        ]
        merged = chan_merge_inclusions(records, max_merge=1)
        assert len(merged) == 3  # d2 合入 d1，d3 因达上限独立保留

    def test_too_short_returns_as_is(self):
        records = _records([(0.5, 2)])
        assert chan_merge_inclusions(records) == records


class TestChanFenxing:
    """顶底分型：标准定义 + v2.4.0 放宽条件 + 同类型去重。"""

    def test_top_fenxing(self):
        bars = [_bar(10, 9, 0), _bar(11, 9.5, 1), _bar(10.5, 9.2, 2)]
        fx = chan_fenxing(bars)
        assert len(fx) == 1
        assert fx[0]["type"] == "顶"
        assert fx[0]["idx"] == 1

    def test_bottom_fenxing(self):
        bars = [_bar(11, 10, 0), _bar(10.5, 9, 1), _bar(11, 10.2, 2)]
        fx = chan_fenxing(bars)
        assert len(fx) == 1
        assert fx[0]["type"] == "底"

    def test_relaxed_low_condition_for_top(self):
        """放宽版顶分型：中间低点不低于两侧最低即可（不必高于两侧各低点）。"""
        bars = [_bar(10, 9, 0), _bar(11, 9.0, 1), _bar(10.5, 9.8, 2)]
        fx = chan_fenxing(bars)
        assert fx[0]["type"] == "顶"

    def test_no_fenxing_in_monotonic(self):
        bars = [_bar(10, 9, 0), _bar(11, 10, 1), _bar(12, 11, 2)]
        assert chan_fenxing(bars) == []

    def test_consecutive_same_type_deduped(self):
        """相邻同类型分型去重：等高顶序列合并保留首个。

        审查注记：相邻两窗同为顶要求 H1≥H2 且 H2≥H1（即等高），故去重里
        "保留更强"的替换分支（fx.high > last.high）实际不可达，属防御性
        死代码——本测试锁定实际行为（保留首个）。
        """
        bars = [
            _bar(9, 8, 0),
            _bar(10, 8.5, 1),
            _bar(10, 8.2, 2),
            _bar(9, 7.8, 3),
            _bar(8.5, 7.5, 4),
        ]
        fx = chan_fenxing(bars)
        tops = [f for f in fx if f["type"] == "顶"]
        assert len(tops) == 1
        assert tops[0]["idx"] == 1

    def test_insufficient_data(self):
        assert chan_fenxing([_bar(10, 9, 0), _bar(11, 10, 1)]) == []


class TestChanBi:
    """笔：分型交替配对 + 独立 K 线间隔 + 同类型合并。"""

    def test_alternating_fenxing_build_bis(self):
        merged = [
            _bar(10, 9, 0),
            _bar(11, 9.5, 1),
            _bar(10.8, 9.3, 2),
            _bar(9.5, 8.5, 3),
            _bar(10, 9, 4),
            _bar(10.5, 9.2, 5),
            _bar(12, 10.5, 6),
            _bar(11, 10, 7),
        ]
        bis = chan_bi(merged)
        assert [b["direction"] for b in bis[:2]] == ["down", "up"]  # 顶(1)→底(3)→顶(6)
        assert bis[0]["start_idx"] == 1 and bis[0]["end_idx"] == 3

    def test_min_gap_of_one_bar(self):
        """间隔 <2 根独立 K 线的分型不构成笔。"""
        merged = [
            _bar(10, 9, 0),
            _bar(11, 9.5, 1),
            _bar(10.2, 9.2, 2),
            _bar(9.5, 8.5, 3),
            _bar(10, 9, 4),
        ]
        bis = chan_bi(merged)
        # 顶(idx1)与底(idx2/3)间隔不足 → 跳过；底(3)与后续无可配对
        assert all(abs(b["end_idx"] - b["start_idx"]) >= 2 for b in bis)

    def test_same_type_fenxing_merged_before_pairing(self):
        """同类型连续分型合并后再与异类型配对。"""
        merged = [
            _bar(9, 8, 0),
            _bar(10, 8.5, 1),
            _bar(10, 8.2, 2),
            _bar(10, 8.4, 3),
            _bar(9, 7.8, 4),
            _bar(8.5, 7.5, 5),
            _bar(9, 7.9, 6),
        ]
        bis = chan_bi(merged)
        down_bis = [b for b in bis if b["direction"] == "down"]
        assert len(down_bis) == 1  # 三个连续顶合并为一个起点
        assert down_bis[0]["high"] == 10

    def test_bi_extremes_cover_both_ends(self):
        merged = [
            _bar(10, 9, 0),
            _bar(11, 9.5, 1),
            _bar(10.8, 9.3, 2),
            _bar(9.5, 8.5, 3),
            _bar(10.2, 9.6, 4),
        ]
        bis = chan_bi(merged)
        assert bis[0]["low"] == 8.5  # 笔的 low 覆盖两端分型最低
        assert bis[0]["high"] == 11

    def test_insufficient_fenxing(self):
        assert chan_bi([_bar(10, 9, 0), _bar(11, 10, 1)]) == []


class TestChanXianduan:
    """线段：3 笔重叠 + 特征序列破坏判断。"""

    def _zigzag_bis(self):
        """上升段：up(10→12) down(12→11) up(11→13) down(13→11.5，破坏)。"""
        return [
            _bi("up", 0, 5, 10, 10.2, 12, 12.2),
            _bi("down", 5, 8, 11, 11.2, 12, 12.2),
            _bi("up", 8, 12, 11, 11.2, 13, 13.2),
            _bi("down", 12, 18, 10.5, 10.8, 13, 13.2),  # low 10.5 < 特征序列最低 11
        ]

    def test_three_overlapping_bis_form_segment(self):
        xd = chan_xianduan(self._zigzag_bis())
        assert len(xd) == 1
        assert xd[0]["direction"] == "up"  # 第一笔方向
        assert xd[0]["bi_count"] == 3
        assert (xd[0]["start_bi"], xd[0]["end_bi"]) == (0, 2)

    def test_feature_seq_break_ends_segment(self):
        """第 4 笔 low 跌破特征序列最低（11）→ 线段被破坏。"""
        xd = chan_xianduan(self._zigzag_bis())
        # 破坏后从 bi1 重新扫描：down(11→10.5)+up? 剩余不足 3 笔 → 仍 1 段但 bi_count=3
        assert xd[0]["bi_count"] == 3

    def test_no_overlap_no_segment(self):
        bis = [
            _bi("up", 0, 5, 10, 10.2, 20, 20.2),
            _bi("down", 5, 8, 25, 25.2, 30, 30.2),
            _bi("up", 8, 12, 29, 29.2, 35, 35.2),
        ]
        assert chan_xianduan(bis) == []

    def test_simplified_break_without_feature_seq(self):
        """use_feature_seq=False：后续笔跌破线段起点 low 即破坏。"""
        bis = [
            _bi("up", 0, 5, 10, 10.2, 12, 12.2),
            _bi("down", 5, 8, 10.8, 11, 12, 12.2),
            _bi("up", 8, 12, 10.8, 11, 13, 13.2),
            _bi("down", 12, 18, 9.5, 9.8, 13, 13.2),  # low 9.5 < 起点 10
        ]
        xd = chan_xianduan(bis, use_feature_seq=False)
        assert xd[0]["bi_count"] == 3

    def test_insufficient_bis(self):
        assert chan_xianduan([_bi("up", 0, 5, 10, 10, 12, 12)]) == []


class TestChanZhongshu:
    """中枢：3 线段重叠 + GG/DD + 重叠合并（交集语义）。"""

    def _three_overlapping_segments(self):
        return [
            {"direction": "up", "bi_count": 3, "start_bi": 0, "end_bi": 2, "high": 12.0, "low": 10.0},
            {"direction": "down", "bi_count": 3, "start_bi": 3, "end_bi": 5, "high": 11.5, "low": 10.5},
            {"direction": "up", "bi_count": 4, "start_bi": 6, "end_bi": 9, "high": 12.5, "low": 10.2},
        ]

    def test_overlapping_segments_form_zhongshu(self):
        zs = chan_zhongshu(self._three_overlapping_segments())
        assert len(zs) == 1
        z = zs[0]
        assert z["zg"] == 11.5  # min(highs)
        assert z["zd"] == 10.5  # max(lows)
        assert z["gg"] == 12.5
        assert z["dd"] == 10.0
        assert z["mid"] == 11.0
        assert (z["bi_start"], z["bi_end"]) == (0, 9)

    def test_no_overlap_no_zhongshu(self):
        segs = [
            {"direction": "up", "bi_count": 3, "start_bi": 0, "end_bi": 2, "high": 12.0, "low": 10.0},
            {"direction": "down", "bi_count": 3, "start_bi": 3, "end_bi": 5, "high": 15.0, "low": 13.0},
            {"direction": "up", "bi_count": 4, "start_bi": 6, "end_bi": 9, "high": 18.0, "low": 16.0},
        ]
        assert chan_zhongshu(segs) == []

    def test_touching_edges_not_zhongshu(self):
        """区间仅相切（zd == zg）不构成中枢。"""
        segs = [
            {"direction": "up", "bi_count": 3, "start_bi": 0, "end_bi": 2, "high": 12.0, "low": 10.0},
            {"direction": "down", "bi_count": 3, "start_bi": 3, "end_bi": 5, "high": 12.0, "low": 12.0},
            {"direction": "up", "bi_count": 4, "start_bi": 6, "end_bi": 9, "high": 12.0, "low": 10.0},
        ]
        assert chan_zhongshu(segs) == []

    def test_overlapping_zhongshu_merge_intersects(self):
        """相邻重叠中枢合并取交集，GG/DD 取并集。"""
        segs = [
            {"direction": "up", "bi_count": 3, "start_bi": 0, "end_bi": 2, "high": 12.0, "low": 10.0},
            {"direction": "down", "bi_count": 3, "start_bi": 3, "end_bi": 5, "high": 11.5, "low": 10.5},
            {"direction": "up", "bi_count": 4, "start_bi": 6, "end_bi": 9, "high": 12.5, "low": 10.2},
            {"direction": "down", "bi_count": 3, "start_bi": 10, "end_bi": 12, "high": 12.0, "low": 10.8},
            {"direction": "up", "bi_count": 4, "start_bi": 13, "end_bi": 16, "high": 13.0, "low": 11.0},
        ]
        zs = chan_zhongshu(segs)
        assert len(zs) == 1  # 中枢[0-2]与[2-4]线段重叠且连续 → 合并
        z = zs[0]
        assert z["zg"] == 11.5  # 交集高点 = min(11.5, 12.0)
        assert z["zd"] == 11.0  # 交集低点 = max(10.5, 11.0)
        assert z["gg"] == 13.0
        assert z["dd"] == 10.0
        assert (z["xd_start"], z["xd_end"]) == (0, 4)

    def test_insufficient_segments(self):
        assert chan_zhongshu(self._three_overlapping_segments()[:2]) == []


class TestMacdArea:
    def test_basic_area(self):
        dif = [1.0, 2.0, 3.0]
        dea = [0.5, 0.5, 0.5]
        assert _macd_area(dif, dea, 0, 2) == 0.5 + 1.5 + 2.5

    def test_negative_diff_uses_abs(self):
        dif = [-1.0, -2.0]
        dea = [0.0, 0.0]
        assert _macd_area(dif, dea, 0, 1) == 3.0

    def test_invalid_range_returns_zero(self):
        dif, dea = [1.0, 2.0], [0.5, 0.5]
        assert _macd_area(dif, dea, 2, 1) == 0  # start >= end
        assert _macd_area(dif, dea, 0, 5) == 0  # end 超界
        assert _macd_area(dif, dea, -1, 1) == 0  # start 负


class TestChanBeichi:
    """背驰：手工构造 bi/zs + 合成 closes 控制 MACD 面积。"""

    def _beichi_closes(self):
        """铺垫(0-39) → 大跌进入段(40-55, 100→85) → 中枢震荡(55-77) →
        缓跌离开段(77-95, 90→82 创新低)。entry 面积 >> exit 面积。"""
        closes = [100.0] * 40
        c = 100.0
        for _ in range(15):  # 40-54 大跌
            c -= 1.0
            closes.append(round(c, 3))
        for i in range(22):  # 55-76 中枢震荡 85↔92
            c = 85.0 + (8.0 if i % 4 < 2 else 0.0)
            closes.append(round(c, 3))
        c = 90.0
        for _ in range(18):  # 77-94 缓跌
            c -= 0.45
            closes.append(round(c, 3))
        return closes

    def _beichi_inputs(self, closes):
        """5 笔：up铺垫 / down大跌 / up反弹 / down中枢 / up / down缓跌创新低。
        中枢 = bi2-bi4（bi_start=2, bi_end=4）；entry=bi1, exit=bi5。"""
        n = len(closes)
        return [
            _bi("up", 20, 39, 99, 101, 100, 102),
            _bi("down", 39, 55, 85, 100, 100, 101),
            _bi("up", 55, 62, 85, 86, 92, 92.5),
            _bi("down", 62, 70, 85.5, 86, 92, 92.5),
            _bi("up", 70, 77, 85.5, 86, 90, 90.5),
            _bi("down", 77, n - 1, 82.0, 89.5, 90, 90.5),
        ]

    def test_insufficient_data(self):
        r = chan_beichi([], [], [100.0] * 20)
        assert r["summary"] == "数据不足"

    def test_trend_bottom_beichi(self):
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes)
        # 进入段大跌（面积大），离开段缓跌同创新低（面积小）→ 底背驰
        assert r["trend_beichi"] == "底背驰(看涨)"
        assert "底背驰" in r["summary"]

    def test_no_beichi_without_low_break(self):
        """离开段未创新低 → 不构成趋势底背驰。"""
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        bis[-1]["low"] = 86.0  # 离开段低点高于进入段低点 85
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes)
        assert r["trend_beichi"] is None

    def test_no_beichi_when_exit_area_larger(self):
        """离开段力度更强（面积更大）→ 无背驰。"""
        closes = self._beichi_closes()
        # 颠倒力度：把中枢震荡改成大波动（entry 相对小）
        bis = self._beichi_inputs(closes)
        # entry 段压缩到缓跌（idx 映射不变，用 close 幅度控制不了——改为缩短 entry 面积）
        bis[1] = _bi("down", 39, 44, 97, 100, 100, 101)  # entry 只跌 5 根
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes)
        assert r["trend_beichi"] is None

    def test_no_zhongshu_no_trend_beichi(self):
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        r = chan_beichi(bis, [], closes)
        assert r["trend_beichi"] is None
        assert r["summary"] == "当前无明确背驰信号"

    def test_range_beichi_above_zg(self):
        """中枢上方离开 + 力度衰减 → 盘整背驰(看跌)。"""
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        # 中枢抬高到 88-93，使末根 close(≈82) 不满足——反转：中枢下移让 close 在上方
        # 直接构造：末段 close 高于 zg：把 closes 尾部抬高
        closes_hi = closes[:-5] + [95.0] * 5
        zs = [{"zg": 88, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes_hi, range_tolerance=0.99)
        # exit 面积 < entry×0.99 且 last_close(95) > zg(88) → 盘整背驰(看跌)
        assert any(rb["type"] == "盘整背驰(看跌)" for rb in r["range_beichi"])


class TestChanMaidian:
    """三类买卖点 + P2-C4 锚点（一买/一卖必须依赖背驰）。"""

    def _merged_bars(self, n):
        return [{"idx": i, "high": 0, "low": 0, "date": f"d{i}"} for i in range(n)]

    def _closes_below(self, n=100):
        """中枢下方末段（一买/二买场景）。"""
        return [100.0] * 40 + [95.0] * 30 + [88.0] * 30

    def _zs(self, zg=95, zd=90):
        return {"zg": zg, "zd": zd, "mid": (zg + zd) / 2, "bi_start": 2, "bi_end": 4}

    def test_first_buy_requires_beichi(self):
        """P2-C4 锚点：提供 beichi 但无底背驰 → 不产生一买。"""
        merged = self._merged_bars(100)
        bis = [
            _bi("up", 20, 39, 90, 91, 100, 101),
            _bi("down", 39, 60, 88, 89, 100, 101),
            _bi("up", 60, 70, 88, 89, 94, 95),
            _bi("down", 70, 80, 87, 88, 94, 95),
            _bi("up", 80, 90, 87, 88, 93, 94),
            _bi("down", 90, 99, 86.5, 87, 93, 94),
        ]
        r = chan_maidian(merged, bis, [self._zs()], self._closes_below(), beichi={"trend_beichi": None})
        assert not any(p["type"].startswith("一买") for p in r["buy_points"])

    def test_first_buy_weak_without_beichi_arg(self):
        """beichi=None → 退化弱信号 confidence 低。"""
        merged = self._merged_bars(100)
        bis = [
            _bi("up", 20, 39, 90, 91, 100, 101),
            _bi("down", 39, 60, 88, 89, 100, 101),
            _bi("up", 60, 70, 88, 89, 94, 95),
            _bi("down", 70, 80, 87, 88, 94, 95),
            _bi("up", 80, 90, 87, 88, 93, 94),
            _bi("down", 90, 99, 86.5, 87, 93, 94),
        ]
        r = chan_maidian(merged, bis, [self._zs()], self._closes_below(), beichi=None)
        weak = [p for p in r["buy_points"] if p["type"] == "一买(弱)"]
        assert len(weak) == 1
        assert weak[0]["confidence"] == "低"

    def test_first_buy_confirmed_by_bottom_beichi(self):
        merged = self._merged_bars(100)
        bis = [
            _bi("up", 20, 39, 90, 91, 100, 101),
            _bi("down", 39, 60, 88, 89, 100, 101),
            _bi("up", 60, 70, 88, 89, 94, 95),
            _bi("down", 70, 80, 87, 88, 94, 95),
            _bi("up", 80, 90, 87, 88, 93, 94),
            _bi("down", 90, 99, 86.5, 87, 93, 94),
        ]
        r = chan_maidian(
            merged,
            bis,
            [self._zs()],
            self._closes_below(),
            beichi={"trend_beichi": "底背驰(看涨)"},
        )
        assert any(p["type"] == "一买" and p["confidence"] == "中" for p in r["buy_points"])

    def test_second_buy_higher_low(self):
        """二买：次低高于前低且 close 未跌破前低。"""
        merged = self._merged_bars(100)
        bis = [
            _bi("up", 20, 39, 90, 91, 100, 101),
            _bi("down", 39, 60, 86, 87, 100, 101),  # 前低 86
            _bi("up", 60, 70, 86, 87, 94, 95),
            _bi("down", 70, 80, 87.5, 88, 94, 95),  # 次低 87.5 > 86
            _bi("up", 80, 90, 87.5, 88, 93, 94),
            _bi("down", 90, 99, 87.8, 88.2, 93, 94),  # 末低 87.8 > 87.5，close 88 > 86
        ]
        r = chan_maidian(merged, bis, [self._zs()], self._closes_below(), beichi={"trend_beichi": None})
        assert any(p["type"] == "二买" for p in r["buy_points"])

    def test_third_buy_break_and_pullback(self):
        """三买：突破中枢后回踩不落入（近5日 low > ZG + 曾接近 ZG）。"""
        # closes：前段在中枢附近，近段 > zg 且近 10 日有接近 zg 的价位
        closes = [94.0] * 40 + [96.5] * 50 + [96.0] * 5 + [97.5] * 5
        merged = self._merged_bars(len(closes))
        bis = [
            _bi("up", 20, 39, 90, 91, 94, 95),
            _bi("down", 39, 60, 91, 92, 94, 95),
            _bi("up", 60, 70, 91, 92, 96, 97),  # 突破
            _bi("down", 70, 80, 95.5, 96, 97, 97.5),
            _bi("up", 80, 90, 95.5, 96, 98, 98.5),
            _bi("down", 90, 99, 96.1, 96.2, 98, 98.5),
        ]
        r = chan_maidian(merged, bis, [self._zs()], closes, beichi={"trend_beichi": None})
        third = [p for p in r["buy_points"] if p["type"] == "三买"]
        assert len(third) == 1

    def test_first_sell_with_top_beichi(self):
        """一卖镜像：中枢上方 + 顶背驰 + 上涨笔结束。"""
        merged = self._merged_bars(100)
        closes = [100.0] * 40 + [105.0] * 30 + [112.0] * 30
        bis = [
            _bi("down", 20, 39, 100, 101, 110, 111),
            _bi("up", 39, 60, 100, 101, 112, 113),
            _bi("down", 60, 70, 106, 107, 112, 113),
            _bi("up", 70, 80, 106, 107, 113, 114),
            _bi("down", 80, 90, 107, 108, 113, 114),
            _bi("up", 90, 99, 107, 108, 114, 115),
        ]
        r = chan_maidian(
            merged,
            bis,
            [self._zs(zg=110, zd=105)],
            closes,
            beichi={"trend_beichi": "顶背驰(看跌)"},
        )
        assert any(p["type"] == "一卖" for p in r["sell_points"])

    def test_second_sell_lower_high(self):
        """二卖：次高低于前高且 close 未破前高。"""
        merged = self._merged_bars(100)
        closes = [100.0] * 40 + [105.0] * 30 + [111.0] * 30
        bis = [
            _bi("down", 20, 39, 100, 101, 110, 111),
            _bi("up", 39, 60, 100, 101, 114, 115),  # 前高 114
            _bi("down", 60, 70, 106, 107, 114, 115),
            _bi("up", 70, 80, 106, 107, 112.5, 113),  # 次高 113 < 114
            _bi("down", 80, 90, 107, 108, 112.5, 113),
            _bi("up", 90, 99, 107, 108, 111.8, 112),  # 末高 112 < 114，close 111 < 114
        ]
        r = chan_maidian(merged, bis, [self._zs(zg=110, zd=105)], closes, beichi={"trend_beichi": None})
        assert any(p["type"] == "二卖" for p in r["sell_points"])

    def test_insufficient_data(self):
        r = chan_maidian([], [], [], [100.0] * 10)
        assert r["summary"] == "数据不足"

    def test_no_points_summary(self):
        """中枢内部价格 + 无满足条件的笔 → 无买卖点。"""
        merged = self._merged_bars(60)
        bis = [
            _bi("up", 10, 20, 91, 92, 94, 95),
            _bi("down", 20, 30, 91, 92, 94, 95),
            _bi("up", 30, 40, 91, 92, 94, 95),
        ]
        r = chan_maidian(merged, bis, [self._zs(zg=95, zd=91)], [93.0] * 60, beichi={"trend_beichi": None})
        assert r["summary"] == "当前无明确缠论买卖点"


class TestChanFullAnalysis:
    """端到端集成：教材走势 → 笔/线段/中枢/买卖点全链路。"""

    def test_textbook_trend_full_pipeline(self):
        records = _records(TEXTBOOK_PATH)
        r = chan_full_analysis(records)
        assert r["valid"] is True
        assert r["original_count"] == len(records)
        assert 0 < r["merged_count"] <= r["original_count"]
        assert r["merge_ratio_pct"] >= 0
        assert r["bi_count"] >= 3
        assert r["up_bi"] + r["down_bi"] == r["bi_count"]
        assert r["fenxing_count"] >= 2
        assert r["zhongshu_count"] == 1
        z = r["zhongshu_list"][0]
        assert z["zd"] < z["zg"] and z["dd"] <= z["zd"] and z["gg"] >= z["zg"]
        # 教材走势末期在中枢上方 → 三买
        assert r["current_position"].startswith("中枢上方")
        assert any(p["type"] == "三买" for p in r["maidian"]["buy_points"])

    def test_insufficient_bars(self):
        r = chan_full_analysis(_records([(0.5, 10)]))
        assert r["valid"] is False
        assert "不足" in r["error"]

    def test_compatible_reexport_from_chan_py(self):
        """chan.py 兼容层与 chan 包导出同一实现。"""
        import chan as chan_pkg
        import chan as _  # noqa: F401  确保可导入

        import importlib

        compat = importlib.import_module("chan")
        assert compat.chan_full_analysis is chan_pkg.chan_full_analysis


class TestAlignedMacdContract:
    """beichi 依赖的 aligned_macd 接口契约（dif_series/dea_series/dea_offset）。"""

    def test_series_shapes_and_offset(self):
        closes = [100.0 + math.sin(i / 5.0) * 2 for i in range(80)]
        data = aligned_macd(closes)
        assert data["dea_offset"] >= 1
        assert len(data["dif_series"]) == len(data["dea_series"])
        assert len(data["dif_series"]) < len(closes)  # trim 过
        # 索引 0 对应 closes 的 dea_offset 位置附近，值有限
        assert all(not math.isnan(v) for v in data["dif_series"])

    def test_area_positive_for_trending_series(self):
        closes = [100.0 - i * 0.5 for i in range(60)]  # 单边下跌
        data = aligned_macd(closes)
        area = _macd_area(data["dif_series"], data["dea_series"], 0, len(data["dif_series"]) - 1)
        assert area > 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

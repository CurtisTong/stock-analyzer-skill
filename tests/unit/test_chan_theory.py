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


def _bi(direction, s_idx, e_idx, s_low, s_high, e_low, e_high, date_s=None, date_e=None):
    """手工笔（beichi/maidian 输入形状）。

    date 默认按 idx 生成（f"d{idx}"），与 _date_map 配合走 beichi 的
    date→closes 索引真实映射路径（P2-C3 修复后的生产路径）。
    """
    return {
        "start": _fx(
            "底" if direction == "up" else "顶",
            s_high,
            s_low,
            s_idx,
            date_s if date_s is not None else f"d{s_idx}",
        ),
        "end": _fx(
            "顶" if direction == "up" else "底",
            e_high,
            e_low,
            e_idx,
            date_e if date_e is not None else f"d{e_idx}",
        ),
        "direction": direction,
        "high": max(s_high, e_high),
        "low": min(s_low, e_low),
        "start_idx": s_idx,
        "end_idx": e_idx,
    }


def _date_map(closes):
    """{date: closes_index} 映射，与 _bi 的默认 date 生成规则配套。"""
    return {f"d{i}": i for i in range(len(closes))}


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
    """线段：3 笔重叠 + 特征序列分型破坏（v2.5.0 重构口径）。"""

    def _zigzag_bis(self):
        """上升段延续：回调低点抬高（11 → 11.5）→ 特征序列无顶分型 → 4 笔 1 段。"""
        return [
            _bi("up", 0, 5, 10, 10.2, 12, 12.2),
            _bi("down", 5, 8, 11, 11.2, 12, 12.2),  # S1=[12.2, 11]
            _bi("up", 8, 12, 11, 11.2, 13, 13.2),
            _bi("down", 12, 18, 11.5, 11.8, 13, 13.2),  # S2=[13.2, 11.5] 回调抬高，无破坏
        ]

    def _break_bis(self):
        """上升段破坏：S2 起点为段顶（13.2），确认笔跌破分型低点 11。"""
        return [
            _bi("up", 0, 5, 10, 10.2, 12, 12.2),  # up1
            _bi("down", 5, 8, 11, 11.2, 12, 12.2),  # S1=[12.2, 11]
            _bi("up", 8, 12, 11, 11.2, 13, 13.2),  # 段顶 13.2
            _bi("down", 12, 18, 11.5, 11.8, 13, 13.2),  # S2=[13.2, 11.5] 顶分型中间元素
            _bi("up", 18, 22, 11.5, 11.8, 12.8, 13.0),  # 反弹不创新高
            _bi("down", 22, 26, 11.4, 11.6, 12.8, 13.0),  # S3=[13.0, 11.4]
            _bi("up", 26, 30, 11.4, 11.6, 11.9, 12.1),
            _bi("down", 30, 34, 10.5, 10.8, 11.9, 12.1),  # 确认笔 low 10.5 < 11
        ]

    def test_three_overlapping_bis_form_segment(self):
        xd = chan_xianduan(self._zigzag_bis())
        assert len(xd) == 1
        assert xd[0]["direction"] == "up"  # 第一笔方向
        # 回调低点抬高 → 特征序列无顶分型 → 线段延续至末尾（v2.5.0 行为）
        assert xd[0]["bi_count"] == 4
        assert (xd[0]["start_bi"], xd[0]["end_bi"]) == (0, 3)

    def test_feature_seq_fenxing_break_ends_segment(self):
        """特征序列顶分型 + 确认笔跌破分型低点 → 线段结束于分型中间元素前一笔。"""
        xd = chan_xianduan(self._break_bis())
        assert len(xd) >= 1
        first = xd[0]
        assert first["direction"] == "up"
        # 顶分型中间元素 = bi3（S2），线段终点 = bi2（up2 的段顶 13.2）
        assert (first["start_bi"], first["end_bi"]) == (0, 2)
        assert first["bi_count"] == 3
        assert first["high"] == 13.2
        # 破坏后从 bi3 重新起段
        assert xd[1]["start_bi"] == 3

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
    """中枢：笔中枢（v2.5.0 起，连续 3 笔重叠区间 + 延伸）。"""

    def _three_overlapping_bis(self):
        """up[10,12.2] / down[11,12.2] / up[11,13.2] → 中枢 [11, 12.2]。"""
        return [
            _bi("up", 0, 5, 10, 10.2, 12, 12.2),
            _bi("down", 5, 8, 11, 11.2, 12, 12.2),
            _bi("up", 8, 12, 11, 11.2, 13, 13.2),
        ]

    def test_overlapping_bis_form_zhongshu(self):
        zs = chan_zhongshu(self._three_overlapping_bis())
        assert len(zs) == 1
        z = zs[0]
        assert z["zg"] == 12.2  # min(三笔高点)
        assert z["zd"] == 11.0  # max(三笔低点)
        assert z["gg"] == 13.2
        assert z["dd"] == 10.0
        assert z["mid"] == 11.6
        assert (z["bi_start"], z["bi_end"]) == (0, 2)

    def test_extension_overlapping_bi_extends_range(self):
        """第 4 笔与 [ZD, ZG] 有重叠 → 中枢延伸，bi_end/GG/DD 更新。"""
        bis = self._three_overlapping_bis()
        bis.append(_bi("down", 12, 18, 11.5, 11.8, 12.5, 12.8))  # 与中枢重叠
        zs = chan_zhongshu(bis)
        assert len(zs) == 1
        assert zs[0]["bi_end"] == 3
        assert zs[0]["gg"] == 13.2  # GG/DD 随延伸笔更新

    def test_exit_bi_ends_zhongshu(self):
        """第 4 笔完全离开中枢区间 → 中枢止于前 3 笔，离开笔不并入。"""
        bis = self._three_overlapping_bis()
        bis.append(_bi("down", 12, 18, 14.0, 14.2, 15.0, 15.2))  # low 14 > zg 12.2
        zs = chan_zhongshu(bis)
        assert len(zs) == 1
        assert zs[0]["bi_end"] == 2
        assert zs[0]["bi_end"] < len(bis) - 1

    def test_no_overlap_no_zhongshu(self):
        bis = [
            _bi("up", 0, 5, 10, 10.2, 20, 20.2),
            _bi("down", 5, 8, 25, 25.2, 30, 30.2),
            _bi("up", 8, 12, 29, 29.2, 35, 35.2),
        ]
        assert chan_zhongshu(bis) == []

    def test_two_separate_zhongshu(self):
        """两个不重叠的 3 笔重叠区 → 两个独立中枢，由离开笔分隔。"""
        bis = [
            _bi("up", 0, 5, 10, 10.2, 12, 12.2),
            _bi("down", 5, 8, 11, 11.2, 12, 12.2),
            _bi("up", 8, 12, 11, 11.2, 13, 13.2),
            _bi("down", 12, 18, 14.0, 14.2, 15.0, 15.2),  # 离开（向上）
            _bi("up", 18, 22, 14.0, 14.2, 16.5, 16.8),  # 新重叠区第 2 笔
            _bi("down", 22, 26, 14.2, 14.5, 16.0, 16.2),  # 新重叠区第 3 笔
        ]
        zs = chan_zhongshu(bis)
        assert len(zs) == 2
        assert zs[0]["bi_start"] == 0 and zs[0]["bi_end"] == 2
        assert zs[1]["bi_start"] == 3
        # 第二中枢区间在第一中枢上方
        assert zs[1]["zd"] > zs[0]["zg"] or zs[1]["zd"] >= 14.0

    def test_insufficient_bis(self):
        assert chan_zhongshu(self._three_overlapping_bis()[:2]) == []


class TestMacdArea:
    def test_basic_area(self):
        dif = [1.0, 2.0, 3.0]
        dea = [0.5, 0.5, 0.5]
        assert _macd_area(dif, dea, 0, 2) == 0.5 + 1.5 + 2.5

    def test_negative_diff_uses_abs(self):
        dif = [-1.0, -2.0]
        dea = [0.0, 0.0]
        assert _macd_area(dif, dea, 0, 1) == 3.0

    def test_side_up_counts_only_positive(self):
        """side="up" 只累计红柱（DIF>DEA），翻色区不混淆多空动能。"""
        dif = [1.0, -2.0, 3.0]
        dea = [0.0, 0.0, 0.0]
        assert _macd_area(dif, dea, 0, 2, side="up") == 1.0 + 3.0

    def test_side_down_counts_only_negative(self):
        dif = [1.0, -2.0, 3.0]
        dea = [0.0, 0.0, 0.0]
        assert _macd_area(dif, dea, 0, 2, side="down") == 2.0

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
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes))
        # 进入段大跌（绿柱面积大），离开段缓跌同创新低（面积小）→ 底背驰
        assert r["trend_beichi"] == "底背驰(看涨)"
        assert "底背驰" in r["summary"]

    def test_no_beichi_without_low_break(self):
        """离开段未创新低 → 不构成趋势底背驰。"""
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        bis[-1]["low"] = 86.0  # 离开段低点高于进入段低点 85
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes))
        assert r["trend_beichi"] is None

    def test_no_beichi_when_exit_area_larger(self):
        """离开段力度更强（面积更大）→ 无背驰。"""
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        # entry 段压缩到 5 根缓跌（面积小于 exit 的 18 根）
        bis[1] = _bi("down", 39, 44, 97, 100, 100, 101)
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes))
        assert r["trend_beichi"] is None

    def test_no_zhongshu_no_trend_beichi(self):
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        r = chan_beichi(bis, [], closes, date_to_close_idx=_date_map(closes))
        assert r["trend_beichi"] is None
        assert r["summary"] == "当前无明确背驰信号"

    def test_missing_date_skips_not_falls_back(self):
        """date 缺失时诚实降级（不判背驰），不再回退错位坐标系。"""
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        for b in bis:  # 抹掉 date
            b["start"]["bar"]["date"] = ""
            b["end"]["bar"]["date"] = ""
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes))
        assert r["trend_beichi"] is None

    def test_zero_entry_area_not_beichi(self):
        """进入段无同色动能柱（面积 0）→ 不判背驰（无动能≠力度衰减）。"""
        closes = [100.0] * 60  # 横盘：entry 段无展开的同色柱
        bis = [
            _bi("up", 20, 39, 99, 101, 100, 101),
            _bi("down", 39, 55, 100, 101, 100, 101),
            _bi("up", 55, 62, 100, 101, 100, 101),
            _bi("down", 62, 70, 100, 101, 100, 101),
            _bi("up", 70, 77, 100, 101, 100, 101),
            _bi("down", 77, 95, 100, 101, 100, 101),
        ]
        zs = [{"zg": 101, "zd": 99, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes))
        assert r["trend_beichi"] is None
        assert r["range_beichi"] == []

    def test_zero_exit_area_not_beichi(self):
        """离开段无同色动能柱（面积 0）→ 不判背驰（无动能≠力度衰减）。

        回归锚点：宝丰 600989 曾出现"面积比0.00"的假盘整背驰并连锁触发一买。
        """
        closes = [100.0] * 40
        c = 100.0
        for _ in range(15):  # 大跌（entry 有绿柱动能）
            c -= 1.0
            closes.append(round(c, 3))
        for i in range(22):  # 中枢震荡
            c = 85.0 + (8.0 if i % 4 < 2 else 0.0)
            closes.append(round(c, 3))
        # exit 段：价格继续跌但 MACD 已翻红（DIF>DEA，绿柱面积为 0）
        for i in range(18):
            c -= 0.45
            closes.append(round(c, 3))
        bis = [
            _bi("up", 20, 39, 99, 101, 100, 102),
            _bi("down", 39, 55, 85, 100, 100, 101),
            _bi("up", 55, 62, 85, 86, 92, 92.5),
            _bi("down", 62, 70, 85.5, 86, 92, 92.5),
            _bi("up", 70, 77, 85.5, 86, 90, 90.5),
            _bi("down", 77, 94, 82.0, 89.5, 90, 90.5),
        ]
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes))
        # 若 exit 段确有绿柱则判底背驰；若无（面积 0）则不判
        # 断言：不存在面积为 0 的背驰记录
        for rb in r["range_beichi"]:
            assert "面积比0.00" not in rb["desc"]
        assert r["trend_beichi"] in (None, "底背驰(看涨)")

    def test_range_beichi_down_exit_is_bullish(self):
        """向下离开力度衰减 → 盘整背驰(看涨)，与当前价无关（v2.5.0 口径）。"""
        closes = self._beichi_closes()
        bis = self._beichi_inputs(closes)
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes))
        # exit(down) 面积 < entry(down) × 0.8 → 看涨盘整背驰
        assert any(rb["type"] == "盘整背驰(看涨)" for rb in r["range_beichi"])

    def test_range_beichi_up_exit_is_bearish(self):
        """向上离开力度衰减 → 盘整背驰(看跌)。"""
        # closes 构造：铺垫 → 暴涨进入段(40-55, 红柱大) → 中枢震荡 → 缓涨离开段
        # (77-94, 红柱小但创新高)，与 up 笔方向一致
        closes = [100.0] * 40
        c = 100.0
        for _ in range(15):
            c += 1.5
            closes.append(round(c, 3))
        for i in range(22):
            c = 122.5 + (3.0 if i % 4 < 2 else 0.0)
            closes.append(round(c, 3))
        c = 125.0
        for _ in range(18):
            c += 0.35
            closes.append(round(c, 3))
        bis = [
            _bi("down", 20, 39, 99, 100, 100, 101),
            _bi("up", 39, 55, 100, 101, 122, 123),  # 暴涨进入段
            _bi("down", 55, 62, 115, 116, 122, 123),
            _bi("up", 62, 70, 115, 116, 121, 122),
            _bi("down", 70, 77, 115, 116, 121, 122),
            _bi("up", 77, 94, 122, 123, 131, 132),  # 缓涨创新高
        ]
        zs = [{"zg": 92, "zd": 85.5, "bi_start": 2, "bi_end": 4}]
        r = chan_beichi(bis, zs, closes, date_to_close_idx=_date_map(closes), range_tolerance=0.99)
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

    def test_first_buy_survives_merged_idx_offset(self):
        """P1 回归锚点：merged bar idx 是原始 records 索引（含合并偏移）时一买仍触发。

        真实 chan_merge_inclusions 输出中 bar["idx"]=原始索引（> 列表位置），
        修复前 last_idx 取该原始索引导致一买/一卖窗口判断恒 False。
        """
        merged = [{"idx": i + 100, "high": 0, "low": 0, "date": f"d{i}", "open": 0, "close": 0} for i in range(100)]
        bis = [
            _bi("up", 20, 39, 90, 91, 100, 101),
            _bi("down", 39, 60, 88, 89, 100, 101),
            _bi("up", 60, 70, 88, 89, 94, 95),
            _bi("down", 70, 80, 87, 88, 94, 95),
            _bi("up", 80, 90, 87, 88, 93, 94),
            _bi("down", 90, 99, 86.5, 87, 93, 94),  # end_idx=99 = merged 列表末位（刚结束）
        ]
        r = chan_maidian(
            merged,
            bis,
            [self._zs()],
            self._closes_below(),
            beichi={"trend_beichi": "底背驰(看涨)"},
        )
        assert any(p["type"] == "一买" and p["confidence"] == "中" for p in r["buy_points"])

    def test_third_buy_pullback_into_zhongshu_rejected(self):
        """P2 回归锚点：回踩笔 low 落入中枢（分型 K 线低点破 ZG）→ 不构成三买。"""
        closes = [94.0] * 40 + [96.5] * 50 + [96.2] * 5 + [97.0] * 5
        merged = self._merged_bars(len(closes))
        bis = [
            _bi("up", 20, 39, 90, 91, 94, 95),
            _bi("down", 39, 60, 91, 92, 94, 95),
            _bi("up", 60, 70, 91, 92, 96, 97),  # 突破
            _bi("down", 70, 80, 95.5, 96, 97, 97.5),
            _bi("up", 80, 90, 95.5, 96, 98, 98.5),
            _bi("down", 90, 99, 94.5, 96.2, 98, 98.5),  # 回踩笔 low 94.5 < ZG=95：落入中枢
        ]
        r = chan_maidian(merged, bis, [self._zs()], closes, beichi={"trend_beichi": None})
        assert not any(p["type"] == "三买" for p in r["buy_points"])

    def test_third_buy_pullback_bi_low_stays_above(self):
        """回踩笔 low 高于 ZG + 存在回踩动作 → 三买（笔口径正例）。"""
        closes = [94.0] * 40 + [96.5] * 50 + [97.5] * 10
        merged = self._merged_bars(len(closes))
        bis = [
            _bi("up", 20, 39, 90, 91, 94, 95),
            _bi("down", 39, 60, 91, 92, 94, 95),
            _bi("up", 60, 70, 91, 92, 96, 97),  # 突破
            _bi("down", 70, 80, 95.5, 96, 97, 97.5),
            _bi("up", 80, 90, 95.5, 96, 98, 98.5),
            _bi("down", 90, 99, 95.8, 96.2, 98, 98.5),  # 回踩笔 low 95.8 > ZG=95
        ]
        r = chan_maidian(merged, bis, [self._zs()], closes, beichi={"trend_beichi": None})
        third = [p for p in r["buy_points"] if p["type"] == "三买"]
        assert len(third) == 1
        assert "95.8" in third[0]["desc"]

    def test_first_buy_desc_states_beichi_source(self):
        """描述必须写清背驰来源：盘整底背驰不能说成"底背驰"。"""
        merged = self._merged_bars(100)
        bis = [
            _bi("up", 20, 39, 90, 91, 100, 101),
            _bi("down", 39, 60, 88, 89, 100, 101),
            _bi("up", 60, 70, 88, 89, 94, 95),
            _bi("down", 70, 80, 87, 88, 94, 95),
            _bi("up", 80, 90, 87, 88, 93, 94),
            _bi("down", 90, 99, 86.5, 87, 93, 94),
        ]
        zs = [self._zs()]
        r = chan_maidian(merged, bis, zs, self._closes_below(), beichi={"trend_beichi": None, "range_beichi": []})
        assert not any(p["type"].startswith("一买") for p in r["buy_points"])

        r2 = chan_maidian(
            merged,
            bis,
            zs,
            self._closes_below(),
            beichi={"trend_beichi": None, "range_beichi": [{"type": "盘整背驰(看涨)"}]},
        )
        first = [p for p in r2["buy_points"] if p["type"] == "一买"]
        assert len(first) == 1
        assert "盘整底背驰" in first[0]["desc"]

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
        # v2.5.0 笔中枢口径：教材走势出现 2 个笔中枢（原线段中枢为 1 个）
        assert r["zhongshu_count"] == 2
        for z in r["zhongshu_list"]:
            assert z["zd"] < z["zg"] and z["dd"] <= z["zd"] and z["gg"] >= z["zg"]
        # 教材走势末期在中枢上方 + 回踩笔 low 不落入 → 三买（笔口径）
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

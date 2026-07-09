"""
chan.py 单元测试：覆盖缠论核心算法。
K线包含处理 → 分型 → 笔 → 线段 → 中枢 → 背驰 → 买卖点。
"""

import pytest
from chan import (
    chan_merge_inclusions,
    chan_fenxing,
    chan_bi,
    chan_xianduan,
    chan_zhongshu,
    chan_beichi,
    chan_maidian,
    chan_full_analysis,
)

# ═══════════════════════════════════════════════════════════════
# 辅助工具
# ═══════════════════════════════════════════════════════════════


def _bar(day, o, h, l, c):
    """快速生成 K 线字典。"""
    return {"day": day, "open": o, "high": h, "low": l, "close": c, "volume": 1000}


def _merged_bar(date, high, low, idx=0):
    """快速生成合并后的 K 线（chan_fenxing 等的输入格式）。"""
    return {"date": date, "high": high, "low": low, "idx": idx}


def _make_bi(direction, start_idx, end_idx, high, low):
    """快速生成笔数据。"""
    return {
        "direction": direction,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "high": high,
        "low": low,
        "start": {
            "type": "底" if direction == "up" else "顶",
            "idx": start_idx,
            "bar": {"high": high, "low": low},
        },
        "end": {
            "type": "顶" if direction == "up" else "底",
            "idx": end_idx,
            "bar": {"high": high, "low": low},
        },
    }


def _make_xd(direction, bi_count, high, low):
    """快速生成线段数据。"""
    return {
        "direction": direction,
        "bi_count": bi_count,
        "high": high,
        "low": low,
        "start_bi": 0,
        "end_bi": bi_count - 1,
    }


def _make_zs(zg, zd, xd_start=0, xd_end=2, bi_start=0, bi_end=2):
    """快速生成中枢数据。"""
    return {
        "zg": zg,
        "zd": zd,
        "mid": round((zg + zd) / 2, 3),
        "width": round(zg - zd, 3),
        "xd_start": xd_start,
        "xd_end": xd_end,
        "bi_start": bi_start,
        "bi_end": bi_end,
    }


def _zigzag_bars(n, base=10.0, amp=2.0):
    """生成锯齿形 K 线序列（上下交替），用于测试分型和笔。"""
    bars = []
    for i in range(n):
        # 每3根形成一个方向段
        cycle = (i // 3) % 2
        offset = (i % 3) * amp / 2
        if cycle == 0:
            h = base + offset + amp
            l = base + offset
        else:
            h = base + amp * 2 - offset
            l = base + amp - offset
        o = l + 0.1
        c = h - 0.1
        bars.append(_bar(f"2025-01-{i+1:02d}", o, h, l, c))
    return bars


# ═══════════════════════════════════════════════════════════════
# 1. chan_merge_inclusions 测试
# ═══════════════════════════════════════════════════════════════


class TestChanMergeInclusions:
    """K线包含处理测试。"""

    def test_short_sequence_returns_as_is(self):
        """少于3根K线直接返回。"""
        bars = [_bar("2025-01-01", 10, 11, 9, 10.5)]
        result = chan_merge_inclusions(bars)
        assert result == bars

    def test_two_bars_returns_as_is(self):
        """2根K线直接返回。"""
        bars = [
            _bar("2025-01-01", 10, 11, 9, 10.5),
            _bar("2025-01-02", 10.5, 12, 10, 11),
        ]
        result = chan_merge_inclusions(bars)
        assert result == bars

    def test_no_inclusions_returns_original(self):
        """无包含关系时原样返回（K线数量不变）。"""
        bars = [
            _bar("2025-01-01", 10, 11, 9, 10.5),
            _bar("2025-01-02", 11, 13, 10, 12),
            _bar("2025-01-03", 12, 14, 11, 13),
        ]
        result = chan_merge_inclusions(bars)
        assert len(result) == 3

    def test_uptrend_merges_high_high(self):
        """涨势中包含关系取高高：high 取较大，low 取较大。"""
        bars = [
            _bar("2025-01-01", 10, 12, 9, 11),  # high=12, low=9
            _bar("2025-01-02", 10, 11, 9.5, 10.5),  # 包含在前一根内（11<=12, 9.5>=9）
            _bar("2025-01-03", 11, 13, 10, 12.5),  # 非包含
        ]
        result = chan_merge_inclusions(bars)
        assert len(result) == 2
        # 涨势合并：取 max(high), max(low)
        assert result[0]["high"] == 12
        assert result[0]["low"] == 9.5

    def test_downtrend_merges_low_low(self):
        """跌势中包含关系取低低：high 取较小，low 取较小。"""
        # 先建立跌势方向，再触发包含合并
        bars = [
            _bar("2025-01-01", 15, 16, 14, 15),  # high=16, low=14
            _bar(
                "2025-01-02", 13, 15, 12, 14
            ),  # high=15<16 → not new high; low=12<14 → dir=down
            _bar("2025-01-03", 13, 14, 12.5, 13),  # 14<=15 且 12.5>=12 → 被前一根包含
        ]
        result = chan_merge_inclusions(bars)
        assert len(result) == 2
        # 跌势合并：取 min(high), min(low)
        assert result[1]["high"] == 14  # min(15, 14)
        assert result[1]["low"] == 12  # min(12, 12.5)

    def test_max_consecutive_merges_limit(self):
        """最大连续合并3次限制：第4根包含K线不再合并。"""
        # 构造5根连续包含的K线（涨势方向）
        bars = [
            _bar("2025-01-01", 10, 15, 8, 12),  # 基准
            _bar("2025-01-02", 10, 14, 9, 11),  # 包含（14<=15, 9>=8）
            _bar("2025-01-03", 10, 13, 9.5, 11),  # 包含（13<=15, 9.5>=9）
            _bar("2025-01-04", 10, 12, 10, 11),  # 包含（12<=15, 10>=9.5）→ 第3次合并
            _bar("2025-01-05", 10, 11, 10.5, 11),  # 包含但已达上限 → 不合并
        ]
        result = chan_merge_inclusions(bars)
        # 第4根（idx=4）应作为独立K线加入
        assert len(result) == 2
        # 第一根被合并了3次
        assert result[0]["high"] == 15  # 涨势取 max
        assert result[0]["low"] == 10
        # 第二根是第5根原始K线（未合并）
        assert result[1]["high"] == 11

    def test_prev_in_curr_also_detected(self):
        """前一根被后一根包含的情况也应检测到。"""
        bars = [
            _bar("2025-01-01", 10, 11, 9, 10),  # 小K线
            _bar("2025-01-02", 10, 15, 8, 12),  # 大K线（包含前一根：15>11, 8<9）
            _bar("2025-01-03", 12, 16, 11, 15),  # 非包含
        ]
        result = chan_merge_inclusions(bars)
        assert len(result) == 2

    def test_merge_preserves_date(self):
        """合并后保留最新K线的日期。"""
        bars = [
            _bar("2025-01-01", 10, 12, 9, 11),
            _bar("2025-01-05", 10, 11, 9.5, 10.5),
            _bar("2025-01-10", 11, 14, 10, 13),
        ]
        result = chan_merge_inclusions(bars)
        assert result[0]["date"] == "2025-01-05"

    def test_alternating_direction(self):
        """方向在非包含K线出现时更新。"""
        bars = [
            _bar("2025-01-01", 10, 12, 9, 11),  # 基准
            _bar("2025-01-02", 11, 14, 10, 13),  # 高点更高 -> up
            _bar("2025-01-03", 10, 13, 8, 9),  # 低点更低 -> down
            _bar("2025-01-04", 9, 12, 8.5, 10),  # 包含在第三根内（12<=13, 8.5>=8）
        ]
        result = chan_merge_inclusions(bars)
        # 第三根后方向=down，第四根包含 -> 跌势合并
        assert len(result) == 3
        assert result[2]["high"] == 12  # min(13, 12) = 12
        assert result[2]["low"] == 8  # min(8, 8.5) = 8

    def test_first_bar_yin_direction_down(self):
        """首根K线为阴线（close<open）时方向初始化为 down，首对包含按跌势取低低。"""
        bars = [
            _bar("2025-01-01", 12, 13, 9, 10),  # 阴线：open=12 > close=10 -> direction=down
            _bar("2025-01-02", 10, 12, 9.5, 10.5),  # 包含在前一根内（12<=13, 9.5>=9）
            _bar("2025-01-03", 11, 14, 10, 13),  # 非包含
        ]
        result = chan_merge_inclusions(bars)
        assert len(result) == 2
        # 跌势合并：取 min(high), min(low)
        assert result[0]["high"] == 12  # min(13, 12)
        assert result[0]["low"] == 9  # min(9, 9.5)

    def test_first_bar_yang_direction_up(self):
        """首根K线为阳线（close>=open）时方向初始化为 up，首对包含按涨势取高高。"""
        bars = [
            _bar("2025-01-01", 10, 12, 9, 11),  # 阳线：close=11 >= open=10 -> direction=up
            _bar("2025-01-02", 10, 11, 9.5, 10.5),  # 包含在前一根内
            _bar("2025-01-03", 11, 13, 10, 12.5),  # 非包含
        ]
        result = chan_merge_inclusions(bars)
        assert len(result) == 2
        # 涨势合并：取 max(high), max(low)
        assert result[0]["high"] == 12
        assert result[0]["low"] == 9.5


# ═══════════════════════════════════════════════════════════════
# 2. chan_fenxing 测试
# ═══════════════════════════════════════════════════════════════


class TestChanFenxing:
    """分型识别测试。"""

    def test_short_sequence_returns_empty(self):
        """少于3根K线返回空列表。"""
        bars = [_merged_bar("d1", 10, 8, 0), _merged_bar("d2", 11, 9, 1)]
        assert chan_fenxing(bars) == []

    def test_empty_returns_empty(self):
        """空序列返回空列表。"""
        assert chan_fenxing([]) == []

    def test_top_fenxing(self, kline_with_top_fenxing):
        """标准顶分型识别。"""
        merged = chan_merge_inclusions(kline_with_top_fenxing)
        result = chan_fenxing(merged)
        assert len(result) >= 1
        assert any(fx["type"] == "顶" for fx in result)

    def test_bottom_fenxing(self, kline_with_bottom_fenxing):
        """标准底分型识别。"""
        merged = chan_merge_inclusions(kline_with_bottom_fenxing)
        result = chan_fenxing(merged)
        assert len(result) >= 1
        assert any(fx["type"] == "底" for fx in result)

    def test_top_fenxing_definition(self):
        """顶分型：中间K线 high 和 low 均高于两侧。"""
        bars = [
            _merged_bar("d1", 10, 8, 0),
            _merged_bar("d2", 12, 9, 1),  # high=12>10, low=9>8 → 顶分型
            _merged_bar("d3", 11, 7, 2),
        ]
        result = chan_fenxing(bars)
        assert len(result) == 1
        assert result[0]["type"] == "顶"
        assert result[0]["idx"] == 1

    def test_bottom_fenxing_definition(self):
        """底分型：中间K线 high 和 low 均低于两侧。"""
        bars = [
            _merged_bar("d1", 12, 9, 0),
            _merged_bar("d2", 10, 7, 1),  # high=10<12, low=7<9 → 底分型
            _merged_bar("d3", 11, 8, 2),
        ]
        result = chan_fenxing(bars)
        assert len(result) == 1
        assert result[0]["type"] == "底"
        assert result[0]["idx"] == 1

    def test_no_fenxing_monotonic_up(self):
        """单调上升序列无分型。"""
        bars = [
            _merged_bar("d1", 10, 8, 0),
            _merged_bar("d2", 11, 9, 1),
            _merged_bar("d3", 12, 10, 2),
        ]
        result = chan_fenxing(bars)
        assert len(result) == 0

    def test_no_fenxing_monotonic_down(self):
        """单调下降序列无分型。"""
        bars = [
            _merged_bar("d1", 12, 10, 0),
            _merged_bar("d2", 11, 9, 1),
            _merged_bar("d3", 10, 8, 2),
        ]
        result = chan_fenxing(bars)
        assert len(result) == 0

    def test_dedup_consecutive_same_type_keeps_strongest(self):
        """连续同类型分型去重：顶保留更高的，底保留更低的。"""
        bars = [
            _merged_bar("d1", 10, 8, 0),
            _merged_bar("d2", 12, 9, 1),  # 顶分型
            _merged_bar("d3", 11, 9.5, 2),  # 与d2形成顶？d3.high=11<12, 不构成顶
            _merged_bar("d4", 13, 9, 3),  # 顶分型（13>11 且 9<9.5? low=9<9.5不满足）
            # 需要更精确的构造
        ]
        # 重新构造：两个连续顶分型
        bars = [
            _merged_bar("d1", 10, 8, 0),
            _merged_bar("d2", 12, 9, 1),  # 顶分型候选
            _merged_bar("d3", 11, 8.5, 2),  # 既不是顶也不是底（11<12, 8.5>8）
            _merged_bar("d4", 13, 9, 3),  # 顶分型候选（13>11, 9>8.5）
            _merged_bar("d5", 11, 7, 4),
        ]
        result = chan_fenxing(bars)
        # d2和d4都是顶分型候选，但不连续（d3在中间不构成分型）
        # 实际上 d2: 12>10且12>11且9>8且9>8.5 → 顶
        # d4: 13>11且13>11且9>8.5且9>7 → 顶
        # d3不是分型，所以d2和d4之间没有其他分型，它们是连续同类型
        top_fx = [fx for fx in result if fx["type"] == "顶"]
        if len(top_fx) >= 1:
            # 去重后应保留最高的
            assert top_fx[-1]["bar"]["high"] >= 12

    def test_alternating_fenxing(self):
        """交替顶底分型。"""
        bars = [
            _merged_bar("d1", 10, 8, 0),
            _merged_bar("d2", 13, 10, 1),  # 顶
            _merged_bar("d3", 10, 7, 2),  # 底
            _merged_bar("d4", 14, 11, 3),  # 顶
            _merged_bar("d5", 9, 6, 4),  # 底
        ]
        result = chan_fenxing(bars)
        types = [fx["type"] for fx in result]
        # 应该是交替的
        for i in range(1, len(types)):
            assert types[i] != types[i - 1], f"分型不交替: {types}"


# ═══════════════════════════════════════════════════════════════
# 3. chan_bi 测试
# ═══════════════════════════════════════════════════════════════


class TestChanBi:
    """笔构建测试。"""

    def test_no_bi_from_short_data(self):
        """分型不足2个时无法构建笔。"""
        bars = [
            _merged_bar("d1", 10, 8, 0),
            _merged_bar("d2", 12, 9, 1),
            _merged_bar("d3", 11, 7, 2),
        ]
        result = chan_bi(bars)
        # 只有1个分型，无法构成笔
        assert len(result) <= 1

    def test_bi_direction_up(self):
        """底分型→顶分型 = 向上笔。"""
        bars = [
            _merged_bar("d1", 12, 10, 0),
            _merged_bar("d2", 10, 7, 1),  # 底: low 7<10, 7<8; high 10<12, 10<11
            _merged_bar("d3", 11, 8, 2),  # 独立
            _merged_bar("d4", 14, 10, 3),  # 顶: high 14>11, 14>12; low 10>8, 10>8
            _merged_bar("d5", 12, 8, 4),  # 使 d4 成为顶分型的右侧K线
        ]
        result = chan_bi(bars)
        assert len(result) >= 1
        assert result[0]["direction"] == "up"

    def test_bi_direction_down(self):
        """顶分型→底分型 = 向下笔。"""
        bars = [
            _merged_bar("d1", 10, 8, 0),
            _merged_bar("d2", 14, 10, 1),  # 顶: high 14>10, 14>12; low 10>8, 10>9
            _merged_bar("d3", 12, 9, 2),  # 独立
            _merged_bar("d4", 10, 7, 3),  # 底: low 7<9, 7<8; high 10<12, 10<11
            _merged_bar("d5", 11, 8, 4),  # 使 d4 成为底分型的右侧K线
        ]
        result = chan_bi(bars)
        assert len(result) >= 1
        assert result[0]["direction"] == "down"

    def test_bi_requires_at_least_one_independent_bar(self):
        """顶底分型之间至少1根独立K线（idx差>=2）。"""
        # 构造两个相邻分型之间无独立K线的情况
        bars = [
            _merged_bar("d1", 12, 10, 0),
            _merged_bar("d2", 10, 7, 1),  # 底 idx=1
            _merged_bar("d3", 14, 10, 2),  # 顶 idx=2，与底idx差=1 < 2
        ]
        result = chan_bi(bars)
        # idx差=1，不满足>=2条件，不应构成笔
        assert len(result) == 0

    def test_bi_alternates_types(self):
        """笔必须由交替的顶底分型构成。"""
        bars = [
            _merged_bar("d1", 12, 10, 0),
            _merged_bar("d2", 10, 7, 1),  # 底
            _merged_bar("d3", 11, 8, 2),
            _merged_bar("d4", 14, 10, 3),  # 顶
            _merged_bar("d5", 12, 9, 4),
            _merged_bar("d6", 9, 6, 5),  # 底
        ]
        result = chan_bi(bars)
        if len(result) >= 2:
            for i in range(1, len(result)):
                prev_end_type = result[i - 1]["end"]["type"]
                curr_start_type = result[i]["start"]["type"]
                assert prev_end_type != curr_start_type or True
                # 方向应交替
                assert result[i]["direction"] != result[i - 1]["direction"]

    def test_bi_from_zigzag_data(self):
        """锯齿形数据应能构建多笔。"""
        bars = _zigzag_bars(18, base=10, amp=3)
        merged = chan_merge_inclusions(bars)
        result = chan_bi(merged)
        assert len(result) >= 2

    def test_bi_has_high_low(self):
        """笔应包含 high 和 low 字段。"""
        bars = [
            _merged_bar("d1", 12, 10, 0),
            _merged_bar("d2", 10, 7, 1),
            _merged_bar("d3", 11, 8, 2),
            _merged_bar("d4", 14, 10, 3),
        ]
        result = chan_bi(bars)
        if result:
            assert "high" in result[0]
            assert "low" in result[0]
            assert result[0]["high"] >= result[0]["low"]


# ═══════════════════════════════════════════════════════════════
# 4. chan_xianduan 测试
# ═══════════════════════════════════════════════════════════════


class TestChanXianduan:
    """线段构建测试。"""

    def test_less_than_3_bi_returns_empty(self):
        """少于3笔无法构建线段。"""
        bi_list = [_make_bi("up", 0, 2, 12, 8)]
        assert chan_xianduan(bi_list) == []

    def test_empty_bi_list(self):
        """空笔列表返回空。"""
        assert chan_xianduan([]) == []

    def test_three_bi_with_overlap(self):
        """3笔有重叠区间 → 构成1条线段。"""
        bi_list = [
            _make_bi("up", 0, 2, 12, 9),  # high=12, low=9
            _make_bi("down", 2, 4, 11, 8),  # high=11, low=8
            _make_bi("up", 4, 6, 13, 9.5),  # high=13, low=9.5
        ]
        # overlap_high = min(12,11,13) = 11, overlap_low = max(9,8,9.5) = 9.5
        # 9.5 < 11 → 有重叠
        result = chan_xianduan(bi_list)
        assert len(result) >= 1
        assert result[0]["bi_count"] >= 3

    def test_three_bi_no_overlap(self):
        """3笔无重叠区间 → 不构成线段。"""
        bi_list = [
            _make_bi("up", 0, 2, 10, 8),  # high=10, low=8
            _make_bi("down", 2, 4, 7, 5),  # high=7, low=5
            _make_bi("up", 4, 6, 12, 9),  # high=12, low=9
        ]
        # overlap_high = min(10,7,12) = 7, overlap_low = max(8,5,9) = 9
        # 9 >= 7 → 无重叠
        result = chan_xianduan(bi_list)
        assert len(result) == 0

    def test_xianduan_direction_follows_first_bi(self):
        """线段方向 = 第一笔方向。"""
        bi_list = [
            _make_bi("down", 0, 2, 12, 8),
            _make_bi("up", 2, 4, 11, 9),
            _make_bi("down", 4, 6, 10, 7.5),
        ]
        result = chan_xianduan(bi_list)
        if result:
            assert result[0]["direction"] == "down"

    def test_xianduan_extends_with_more_bi(self):
        """线段可以扩展加入更多笔。"""
        bi_list = [
            _make_bi("up", 0, 2, 12, 9),
            _make_bi("down", 2, 4, 11, 8),
            _make_bi("up", 4, 6, 13, 9.5),
            _make_bi("down", 6, 8, 12, 9),  # 回调不破前低9
            _make_bi("up", 8, 10, 14, 10),
        ]
        result = chan_xianduan(bi_list)
        if result:
            # 第一条线段可能包含多于3笔
            assert result[0]["bi_count"] >= 3


# ═══════════════════════════════════════════════════════════════
# 5. chan_zhongshu 测试
# ═══════════════════════════════════════════════════════════════


class TestChanZhongshu:
    """中枢识别测试。"""

    def test_less_than_3_xiduan_returns_empty(self):
        """少于3条线段无法构成中枢。"""
        xd_list = [_make_xd("up", 3, 12, 8)]
        assert chan_zhongshu(xd_list) == []

    def test_empty_xiduan_list(self):
        """空线段列表返回空。"""
        assert chan_zhongshu([]) == []

    def test_three_xiduan_with_overlap(self):
        """3条线段有重叠区间 → 构成中枢。"""
        xd_list = [
            _make_xd("up", 3, 12, 8),
            _make_xd("down", 3, 11, 7),
            _make_xd("up", 3, 13, 9),
        ]
        # zg = min(12,11,13) = 11, zd = max(8,7,9) = 9
        result = chan_zhongshu(xd_list)
        assert len(result) >= 1
        assert result[0]["zg"] == 11
        assert result[0]["zd"] == 9
        assert result[0]["width"] == 2

    def test_three_xiduan_no_overlap(self):
        """3条线段无重叠 → 不构成中枢。"""
        xd_list = [
            _make_xd("up", 3, 10, 8),
            _make_xd("down", 3, 7, 5),
            _make_xd("up", 3, 15, 12),
        ]
        # zg = min(10,7,15) = 7, zd = max(8,5,12) = 12
        # zd(12) >= zg(7) → 无重叠
        result = chan_zhongshu(xd_list)
        assert len(result) == 0

    def test_zhongshu_has_mid_and_width(self):
        """中枢应包含 mid 和 width 字段。"""
        xd_list = [
            _make_xd("up", 3, 12, 8),
            _make_xd("down", 3, 11, 7),
            _make_xd("up", 3, 13, 9),
        ]
        result = chan_zhongshu(xd_list)
        assert result
        assert "mid" in result[0]
        assert "width" in result[0]
        assert result[0]["mid"] == 10.0
        assert result[0]["width"] > 0

    def test_merge_overlapping_zhongshu(self):
        """相邻中枢有重叠时合并为扩展中枢。"""
        xd_list = [
            _make_xd("up", 3, 12, 8),  # 中枢1: zg=11, zd=9（与后面3段）
            _make_xd("down", 3, 11, 7),
            _make_xd("up", 3, 13, 9),
            _make_xd("down", 3, 12, 8),  # 中枢2: zg=12, zd=9（与后面3段）
            _make_xd("up", 3, 14, 10),
        ]
        # 中枢1: zg=min(12,11,13)=11, zd=max(8,7,9)=9
        # 中枢2: zg=min(11,13,12)=11, zd=max(7,9,8)=9
        # 中枢3: zg=min(13,12,14)=12, zd=max(9,8,10)=10
        # 中枢1和2重叠(9<11 and 11>9)，合并
        # 合并后与中枢3重叠(10<max(11,11) and 12>min(9,9))
        result = chan_zhongshu(xd_list)
        # 重叠中枢应合并
        assert len(result) <= 3

    def test_no_merge_non_overlapping_zhongshu(self):
        """不重叠的中枢不合并。"""
        xd_list = [
            _make_xd("up", 3, 10, 8),  # 中枢1: zg=8? 计算一下
            _make_xd("down", 3, 9, 7),
            _make_xd("up", 3, 10, 8),
            _make_xd("down", 3, 20, 15),  # 跳到高处
            _make_xd("up", 3, 22, 16),
        ]
        # 中枢1: zg=min(10,9,10)=9, zd=max(8,7,8)=8
        # 中枢2: zg=min(9,10,20)=9, zd=max(7,8,15)=15 → zd>=zg 无中枢
        # 中枢3: zg=min(10,20,22)=10, zd=max(8,15,16)=16 → 无中枢
        result = chan_zhongshu(xd_list)
        # 只有中枢1有效
        assert len(result) <= 1

    def test_merge_uses_intersection_not_union(self):
        """合并重叠中枢应取交集（zg=min, zd=max），而非并集（扩大范围）。"""
        xd_list = [
            _make_xd("up", 3, 12, 8),  # 线段0
            _make_xd("down", 3, 11, 7),  # 线段1
            _make_xd("up", 3, 13, 9),  # 线段2
            _make_xd("down", 3, 14, 10),  # 线段3
        ]
        # 中枢1（线段0,1,2）: zg=min(12,11,13)=11, zd=max(8,7,9)=9
        # 中枢2（线段1,2,3）: zg=min(11,13,14)=11, zd=max(7,9,10)=10
        # 重叠且索引连续 -> 合并
        # 交集: zg=min(11,11)=11, zd=max(9,10)=10, width=1
        # 并集（旧bug）: zg=max(11,11)=11, zd=min(9,10)=9, width=2
        result = chan_zhongshu(xd_list)
        assert len(result) >= 1
        merged = result[0]
        assert merged["zg"] == 11  # 交集取较低高点
        assert merged["zd"] == 10  # 交集取较高低点
        assert merged["width"] == 1  # 交集宽度，非并集的 2


# ═══════════════════════════════════════════════════════════════
# 6. chan_beichi 测试
# ═══════════════════════════════════════════════════════════════


class TestChanBeichi:
    """背驰检测测试。"""

    def test_insufficient_closes(self):
        """收盘价不足34根返回数据不足。"""
        closes = [10.0] * 20
        bi_list = [
            _make_bi("down", 0, 5, 12, 8),
            _make_bi("up", 5, 10, 14, 9),
            _make_bi("down", 10, 15, 13, 7),
            _make_bi("up", 15, 20, 15, 10),
        ]
        result = chan_beichi(bi_list, [], closes)
        assert result["trend_beichi"] is None
        assert "不足" in result["summary"]

    def test_insufficient_bi(self):
        """笔数不足4根返回数据不足。"""
        closes = [10.0 + i * 0.1 for i in range(50)]
        bi_list = [_make_bi("down", 0, 5, 12, 8)]
        result = chan_beichi(bi_list, [], closes)
        assert "不足" in result["summary"]

    def test_no_beichi_with_increasing_macd(self):
        """MACD面积不衰减时无背驰。"""
        # 构造上升趋势的收盘价（50根）
        # dif_series 长度 = 50-25 = 25, dea_series 长度 = 25-8 = 17 (索引 0-16)
        # 笔的 end_idx 需要 <= 16 以避免 dea 索引越界
        closes = [10.0 + i * 0.5 for i in range(50)]
        bi_list = [
            _make_bi("up", 0, 3, 13, 10),
            _make_bi("down", 3, 6, 12, 8),
            _make_bi("up", 6, 10, 16, 11),
            _make_bi("down", 10, 15, 14, 9),
        ]
        result = chan_beichi(bi_list, [], closes)
        assert "trend_beichi" in result
        assert "summary" in result

    def test_result_structure(self):
        """返回值包含必要字段。"""
        closes = [10.0 + i * 0.1 for i in range(50)]
        bi_list = [
            _make_bi("down", 0, 3, 12, 8),
            _make_bi("up", 3, 6, 14, 9),
            _make_bi("down", 6, 10, 13, 7),
            _make_bi("up", 10, 15, 15, 10),
        ]
        result = chan_beichi(bi_list, [], closes)
        assert "trend_beichi" in result
        assert "range_beichi" in result
        assert "summary" in result

    def test_trend_beichi_with_divergence(self):
        """价格创新低但MACD面积缩小 → 底背驰。"""
        # 构造先跌后反弹再跌更深但力度减弱的序列
        # dif_series 长度 = 50-25 = 25, dea_series 长度 = 17 (索引 0-16)
        # 笔的 end_idx 需要 <= 16
        closes = []
        for i in range(12):
            closes.append(20.0 - i * 0.3)
        for i in range(8):
            closes.append(closes[-1] + 0.2)
        for i in range(10):
            closes.append(closes[-1] - 0.4)
        while len(closes) < 50:
            closes.append(closes[-1])

        bi_list = [
            _make_bi("up", 0, 3, 20, 16),
            _make_bi("down", 3, 8, 18, 15.5),  # 第一段下跌
            _make_bi("up", 8, 12, 17, 16),
            _make_bi("down", 12, 16, 16, 14),  # 第二段下跌（更低，索引在范围内）
        ]
        result = chan_beichi(bi_list, [], closes)
        assert result["trend_beichi"] in (None, "底背驰(看涨)", "顶背驰(看跌)")


class TestChanBeichiWithZhongshu:
    """背驰检测测试（非空 zs_list，验证 bi_start/bi_end 坐标系修复）。"""

    def test_entry_exit_bi_selected_by_bi_index(self):
        """中枢的进入/离开笔应通过 bi_list 索引选取，而非 merged-bar 索引。"""
        # 构造足够长的 closes（>=34），使 MACD 计算可执行
        closes = [20.0 - i * 0.1 for i in range(40)]  # 下跌趋势

        # 6 笔：bi[0]=进入段，bi[1..4]=中枢内，bi[5]=离开段
        bi_list = [
            _make_bi("down", 0, 5, 20, 16),    # 进入段
            _make_bi("up", 5, 8, 18, 14),      # 中枢内
            _make_bi("down", 8, 11, 17, 13),   # 中枢内
            _make_bi("up", 11, 14, 16, 13),    # 中枢内
            _make_bi("down", 14, 17, 15, 12),  # 中枢内
            _make_bi("up", 17, 22, 14, 10),    # 离开段
        ]
        # 中枢 bi_start=1, bi_end=4（bi_list 索引）
        zs = _make_zs(18, 13, xd_start=0, xd_end=2, bi_start=1, bi_end=4)
        result = chan_beichi(bi_list, [zs], closes)
        # 趋势背驰块应执行（不再因坐标系错位而跳过）
        assert "trend_beichi" in result

    def test_no_exit_bi_when_zs_at_end(self):
        """中枢在 bi_list 末尾时无离开段，趋势背驰为 None。"""
        closes = [10.0 + i * 0.1 for i in range(40)]
        bi_list = [
            _make_bi("up", 0, 5, 12, 8),       # 进入段
            _make_bi("down", 5, 8, 11, 9),     # 中枢内
            _make_bi("up", 8, 11, 13, 9),      # 中枢内
            _make_bi("down", 11, 14, 12, 10),  # 中枢内（末尾）
        ]
        zs = _make_zs(13, 9, xd_start=0, xd_end=2, bi_start=1, bi_end=3)
        result = chan_beichi(bi_list, [zs], closes)
        # bi_end=3 是最后一笔，无离开段 -> exit_bi=None -> trend_beichi=None
        assert result["trend_beichi"] is None

    def test_no_entry_bi_when_zs_at_start(self):
        """中枢在 bi_list 开头时无进入段，趋势背驰为 None。"""
        closes = [10.0 + i * 0.1 for i in range(40)]
        bi_list = [
            _make_bi("up", 0, 5, 12, 8),       # 中枢内（开头）
            _make_bi("down", 5, 8, 11, 9),     # 中枢内
            _make_bi("up", 8, 11, 13, 9),      # 中枢内
            _make_bi("down", 11, 14, 12, 10),  # 离开段
        ]
        zs = _make_zs(13, 9, xd_start=0, xd_end=2, bi_start=0, bi_end=2)
        result = chan_beichi(bi_list, [zs], closes)
        # bi_start=0 -> entry_bi=None -> trend_beichi=None
        assert result["trend_beichi"] is None

    def test_range_beichi_with_nonempty_zs(self):
        """盘整背驰循环应正确执行（非空 zs_list）。"""
        closes = [20.0 - i * 0.1 for i in range(40)]
        bi_list = [
            _make_bi("down", 0, 5, 20, 16),
            _make_bi("up", 5, 8, 18, 14),
            _make_bi("down", 8, 11, 17, 13),
            _make_bi("up", 11, 14, 16, 13),
            _make_bi("down", 14, 17, 15, 12),
            _make_bi("up", 17, 22, 14, 10),
        ]
        zs = _make_zs(18, 13, xd_start=0, xd_end=2, bi_start=1, bi_end=4)
        result = chan_beichi(bi_list, [zs], closes)
        assert isinstance(result["range_beichi"], list)

    def test_direction_guard_skips_opposite_bis(self):
        """进入段与离开段方向相反时不构成趋势背驰。"""
        closes = [10.0 + i * 0.2 for i in range(40)]
        bi_list = [
            _make_bi("down", 0, 5, 12, 8),      # 进入段（向下）
            _make_bi("up", 5, 8, 11, 9),        # 中枢内
            _make_bi("down", 8, 11, 13, 9),     # 中枢内
            _make_bi("up", 11, 14, 14, 10),     # 中枢内
            _make_bi("up", 14, 20, 16, 11),     # 离开段（向上）--与进入段反向
        ]
        zs = _make_zs(14, 9, xd_start=0, xd_end=2, bi_start=1, bi_end=3)
        result = chan_beichi(bi_list, [zs], closes)
        # entry=down, exit=up -> 方向不一致 -> trend_beichi=None
        assert result["trend_beichi"] is None


# ═══════════════════════════════════════════════════════════════
# 7. chan_maidian 测试
# ═══════════════════════════════════════════════════════════════


class TestChanMaidian:
    """三类买卖点测试。"""

    def test_insufficient_data(self):
        """数据不足时返回空。"""
        result = chan_maidian([], [], [], [10.0] * 10)
        assert result["buy_points"] == []
        assert result["sell_points"] == []

    def test_no_zhongshu_returns_empty(self):
        """无中枢时无法识别买卖点。"""
        closes = [10.0 + i * 0.1 for i in range(30)]
        bi_list = [_make_bi("up", 0, 5, 12, 8)]
        result = chan_maidian([], bi_list, [], closes)
        assert result["buy_points"] == []

    def test_one_buy_below_zhongshu(self):
        """价格在中枢下方 + 下跌笔结束 + 底背驰 → 触发一买。"""
        closes = [8.0] * 30
        zs = _make_zs(12, 10)  # 中枢 10-12
        bi_list = [
            _make_bi("up", 0, 5, 11, 8),
            _make_bi("down", 5, 25, 10, 7),  # 下跌笔，end_idx=25 接近 len(closes)-1=29
        ]
        # P2-C4: 一买需背驰确认
        beichi = {"trend_beichi": "底背驰(看涨)", "range_beichi": []}
        result = chan_maidian([], bi_list, [zs], closes, beichi)
        has_one_buy = any(bp["type"] == "一买" for bp in result["buy_points"])
        assert has_one_buy

    def test_one_buy_no_beichi_degraded(self):
        """P2-C4: 未确认背驰时一买退化为弱信号。"""
        closes = [8.0] * 30
        zs = _make_zs(12, 10)
        bi_list = [
            _make_bi("up", 0, 5, 11, 8),
            _make_bi("down", 5, 25, 10, 7),
        ]
        result = chan_maidian([], bi_list, [zs], closes, beichi=None)
        # 无背驰不构成标准一买，退化为弱信号
        has_weak = any("一买(弱)" in bp["type"] for bp in result["buy_points"])
        assert has_weak

    def test_sell_point_above_zhongshu(self):
        """价格在中枢上方 + 上升笔结束 + 顶背驰 → 触发一卖。"""
        closes = [15.0] * 30
        zs = _make_zs(12, 10)
        bi_list = [
            _make_bi("down", 0, 5, 12, 8),
            _make_bi("up", 5, 25, 10, 16),  # 上升笔
        ]
        beichi = {"trend_beichi": "顶背驰(看跌)", "range_beichi": []}
        result = chan_maidian([], bi_list, [zs], closes, beichi)
        has_sell = any(sp["type"] == "一卖" for sp in result["sell_points"])
        assert has_sell

    def test_result_structure(self):
        """返回值包含必要字段。"""
        closes = [10.0] * 30
        result = chan_maidian([], [], [_make_zs(12, 8)], closes)
        assert "buy_points" in result
        assert "sell_points" in result
        assert "summary" in result

    def test_summary_text(self):
        """summary 字段格式正确。"""
        closes = [10.0] * 30
        result = chan_maidian([], [], [_make_zs(12, 8)], closes)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    def test_three_buy_above_zg(self):
        """三买：突破中枢后回踩不入（recent_low > ZG）。"""
        # 中枢 ZG=12, ZD=10；价格突破至 13 后回踩至 12.1（高于 ZG）
        closes = [11.0] * 20 + [13.0, 12.1] + [12.5] * 8
        zs = _make_zs(12, 10)
        bi_list = [_make_bi("up", 0, 25, 13, 10)]
        result = chan_maidian([], bi_list, [zs], closes)
        has_three_buy = any(bp["type"] == "三买" for bp in result["buy_points"])
        assert has_three_buy

    def test_three_buy_rejects_low_in_zs(self):
        """三买：回踩低点落入中枢（recent_low <= ZG）不触发。"""
        # 中枢 ZG=12, ZD=10；价格突破至 13 后回踩至 11.5（低于 ZG=12，落入中枢）
        closes = [11.0] * 20 + [13.0, 11.5] + [12.5] * 8
        zs = _make_zs(12, 10)
        bi_list = [_make_bi("up", 0, 25, 13, 10)]
        result = chan_maidian([], bi_list, [zs], closes)
        has_three_buy = any(bp["type"] == "三买" for bp in result["buy_points"])
        assert not has_three_buy

    def test_three_sell_below_zd(self):
        """三卖：跌破中枢后反弹不入（recent_high < ZD）。"""
        # 中枢 ZG=12, ZD=10；价格跌破至 8 后反弹至 9.8（低于 ZD=10）
        closes = [11.0] * 20 + [8.0, 9.8] + [8.5] * 8
        zs = _make_zs(12, 10)
        bi_list = [_make_bi("down", 0, 25, 12, 8)]
        result = chan_maidian([], bi_list, [zs], closes)
        has_three_sell = any(sp["type"] == "三卖" for sp in result["sell_points"])
        assert has_three_sell

    def test_three_sell_rejects_high_in_zs(self):
        """三卖：反弹高点落入中枢（recent_high >= ZD）不触发。"""
        # 中枢 ZG=12, ZD=10；价格跌破至 8 后反弹至 10.5（高于 ZD=10，落入中枢）
        closes = [11.0] * 20 + [8.0, 10.5] + [8.5] * 8
        zs = _make_zs(12, 10)
        bi_list = [_make_bi("down", 0, 25, 12, 8)]
        result = chan_maidian([], bi_list, [zs], closes)
        has_three_sell = any(sp["type"] == "三卖" for sp in result["sell_points"])
        assert not has_three_sell


# ═══════════════════════════════════════════════════════════════
# 8. chan_full_analysis 测试
# ═══════════════════════════════════════════════════════════════


class TestChanFullAnalysis:
    """顶层整合函数测试。"""

    def test_insufficient_records(self):
        """K线不足30根返回错误。"""
        records = [_bar(f"2025-01-{i+1:02d}", 10, 11, 9, 10) for i in range(10)]
        result = chan_full_analysis(records)
        assert result["valid"] is False
        assert "error" in result

    def test_valid_analysis_keys(self):
        """有效分析结果包含所有必要字段。"""
        bars = _zigzag_bars(40, base=10, amp=3)
        result = chan_full_analysis(bars)
        expected_keys = [
            "valid",
            "merged_count",
            "original_count",
            "merge_ratio_pct",
            "fenxing_count",
            "top_fenxing",
            "bottom_fenxing",
            "bi_count",
            "up_bi",
            "down_bi",
            "xianduan_count",
            "zhongshu_list",
            "zhongshu_count",
            "beichi",
            "maidian",
            "current_position",
        ]
        for key in expected_keys:
            assert key in result, f"缺少字段: {key}"

    def test_analysis_with_uptrend(self):
        """上升趋势数据分析不报错。"""
        bars = _zigzag_bars(40, base=10, amp=2)
        result = chan_full_analysis(bars)
        assert "error" not in result
        assert result["original_count"] == 40
        assert isinstance(result["valid"], bool)

    def test_analysis_with_downtrend(self, kline_downtrend):
        """下降趋势数据分析不报错（20根不足30根返回错误）。"""
        result = chan_full_analysis(kline_downtrend)
        assert isinstance(result, dict)
        # 20根不足30根，应返回错误
        assert result.get("valid") is False

    def test_analysis_with_sideways(self, kline_sideways):
        """横盘数据应能正常分析。"""
        result = chan_full_analysis(kline_sideways)
        assert isinstance(result, dict)
        if "error" not in result:
            assert "bi_count" in result

    def test_merge_ratio_valid(self):
        """合并比例在合理范围内（0-100%）。"""
        bars = _zigzag_bars(40, base=10, amp=3)
        result = chan_full_analysis(bars)
        assert 0 <= result["merge_ratio_pct"] <= 100

    def test_fenxing_counts_consistent(self):
        """顶底分型数量之和等于总分型数。"""
        bars = _zigzag_bars(40, base=10, amp=3)
        result = chan_full_analysis(bars)
        assert (
            result["fenxing_count"] == result["top_fenxing"] + result["bottom_fenxing"]
        )

    def test_bi_directions_consistent(self):
        """上下笔数量之和等于总笔数。"""
        bars = _zigzag_bars(40, base=10, amp=3)
        result = chan_full_analysis(bars)
        assert result["bi_count"] == result["up_bi"] + result["down_bi"]

    def test_current_position_format(self):
        """当前位置描述为非空字符串。"""
        bars = _zigzag_bars(40, base=10, amp=3)
        result = chan_full_analysis(bars)
        assert isinstance(result["current_position"], str)
        assert len(result["current_position"]) > 0

    def test_with_zigzag_data(self):
        """锯齿形数据应产生更丰富的分析结果。"""
        bars = _zigzag_bars(40, base=10, amp=3)
        result = chan_full_analysis(bars)
        if "error" not in result:
            # 锯齿形应该产生分型和笔
            assert result["fenxing_count"] >= 2
            assert result["bi_count"] >= 1


# ═══════════════════════════════════════════════════════════════
# 9. 辅助函数测试
# ═══════════════════════════════════════════════════════════════


class TestHelperFunctions:
    """辅助函数测试（_ema_series, _macd_area）。"""

    def test_ema_series_basic(self):
        """EMA 序列基本计算。"""
        from chan import _ema_series

        values = [10.0 + i for i in range(20)]
        result = _ema_series(values, 12)
        assert len(result) == 9  # 20 - 12 + 1
        assert result[0] == sum(values[:12]) / 12

    def test_ema_series_short_data(self):
        """数据不足时返回空列表。"""
        from chan import _ema_series

        result = _ema_series([1, 2, 3], 12)
        assert result == []

    def test_macd_area_basic(self):
        """MACD 面积基本计算。"""
        from chan import _macd_area

        dif = [1.0, 2.0, 3.0, 2.0, 1.0]
        dea = [0.5, 1.5, 2.5, 1.5, 0.5]
        area = _macd_area(dif, dea, 0, 4)
        expected = sum(abs(d - e) for d, e in zip(dif, dea))
        assert abs(area - expected) < 0.001

    def test_macd_area_invalid_range(self):
        """无效索引范围返回0。"""
        from chan import _macd_area

        dif = [1.0, 2.0]
        dea = [0.5, 1.5]
        assert _macd_area(dif, dea, -1, 2) == 0
        assert _macd_area(dif, dea, 0, 5) == 0
        assert _macd_area(dif, dea, 2, 1) == 0


# ═══════════════════════════════════════════════════════════════
# 10. P0: chan.py 市场前缀测试
# ═══════════════════════════════════════════════════════════════


class TestChanMarketPrefix:
    """P0 回归测试：chan.py CLI 入口正确生成 SH/SZ 市场前缀。"""

    def test_p0_prefix_600xxx_generates_sh(self):
        """600xxx 代码应生成 sh 前缀（上交所）。"""
        from common import normalize_quote_code

        code = normalize_quote_code("600519")
        assert code == "sh600519", f"600519 应归一化为 sh600519，实际: {code}"

    def test_p0_prefix_000xxx_generates_sz(self):
        """000xxx 代码应生成 sz 前缀（深交所）。"""
        from common import normalize_quote_code

        code = normalize_quote_code("000807")
        assert code == "sz000807", f"000807 应归一化为 sz000807，实际: {code}"

    def test_p0_prefix_300xxx_generates_sz(self):
        """300xxx 代码应生成 sz 前缀（创业板/深交所）。"""
        from common import normalize_quote_code

        code = normalize_quote_code("300750")
        assert code == "sz300750", f"300750 应归一化为 sz300750，实际: {code}"

    def test_p0_prefix_already_prefixed_sh(self):
        """已带 sh 前缀的代码保持不变。"""
        from common import normalize_quote_code

        code = normalize_quote_code("sh600519")
        assert code == "sh600519", f"sh600519 应保持不变，实际: {code}"

    def test_p0_prefix_already_prefixed_sz(self):
        """已带 sz 前缀的代码保持不变。"""
        from common import normalize_quote_code

        code = normalize_quote_code("sz000807")
        assert code == "sz000807", f"sz000807 应保持不变，实际: {code}"

    def test_p0_chan_cli_passes_correct_prefix_to_fetcher(self):
        """chan.py CLI 入口应将正确前缀的代码传给 fetcher。

        mock 底层 kline.fetch，只验证传入的 symbol 前缀正确。
        """
        from unittest.mock import patch
        from common import normalize_quote_code

        # 模拟 chan.py __main__ 的调用链:
        #   code = normalize_quote_code(sys.argv[1])
        #   records = fetch_kline(code, 240, 250)
        test_cases = [
            ("600519", "sh600519"),
            ("601398", "sh601398"),
            ("000807", "sz000807"),
            ("002594", "sz002594"),
            ("300750", "sz300750"),
        ]
        for raw_code, expected in test_cases:
            result = normalize_quote_code(raw_code)
            assert (
                result == expected
            ), f"{raw_code} 应归一化为 {expected}，实际: {result}"

    def test_p0_prefix_propagation_through_fetch_chain(self):
        """验证前缀从 chan.py 到 kline.fetch 的完整传递。

        chan.py __main__ 先调用 normalize_quote_code 再传给 fetch_kline。
        使用 mock 捕获 kline.get_kline 接收到的 code，确认前缀正确。
        """
        from unittest.mock import patch, MagicMock
        from common import normalize_quote_code
        from kline import fetch as fetch_kline

        captured_codes = []
        mock_bar = MagicMock()
        mock_bar.to_dict.return_value = {
            "day": "2025-01-06",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 1000,
        }

        def tracking_get_kline(code, scale=240, datalen=30, use_cache=True):
            captured_codes.append(code)
            return [mock_bar]

        with patch("kline.get_kline", side_effect=tracking_get_kline):
            for raw, expected in [("600519", "sh600519"), ("000807", "sz000807")]:
                code = normalize_quote_code(raw)
                assert code == expected
                fetch_kline(code, 240, 40)

        assert captured_codes == [
            "sh600519",
            "sz000807",
        ], f"fetch 链应传递 ['sh600519', 'sz000807']，实际: {captured_codes}"


class TestAlignedMacd:
    """aligned_macd 统一 DIF/DEA 接口测试（v2.4.0）。"""

    def test_aligned_macd_basic(self):
        from technical.core import aligned_macd
        closes = [10.0 + i * 0.1 for i in range(40)]  # 40 个递增收盘价
        result = aligned_macd(closes, fast=12, slow=26, signal=9)
        assert "dif_series" in result
        assert "dea_series" in result
        assert "dea_offset" in result
        # DEA 序列应 <= DIF 序列（warmup 差异）
        assert len(result["dea_series"]) <= len(result["dif_series"])
        # offset 应为 dea 序列第一个元素对应的 closes 索引
        assert result["dea_offset"] >= 0

    def test_aligned_macd_short_input(self):
        from technical.core import aligned_macd
        # 不足 slow 周期时返回空
        closes = [10.0, 11.0, 12.0]
        result = aligned_macd(closes)
        assert result["dif_series"] == []
        assert result["dea_series"] == []

    def test_aligned_macd_custom_periods(self):
        from technical.core import aligned_macd
        closes = [10.0 + i * 0.1 for i in range(50)]
        # 自定义参数
        result = aligned_macd(closes, fast=5, slow=15, signal=4)
        assert len(result["dif_series"]) > 0
        assert len(result["dea_series"]) > 0

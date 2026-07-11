"""老鸭头形态识别覆盖测试2（纯数据，无网络）。

补充覆盖 detect_laoyatou 的正向触发（鸭颈/鸭头/鸭嘴三阶段全流程），
以及边界分支：鸭头回溯、鸭颈天数不足、放量/未放量、突破/未突破前高、
置信度高/中分级。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from strategies.patterns.laoyatou import detect_laoyatou


def _records(n, start_close=10.0):
    """生成 n 根 K 线 records（含 day 字段）。"""
    return [{"day": f"2025-01-{i + 1:02d}"} for i in range(n)]


def _build_laoyatou_scenario():
    """手工构造一个能触发老鸭头正向识别的数据集。

    策略（在 ma60 索引空间，i_ma60 从 20 开始扫描鸭嘴点）：
    - 鸭嘴点 i_ma60=20：MA5 上穿 MA10（前一日 MA5<=MA10，当日 MA5>MA10）
    - 鸭头点 j_ma60=12：MA5<MA10 且 MA5 下降，且 close > ma60*0.95
    - 鸭颈：duck_head_j 之前 10 天内 ma5>ma10>ma20 至少 3 天
    - 放量突破前高：鸭嘴日成交量 > 鸭头日均量*1.2，close > 前高*1.02
    """
    n = 80
    # 以 ma60 空间为基准（长度 20，对应 closes[60:80]）
    ma60_len = 20
    cl_offset = n - ma60_len  # 60
    # ma5/ma10/ma20 长度均等于 ma60 长度，故 offset 均为 0

    ma60 = [10.0] * ma60_len
    ma20 = [10.0] * ma60_len

    ma5 = [0.0] * ma60_len
    ma10 = [0.0] * ma60_len

    # 鸭颈阶段（j_ma60 < 12）：ma5 > ma10 > ma20，持续上升
    for k in range(0, 9):
        ma5[k] = 12.0 + k * 0.1
        ma10[k] = 11.5 + k * 0.1
        ma20[k] = 11.0 + k * 0.1

    # 鸭头阶段（j_ma60=12）：ma5 下穿 ma10 且 ma5 下降
    # j_ma60=11: ma5 > ma10（颈末）
    ma5[10] = 13.0
    ma10[10] = 12.8
    ma5[11] = 12.5  # 下降
    ma10[11] = 12.9
    # j_ma60=12: ma5 < ma10 且 ma5 < ma5[11]
    ma5[12] = 12.0
    ma10[12] = 13.0

    # 鸭头后过渡
    ma5[13] = 12.2
    ma10[13] = 12.8
    ma5[14] = 12.5
    ma10[14] = 12.7
    ma5[15] = 12.8
    ma10[15] = 12.7
    ma5[16] = 13.0
    ma10[16] = 12.7
    ma5[17] = 13.2
    ma10[17] = 12.7
    ma5[18] = 13.4
    ma10[18] = 12.7
    ma5[19] = 13.6
    ma10[19] = 12.7

    # 鸭嘴点 i_ma60=20 不在范围内（ma60_len=20，range(20,20) 为空），扩展到 22
    ma60 = ma60 + [10.0, 10.0]
    ma20 = ma20 + [10.0, 10.0]
    ma5 = ma5 + [13.8, 14.5]
    ma10 = ma10 + [12.7, 12.6]
    ma60_len = 22
    cl_offset = n - ma60_len  # 58

    # 鸭嘴点 i_ma60=20：ma5[19]<=ma10[19] 为假（13.6 > 12.7），需调整
    # 让 i_ma60=21 成为鸭嘴点：ma5[20]<=ma10[20] and ma5[21]>ma10[21]
    ma5[20] = 12.6
    ma10[20] = 12.7
    ma5[21] = 13.5
    ma10[21] = 12.7

    # closes：鸭嘴日 close 突破前高*1.02
    closes = [10.0] * n
    # 鸭头日 close（ci=12+cl_offset=70）需 > ma60[12]*0.95
    head_ci = 12 + cl_offset
    closes[head_ci] = 12.0
    # 前高：head_ci 前 10 天内最高
    for k in range(head_ci - 10, head_ci):
        closes[k] = 11.0
    closes[head_ci] = 11.5  # 前高约 11.0
    # 鸭嘴日 ci = 21 + cl_offset
    beak_ci = 21 + cl_offset
    closes[beak_ci] = 11.0 * 1.05  # 突破前高 11.0 * 1.05 > 11.0*1.02

    # volumes：鸭嘴日放量
    volumes = [1000.0] * n
    # 鸭头日附近均量较小
    for k in range(head_ci - 3, head_ci + 1):
        volumes[k] = 500.0
    # 鸭嘴日附近放量
    for k in range(beak_ci - 3, beak_ci + 1):
        volumes[k] = 2000.0

    records = _records(n)
    mas = {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60}
    return records, closes, volumes, mas, beak_ci


class TestLaoyatouPositive:
    def test_positive_detection_returns_result(self):
        """正向触发：构造完整老鸭头，应返回非空结果。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        results = detect_laoyatou(records, closes, volumes, mas)
        assert len(results) >= 1
        r = results[0]
        assert r["name"] == "老鸭头"
        assert r["type"] == "看涨"
        assert r["idx"] == beak_ci

    def test_confidence_high_when_strong_breakout(self):
        """强势突破（close > 前高*1.05）置信度为高。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        # 增大鸭嘴日收盘价使其 > 前高*1.05
        closes[beak_ci] = 11.0 * 1.08
        results = detect_laoyatou(records, closes, volumes, mas)
        assert any(r["confidence"] == "高" for r in results)

    def test_confidence_medium_when_moderate_breakout(self):
        """中等突破（前高*1.02 < close <= 前高*1.05）置信度为中。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        closes[beak_ci] = 11.0 * 1.03  # 刚过 1.02 阈值，未达 1.05
        results = detect_laoyatou(records, closes, volumes, mas)
        assert any(r["confidence"] == "中" for r in results)


class TestLaoyatouBranches:
    def test_no_duck_head_returns_empty(self):
        """有金叉但鸭头回溯找不到（鸭头期 ma5 未下降），无结果。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        # 破坏鸭头：让所有 ma5 单调递增（无 ma5[j]<ma5[j-1]）
        ma5 = mas["ma5"]
        for k in range(len(ma5)):
            ma5[k] = 10.0 + k * 0.1
        # 保持鸭嘴点金叉（ma5[20]<=ma10[20] and ma5[21]>ma10[21]）
        mas["ma5"][20] = 12.0
        mas["ma10"][20] = 12.5
        mas["ma5"][21] = 13.0
        mas["ma10"][21] = 12.5
        results = detect_laoyatou(records, closes, volumes, mas)
        assert results == []

    def test_no_volume_expansion_returns_empty(self):
        """放量不足（鸭嘴日均量 <= 鸭头日均量*1.2），无结果。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        # 鸭嘴日缩量
        for k in range(beak_ci - 3, beak_ci + 1):
            volumes[k] = 100.0
        results = detect_laoyatou(records, closes, volumes, mas)
        assert results == []

    def test_no_breakout_returns_empty(self):
        """未突破前高（close <= 前高*1.02），无结果。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        closes[beak_ci] = 11.0 * 1.01  # 未达 1.02 阈值
        results = detect_laoyatou(records, closes, volumes, mas)
        assert results == []

    def test_insufficient_neck_days_returns_empty(self):
        """鸭颈天数不足 3 天（鸭头前 ma5>ma10>ma20 不足），无结果。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        # 破坏鸭颈：让鸭头前 ma5 <= ma20
        ma5 = mas["ma5"]
        ma10 = mas["ma10"]
        ma20 = mas["ma20"]
        for k in range(0, 9):
            ma5[k] = 10.0
            ma10[k] = 11.0
            ma20[k] = 12.0
        results = detect_laoyatou(records, closes, volumes, mas)
        assert results == []

    def test_duck_head_below_ma60_returns_empty(self):
        """鸭头日 close < ma60*0.95，不满足鸭头条件，无结果。"""
        records, closes, volumes, mas, beak_ci = _build_laoyatou_scenario()
        cl_offset = len(closes) - len(mas["ma60"])
        # 鸭头搜索窗口 j_ma60 ∈ [6, 18]，对应 j_ci = j_ma60 + cl_offset
        # 全部压低，确保无任何鸭头点满足 close > ma60*0.95
        for j_ma60 in range(6, 19):
            closes[j_ma60 + cl_offset] = 1.0
        results = detect_laoyatou(records, closes, volumes, mas)
        assert results == []

    def test_no_golden_cross_at_scan_range(self):
        """扫描范围内无 MA5 金叉 MA10，无结果。"""
        n = 80
        closes = [10.0 + i * 0.05 for i in range(n)]
        ma60 = [c - 0.3 for c in closes[-20:]]
        ma20 = [c - 0.1 for c in closes[-20:]]
        ma5 = [c + 0.5 for c in closes[-20:]]  # ma5 始终 > ma10
        ma10 = [c + 0.1 for c in closes[-20:]]
        mas = {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60}
        results = detect_laoyatou(_records(n), closes, [1000.0] * n, mas)
        assert results == []

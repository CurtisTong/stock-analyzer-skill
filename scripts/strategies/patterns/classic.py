"""经典 K 线形态库（v1.24.0 新增，对标 InStock 61 形态的子集）。

12 个高频单/双/三 K 形态，输出与 ma_volume_strategy 一致的 signal dict：
- 单 K：锤子线 / 吊颈线 / 射击之星 / 倒锤头 / 十字星
- 双 K：看涨吞没 / 看跌吞没 / 曙光初现 / 乌云盖顶 / 孕线
- 三 K：早晨之星 / 黄昏之星 / 三只乌鸦

判定口径（K 线标准定义）：
- 实体 = |close - open|；影线 = high - max(open, close) / min(open, close) - low
- 锤子/吊颈：下影 ≥ 2×实体 且上影短（<1/3 实体）
- 吞没：后 K 实体完全吞没前 K 实体（方向相反）
- 晨/暮星：长阴/长阳 → 小实体（星）→ 反向长实体确认
"""

import sys
import os

scripts_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)


def _body(bar):
    return abs(bar["close"] - bar["open"])


def _upper_shadow(bar):
    return bar["high"] - max(bar["open"], bar["close"])


def _lower_shadow(bar):
    return min(bar["open"], bar["close"]) - bar["low"]


def _is_bull(bar):
    return bar["close"] > bar["open"]


def _is_bear(bar):
    return bar["close"] < bar["open"]


def _trend(closes, i, lookback: int = 5, buffer: float = 0.02):
    """前期趋势（教科书形态的趋势前提）。

    锤子线/倒锤头出现在**下跌趋势末端**，吊颈线/射击之星出现在**上涨趋势末端**。
    只看单根 K 线几何无法区分同一根 K 上的看涨与看跌形态（实测同一根 K 同时
    输出"锤子线(看涨)"与"吊颈线(看空)"），必须引入趋势前提。

    Returns:
        "up" / "down" / "flat"；可比数据不足时返回 None（调用方据此不加约束）
    """
    start = max(i - lookback, 0)
    if i - 1 <= start:
        return None  # 无可比数据
    prev = closes[i - 1]
    earlier = closes[start]
    if prev < earlier * (1 - buffer):
        return "down"
    if prev > earlier * (1 + buffer):
        return "up"
    return "flat"


def _mk_signal(records, idx, name, type_, conditions, desc, strength, confidence):
    return {
        "date": records[idx].get("day", ""),
        "idx": idx,
        "name": name,
        "type": type_,
        "conditions": conditions,
        "strength": strength,
        "desc": desc,
        "confidence": confidence,
    }


def detect_classic_patterns(records, closes):
    """检测全部经典 K 线形态，返回 signal 列表。

    Args:
        records: K 线 dict 列表（含 open/close/high/low/day）
        closes: 收盘价序列（与 records 对齐）

    Returns:
        signal dict 列表（结构同本土战法）。
    """
    signals = []
    n = len(records)
    if n < 2:
        return signals

    def bar(i):
        return records[i]

    for i in range(1, n):
        cur = bar(i)
        prev = bar(i - 1)
        body_c = _body(cur)

        # ── 单 K 形态 ──
        # 十字星独立判定（实体可为零，不依赖 body_c > 0 分支）
        if body_c <= (cur["high"] - cur["low"]) * 0.15 and (cur["high"] - cur["low"]) > 0:
            signals.append(
                _mk_signal(
                    records, i, "十字星", "中性", ["多空均衡"], "十字星（方向待确认）", strength=1, confidence="低"
                )
            )
        if body_c > 0:
            upper = _upper_shadow(cur)
            lower = _lower_shadow(cur)
            trend = _trend(closes, i)
            # 锤子线（下跌末端长下影）: 下影 ≥ 2×实体，上影 < 实体/3
            # 趋势前提：须出现在下跌趋势（数据不足时不限）
            if lower >= 2 * body_c and upper <= body_c / 3 and trend != "up":
                signals.append(
                    _mk_signal(
                        records,
                        i,
                        "锤子线",
                        "看涨",
                        ["长下影(下影≥2×实体)"],
                        "下跌末端长下影锤子线",
                        strength=4,
                        confidence="中",
                    )
                )
            # 吊颈线（上涨末端长下影）——几何同锤子线，但须处于上涨趋势
            if lower >= 2 * body_c and upper <= body_c / 3 and trend == "up":
                signals.append(
                    _mk_signal(
                        records,
                        i,
                        "吊颈线",
                        "看跌",
                        ["高位长下影"],
                        "高位吊颈线（滞涨警示）",
                        strength=3,
                        confidence="中",
                    )
                )
            # 射击之星（高位长上影）——须处于上涨趋势
            if upper >= 2 * body_c and lower <= body_c / 3 and trend != "down":
                signals.append(
                    _mk_signal(
                        records,
                        i,
                        "射击之星",
                        "看跌",
                        ["长上影(上影≥2×实体)"],
                        "高位射击之星",
                        strength=4,
                        confidence="中",
                    )
                )
            # 倒锤头（低位长上影，反转试探）——须处于下跌趋势
            if upper >= 2 * body_c and lower <= body_c / 3 and trend == "down":
                signals.append(
                    _mk_signal(
                        records,
                        i,
                        "倒锤头",
                        "看涨",
                        ["低位长上影试探"],
                        "低位倒锤头（反转试探）",
                        strength=3,
                        confidence="低",
                    )
                )

        # ── 双 K 形态 ──
        body_p = _body(prev)
        if body_p > 0 and body_c > 0:
            # 看涨吞没：前阴后阳，后实体吞没前实体
            if _is_bear(prev) and _is_bull(cur) and cur["close"] >= prev["open"] and cur["open"] <= prev["close"]:
                signals.append(
                    _mk_signal(
                        records,
                        i,
                        "看涨吞没",
                        "看涨",
                        ["阳线吞没前阴"],
                        f"看涨吞没（{prev.get('day','')}→{cur.get('day','')}）",
                        strength=5,
                        confidence="高",
                    )
                )
            # 看跌吞没
            if _is_bull(prev) and _is_bear(cur) and cur["close"] <= prev["open"] and cur["open"] >= prev["close"]:
                signals.append(
                    _mk_signal(
                        records,
                        i,
                        "看跌吞没",
                        "看跌",
                        ["阴线吞没前阳"],
                        f"看跌吞没（{prev.get('day','')}→{cur.get('day','')}）",
                        strength=5,
                        confidence="高",
                    )
                )
            # 曙光初现：长阴后长阳，开盘低于前收，收盘高于前阴实体中部
            if (
                _is_bear(prev)
                and _is_bull(cur)
                and cur["open"] < prev["close"]
                and cur["close"] > (prev["open"] + prev["close"]) / 2
            ):
                signals.append(
                    _mk_signal(
                        records, i, "曙光初现", "看涨", ["长阴后阳过实体中分"], "曙光初现", strength=4, confidence="高"
                    )
                )
            # 乌云盖顶：长阳后长阴，开盘高于前收，收盘低于前阳实体中部
            if (
                _is_bull(prev)
                and _is_bear(cur)
                and cur["open"] > prev["close"]
                and cur["close"] < (prev["open"] + prev["close"]) / 2
            ):
                signals.append(
                    _mk_signal(
                        records, i, "乌云盖顶", "看跌", ["长阳后阴破实体中分"], "乌云盖顶", strength=4, confidence="高"
                    )
                )
            # 孕线：后实体完全在前实体之内（方向反转预警）
            # 方向相反才构成反转预警：_is_bull(cur) != _is_bull(prev)
            # （原写法 _is_bull(cur) != _is_bear(prev) 在同为 bool 时只对同色 K 成立，
            #   真正的前阴后阳（bullish harami）反被判漏）
            if (
                body_c < body_p
                and _is_bull(cur) != _is_bull(prev)
                and max(cur["open"], cur["close"]) <= max(prev["open"], prev["close"])
                and min(cur["open"], cur["close"]) >= min(prev["open"], prev["close"])
            ):
                signals.append(
                    _mk_signal(
                        records,
                        i,
                        "孕线",
                        "中性",
                        ["实体孕于前K"],
                        "孕线（反转预警，需确认）",
                        strength=2,
                        confidence="低",
                    )
                )

    # ── 三 K 形态 ──
    for i in range(2, n):
        b1, b2, b3 = bar(i - 2), bar(i - 1), bar(i)
        if _body(b1) <= 0 or _body(b3) <= 0:
            continue
        # 早晨之星：长阴 → 小实体星 → 长阳
        if (
            _is_bear(b1)
            and _body(b1) >= _body(b2) * 1.5
            and _body(b2) <= _body(b1) * 0.5
            and _is_bull(b3)
            and b3["close"] > (b1["open"] + b1["close"]) / 2
        ):
            signals.append(
                _mk_signal(
                    records,
                    i,
                    "早晨之星",
                    "看涨",
                    ["长阴-星-长阳"],
                    "早晨之星（底部反转）",
                    strength=5,
                    confidence="高",
                )
            )
        # 黄昏之星
        if (
            _is_bull(b1)
            and _body(b1) >= _body(b2) * 1.5
            and _body(b2) <= _body(b1) * 0.5
            and _is_bear(b3)
            and b3["close"] < (b1["open"] + b1["close"]) / 2
        ):
            signals.append(
                _mk_signal(
                    records,
                    i,
                    "黄昏之星",
                    "看跌",
                    ["长阳-星-长阴"],
                    "黄昏之星（顶部反转）",
                    strength=5,
                    confidence="高",
                )
            )
        # 三只乌鸦：三连阴且收盘渐低
        if _is_bear(b1) and _is_bear(b2) and _is_bear(b3) and b2["close"] < b1["close"] and b3["close"] < b2["close"]:
            signals.append(
                _mk_signal(
                    records,
                    i,
                    "三只乌鸦",
                    "看跌",
                    ["三连阴收盘递减"],
                    "三只乌鸦（空头排列）",
                    strength=4,
                    confidence="高",
                )
            )

    return signals

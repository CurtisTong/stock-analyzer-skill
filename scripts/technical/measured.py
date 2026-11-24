"""
形态量度目标位（measured move）。

补齐网络段子里的"对称派"：双顶（M 顶）/双底（W 底）等形态跌破/突破
颈线后的量度涨跌目标位。

设计要点：
- 纯函数：只读输入序列，无副作用、无 I/O，仅依赖 stdlib 与 core。
- 摆动点复用 core._find_swing_points（confirm=True，左右窗口同时确认，
  最近 window 根等待确认，不是未来数据泄露）。
- 双顶：highs 上找两个相近高度的摆动高点，lows 上取两顶之间的摆动低点
  作颈线；量度目标 = 颈线 - (两顶均值 - 颈线)，方向向下。
- 双底：对称，lows 上找两个相近高度的摆动低点，highs 上取两底之间的
  摆动高点作颈线；量度目标 = 颈线 + (颈线 - 两底均值)，方向向上。
- auto：两种形态都测算，取形态高度（height）更大、即更显著的一个。

对外入口：
    measured_move(closes, highs, lows, pattern='auto') -> dict
"""

from __future__ import annotations

from .core import _EPS, _find_swing_points

_WINDOW = 5
_TOL = 0.03  # 两顶/两底的高度容差 3%
_MIN_LEN = 2 * _WINDOW + 1  # 出现两个经确认的摆动点至少需要 11 根 K 线


def _similar(v1, v2, tol=_TOL):
    """两极值是否相近：相对容差，_EPS 兜底消除除零与浮点噪声。"""
    scale = max(abs(v1), abs(v2), _EPS)
    return abs(v1 - v2) <= tol * scale + _EPS


def _fail(pattern, reason):
    """识别失败/数据不足的统一返回，保持输入 pattern 原样。"""
    return {"pattern": pattern, "target": None, "reason": reason}


def _double_top(highs, lows, ph, pl):
    """找一对相近摆动高点，取其间摆动低点为颈线；成功返回 dict，否则 None。

    ph: highs 序列上的摆动高点索引；pl: lows 序列上的摆动低点索引。
    多对候选时取形态高度最大者（最显著），多颈线取最低者（最保守）。
    """
    best = None
    for a in range(len(ph)):
        for b in range(a + 1, len(ph)):
            i, j = ph[a], ph[b]
            h1, h2 = highs[i], highs[j]
            if not _similar(h1, h2):
                continue
            mids = [k for k in pl if i < k < j]
            if not mids:
                continue
            neckline = min(lows[k] for k in mids)
            peak = (h1 + h2) / 2.0
            height = peak - neckline
            if height <= _EPS:
                continue
            if best is None or height > best["height"]:
                best = {
                    "pattern": "double_top",
                    "neckline": float(neckline),
                    "peak": float(peak),
                    "target": float(neckline - height),
                    "direction": "down",
                    "height": float(height),
                }
    return best


def _double_bottom(highs, lows, ph, pl):
    """找一对相近摆动低点，取其间摆动高点为颈线；成功返回 dict，否则 None。

    返回字段与双顶保持一致以便调用方统一处理：这里的 peak 承载两底均值
    （即谷值），height 为正数，target 在颈线上方。
    多颈线取最高者（压力最显著）。
    """
    best = None
    for a in range(len(pl)):
        for b in range(a + 1, len(pl)):
            i, j = pl[a], pl[b]
            l1, l2 = lows[i], lows[j]
            if not _similar(l1, l2):
                continue
            mids = [k for k in ph if i < k < j]
            if not mids:
                continue
            neckline = max(highs[k] for k in mids)
            trough = (l1 + l2) / 2.0
            height = neckline - trough
            if height <= _EPS:
                continue
            if best is None or height > best["height"]:
                best = {
                    "pattern": "double_bottom",
                    "neckline": float(neckline),
                    "peak": float(trough),
                    "target": float(neckline + height),
                    "direction": "up",
                    "height": float(height),
                }
    return best


def measured_move(closes, highs, lows, pattern="auto"):
    """测算形态量度目标位（对称派）。

    Args:
        closes: 收盘价序列（仅用于长度/上下文一致性，量度本身用高低点）。
        highs: 最高价序列，双顶在此找摆动高点、双底在此找中间颈线高点。
        lows: 最低价序列，双底在此找摆动低点、双顶在此找中间颈线低点。
        pattern: 'double_top' / 'double_bottom' / 'auto'。

    Returns:
        成功：{"pattern", "neckline", "peak", "target", "direction", "height"}；
        失败：{"pattern": <原值>, "target": None, "reason": <原因>}。
    """
    if pattern not in ("double_top", "double_bottom", "auto"):
        return _fail(pattern, "不支持的 pattern")

    n = min(len(closes), len(highs), len(lows))
    if n < _MIN_LEN:
        return _fail(pattern, "数据不足：至少需要 %d 根 K 线" % _MIN_LEN)

    try:
        # 两个独立调用：highs 的摆动高点 / lows 的摆动低点。
        ph, _ = _find_swing_points(highs, window=_WINDOW, confirm=True)
        _, pl = _find_swing_points(lows, window=_WINDOW, confirm=True)

        if pattern == "double_top":
            result = _double_top(highs, lows, ph, pl)
            return result or _fail(pattern, "未识别到相近高度的双顶形态")

        if pattern == "double_bottom":
            result = _double_bottom(highs, lows, ph, pl)
            return result or _fail(pattern, "未识别到相近高度的双底形态")

        top = _double_top(highs, lows, ph, pl)
        bottom = _double_bottom(highs, lows, ph, pl)
        if top and bottom:
            return top if top["height"] >= bottom["height"] else bottom
        if top:
            return top
        if bottom:
            return bottom
        return _fail("auto", "未识别到可量度的双顶/双底形态")
    except (TypeError, ValueError, IndexError):
        # 脏数据（如 None/非数值）不崩溃，降级为失败返回。
        return _fail(pattern, "数据异常，无法测算量度目标位")

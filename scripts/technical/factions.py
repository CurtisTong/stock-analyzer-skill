"""派别状态聚合：把各技术分析派别给出的关键点位统一成带状态标签的清单。

对应网络段子里的"支撑位阵亡名单"——每个"派"给出一个价位，价格跌破即"阵亡"，
尚未触及即"待验证"。本模块只做客观聚合与状态判定，不含任何买卖建议。

状态口径（支撑位视角，以现价 price 为锚）：
- 已跌破：该价位 >= 现价（价格已在该支撑下方或刚好触及，支撑失守转阻力）。
- 待验证：该价位 < 现价（价格尚未跌到该位，是否有效待后续走势验证）。
- 无效/缺失：指标未产出该点位（数据不足或形态未识别）。

阻力位方向相反：价位 <= 现价视为"已突破"，> 现价为"待验证"。
"""

from .core import _EPS
from .gap import detect_gaps, gap_support_resistance
from .measured import measured_move

# 派别顺序与段子一致（从高到低并非必然，仅用于稳定展示）
_FACTION_ORDER = [
    "均线派",
    "布林派",
    "前底派",
    "缺口派",
    "对称派",
    "股票箱",
    "整数派",
    "波浪派",
]


def _status_for_level(level, price, kind="support"):
    """按价位与现价关系判定状态。"""
    if level is None or price is None or price <= 0:
        return "缺失"
    if kind == "support":
        return "已跌破" if level >= price - _EPS else "待验证"
    # 阻力
    return "已突破" if level <= price + _EPS else "待验证"


def _entry(faction, level, source, strength, price, kind="support"):
    if level is None:
        return None
    return {
        "faction": faction,
        "level": round(float(level), 2),
        "source": source,
        "strength": strength,
        "kind": kind,
        "status": _status_for_level(level, price, kind),
    }


def aggregate_factions(features: dict, closes: list, opens: list, highs: list, lows: list, price: float) -> dict:
    """聚合各派别点位，返回带状态标签的清单。

    纯函数：不修改 features 或任何入参。所有点位来源均为已算好的 features，
    唯缺口/对称需要原始 OHLC（按需在此计算，避免改动 analyzer 的字段布局）。
    """
    price = float(price) if price else 0.0
    entries = []

    sr = features.get("support_resistance") or {}
    ma = features.get("ma_system") or {}
    boll = features.get("bollinger") or {}

    # 均线派：取 nearest 均线支撑/阻力
    for name, lv in (ma.get("ma_supports") or [])[:1]:
        e = _entry("均线派", lv, name, "中", price)
        if e:
            entries.append(e)
    for name, lv in (ma.get("ma_resistances") or [])[:1]:
        e = _entry("均线派", lv, name, "中", price, kind="resistance")
        if e:
            entries.append(e)

    # 布林派：下轨作支撑、上轨作阻力
    e = _entry("布林派", boll.get("lower"), "BOLL下轨", "中", price)
    if e:
        entries.append(e)
    e = _entry("布林派", boll.get("upper"), "BOLL上轨", "中", price, kind="resistance")
    if e:
        entries.append(e)

    # 前底派：前低支撑 / 前高阻力
    for s in sr.get("supports", []):
        if s.get("source") == "前低":
            e = _entry("前底派", s.get("level"), "前低", "强", price)
            if e:
                entries.append(e)
            break
    for r in sr.get("resistances", []):
        if r.get("source") == "前高":
            e = _entry("前底派", r.get("level"), "前高", "强", price, kind="resistance")
            if e:
                entries.append(e)
            break

    # 缺口派：未回补缺口的最近支撑/阻力
    gaps = detect_gaps(opens, highs, lows, closes)
    gsr = gap_support_resistance(gaps, price) if price > 0 else {}
    gs = gsr.get("nearest_gap_support")
    if gs:
        e = _entry("缺口派", gs["top"], "未回补缺口", "中", price)
        if e:
            e["gap_type"] = gs.get("gap_type")
            entries.append(e)
    gr = gsr.get("nearest_gap_resistance")
    if gr:
        e = _entry("缺口派", gr["bottom"], "未回补缺口", "中", price, kind="resistance")
        if e:
            e["gap_type"] = gr.get("gap_type")
            entries.append(e)

    # 对称派：形态量度目标位（双顶向下 / 双底向上）
    measured = measured_move(closes, highs, lows)
    if measured.get("target") is not None:
        kind = "support" if measured.get("direction") == "down" else "resistance"
        e = _entry("对称派", measured["target"], "形态量度(%s)" % measured.get("pattern"), "弱", price, kind)
        if e:
            entries.append(e)

    # 股票箱：箱体上下沿
    box = features.get("box")
    if box:
        e = _entry("股票箱", box.get("bottom"), "箱体下沿", "中", price)
        if e:
            entries.append(e)
        e = _entry("股票箱", box.get("top"), "箱体上沿", "中", price, kind="resistance")
        if e:
            entries.append(e)

    # 整数派：最近整数关口（从 support_resistance 的来源为整数关口的项取最近一条）
    for s in sr.get("supports", []):
        if s.get("source") == "整数关口":
            e = _entry("整数派", s.get("level"), "整数关口", "弱", price)
            if e:
                entries.append(e)
            break
    for r in sr.get("resistances", []):
        if r.get("source") == "整数关口":
            e = _entry("整数派", r.get("level"), "整数关口", "弱", price, kind="resistance")
            if e:
                entries.append(e)
            break

    # 波浪派：方向性标签（无具体点位，单列状态文本）
    wave = features.get("wave")
    wave_label = None
    if isinstance(wave, str) and wave and wave != "数据不足":
        if "下跌浪" in wave or "顶部" in wave or "扩张" in wave:
            wave_label = "空头结构"
        elif "上升浪" in wave or "底部" in wave:
            wave_label = "多头结构"
        else:
            wave_label = "中性/盘整"

    # 按级别稳定排序：已跌破的排前（段子里"阵亡"在上），同级按价位降序
    rank = {"已跌破": 0, "已突破": 0, "待验证": 1, "缺失": 2}
    entries.sort(key=lambda x: (rank.get(x["status"], 3), -x["level"] if x["kind"] == "support" else x["level"]))

    support_entries = [e for e in entries if e["kind"] == "support"]
    resistance_entries = [e for e in entries if e["kind"] == "resistance"]
    fallen = [e for e in support_entries if e["status"] == "已跌破"]

    return {
        "entries": entries,
        "supports": support_entries,
        "resistances": resistance_entries,
        "fallen_count": len(fallen),
        "wave_structure": wave_label,
        "order": [f for f in _FACTION_ORDER if any(e["faction"] == f for e in entries)],
    }

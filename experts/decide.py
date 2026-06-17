"""
专家圆桌决策引擎 (decide.md 代码化)。

整合 8 位专家的独立评分，输出加权投票结果、仓位建议和信心指数。
实现 decide.md §一-§七 的完整决策规则。

公开 API：
- detect_market_state(index_quote, kline_data, breadth_data) -> dict
- aggregate_votes(expert_results, market_state, horizon, calibration_factor) -> dict
- format_debate_output(result) -> str
"""

import statistics
from typing import Dict, List, Optional

from experts import (
    ExpertProfile,
    direction_from_score,
    list_long_term_experts,
    list_short_term_experts,
)
from experts.scoring import compute_confidence_index

# ═══════════════════════════════════════════════════════════════
# 市场环境检测 (decide.md §二)
# ═══════════════════════════════════════════════════════════════

# 市场状态 → 长线/短线权重映射
_MARKET_WEIGHTS = {
    "牛市": (0.40, 0.60),
    "熊市": (0.60, 0.40),
    "防御型": (0.65, 0.35),  # 结构性分化：低波独涨、成长亏损，比熊市更偏长线
    "震荡": (0.55, 0.45),
    "冰点": (0.60, 0.40),
    "亢奋": (0.70, 0.30),
}

# 投资期限 → 长线/短线权重映射 (decide.md §一.2)
_HORIZON_WEIGHTS = {
    "short": (0.35, 0.65),  # 短期操作（<1月）
    "medium": (0.40, 0.60),  # 中期持有（1-6月）
    "long": (0.70, 0.30),  # 长期投资（>6月）
}

# 市场状态检测阈值
_MARKET_ICE_ADVANCE_RATIO = 0.20
_MARKET_ICE_LIMIT_DOWN = 50
_MARKET_ICE_HIGH_LOW_RATIO = 0.2

_MARKET_MANIA_PE_PERCENTILE = 90
_MARKET_MANIA_ADVANCE_RATIO = 0.75
_MARKET_MANIA_MARGIN_RATIO = 10

_MARKET_BULL_VOL_RATIO = 1.2
_MARKET_BULL_ADVANCE_RATIO = 0.60
_MARKET_BULL_HIGH_LOW_RATIO = 1.5

_MARKET_BEAR_VOL_RATIO = 0.8
_MARKET_BEAR_ADVANCE_RATIO = 0.40
_MARKET_BEAR_HIGH_LOW_RATIO = 0.5

# 防御型市场：低波独涨、成长亏损、宽度收窄但未到冰点
_MARKET_DEF_VOL_RATIO = 0.9
_MARKET_DEF_ADVANCE_LOW = 0.30
_MARKET_DEF_ADVANCE_HIGH = 0.45


def detect_market_state(
    index_quote: Optional[dict] = None,
    kline_data: Optional[dict] = None,
    breadth_data: Optional[dict] = None,
) -> dict:
    """判断市场环境状态（decide.md §二）。

    Args:
        index_quote: 大盘行情 dict（price/prev_close/change_pct）
        kline_data: 大盘 K 线特征 dict（ma20/closes/volumes）
        breadth_data: 市场宽度 dict（advance_ratio/new_high_low_ratio/
            limit_down_count/margin_ratio）

    Returns:
        {
            "state": "牛市"|"熊市"|"震荡"|"冰点"|"亢奋",
            "long_weight": float,
            "short_weight": float,
            "reason": str,
        }
    """
    state = "震荡"

    if index_quote and kline_data:
        price = index_quote.get("price", 0)
        ma20 = kline_data.get("ma20", 0)
        volumes = kline_data.get("volumes", [])

        try:
            from common.utils import compute_volume_ratio

            vol_ratio = compute_volume_ratio(volumes, recent_window=5, base_window=10)
        except ImportError:
            vol_ratio = 1.0
            if len(volumes) >= 10:
                recent = statistics.mean(volumes[-5:])
                base = statistics.mean(volumes[-10:])
                vol_ratio = recent / base if base > 0 else 1.0

        above_ma20 = price > ma20 > 0 if ma20 > 0 else False
        below_ma20 = price < ma20 > 0 if ma20 > 0 else False

        advance_ratio = breadth_data.get("advance_ratio", 0.5) if breadth_data else 0.5
        high_low_ratio = (
            breadth_data.get("new_high_low_ratio", 1.0) if breadth_data else 1.0
        )
        limit_down = breadth_data.get("limit_down_count", 0) if breadth_data else 0
        margin_ratio = breadth_data.get("margin_ratio", 0) if breadth_data else 0
        pe_percentile = index_quote.get("pe_percentile", 50)

        if (
            advance_ratio < _MARKET_ICE_ADVANCE_RATIO
            and limit_down > _MARKET_ICE_LIMIT_DOWN
            and high_low_ratio < _MARKET_ICE_HIGH_LOW_RATIO
        ):
            state = "冰点"
        elif (
            pe_percentile > _MARKET_MANIA_PE_PERCENTILE
            and advance_ratio > _MARKET_MANIA_ADVANCE_RATIO
            and margin_ratio > _MARKET_MANIA_MARGIN_RATIO
        ):
            state = "亢奋"
        elif (
            above_ma20
            and vol_ratio > _MARKET_BULL_VOL_RATIO
            and advance_ratio > _MARKET_BULL_ADVANCE_RATIO
            and high_low_ratio > _MARKET_BULL_HIGH_LOW_RATIO
        ):
            state = "牛市"
        elif (
            below_ma20
            and vol_ratio < _MARKET_BEAR_VOL_RATIO
            and advance_ratio < _MARKET_BEAR_ADVANCE_RATIO
            and high_low_ratio < _MARKET_BEAR_HIGH_LOW_RATIO
        ):
            state = "熊市"
        elif (
            below_ma20
            and vol_ratio < _MARKET_DEF_VOL_RATIO
            and _MARKET_DEF_ADVANCE_LOW <= advance_ratio <= _MARKET_DEF_ADVANCE_HIGH
        ):
            state = "防御型"
        else:
            state = "震荡"

    lw, sw = _MARKET_WEIGHTS[state]
    return {
        "state": state,
        "long_weight": lw,
        "short_weight": sw,
        "reason": _market_state_reason(state),
    }


def _market_state_reason(state: str) -> str:
    reasons = {
        "牛市": "指数在均线上方，量能放大，市场宽度良好",
        "熊市": "指数在均线下方，量能萎缩，市场宽度收窄",
        "防御型": "指数偏弱，低波/价值品种抗跌，成长品种承压，结构性分化",
        "震荡": "趋势不明确，等待方向选择",
        "冰点": "极度恐慌，上涨家数极少，跌停大量",
        "亢奋": "估值高位，情绪过热，杠杆偏高",
    }
    return reasons.get(state, "")


# ═══════════════════════════════════════════════════════════════
# 投票整合 (decide.md §一 + §三)
# ═══════════════════════════════════════════════════════════════


def _count_votes(scores: List[float]) -> Dict[str, int]:
    """统计看多/看空票数。"""
    bull = sum(1 for s in scores if s >= 60)
    bear = sum(1 for s in scores if s <= 39)
    return {"bull": bull, "bear": bear, "total": len(scores)}


def _resolve_conflict(
    long_votes: dict,
    short_votes: dict,
    long_avg: float,
    short_avg: float,
    buffett_score: float,
    yangjia_score: float,
    is_yangjia_ice: bool,
    horizon: str,
) -> dict:
    """冲突解决规则（decide.md §三）。

    Returns:
        {"direction": str, "position_factor": float, "notes": list}
    """
    notes = []
    direction = "中性"
    position_factor = 1.0

    # 双一致看多
    if long_votes["bull"] >= 3 and short_votes["bull"] >= 3:
        direction = "强烈看多"
        position_factor = 1.0
    # 双一致看空
    elif long_votes["bear"] >= 3 and short_votes["bear"] >= 3:
        direction = "强烈看空"
        position_factor = 0.0
    # 长线主导多
    elif (
        long_votes["bull"] >= 3
        and short_votes["bull"] == 2
        and short_votes["bear"] == 2
    ):
        direction = "看多"
        position_factor = 0.8
    # 长线主导空
    elif (
        long_votes["bear"] >= 3
        and short_votes["bull"] == 2
        and short_votes["bear"] == 2
    ):
        direction = "看空"
        position_factor = 0.0
    # 短线主导多
    elif (
        long_votes["bull"] == 2 and long_votes["bear"] == 2 and short_votes["bull"] >= 3
    ):
        direction = "谨慎看多"
        position_factor = 0.5
    # 短线主导空
    elif (
        long_votes["bull"] == 2 and long_votes["bear"] == 2 and short_votes["bear"] >= 3
    ):
        direction = "谨慎看空"
        position_factor = 0.3
    # 全面分歧（8 人都投票，没有中性票且 2:2:2:2）
    elif (
        long_votes["bull"] == 2
        and long_votes["bear"] == 2
        and short_votes["bull"] == 2
        and short_votes["bear"] == 2
    ):
        direction = "中性"
        position_factor = 0.0
        notes.append("全面分歧，建议观望")
    # 极端两极分歧（4 看多 + 4 看空，没有中性票）
    elif (
        long_votes["bull"] + long_votes["bear"] == 4
        and short_votes["bull"] + short_votes["bear"] == 4
        and (long_votes["bull"] + short_votes["bull"]) == 4
        and (long_votes["bear"] + short_votes["bear"]) == 4
    ):
        direction = "中性"
        position_factor = 0.0
        notes.append("两极分化（4 看多 + 4 看空），建议观望")
    else:
        # 按综合分判断
        avg = (long_avg + short_avg) / 2
        direction = direction_from_score(avg)
        if avg >= 60:
            position_factor = 0.8
        elif avg >= 40:
            position_factor = 0.5
        else:
            position_factor = 0.0

    # 巴菲特否决权（中长期模式）
    if buffett_score <= 39:
        if horizon in ("medium", "long"):
            notes.append("巴菲特否决权触发：中长期模式下方向至少降一级")
            direction = _downgrade_direction(direction)
            position_factor *= 0.7
        else:
            notes.append("巴菲特看空，短期模式下不触发否决权，长线组降权×0.8")

    # 养家情绪周期降权
    if yangjia_score < 30 and not is_yangjia_ice:
        notes.append("养家情绪退潮，短线组评分×0.7 降权")
    elif is_yangjia_ice and yangjia_score < 30:
        notes.append("养家判定冰点期，标注'冰点机会，需确认转折信号'（不降权）")

    return {
        "direction": direction,
        "position_factor": position_factor,
        "notes": notes,
    }


# ═══════════════════════════════════════════════════════════════
# 辅助函数：专家信息提取
# ═══════════════════════════════════════════════════════════════


def _get_yangjia_emotion_score(yangjia: Optional[dict]) -> float:
    """提取养家的情绪得分。

    查找顺序与原始逻辑一致：先 "情绪"，再 fallback "情绪周期"。
    """
    if not yangjia or not yangjia.get("breakdown"):
        return 50
    dim_scores = yangjia.get("dim_scores", {})
    return dim_scores.get("情绪", dim_scores.get("情绪周期", 50))


# legacy 专家名 → 合并型专家名映射（v2.1.0）。
# 降权规则原本绑定 legacy 名（buffett/chaogu_yangjia），但这两位已分别
# 合并进 value_anchor / emotion_tech。本映射让降权逻辑同时认旧名与新名，
# 避免输入新框架 active 专家集时规则静默失效。
_LEGACY_TO_MERGED = {
    "buffett": "value_anchor",
    "duan_yongping": "value_anchor",
    "chaogu_yangjia": "emotion_tech",
    "zuoshou_xinyi": "emotion_tech",
}


def _find_expert(expert_by_name: Dict[str, dict], legacy_name: str) -> Optional[dict]:
    """按 legacy 名查找专家结果，找不到则回退到其合并型专家名。

    保证 aggregate_votes 既能吃旧 8 人（legacy 名）输入，也能吃新 8 人
    （active 合并型名）输入，降权规则在两种输入下都触发。
    """
    expert = expert_by_name.get(legacy_name)
    if expert is not None:
        return expert
    merged_name = _LEGACY_TO_MERGED.get(legacy_name)
    return expert_by_name.get(merged_name) if merged_name else None


def _downgrade_direction(direction: str) -> str:
    """方向降一级。"""
    order = ["强烈看多", "看多", "谨慎看多", "中性", "谨慎看空", "看空", "强烈看空"]
    try:
        idx = order.index(direction)
        return order[min(idx + 1, len(order) - 1)]
    except ValueError:
        return "中性"


# ═══════════════════════════════════════════════════════════════
# 仓位建议 (decide.md §四)
# ═══════════════════════════════════════════════════════════════


def _compute_position(
    direction: str, confidence: float, position_factor: float
) -> dict:
    """基于方向和信心指数计算仓位建议。

    Returns:
        {"recommendation": str, "position_pct": int, "stop_loss": str, "steps": str}
    """
    # 基础仓位（信心驱动）
    if confidence >= 75:
        base = 70
    elif confidence >= 60:
        base = 50
    elif confidence >= 40:
        base = 30
    else:
        base = 0

    position = int(base * position_factor)

    # 方向修正
    if direction in ("强烈看空", "看空"):
        position = 0
    elif direction == "谨慎看空":
        position = min(position, 20)

    if position == 0:
        return {
            "recommendation": "不建仓/观望" if "空" not in direction else "减仓/清仓",
            "position_pct": 0,
            "stop_loss": "-",
            "steps": "-",
        }

    # 分步建仓
    if position >= 50:
        steps = f"首笔{int(position*0.5)}% → 确认后{int(position*0.3)}% → 趋势延续{int(position*0.2)}%"
    elif position >= 30:
        steps = f"首笔{int(position*0.6)}% → 确认后{int(position*0.4)}%"
    else:
        steps = f"试探性{position}%"

    return {
        "recommendation": f"标准仓位×{position_factor:.1f}",
        "position_pct": position,
        "stop_loss": "技术支撑位或-8%",
        "steps": steps,
    }


# ═══════════════════════════════════════════════════════════════
# 主入口：投票整合
# ═══════════════════════════════════════════════════════════════


def aggregate_votes(
    expert_results: List[dict],
    market_state: Optional[dict] = None,
    horizon: str = "medium",
    calibration_factor: float = 0.0,
    *,
    prefer_horizon: bool = False,
) -> dict:
    """整合 8 位专家投票，输出最终决策（decide.md 完整规则）。

    Args:
        ...
        prefer_horizon: True 时用户显式传了 horizon（如 `/stock debate 长线`），
                       horizon 权重优先于 market_state；False（默认）保持向后兼容。

    Args:
        expert_results: 专家评分结果列表，每项包含：
            - name: 专家英文名
            - score: 0-100 评分
            - direction: 方向标签
            - reason: 核心理由（1句话）
            - breakdown: 评分明细 dict
        market_state: detect_market_state() 的输出，None 时使用默认权重
        horizon: "short"(<1月) / "medium"(1-6月) / "long"(>6月)
        calibration_factor: 校准因子 [-1, 1]，默认 0

    Returns:
        {
            "market_state": str,
            "long_weight": float,
            "short_weight": float,
            "expert_results": list,
            "long_avg": float,
            "short_avg": float,
            "composite_score": float,
            "direction": str,
            "confidence": float,
            "long_votes": dict,
            "short_votes": dict,
            "position": dict,
            "risk_notes": list,
            "notes": list,
        }
    """
    # 分组
    long_experts = [r for r in expert_results if r.get("group") == "long_term"]
    short_experts = [r for r in expert_results if r.get("group") == "short_term"]

    # 如果没有 group 信息，按前4后4分
    if not long_experts and not short_experts and len(expert_results) == 8:
        long_experts = expert_results[:4]
        short_experts = expert_results[4:]

    long_scores = [r["score"] for r in long_experts]
    short_scores = [r["score"] for r in short_experts]

    long_avg = statistics.mean(long_scores) if long_scores else 50
    short_avg = statistics.mean(short_scores) if short_scores else 50

    # 市场环境权重 vs 投资期限权重：prefer_horizon=True 时 horizon 优先
    if prefer_horizon:
        mkt = market_state["state"] if market_state else "震荡"
        lw, sw = _HORIZON_WEIGHTS.get(horizon, (0.55, 0.45))
    elif market_state:
        mkt = market_state["state"]
        lw = market_state["long_weight"]
        sw = market_state["short_weight"]
    else:
        mkt = "震荡"
        lw, sw = _HORIZON_WEIGHTS.get(horizon, (0.55, 0.45))

    # 一次性构建专家查找字典，避免重复线性搜索
    expert_by_name = {r.get("name"): r for r in expert_results}
    # 通过 _find_expert 查找：旧 8 人输入认 legacy 名，新 8 人输入回退到合并型名
    yangjia = _find_expert(expert_by_name, "chaogu_yangjia")
    buffett = _find_expert(expert_by_name, "buffett")

    yangjia_score = yangjia["score"] if yangjia else 50
    buffett_score = buffett["score"] if buffett else 50

    # 提取养家情绪得分，判断是否冰点期
    emotion_score = _get_yangjia_emotion_score(yangjia)
    # 冰点判定语义：
    #   emotion_score >= 80 对应养家评分矩阵中"冰点转折+题材发酵→100分"或"主升初期→80分"，
    #   即养家看到了情绪层面的机会（chaogu_yangjia.md §九）；
    #   yangjia_score < 30 表示综合分被基本面/估值/风险维度拖累到强烈看空；
    #   两者并存 = "情绪看到冰点机会但其他维度不支持"，需保留机会但不降权（冰点=机会）。
    is_yangjia_ice = emotion_score >= 80 and yangjia_score < 30

    # 养家情绪退潮降权（非冰点时）：降权规则自身不降，其余短线 ×0.7
    # identity_name 认旧名（chaogu_yangjia）与新合并型名（emotion_tech）
    if yangjia_score < 30 and not is_yangjia_ice:
        identity_names = {"chaogu_yangjia", "emotion_tech"}
        total_score = sum(
            r["score"] * (1.0 if r.get("name") in identity_names else 0.7)
            for r in short_experts
        )
        short_avg = total_score / len(short_experts) if short_experts else short_avg

    # 巴菲特降权（短期模式看空时）：巴菲特自身不降，其余长线 ×0.8
    # identity_name 认旧名（buffett）与新合并型名（value_anchor）
    if buffett_score <= 39 and horizon == "short":
        identity_names = {"buffett", "value_anchor"}
        total_score = sum(
            r["score"] * (1.0 if r.get("name") in identity_names else 0.8)
            for r in long_experts
        )
        long_avg = total_score / len(long_experts) if long_experts else long_avg

    # 综合分
    composite = long_avg * lw + short_avg * sw

    # 投票统计
    long_votes = _count_votes(long_scores)
    short_votes = _count_votes(short_scores)

    # 冲突解决
    conflict = _resolve_conflict(
        long_votes,
        short_votes,
        long_avg,
        short_avg,
        buffett_score,
        yangjia_score,
        is_yangjia_ice,
        horizon,
    )
    direction = conflict["direction"]
    position_factor = conflict["position_factor"]
    notes = list(conflict["notes"])

    # 估值硬约束（反追涨杀跌）：长线组估值维度评分过低 → 高估警示，短期也降权
    long_valuation_scores = []
    for r in long_experts:
        dim = r.get("dim_scores") or {}
        v = dim.get("估值", dim.get("valuation"))
        if v is not None:
            long_valuation_scores.append(v)
    if long_valuation_scores:
        val_avg = sum(long_valuation_scores) / len(long_valuation_scores)
        if val_avg < 20:
            notes.append(f"估值警报：长线组估值分仅{val_avg:.0f}（高度高估），仓位×0.5")
            position_factor *= 0.5
        elif val_avg < 30:
            notes.append(f"估值偏低：长线组估值分{val_avg:.0f}（偏高估），仓位×0.7")
            position_factor *= 0.7

    # 信心指数
    all_scores = long_scores + short_scores
    confidence = compute_confidence_index(all_scores, composite, calibration_factor)

    # 仓位建议
    position = _compute_position(direction, confidence, position_factor)

    # 风险提示
    risk_notes = []
    for r in expert_results:
        if r["score"] <= 39:
            risk_notes.append(
                f"{r.get('display_name', r['name'])}({r['score']}分): {r.get('reason', '看空')}"
            )

    return {
        "market_state": mkt,
        "long_weight": lw,
        "short_weight": sw,
        "expert_results": expert_results,
        "long_avg": round(long_avg, 1),
        "short_avg": round(short_avg, 1),
        "composite_score": round(composite, 1),
        "direction": direction,
        "confidence": round(confidence, 1),
        "long_votes": long_votes,
        "short_votes": short_votes,
        "position_factor": position_factor,
        "position": position,
        "risk_notes": risk_notes,
        "notes": notes,
    }


# ═══════════════════════════════════════════════════════════════
# 单组模式 (decide.md §七)
# ═══════════════════════════════════════════════════════════════


def aggregate_group_votes(
    expert_results: List[dict],
    group: str = "long_term",
    calibration_factor: float = 0.0,
) -> dict:
    """单组模式投票整合（decide.md §七）。

    Args:
        expert_results: 该组 4 位专家的评分结果
        group: "long_term" 或 "short_term"
        calibration_factor: 校准因子

    Returns:
        与 aggregate_votes 类似的结构，但只有单组数据
    """
    scores = [r["score"] for r in expert_results]
    avg = statistics.mean(scores) if scores else 50

    votes = _count_votes(scores)
    direction = "中性"
    position_factor = 0.0

    # 组内投票规则 (§七.1)
    if all(s >= 70 for s in scores):
        direction = "强烈看多"
        position_factor = 1.2
    elif votes["bull"] >= 3 and votes["bear"] == 0:
        direction = "看多"
        position_factor = 1.0
    elif votes["bull"] == 3 and any(s <= 39 for s in scores):
        # 3/4看多 + 1票否决
        direction = "看多"
        position_factor = 0.7
    elif votes["bull"] == 2 and votes["bear"] == 2:
        direction = "中性"
        position_factor = 0.0
    elif votes["bear"] >= 3:
        direction = "看空"
        position_factor = 0.0
    elif all(s <= 30 for s in scores):
        direction = "强烈看空"
        position_factor = 0.0

    # 信心指数（单组模式 §七.3）
    if scores:
        mean = statistics.mean(scores)
        cv = statistics.stdev(scores) / mean if mean > 0 and len(scores) > 1 else 0
        consistency = max(0.0, min(100.0, 100 - cv * 150))
        confidence = consistency * 0.45 + avg * 0.55
    else:
        confidence = 50.0

    position = _compute_position(direction, confidence, position_factor)

    risk_notes = []
    for r in expert_results:
        if r["score"] <= 39:
            risk_notes.append(
                f"{r.get('display_name', r['name'])}({r['score']}分): {r.get('reason', '看空')}"
            )

    return {
        "group": group,
        "avg_score": round(avg, 1),
        "direction": direction,
        "confidence": round(confidence, 1),
        "votes": votes,
        "position_factor": position_factor,
        "position": position,
        "expert_results": expert_results,
        "risk_notes": risk_notes,
    }


# ═══════════════════════════════════════════════════════════════
# 输出格式化 (decide.md §四)
# ═══════════════════════════════════════════════════════════════


def format_debate_output(result: dict) -> str:
    """格式化 debate 输出（decide.md §四 格式）。"""
    lines = []

    lines.append("## 专家圆桌投票结果")
    lines.append(
        f"**市场状态**: {result['market_state']} | "
        f"**长线权重**: {result['long_weight']:.0%} | "
        f"**短线权重**: {result['short_weight']:.0%}"
    )
    lines.append("")

    # 评分表
    lines.append("| 专家 | 评分 | 方向 | 核心理由 |")
    lines.append("|------|------|------|----------|")
    for r in result.get("expert_results", []):
        name = r.get("display_name", r.get("name", "?"))
        score = r.get("score", 0)
        direction = r.get("direction", direction_from_score(score))
        reason = r.get("reason", "-")
        lines.append(f"| {name} | {score} | {direction} | {reason} |")

    lines.append("")

    # 分组汇总
    lines.append("## 分组汇总")
    lv = result["long_votes"]
    sv = result["short_votes"]
    lines.append(
        f"- 长线组平均: {result['long_avg']}分 | "
        f"看多{lv['bull']}票 / 看空{lv['bear']}票"
    )
    lines.append(
        f"- 短线组平均: {result['short_avg']}分 | "
        f"看多{sv['bull']}票 / 看空{sv['bear']}票"
    )
    lines.append(f"- 调整后综合分: {result['composite_score']}/100")
    lines.append(f"- **最终方向: {result['direction']}**")
    lines.append(f"- 信心指数: {result['confidence']}/100")
    lines.append("")

    # 风险提示
    if result.get("risk_notes"):
        lines.append("## 风险提示")
        for note in result["risk_notes"]:
            lines.append(f"- {note}")
        lines.append("")

    # 仓位建议
    pos = result.get("position", {})
    lines.append("## 仓位建议")
    lines.append(
        f"- 推荐仓位: {pos.get('position_pct', 0)}% ({pos.get('recommendation', '-')})"
    )
    lines.append(f"- 止损位: {pos.get('stop_loss', '-')}")
    lines.append(f"- 分步建仓: {pos.get('steps', '-')}")

    # 特殊备注
    if result.get("notes"):
        lines.append("")
        lines.append("### 特殊规则触发")
        for note in result["notes"]:
            lines.append(f"- {note}")

    # 校准胜率卡片
    try:
        from experts.calibration import get_calibration, get_calibration_report

        calibration = get_calibration()
        has_data = any(v.get("events", 0) > 0 for v in calibration.values())
        if has_data:
            lines.append("")
            lines.append("## 📊 专家校准胜率")
            lines.append("")
            lines.append("| 专家 | 事件数 | 正确数 | 胜率 |")
            lines.append("|------|--------|--------|------|")
            for name, rec in calibration.items():
                events = rec.get("events", 0)
                correct = rec.get("correct", 0)
                rate = f"{correct/events:.0%}" if events > 0 else "样本不足"
                lines.append(f"| {name} | {events} | {correct} | {rate} |")
    except Exception:
        pass  # 校准数据不可用时静默跳过

    return "\n".join(lines)


def format_debate_card(result: dict) -> str:
    """格式化专家投票卡片（简洁版）。

    输出示例：
    ┌─────────────────────────────────────────────┐
    │  专家投票结果                                 │
    ├─────────────────────────────────────────────┤
    │  ██████████████████████░░░░░░  75% 买入 (6)  │
    │  ████████░░░░░░░░░░░░░░░░░░░░  12.5% 持有 (1)│
    │  ████████░░░░░░░░░░░░░░░░░░░░  12.5% 卖出 (1)│
    ├─────────────────────────────────────────────┤
    │  综合建议：买入 | 信心：78%                    │
    │  核心分歧：索罗斯看空宏观风险                   │
    └─────────────────────────────────────────────┘
    """
    expert_results = result.get("expert_results", [])
    total = len(expert_results)
    if total == 0:
        return "暂无专家投票数据"

    # 统计投票
    buy_count = sum(1 for r in expert_results if r.get("score", 0) >= 60)
    hold_count = sum(1 for r in expert_results if 40 <= r.get("score", 0) < 60)
    sell_count = sum(1 for r in expert_results if r.get("score", 0) < 40)

    buy_pct = buy_count / total * 100
    hold_pct = hold_count / total * 100
    sell_pct = sell_count / total * 100

    # 生成进度条（30 字符宽）
    bar_width = 30
    buy_bar = "█" * int(buy_pct / 100 * bar_width)
    hold_bar = "█" * int(hold_pct / 100 * bar_width)
    sell_bar = "█" * int(sell_pct / 100 * bar_width)

    # 填充到固定宽度
    buy_bar = buy_bar.ljust(bar_width, "░")
    hold_bar = hold_bar.ljust(bar_width, "░")
    sell_bar = sell_bar.ljust(bar_width, "░")

    # 找出分歧点
    dissent = _find_dissent(expert_results)

    # 综合建议
    direction = result.get("direction", "中性")
    confidence = result.get("confidence", 50)

    # 构建卡片
    card = f"""┌─────────────────────────────────────────────┐
│  专家投票结果                                 │
├─────────────────────────────────────────────┤
│  {buy_bar}  {buy_pct:5.1f}% 买入 ({buy_count})  │
│  {hold_bar}  {hold_pct:5.1f}% 持有 ({hold_count})│
│  {sell_bar}  {sell_pct:5.1f}% 卖出 ({sell_count})│
├─────────────────────────────────────────────┤
│  综合建议：{direction} | 信心：{confidence:.0f}%                    │
│  核心分歧：{dissent}                         │
└─────────────────────────────────────────────┘"""

    return card


def _find_dissent(expert_results: list) -> str:
    """找出分歧点。"""
    if not expert_results:
        return "无数据"

    # 找出看空的专家
    dissenters = [r for r in expert_results if r.get("score", 0) < 40]
    if not dissenters:
        return "无分歧"

    # 找出看多的专家
    supporters = [r for r in expert_results if r.get("score", 0) >= 60]
    if not supporters:
        return "一致看空"

    # 提取分歧原因
    names = [r.get("display_name", r.get("name", "?")) for r in dissenters]
    reasons = [r.get("reason", "看空") for r in dissenters]

    # 截断原因（保留前 20 字符）
    reason_short = reasons[0][:20] if reasons else "看空"

    return f"{','.join(names)}看空：{reason_short}"


def format_group_output(result: dict) -> str:
    """格式化单组模式输出（decide.md §七.4）。"""
    group_name = "长线模式" if result["group"] == "long_term" else "短线模式"
    lines = []

    lines.append(f"## 专家圆桌投票结果（{group_name}）")
    lines.append("")

    lines.append("| 专家 | 评分 | 方向 | 核心理由 |")
    lines.append("|------|------|------|----------|")
    for r in result.get("expert_results", []):
        name = r.get("display_name", r.get("name", "?"))
        score = r.get("score", 0)
        direction = r.get("direction", direction_from_score(score))
        reason = r.get("reason", "-")
        lines.append(f"| {name} | {score} | {direction} | {reason} |")

    lines.append("")
    lines.append("## 组内汇总")
    v = result["votes"]
    lines.append(
        f"- 平均分: {result['avg_score']}/100 | 看多{v['bull']}票 / 看空{v['bear']}票"
    )
    lines.append(f"- **最终方向: {result['direction']}**")
    lines.append(f"- 信心指数: {result['confidence']}/100")
    lines.append("")

    if result.get("risk_notes"):
        lines.append("## 风险提示")
        for note in result["risk_notes"]:
            lines.append(f"- {note}")
        lines.append("")

    pos = result.get("position", {})
    lines.append("## 仓位建议")
    lines.append(f"- 推荐仓位: {pos.get('position_pct', 0)}%")
    lines.append(f"- 止损位: {pos.get('stop_loss', '-')}")

    return "\n".join(lines)


__all__ = [
    "detect_market_state",
    "aggregate_votes",
    "aggregate_group_votes",
    "format_debate_output",
    "format_debate_card",
    "format_group_output",
]

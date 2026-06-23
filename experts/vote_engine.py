"""投票统计与冲突解决。"""

import statistics
from typing import Dict, List, Optional

from experts import ExpertProfile, direction_from_score
from experts.scoring import _consistency_from_scores

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

    v2.2.0 适配：长线组 6 人、短线组 3 人。
    统一 67% 多数阈值：长线 ≥4/6，短线 ≥2/3。

    Returns:
        {"direction": str, "position_factor": float, "notes": list}
    """
    notes = []
    direction = "中性"
    position_factor = 1.0

    # 分歧检测（组内无多数方向）
    long_divergent = long_votes["bull"] < 4 and long_votes["bear"] < 4
    short_divergent = short_votes["bull"] < 2 and short_votes["bear"] < 2

    # 双一致看多：长线 ≥4/6 看多 + 短线 ≥2/3 看多
    if long_votes["bull"] >= 4 and short_votes["bull"] >= 2:
        direction = "强烈看多"
        position_factor = 1.0
    # 双一致看空：长线 ≥4/6 看空 + 短线 ≥2/3 看空
    elif long_votes["bear"] >= 4 and short_votes["bear"] >= 2:
        direction = "强烈看空"
        position_factor = 0.0
    # 长线主导多：长线 ≥4/6 看多 + 短线分歧
    elif long_votes["bull"] >= 4 and short_divergent:
        direction = "看多"
        position_factor = 0.8
    # 长线主导空：长线 ≥4/6 看空 + 短线分歧
    elif long_votes["bear"] >= 4 and short_divergent:
        direction = "看空"
        position_factor = 0.0
    # 短线主导多：长线分歧 + 短线 ≥2/3 看多
    elif long_divergent and short_votes["bull"] >= 2:
        direction = "谨慎看多"
        position_factor = 0.5
    # 短线主导空：长线分歧 + 短线 ≥2/3 看空
    elif long_divergent and short_votes["bear"] >= 2:
        direction = "谨慎看空"
        position_factor = 0.3
    # 全面分歧：两组均无多数方向
    elif long_divergent and short_divergent:
        direction = "中性"
        position_factor = 0.0
        notes.append("全面分歧，建议观望")
    # 极端两极分化：一组全多 + 另一组全空（6+3=9 人全部投票且方向对立）
    elif (
        long_votes["bull"] + long_votes["bear"] == 6
        and short_votes["bull"] + short_votes["bear"] == 3
        and (
            (long_votes["bull"] >= 5 and short_votes["bear"] >= 2)
            or (long_votes["bear"] >= 5 and short_votes["bull"] >= 2)
        )
    ):
        direction = "中性"
        position_factor = 0.0
        total_bull = long_votes["bull"] + short_votes["bull"]
        total_bear = long_votes["bear"] + short_votes["bear"]
        notes.append(f"两极分化（{total_bull} 看多 + {total_bear} 看空），建议观望")
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
# 合并进 value_anchor / emotion_tech。本映射让降权规则同时认旧名与新名，
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
# 巴菲特降权规则（v2.2.0 收敛）
# 原本规则分散在 _resolve_conflict 与 aggregate_votes 两处，现统一到
# _buffett_downweight_policy 与 _apply_buffett_long_downweight 函数。
# 行为完全保留：medium/long → 方向降一级+仓位×0.7，short → 其余长线×0.8
# ═══════════════════════════════════════════════════════════════


def _buffett_downweight_policy(buffett_score: float, horizon: str) -> dict:
    """返回巴菲特降权策略（v2.2.0 收敛）。

    巴菲特在两种模式下触发降权：
    - medium/long：中长期模式下视为"否决权"，方向降一级 + 仓位×0.7
    - short：短期模式下仅"权重警示"，其余长线专家评分×0.8
    """
    if buffett_score > 39:
        return {"triggered": False, "mode": None, "factor": 1.0}
    if horizon in ("medium", "long"):
        return {"triggered": True, "mode": "veto", "factor": 0.7}
    return {"triggered": True, "mode": "weight", "factor": 0.8}


def _apply_buffett_long_downweight(long_experts: List[dict]) -> float:
    """短期模式下，对除 buffett/value_anchor 外的长线专家×0.8 加权平均。

    单一来源（v2.2.0 收敛），原 aggregate_votes 内联实现已替换为此函数。
    """
    identity_names = {"buffett", "value_anchor"}
    total = sum(
        r["score"] * (1.0 if r.get("name") in identity_names else 0.8)
        for r in long_experts
    )
    return total / len(long_experts) if long_experts else 50.0


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

# 从 market_detector 导入权重常量，避免重复定义
from experts.market_detector import _HORIZON_WEIGHTS  # noqa: E402


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
        expert_results: 专家评分结果列表，每项包含：
            - name: 专家英文名
            - score: 0-100 评分
            - direction: 方向标签
            - reason: 核心理由（1句话）
            - breakdown: 评分明细 dict
        market_state: detect_market_state() 的输出，None 时使用默认权重
        horizon: "short"(<1月) / "medium"(1-6月) / "long"(>6月)
        calibration_factor: 校准因子 [-1, 1]，默认 0
        prefer_horizon: True 时用户显式传了 horizon（如 `/stock debate 长线`），
                       horizon 权重优先于 market_state；False（默认）保持向后兼容。

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
    from experts.scoring import compute_confidence_index

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
    # v2.2.0 起收敛到 _buffett_downweight_policy + _apply_buffett_long_downweight
    buffett_policy = _buffett_downweight_policy(buffett_score, horizon)
    if buffett_policy["triggered"] and buffett_policy["mode"] == "weight":
        long_avg = _apply_buffett_long_downweight(long_experts)

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
        consistency = _consistency_from_scores(scores)
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

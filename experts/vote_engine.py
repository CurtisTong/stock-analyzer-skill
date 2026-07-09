"""投票统计与冲突解决。"""

import statistics
from typing import Dict, List, Optional

from experts import direction_from_score
from experts.scoring import _consistency_from_scores

# ═══════════════════════════════════════════════════════════════
# 投票整合 (decide.md §一 + §三)
# ═══════════════════════════════════════════════════════════════

_BULL_THRESHOLD = 60  # 评分>=60 计为看多
_BEAR_THRESHOLD = 39  # 评分<=39 计为看空


def _majority(n: int) -> int:
    """67% 多数阈值：ceil(n * 2/3)。

    5 人 -> 4，6 人 -> 4，3 人 -> 2。与 aggregate_group_votes 的动态阈值统一。
    """
    return max(1, -(-n * 2 // 3))  # ceil(n * 2/3)


def _count_votes(scores: List[float]) -> Dict[str, int]:
    """统计看多/看空票数。"""
    bull = sum(1 for s in scores if s >= _BULL_THRESHOLD)
    bear = sum(1 for s in scores if s <= _BEAR_THRESHOLD)
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
    long_n: int,
    short_n: int,
) -> dict:
    """冲突解决规则（decide.md §三）。

    v2.4.2：短线组方向改为均分驱动（P2-10）。
    - 长线多数阈值 = ceil(long_n * 2/3)（5 人 -> 4），长线方向仍用投票计数。
    - 短线方向由 short_avg 区间驱动：>=60 看多、<=39 看空、40-59 分歧（不再依赖
      3 人投票的 ≥2/3 计数，因 1 人翻转即翻多数，统计噪声过大）。
    - 极端两极分化检测：长线 bull >= long_n-1 且 bear==0（5 人时即 4/5）；
      短线 bull/bear == short_n 且反向 ==0（全员反向，基于原始投票计数）。

    Returns:
        {"direction": str, "position_factor": float, "notes": list}
    """
    notes = []
    direction = "中性"
    position_factor = 1.0

    long_majority = _majority(long_n)

    # 分歧检测（组内无多数方向）
    # 长线组（5 人）仍用投票计数：bull/bear 均 < ceil(5*2/3)=4 时为分歧。
    long_divergent = (
        long_votes["bull"] < long_majority and long_votes["bear"] < long_majority
    )
    # B4（P2-10）：短线组方向改为均分驱动，不再依赖 3 人投票的 ≥2/3 计数。
    # 短线仅 3 人，1 人翻转即翻转投票多数，统计噪声过大；改用加权均分映射方向：
    #   short_avg >= 60 -> 短线看多；<= 39 -> 短线看空；40-59 -> 短线分歧。
    # short_signal 驱动所有短线方向判定；short_votes（原始计数）仅用于两极分化检测。
    if short_avg >= _BULL_THRESHOLD:
        short_divergent = False
        short_signal = "bull"
    elif short_avg <= _BEAR_THRESHOLD:
        short_divergent = False
        short_signal = "bear"
    else:
        short_divergent = True
        short_signal = "divergent"

    # 极端两极分化检测（优先于其他分支）
    # 一组压倒性看多 + 另一组压倒性看空 = 最危险的分歧场景
    # 长线"压倒性"= bull>=n-1 且 bear==0；短线"全员反向"= 全员落在反向底线（原始计数）。
    long_extreme_bull = long_votes["bull"] >= long_n - 1 and long_votes["bear"] == 0
    long_extreme_bear = long_votes["bear"] >= long_n - 1 and long_votes["bull"] == 0
    short_extreme_bull = short_votes["bull"] == short_n and short_votes["bear"] == 0
    short_extreme_bear = short_votes["bear"] == short_n and short_votes["bull"] == 0
    polarized = (
        (long_extreme_bull and short_extreme_bear)
        or (long_extreme_bear and short_extreme_bull)
    )

    if polarized:
        direction = "中性"
        position_factor = 0.0
        total_bull = long_votes["bull"] + short_votes["bull"]
        total_bear = long_votes["bear"] + short_votes["bear"]
        notes.append(f"两极分化（{total_bull} 看多 + {total_bear} 看空），建议观望")
    # 双一致看多：长线 ≥多数 看多 + 短线均分看多
    elif long_votes["bull"] >= long_majority and short_signal == "bull":
        direction = "强烈看多"
        position_factor = 1.0
    # 双一致看空：长线 ≥多数 看空 + 短线均分看空
    elif long_votes["bear"] >= long_majority and short_signal == "bear":
        direction = "强烈看空"
        position_factor = 0.0
    # 长线主导多：长线 ≥多数 看多 + 短线分歧
    elif long_votes["bull"] >= long_majority and short_divergent:
        direction = "看多"
        position_factor = 0.8
    # 长线主导空：长线 ≥多数 看空 + 短线分歧
    elif long_votes["bear"] >= long_majority and short_divergent:
        direction = "看空"
        position_factor = 0.0
    # 短线主导多：长线分歧 + 短线均分看多
    elif long_divergent and short_signal == "bull":
        direction = "谨慎看多"
        position_factor = 0.5
    # 短线主导空：长线分歧 + 短线均分看空
    elif long_divergent and short_signal == "bear":
        direction = "谨慎看空"
        position_factor = 0.3
    # 全面分歧：两组均无多数方向
    elif long_divergent and short_divergent:
        direction = "中性"
        position_factor = 0.0
        notes.append("全面分歧，建议观望")
    else:
        # 按综合分判断（覆盖长线看多+短线看空等非极端分歧场景）
        avg = (long_avg + short_avg) / 2
        direction = direction_from_score(avg)
        if avg >= 60:
            position_factor = 0.8
        elif avg >= 40:
            position_factor = 0.5
        else:
            position_factor = 0.0

    # 巴菲特警示 / 强势确认（中长期模式）
    # v2.4.0 改进：原"否决权"改为"否决警示"——保留信号但不强制推翻投票共识。
    # 触发时降低信心指数（confidence -15）而非强制改变方向，方向仍由 8 人投票统计决定。
    # 短期模式保持不变：仅长线组降权×0.8。
    if buffett_score <= 39:
        if horizon in ("medium", "long"):
            notes.append("巴菲特否决警示：中长期模式下巴菲特看空，信心指数降低")
            # 不再强制降级方向和仓位因子，仅通过信心指数传导
        else:
            notes.append("巴菲特看空，短期模式下不触发否决权，长线组降权×0.8")
    elif buffett_score >= 70 and horizon in ("medium", "long") and "看多" in direction:
        # 对称处理：巴菲特强烈看多时，标注强势确认
        notes.append("巴菲特强势确认：中长期模式下巴菲特强烈看多")

    # 养家情绪周期降权
    if yangjia_score < 30 and not is_yangjia_ice:
        notes.append("养家情绪退潮，短线组评分×0.7 降权")
    elif is_yangjia_ice and yangjia_score < 30:
        notes.append("养家判定冰点期，标注'冰点机会，需确认转折信号'（不降权）")

    # I15: position_factor 地板值保护——多个否决条件叠加时确保有最低试探空间
    # 仅在看多方向时生效（中性/看空方向 position_factor 降为 0 是合理风控）
    if direction in ("看多", "谨慎看多", "强烈看多") and position_factor < 0.3:
        notes.append(f"仓位因子地板值保护：{position_factor:.2f} → 0.30")
        position_factor = 0.3

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

    v2.4.0 改进：优先使用 yangjia_sub_score（养家独立情绪评分），
    避免合并型专家（emotion_tech）中作手新一的评分稀释养家的退潮信号。

    回退链：yangjia_sub_score → dim_scores["情绪"] → 50
    """
    if not yangjia:
        return 50
    # 优先使用独立子评分
    sub_score = yangjia.get("yangjia_sub_score")
    if sub_score is not None:
        return float(sub_score)
    # 回退到 dim_scores
    if not yangjia.get("breakdown"):
        return 50
    dim_scores = yangjia.get("dim_scores", {})
    return dim_scores.get("情绪", dim_scores.get("情绪/资金", dim_scores.get("情绪周期", 50)))


# legacy 专家名 → 合并型专家名映射（v2.1.0）。
# 降权规则原本绑定 legacy 名（buffett/chaogu_yangjia），但这两位已分别
# 合并进 value_anchor / emotion_tech。本映射让降权规则同时认旧名与新名，
# 避免输入新框架 active 专家集时规则静默失效。
_LEGACY_TO_MERGED = {
    "buffett": "value_institution",  # v2.4.0: buffett → value_anchor → value_institution
    "duan_yongping": "value_institution",  # v2.4.0: 段永平 → value_anchor → value_institution
    "value_anchor": "value_institution",  # v2.4.0: value_anchor → value_institution
    "institution": "value_institution",  # v2.4.0: institution → value_institution
    "chaogu_yangjia": "emotion_tech",
    "zuoshou_xinyi": "emotion_tech",
}


def _find_expert(expert_by_name: Dict[str, dict], legacy_name: str) -> Optional[dict]:
    """按 legacy 名查找专家结果，找不到则回退到其合并型专家名。

    保证 aggregate_votes 既能吃旧 8 人（legacy 名）输入，也能吃新框架
    active 合并型名（value_institution/topic_leader/emotion_tech）输入，
    降权规则在两种输入下都触发。

    查找顺序（B5 简化为两级）：
    1. 直接按 legacy_name 查找（旧名 buffett/chaogu_yangjia 直接命中）
    2. 按 _LEGACY_TO_MERGED 映射查最终合并型名（buffett->value_institution 等）

    注：v2.4.2 前有第三级"同组合并名遍历"（buffett->value_institution 找不到
    时回退 value_anchor），但 active 流程只用最终合并型名，中间名 value_anchor/
    institution 已 legacy，故移除第三级。需中间名兼容的旧测试已改用最终名。
    """
    # 1. 直接查找
    expert = expert_by_name.get(legacy_name)
    if expert is not None:
        return expert
    # 2. 按 _LEGACY_TO_MERGED 映射查最终合并型名
    merged_name = _LEGACY_TO_MERGED.get(legacy_name)
    if merged_name:
        return expert_by_name.get(merged_name)
    return None


def _downgrade_direction(direction: str) -> str:
    """方向降一级。"""
    order = ["强烈看多", "看多", "谨慎看多", "中性", "谨慎看空", "看空", "强烈看空"]
    try:
        idx = order.index(direction)
        return order[min(idx + 1, len(order) - 1)]
    except ValueError:
        return "中性"


def _upgrade_direction(direction: str) -> str:
    """方向升一级。"""
    order = ["强烈看多", "看多", "谨慎看多", "中性", "谨慎看空", "看空", "强烈看空"]
    try:
        idx = order.index(direction)
        return order[max(idx - 1, 0)]
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
    - medium/long：中长期模式下改为"否决警示"，降低信心指数而非强制改变方向
    - short：短期模式下仅"权重警示"，其余长线专家评分×0.8
    """
    if buffett_score > 39:
        return {"triggered": False, "mode": None, "factor": 1.0}
    if horizon in ("medium", "long"):
        return {"triggered": True, "mode": "warning", "factor": 1.0}
    return {"triggered": True, "mode": "weight", "factor": 0.8}


def _apply_buffett_long_downweight(long_experts: List[dict]) -> float:
    """短期模式下，对除 buffett/value_institution 外的长线专家×0.8 加权平均。

    v2.3.0 修正：使用加权平均（权重和为分母），而非简单平均（人数为分母），
    避免所有专家评分相同时结果系统性偏低。

    v2.4.2（B5）：identity_names 补 value_institution（最终合并名）。
    原 only {buffett, value_anchor} 漏 value_institution，导致输入最终名时
    巴菲特代理被误降权（预存 bug，原测试用 value_anchor 中间名掩盖）。

    单一来源（v2.2.0 收敛），原 aggregate_votes 内联实现已替换为此函数。
    """
    identity_names = {"buffett", "value_anchor", "value_institution"}
    weighted_sum = 0.0
    weight_total = 0.0
    for r in long_experts:
        w = 1.0 if r.get("name") in identity_names else 0.8
        weighted_sum += r["score"] * w
        weight_total += w
    return weighted_sum / weight_total if weight_total > 0 else 50.0


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
    elif direction in ("看多", "谨慎看多", "强烈看多", "中性"):
        # 否决叠加地板值保护：多个否决条件叠加时确保有最低试探仓位
        # 仅在非看空方向时生效，看空方向仓位应为 0
        if position > 0 and position < 10:
            position = 10

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
    veto_results: Optional[Dict[str, Dict[str, bool]]] = None,
) -> dict:
    """整合 8 位 active 专家投票（5 长线 + 3 短线），输出最终决策（decide.md 完整规则）。

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
        veto_results: 一票否决预评估结果。格式为
            {expert_name: {condition_desc: bool_triggered, ...}, ...}。
            触发否决的专家评分被强制降至 20（强烈看空）。

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

    # P1-19: 入口浅拷贝 expert_results，避免 veto_results 原地修改 r["score"]/direction
    # 污染调用方持有的原始评分（影响风险提示、A/B 对比、校准记录、二次渲染）。
    expert_results = [dict(r) for r in expert_results]

    # 一票否决机制：当某专家的否决条件被触发时，强制降分至 20（强烈看空）
    veto_notes = []
    if veto_results:
        for r in expert_results:
            name = r.get("name", "")
            expert_veto = veto_results.get(name, {})
            triggered = [cond for cond, triggered in expert_veto.items() if triggered]
            if triggered:
                original_score = r["score"]
                r["score"] = 20.0
                r["direction"] = "强烈看空"
                veto_notes.append(
                    f"{r.get('display_name', name)} 被一票否决"
                    f"（{'; '.join(triggered)}），评分 {original_score:.0f}→20"
                )

    # 分组：优先用专家结果自带的 group 字段；缺失时从注册表按 name 补全。
    # P0-1（v2.4.1）：原实现按规模硬编码切分（n==8->4+4，n==9->6+3），对真实
    # 8 人 active 集（5 长 + 3 短）会错切成 4+4，导致分组均值/投票统计全部错误。
    # 改为按 EXPERT_REGISTRY 的 group 字段补全，注册表查不到的条目才回退到
    # active 集真实分布（5 长 + 3 短）切分。
    if expert_results and not any(r.get("group") for r in expert_results):
        try:
            from experts.registry import EXPERT_REGISTRY

            for r in expert_results:
                profile = EXPERT_REGISTRY.get(r.get("name", ""))
                if profile is not None and not r.get("group"):
                    r["group"] = profile.group
        except ImportError:
            pass

    long_experts = [r for r in expert_results if r.get("group") == "long_term"]
    short_experts = [r for r in expert_results if r.get("group") == "short_term"]

    # 注册表也补全不了的条目（未知专家名）：按 active 集真实分布 5 长 + 3 短 切分，
    # 而非旧的 4+4。仅当仍有未分组条目时触发。
    ungrouped = [
        r for r in expert_results
        if r.get("group") not in ("long_term", "short_term")
    ]
    if ungrouped and (not long_experts or not short_experts):
        n = len(expert_results)
        # active 集真实分布：长线占 ceil(n*5/8)，短线占其余。
        long_count = -(-n * 5 // 8)  # ceil(n * 5/8)
        long_experts = expert_results[:long_count]
        short_experts = expert_results[long_count:]

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
    # 通过 _find_expert 查找：旧 8 人输入认 legacy 名，新 9 人输入回退到合并型名
    yangjia = _find_expert(expert_by_name, "chaogu_yangjia")
    buffett = _find_expert(expert_by_name, "buffett")

    yangjia_score = yangjia["score"] if yangjia else 50

    # 巴菲特否决权评分：优先使用 buffett_sub_score（独立子评分），
    # 避免合并型专家（value_institution/value_anchor）中段永平的看多稀释巴菲特的看空。
    # v2.1.2 修正：否决权判断应基于巴菲特独立观点，而非合并后总分。
    # v2.4.2（B5）：buffett 经 _LEGACY_TO_MERGED 映射到 value_institution（最终名），
    # 旧 value_anchor 中间名仍兼容（直接名查找命中）。
    if buffett and buffett.get("name") in ("value_institution", "value_anchor"):
        # 合并型专家场景：从 buffett_sub_score 字段读取巴菲特独立评分
        buffett_score = buffett.get("buffett_sub_score", buffett["score"])
    elif buffett:
        # legacy 场景：直接使用巴菲特评分
        buffett_score = buffett["score"]
    else:
        buffett_score = 50

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
    # v2.3.0 修正：降权后同步更新 short_scores 和 short_votes，避免投票方向与均值矛盾
    if yangjia_score < 30 and not is_yangjia_ice:
        identity_names = {"chaogu_yangjia", "emotion_tech"}
        adjusted_scores = []
        for r in short_experts:
            if r.get("name") in identity_names:
                adjusted_scores.append(r["score"])
            else:
                adjusted_scores.append(r["score"] * 0.7)
        short_avg = statistics.mean(adjusted_scores) if adjusted_scores else short_avg
        # 同步更新投票统计，确保方向与均值一致
        short_scores = adjusted_scores
        short_votes = _count_votes(adjusted_scores)

    # 巴菲特降权（短期模式看空时）：巴菲特自身不降，其余长线 ×0.8
    # v2.2.0 起收敛到 _buffett_downweight_policy + _apply_buffett_long_downweight
    buffett_policy = _buffett_downweight_policy(buffett_score, horizon)
    if buffett_policy["triggered"] and buffett_policy["mode"] == "weight":
        long_avg = _apply_buffett_long_downweight(long_experts)

    # 综合分
    # I16: 综合分用校准率加权--校准率越高（历史预测越准）的组权重越大
    # calibration_factor ∈ [-1, 1]，映射为长线权重调整 ±0.1
    calib_adj = calibration_factor * 0.1
    adj_lw = max(0.3, min(0.7, lw + calib_adj))
    adj_sw = 1.0 - adj_lw
    composite = long_avg * adj_lw + short_avg * adj_sw

    # 投票统计
    long_votes = _count_votes(long_scores)
    # 养家降权已更新 short_votes 时不再覆盖（避免用原始 short_scores 重算覆盖降权结果）
    if yangjia_score >= 30 or is_yangjia_ice:
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
        len(long_experts),
        len(short_experts),
    )
    direction = conflict["direction"]
    position_factor = conflict["position_factor"]
    notes = veto_notes + list(conflict["notes"])

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

    # v2.4.0: 仓位因子地板值——防止多个否决条件叠加导致仓位建议为 0
    # 仅在方向为正向（看多/谨慎看多）时保护，中性/看空方向允许 position_factor=0
    if position_factor < 0.3 and direction in ("强烈看多", "看多", "谨慎看多"):
        notes.append(f"否决叠加保护：仓位因子 {position_factor:.2f} → 0.3（地板值）")
        position_factor = 0.3

    # 信心指数
    all_scores = long_scores + short_scores
    confidence = compute_confidence_index(all_scores, composite, calibration_factor)

    # 巴菲特否决警示效果：降低信心指数而非改变方向
    # v2.4.0：原否决权改为警示，保留信号但不推翻投票共识
    if buffett_score <= 39 and horizon in ("medium", "long"):
        confidence = max(0, confidence - 15)

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

    v2.4.1 适配：长线组 5 人、短线组 3 人，投票阈值动态计算。
    多数阈值 = ceil(n * 2/3)，即 5 人需 4 票、3 人需 2 票。

    Args:
        expert_results: 该组专家的评分结果
        group: "long_term" 或 "short_term"
        calibration_factor: 校准因子

    Returns:
        与 aggregate_votes 类似的结构，但只有单组数据
    """
    scores = [r["score"] for r in expert_results]
    avg = statistics.mean(scores) if scores else 50

    votes = _count_votes(scores)
    n = len(scores)
    # 动态多数阈值：67% 多数（与双组模式一致）
    majority = max(1, -(-n * 2 // 3))  # ceil(n * 2/3)

    direction = "中性"
    position_factor = 0.0

    # 组内投票规则（动态阈值）
    if all(s >= 70 for s in scores):
        direction = "强烈看多"
        position_factor = 1.2
    elif votes["bull"] >= majority and votes["bear"] == 0:
        direction = "看多"
        position_factor = 1.0
    elif votes["bull"] >= majority and any(s <= 39 for s in scores):
        # 多数看多 + 存在否决票
        direction = "看多"
        position_factor = 0.7
    elif votes["bear"] >= majority and votes["bull"] == 0:
        # 多数看空且无看多票
        direction = "看空"
        position_factor = 0.0
    elif votes["bear"] >= majority:
        # 多数看空（可能存在少数看多票，仍判定看空）
        direction = "看空"
        position_factor = 0.0
    elif (
        votes["bull"] < majority
        and votes["bear"] < majority
        and votes["bull"] >= 1
        and votes["bear"] >= 1
        and abs(votes["bull"] - votes["bear"]) <= 1
    ):
        # 接近均势分歧（如 2:1 或 3:3），且任一方均未达多数
        direction = "中性"
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

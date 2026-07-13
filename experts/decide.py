"""专家圆桌决策引擎（编排层）。

保持原有公开 API 不变，内部委托给 market_detector / vote_engine / formatter。

公开 API：
- detect_market_state(index_quote, kline_data, breadth_data) -> dict
- aggregate_votes(expert_results, market_state, horizon, calibration_factor) -> dict
- aggregate_group_votes(expert_results, group, calibration_factor) -> dict
- run_debate(stock_code, expert_results, market_state, horizon) -> dict  (v2.4.3 新增)
- format_debate_output(result) -> str
- format_debate_brief(result) -> str  (v2.4.0 新增)
- format_debate_card(result) -> str
- format_group_output(result) -> str
"""

import logging
from typing import Optional

from experts.market_detector import detect_market_state
from experts.vote_engine import aggregate_votes, aggregate_group_votes
from experts.formatter import (
    format_debate_output,
    format_debate_brief,
    format_debate_card,
    format_group_output,
)

_logger = logging.getLogger(__name__)


def run_debate(
    stock_code: str,
    expert_results: list,
    market_state: Optional[dict] = None,
    horizon: str = "medium",
    *,
    prefer_horizon: bool = False,
    veto_results: Optional[dict] = None,
    stock_data: Optional[dict] = None,
) -> dict:
    """运行完整 debate 流程：校准因子回灌 + 风险分级 + 投票聚合 + 预测落库。

    第六轮审查（v2.4.3）新增的闭环编排器，将原本散落在 SKILL.md 手动步骤中的
    "取校准因子 -> aggregate_votes -> record_prediction" 收敛为单一入口。

    v2.5.0 Phase 2：新增 stock_data 参数，自动调用 veto_evaluator 评估
    veto_conditions 并生成 risk_coefficients，实现风险分级（刚性底线归零 +
    弹性系数折扣）。若同时传入 veto_results，risk_coefficients 优先。

    Args:
        stock_code: 股票代码（sh600989）
        expert_results: 专家评分结果列表（含 name/score/direction/group 等）
        market_state: detect_market_state 返回的 dict，None 时内部调用
        horizon: 投资期限 short/medium/long
        prefer_horizon: 期限权重优先于市场状态权重
        veto_results: 否决条件字典（向后兼容，优先级低于 risk_coefficients）
        stock_data: 股票数据 dict（含 finance/quote/kline_features），
                    传入时自动评估 veto_conditions 生成 risk_coefficients

    Returns:
        aggregate_votes 的返回 dict，附加：
        - _pred_id: 预测记录 ID（落库失败为 None）
        - _calibration_factor: 使用的校准因子
        - _risk_coefficients: 使用的风险系数（如有）
    """
    # 1. 自动获取校准因子（回灌 debate）
    calibration_factor = 0.0
    try:
        from experts.calibration import compute_calibration_factor

        calibration_factor = compute_calibration_factor()
    except Exception as e:
        _logger.debug("获取校准因子失败，使用默认 0.0: %s", e)

    # 1.5. 风险分级：自动评估 veto_conditions 生成 risk_coefficients（v2.5.0）
    risk_coefficients = None
    if stock_data is not None:
        try:
            from experts.veto_evaluator import evaluate_veto_conditions
            from experts.registry import EXPERT_REGISTRY

            # 只评估 expert_results 中实际参与的专家
            active_names = {r.get("name") for r in expert_results if r.get("name")}
            active_profiles = {
                name: EXPERT_REGISTRY[name]
                for name in active_names
                if name in EXPERT_REGISTRY
            }
            if active_profiles:
                _, risk_coefficients = evaluate_veto_conditions(
                    stock_data, active_profiles
                )
                # 过滤掉无折扣的专家（coeff=1.0），减少 notes 噪声
                risk_coefficients = {
                    name: coeff
                    for name, coeff in risk_coefficients.items()
                    if coeff < 1.0
                } or None
        except Exception as e:
            _logger.warning("风险分级评估失败（不影响 debate 结果）: %s", e)

    # 2. 投票聚合
    result = aggregate_votes(
        expert_results,
        market_state=market_state,
        horizon=horizon,
        calibration_factor=calibration_factor,
        prefer_horizon=prefer_horizon,
        veto_results=veto_results,
        risk_coefficients=risk_coefficients,
    )

    # 3. 落库预测记录
    pred_id = None
    try:
        from experts.calibration import record_prediction

        # 兼容双组/单组返回结构
        composite = result.get("composite_score") or result.get("avg_score", 0.0)
        expert_scores = {
            r.get("name"): r.get("score", 50.0)
            for r in result.get("expert_results", [])
        }
        pred_id = record_prediction(
            stock_code=stock_code,
            expert_scores=expert_scores,
            direction=result.get("direction", "中性"),
            composite_score=float(composite),
        )
    except Exception as e:
        _logger.warning("记录预测失败（不影响 debate 结果）: %s", e)

    # P1-10: 自动检查到期待验证预测数（不拉价格，不标记 verified），
    # 提示用户有 pending 预测需手动 `calibration verify` 拉价验证
    try:
        from experts.calibration import get_pending_predictions

        pending = get_pending_predictions()
        if pending:
            result["_pending_verification_count"] = len(pending)
    except Exception:
        pass

    result["_pred_id"] = pred_id
    result["_calibration_factor"] = calibration_factor
    if risk_coefficients is not None:
        result["_risk_coefficients"] = risk_coefficients
    return result


__all__ = [
    "detect_market_state",
    "aggregate_votes",
    "aggregate_group_votes",
    "run_debate",
    "format_debate_output",
    "format_debate_brief",
    "format_debate_card",
    "format_group_output",
]

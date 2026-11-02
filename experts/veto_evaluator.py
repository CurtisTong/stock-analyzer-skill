"""一票否决条件评估器（v2.5.0 Phase 2）。

填补 vote_engine.veto_results 的空接口：YAML 中各专家的 veto_conditions
原本是纯自然语言字符串（如 "ROE < 10% 或负债率 > 70%"），无任何代码
判定它们是否触发。本模块为这些条件配可执行评估器，并按优化建议#4
将硬性否决改造为"刚性底线(0/1) + 弹性风险系数(0.2-1.0)"两级体系。

设计要点：
- **刚性底线**（risk_coeff=0.0，触发则直接归零）：仅保留极少数真正的
  生存底线指标，如商誉/净资产>50%、管理层欺诈。这些一旦触发，资产
  本身存续性存疑，不应给出任何非零分数。
- **弹性风险系数**（0.2-1.0）：将"利润可预测性""周期位置""杠杆率"
  等转为折扣系数。例如处于周期高位、可预测性差的周期股 coeff=0.4，
  用这个系数乘以初步得分，而非直接给零分。这样一只财务底子优秀的
  周期股就能得到"因周期风险打折但非零"的分数。
- **不可评估条件**：veto_conditions 中约 60% 依赖市场情绪/组合持仓/
  政策等单股 stock_data 无法获取的数据，标记 evaluable=False 跳过，
  不阻塞主流程（由 LLM 在 debate 中自行判断）。

评估器映射表（_CONDITION_EVALUATORS）的 key 是 veto_conditions 的
自然语言子串，value 是 (evaluator_fn, condition_type) 元组。
匹配方式为子串包含，降低对 YAML 文案精确一致性的要求。
"""

import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

from experts.types import ExpertProfile

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 条件类型
# ═══════════════════════════════════════════════════════════════

RIGID = "rigid"  # 刚性底线：触发则 risk_coeff=0.0，直接归零
ELASTIC = "elastic"  # 弹性风险系数：0.2-1.0，折扣但非零


# 单条条件评估结果
class ConditionResult:
    """单条 veto_condition 的评估结果。"""

    __slots__ = ("triggered", "risk_coeff", "evaluable", "detail")

    def __init__(
        self,
        triggered: bool = False,
        risk_coeff: float = 1.0,
        evaluable: bool = True,
        detail: str = "",
    ):
        self.triggered = triggered
        self.risk_coeff = risk_coeff
        self.evaluable = evaluable
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "risk_coeff": self.risk_coeff,
            "evaluable": self.evaluable,
            "detail": self.detail,
        }


# ═══════════════════════════════════════════════════════════════
# 安全数值提取
# ═══════════════════════════════════════════════════════════════


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _get_fin(stock_data: dict) -> dict:
    return stock_data.get("finance") or {}


def _get_quote(stock_data: dict) -> dict:
    return stock_data.get("quote") or {}


def _get_kline(stock_data: dict) -> dict:
    return stock_data.get("kline_features") or {}


# ═══════════════════════════════════════════════════════════════
# 刚性底线评估器（触发 -> risk_coeff=0.0）
# ═══════════════════════════════════════════════════════════════


def _check_goodwill_ratio(stock_data: dict) -> ConditionResult:
    """商誉/净资产 > 50% -> 刚性底线归零。

    商誉占比过高意味着并购溢价大、减值风险高，是真正的生存底线。
    数据来源：finance.goodwill / GOODWILL, net_assets / TOTAL_EQUITY。

    （v1.26.0 现状说明）**预留能力**：16 份专家 YAML 均未声明含"商誉"的
    veto_conditions，故本检查当前不会被任何专家命中。评估器与数据接口
    已就绪，待专家档案或数据源接入后即生效——不是缺陷。
    """
    fin = _get_fin(stock_data)
    goodwill = _safe_float(fin.get("goodwill") or fin.get("GOODWILL"))
    net_assets = _safe_float(fin.get("net_assets") or fin.get("TOTAL_EQUITY") or fin.get("BPS"))
    if goodwill <= 0 or net_assets <= 0:
        return ConditionResult(evaluable=False, detail="商誉或净资产数据缺失")
    ratio = goodwill / net_assets
    if ratio > 0.5:
        return ConditionResult(
            triggered=True,
            risk_coeff=0.0,
            detail=f"商誉/净资产={ratio:.0%}>50%",
        )
    return ConditionResult(detail=f"商誉/净资产={ratio:.0%}<=50%")


def _check_fraud(stock_data: dict) -> ConditionResult:
    """管理层欺诈/财务造假 -> 刚性底线归零。

    此条件无法从财务数据自动判定（需公告/监管信息），标记不可评估。
    但提供 quote.fraud_flag 或 stock_data.fraud_flag 接口供外部注入。

    （v1.26.0 现状说明）**预留能力**：注入接口已就绪，等公告/监管数据源
    接入后即生效——不是缺陷。
    """
    fraud_flag = stock_data.get("fraud_flag") or _get_quote(stock_data).get("fraud_flag")
    if fraud_flag is None:
        return ConditionResult(evaluable=False, detail="欺诈标记数据缺失，需外部注入")
    if fraud_flag:
        return ConditionResult(
            triggered=True,
            risk_coeff=0.0,
            detail="管理层欺诈/财务造假标记为True",
        )
    return ConditionResult(detail="无欺诈标记")


# ═══════════════════════════════════════════════════════════════
# 弹性风险系数评估器（触发 -> risk_coeff 0.2-1.0）
# ═══════════════════════════════════════════════════════════════


def _check_roe_low(stock_data: dict) -> ConditionResult:
    """ROE < 10% 或负债率 > 70% -> 弹性风险系数。

    原为硬否决，现改为风险折扣：ROE过低意味着盈利能力不足，
    但不一定归零（可能只是"不符合价值投资标准"）。
    - ROE < 5% 或负债率 > 80%：risk_coeff=0.3（严重风险）
    - ROE < 10% 或负债率 > 70%：risk_coeff=0.5（中等风险）
    """
    fin = _get_fin(stock_data)
    # （v1.26.0）缺失判定改用**键存在性**而非数值：原实现用
    # "roe == 0 and debt == 50" 判定数据缺失，而 ROE=0 是合法的亏损信号
    # （亏损公司）、负债率=50 也是合法值——两者同时成立时亏损公司被误判为
    # "数据缺失"，风险折扣不触发（evaluable=False, coeff=1.0）。
    has_roe = "ROEJQ" in fin or "roe" in fin
    has_debt = "ZCFZL" in fin or "debt_ratio" in fin
    if not has_roe and not has_debt:
        return ConditionResult(evaluable=False, detail="ROE和负债率数据缺失")
    roe = _safe_float(fin.get("ROEJQ") or fin.get("roe"))
    debt = _safe_float(fin.get("ZCFZL") or fin.get("debt_ratio"), 50)

    triggered = roe < 10 or debt > 70
    if not triggered:
        return ConditionResult(detail=f"ROE={roe:.1f}%, 负债率={debt:.1f}%")

    # 严重程度分级
    if roe < 5 or debt > 80:
        return ConditionResult(
            triggered=True,
            risk_coeff=0.3,
            detail=f"ROE={roe:.1f}%<5% 或 负债率={debt:.1f}%>80%（严重）",
        )
    return ConditionResult(
        triggered=True,
        risk_coeff=0.5,
        detail=f"ROE={roe:.1f}%<10% 或 负债率={debt:.1f}%>70%（中等）",
    )


def _check_fcf_negative(stock_data: dict) -> ConditionResult:
    """FCF 为负 / 连续2年负 -> 弹性风险系数。

    单年 FCF 为负可能是暂时性资本支出，连续为负才是结构性问题。
    - FCF < 0：risk_coeff=0.6
    - 连续2年负（需多期数据）：risk_coeff=0.3

    （v1.26.0）实现连续 2 年判定：原实现只有单年分支，docstring 承诺的
    0.3 永远不会触发——YAML 里 "FCF 连续 2 年为负" 条件命中的实际是
    单年 0.6 档。现从 stock_data["finance_records"] 取多期数据判定。
    """
    fin = _get_fin(stock_data)
    fcf = _safe_float(fin.get("MGJYXJJE") or fin.get("ocf_per_share"))
    if fcf == 0 and not fin.get("MGJYXJJE"):
        return ConditionResult(evaluable=False, detail="FCF数据缺失")
    if fcf < 0:
        # 连续 2 年为负 -> 更严厉的 0.3 档（结构性问题）
        consecutive = _consecutive_negative_fcf(stock_data)
        if consecutive >= 2:
            return ConditionResult(
                triggered=True,
                risk_coeff=0.3,
                detail=f"FCF/股={fcf:.2f}<0（连续 {consecutive} 年为负）",
            )
        return ConditionResult(
            triggered=True,
            risk_coeff=0.6,
            detail=f"FCF/股={fcf:.2f}<0",
        )
    return ConditionResult(detail=f"FCF/股={fcf:.2f}>=0")


def _consecutive_negative_fcf(stock_data: dict) -> int:
    """统计连续为负的 FCF 年数（最多看最近若干期）。

    数据源：stock_data["finance_records"]（多期财务记录列表，每项含
    MGJYXJJE / ocf_per_share）。无多期数据时返回 1（只能确认当年为负）。
    """
    records = stock_data.get("finance_records")
    if not isinstance(records, list) or len(records) < 2:
        return 1
    count = 0
    for record in records[:5]:  # 最多看最近 5 期
        if not isinstance(record, dict):
            break
        value = record.get("MGJYXJJE")
        if value is None:
            value = record.get("ocf_per_share")
        if value is None:
            break
        if _safe_float(value) < 0:
            count += 1
        else:
            break  # 遇到非负即中断（只统计连续段）
    return max(1, count)


def _check_peg_high(stock_data: dict) -> ConditionResult:
    """PEG > 2.5 -> 弹性风险系数（增速无法消化估值）。

    PEG = PE / 净利增速，>2.5 意味着估值远超增速支撑。
    """
    quote = _get_quote(stock_data)
    fin = _get_fin(stock_data)
    pe = _safe_float(quote.get("pe"))
    growth = _safe_float(fin.get("PARENTNETPROFITTZ") or fin.get("net_profit_yoy"))
    if pe <= 0 or growth <= 0:
        return ConditionResult(evaluable=False, detail="PE或增速数据缺失/非正")
    peg = pe / growth
    if peg > 2.5:
        return ConditionResult(
            triggered=True,
            risk_coeff=0.4,
            detail=f"PEG={peg:.1f}>2.5",
        )
    return ConditionResult(detail=f"PEG={peg:.1f}<=2.5")


def _check_continuous_loss(stock_data: dict) -> ConditionResult:
    """连续2年亏损 -> 弹性风险系数（退市风险 + 价值陷阱）。

    需多期财务数据。单期数据无法判定连续性。
    """
    fin_records = stock_data.get("finance_records")
    if not fin_records or len(fin_records) < 4:
        return ConditionResult(evaluable=False, detail="多期财务数据缺失")
    # 检查最近4期（约2年）的 EPS 是否连续为负
    eps_values = [_safe_float(r.get("EPSJB") or r.get("eps")) for r in fin_records[:4]]
    if all(e < 0 for e in eps_values):
        return ConditionResult(
            triggered=True,
            risk_coeff=0.3,
            detail="最近4期EPS均<0（连续亏损）",
        )
    return ConditionResult(detail="无连续亏损")


def _check_cycle_position(stock_data: dict) -> ConditionResult:
    """周期位置高位 -> 弹性风险系数（v2.5.0 Phase 3）。

    调用 factors/cyclical.py 的三维度周期矩阵判定周期位置。
    周期高位 -> risk_coeff=0.4（折扣但非零，避免误杀周期成长股）。
    非周期行业 -> 不触发。
    """
    try:
        from strategies.factors.cyclical import get_cycle_position

        fin = _get_fin(stock_data)
        quote = _get_quote(stock_data)
        # 行业推断：优先用 stock_data["industry"]，否则默认
        industry = stock_data.get("industry", "默认")
        code = stock_data.get("code", "")
        position = get_cycle_position(fin, quote, industry, code)
    except Exception as e:
        logger.debug("周期位置评估失败: %s", e)
        return ConditionResult(evaluable=False, detail=f"周期评估失败: {e}")

    if position == "high":
        return ConditionResult(
            triggered=True,
            risk_coeff=0.4,
            detail="周期矩阵判定高位（≥2维高位信号）",
        )
    if position == "low":
        return ConditionResult(detail="周期矩阵判定低位（机会）")
    if position == "mid":
        return ConditionResult(detail="周期矩阵判定中性")
    return ConditionResult(evaluable=False, detail="非周期行业或数据不足")


# ═══════════════════════════════════════════════════════════════
# 条件 -> 评估器映射表
# ═══════════════════════════════════════════════════════════════
# key = veto_condition 自然语言子串（子串匹配，容错YAML文案微调）
# value = (evaluator_fn, condition_type)
#
# 未列出的条件标记为 evaluable=False（依赖市场情绪/组合持仓/政策等
# 单股 stock_data 无法获取的数据，由 LLM 在 debate 中自行判断）

_CONDITION_EVALUATORS: Dict[str, Tuple[Callable, str]] = {
    # 刚性底线
    "商誉": (_check_goodwill_ratio, RIGID),
    "造假": (_check_fraud, RIGID),
    "失信": (_check_fraud, RIGID),
    "不诚信": (_check_fraud, RIGID),
    # 弹性风险系数
    "ROE < 10%": (_check_roe_low, ELASTIC),
    "ROE<10%": (_check_roe_low, ELASTIC),
    "FCF": (_check_fcf_negative, ELASTIC),
    "PEG": (_check_peg_high, ELASTIC),
    "连续2年亏损": (_check_continuous_loss, ELASTIC),
    "连续 2 年亏损": (_check_continuous_loss, ELASTIC),
    "不赚钱": (_check_fcf_negative, ELASTIC),
    # 周期位置（v2.5.0 Phase 3）
    "周期顶部": (_check_cycle_position, ELASTIC),
    "周期顶点": (_check_cycle_position, ELASTIC),
    "行业周期顶点": (_check_cycle_position, ELASTIC),
}


def _match_evaluator(condition_desc: str) -> Optional[Tuple[Callable, str]]:
    """子串匹配：返回第一个匹配的评估器，无匹配返回 None。"""
    for key, evaluator in _CONDITION_EVALUATORS.items():
        if key in condition_desc:
            return evaluator
    return None


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════


def evaluate_veto_conditions(
    stock_data: dict,
    expert_profiles: Dict[str, ExpertProfile],
) -> Tuple[Dict[str, Dict[str, dict]], Dict[str, float]]:
    """评估所有专家的 veto_conditions，输出 veto_results + risk_coefficients。

    Args:
        stock_data: 股票数据 dict（含 finance/quote/kline_features）
        expert_profiles: {expert_name: ExpertProfile}，从 EXPERT_REGISTRY 获取

    Returns:
        (veto_results, risk_coefficients)
        - veto_results: {expert_name: {condition_desc: ConditionResult.to_dict()}}
          格式兼容 vote_engine 旧消费逻辑（含 triggered bool）
        - risk_coefficients: {expert_name: float}
          每位专家的复合风险系数（取所有触发条件中最低的 risk_coeff，
          即最严厉的折扣）。无触发条件时为 1.0（无折扣）。
    """
    veto_results: Dict[str, Dict[str, dict]] = {}
    risk_coefficients: Dict[str, float] = {}

    for name, profile in expert_profiles.items():
        if not profile.veto_conditions:
            continue

        conditions: Dict[str, dict] = {}
        min_coeff = 1.0  # 复合系数取最严厉（最低值）

        for cond_desc in profile.veto_conditions:
            matched = _match_evaluator(cond_desc)
            if matched is None:
                # 不可评估条件：标记跳过
                conditions[cond_desc] = ConditionResult(
                    evaluable=False, detail="依赖市场/组合/政策数据，需LLM判断"
                ).to_dict()
                continue

            evaluator_fn, cond_type = matched
            try:
                result = evaluator_fn(stock_data)
            except Exception as e:
                logger.warning("评估器异常 (%s): %s", cond_desc, e)
                result = ConditionResult(evaluable=False, detail=f"评估异常: {e}")
            conditions[cond_desc] = result.to_dict()

            # 复合系数：取所有触发条件中最低的 risk_coeff
            if result.triggered and result.risk_coeff < min_coeff:
                min_coeff = result.risk_coeff

        veto_results[name] = conditions
        risk_coefficients[name] = min_coeff

    return veto_results, risk_coefficients


__all__ = [
    "evaluate_veto_conditions",
    "ConditionResult",
    "RIGID",
    "ELASTIC",
]

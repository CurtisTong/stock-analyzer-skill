"""数据可得性判定（v1.26.0）。

**问题背景**：v1.24.0 引入了弃权第四态（`experts.types.ABSTAIN`），
`vote_engine` 消费侧也早已就绪，但**没有任何 `score()` 会产出弃权**——
数据缺失时专家要么把 None 当 0 分（`value_institution` 缺财务 → 11.4 分
「强烈看空」），要么把 None 当 50 分（隐性中性票）。前者会让**方向仅因
数据拉取失败就翻转**，后者把"读不出来的沉默"登记为中性票——两者都是
decide.md §一.2 明令禁止的反模式。

**本模块职责**：在评分前判断各类信号是否可得，供上层决定

1. 该专家是否应当**显式弃权**（核心信号全缺）；
2. 哪些维度应当**降权/中性化**（部分信号缺失）。

**判定原则**：区分「数据不可得」与「数据可得但差」——
PE 高是数据可得且差（应扣分），PE 字段不存在是数据不可得（不应扣分）。

数据契约（与 `experts/scoring/__init__.py::score_expert_precise` 文档一致）：

    stock_data = {
        "quote":  {"pe", "pb", "price", "circulating_cap", "pe_percentile", "name", "amount"},
        "finance": {"roe", "net_profit_yoy", "debt_ratio", "eps", "ocf_per_share"},
        "kline_features": {"trend", "rsi", "macd_signal"},
        "kline_data": {"closes", "volumes"},
        "market_features": {"limit_up_count", "advance_ratio", "break_rate", ...},
    }
"""

from typing import Dict, List, Set

# ═══════════════════════════════════════════════════════════════
# 信号分组
# ═══════════════════════════════════════════════════════════════

# 价量信号：K 线/技术指标。趋势型与情绪型专家的核心依据。
SIGNAL_PRICE_VOLUME = "价量"

# 财务信号：基本面/盈利/杠杆。价值型与风控型专家的核心依据。
SIGNAL_FINANCE = "财务"

# 题材信号：涨跌停/情绪/板块联动。题材型与情绪型专家的核心依据。
SIGNAL_SENTIMENT = "题材"

ALL_SIGNALS = (SIGNAL_PRICE_VOLUME, SIGNAL_FINANCE, SIGNAL_SENTIMENT)


def _has_number(value) -> bool:
    """值是否为可用数值（非 None、非空串、可转 float）。"""
    if value is None:
        return False
    if isinstance(value, str):
        value = value.strip()
        if not value or value in ("--", "-", "None", "null", "N/A"):
            return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _section_present(stock_data: Dict, key: str) -> bool:
    """stock_data 的某个子块是否存在且非空。"""
    section = stock_data.get(key)
    return isinstance(section, dict) and len(section) > 0


def available_signals(stock_data: Dict) -> Set[str]:
    """判断 stock_data 里哪些信号类别可得。

    Args:
        stock_data: 专家评分入参

    Returns:
        可得信号类别的集合（SIGNAL_PRICE_VOLUME / SIGNAL_FINANCE / SIGNAL_SENTIMENT 的子集）
    """
    signals: Set[str] = set()
    if not isinstance(stock_data, dict):
        return signals

    # 价量：K 线特征或原始 K 线任一可得即可
    kline_data = stock_data.get("kline_data")
    if _section_present(stock_data, "kline_features"):
        feature = stock_data["kline_features"]
        if any(_has_number(feature.get(k)) for k in ("trend", "rsi", "macd_signal")):
            signals.add(SIGNAL_PRICE_VOLUME)
    if SIGNAL_PRICE_VOLUME not in signals and isinstance(kline_data, dict):
        if kline_data.get("closes"):
            signals.add(SIGNAL_PRICE_VOLUME)

    # 财务：财务块存在且至少一个核心字段是可读数值
    if _section_present(stock_data, "finance"):
        fin = stock_data["finance"]
        if any(
            _has_number(fin.get(k)) for k in ("roe", "ROEJQ", "net_profit_yoy", "PARENTNETPROFITTZ", "eps", "EPSJB")
        ):
            signals.add(SIGNAL_FINANCE)

    # 题材：市场特征块存在且至少一个字段有值
    if _section_present(stock_data, "market_features"):
        market = stock_data["market_features"]
        if any(
            _has_number(market.get(k)) for k in ("limit_up_count", "limit_down_count", "advance_ratio", "break_rate")
        ):
            signals.add(SIGNAL_SENTIMENT)

    return signals


def missing_signals(stock_data: Dict) -> List[str]:
    """返回不可得的信号类别列表（顺序稳定）。"""
    avail = available_signals(stock_data)
    return [s for s in ALL_SIGNALS if s not in avail]


def should_abstain(stock_data: Dict, required_signals: List[str]) -> bool:
    """判断专家是否应显式弃权。

    规则（decide.md §一.2）：**专家所需的核心信号全部不可得**时弃权。
    只要还有一项核心信号可得，专家就该基于可得信息给出判断——
    弃权不是"数据不全就退出"，而是"读不出来"。

    Args:
        stock_data: 专家评分入参
        required_signals: 该专家的核心信号类别列表

    Returns:
        True 表示应当弃权
    """
    if not required_signals:
        return False
    avail = available_signals(stock_data)
    return not any(s in avail for s in required_signals)


def neutral_missing_dims(stock_data: Dict, dim_scores: Dict[str, float]) -> Dict[str, float]:
    """把因数据缺失而失真的维度分回落到中性 50。

    **问题**：部分专家把不可得数据写成 0 分（如 `xu_xiang` 的
    `circ_cap` 缺失 → 估值 0 分），再被 `weighted_merge` 的 veto 阈值
    （<10 取最低分）放大成整维度归零——CLI 真实数据形态下 `topic_leader`
    技术面被 `xu_xiang` 的 0 分 veto 到 0.0（`zhao_laoge` 本会给 80）。

    **处理**：不可得的信号 → 对应维度分重置为 50（中性），而不是 0 或保留
    失真值。这既避免"缺数据=最差信号"的隐性惩罚，也避免"缺数据=中性票"
    的隐性背书（后者由弃权路径处理：核心信号全缺时整位专家弃权）。

    Args:
        stock_data: 专家评分入参
        dim_scores: 各维度原始分（会被复制，不修改入参）

    Returns:
        修正后的维度分 dict
    """
    if not dim_scores:
        return dim_scores

    avail = available_signals(stock_data)
    result = dict(dim_scores)

    # 维度 → 依赖的信号类别
    _DIM_SIGNAL = {
        "技术面": SIGNAL_PRICE_VOLUME,
        "基本面": SIGNAL_FINANCE,
        "安全边际": SIGNAL_FINANCE,
        "估值": SIGNAL_FINANCE,
        "情绪": SIGNAL_SENTIMENT,
        "风险": SIGNAL_FINANCE,
    }

    from experts.types import normalize_dim

    for dim in list(result.keys()):
        std = normalize_dim(dim)
        required = _DIM_SIGNAL.get(std)
        if required and required not in avail:
            # 该维度依赖的信号不可得 → 回落中性
            result[dim] = 50.0

    return result


__all__ = [
    "SIGNAL_PRICE_VOLUME",
    "SIGNAL_FINANCE",
    "SIGNAL_SENTIMENT",
    "ALL_SIGNALS",
    "available_signals",
    "missing_signals",
    "should_abstain",
    "neutral_missing_dims",
]

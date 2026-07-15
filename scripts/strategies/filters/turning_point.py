"""
拐点修复两阶段模型：Stage 1 硬条件过滤 + Stage 2 因子加权打分。

解决问题（review#2）：原 turning_point 与 balanced 区分度不足，
两策略输出大量重叠股票。引入 Stage 1 硬条件显著提高策略专一性。

Stage 1 硬条件（须全部满足）：
  1. 超卖：20 日跌幅 ≤ -10%
  2. 量能恢复：5 日均量 ≥ 20 日均量 × 1.0（至少不萎缩）
  3. 基本面底线：ROE > 8% 且 EPS > 0
  4. 资金流向确认（#4）：近 5 日大单净流入 ≥ 3 日
     - 数据不可用时降级为"放量日（volume_ratio>1.2）同步上涨"判定

可选加分（满足其一增加通过优先级）：
  - MACD 底背离信号
  - KDJ 超卖金叉

通过 Stage 1 的股票进入 Stage 2（复用 balanced 因子加权打分）。
未通过 Stage 1 的股票在 result 中以 rejected=["未通过拐点过滤: <原因>"] 标记。
"""

from common import to_float


def turning_point_filter(
    quote: dict, fin: dict, features: dict, flow_data: list = None
) -> tuple:
    """拐点修复 Stage 1 硬条件过滤。

    Args:
        quote: 行情 dict（含 amount/turnover 等）
        fin: 财务 dict（含 roe/eps 等）
        features: 技术指标 dict（含 ret20/volume_ratio/macd_signal 等）
        flow_data: 近 5 日资金流向数据 list（可选，每项含 main_net 字段）。
                   None 时自动获取；获取失败降级为放量日上涨判定。

    Returns:
        (pass, reason) - pass=True 进入 Stage 2 打分；False 写明拒绝原因
    """
    reasons = []

    # 1. 超跌确认：20 日跌幅 ≤ -10%
    ret20 = features.get("ret20", 0)
    # 数据缺失（ret20 == 0 且 features 无该字段）时跳过该检查
    if "ret20" in features and ret20 > -10:
        reasons.append(f"未超跌(ret20={ret20:.1f}%>-10%)")

    # 2. 量能恢复：5 日均量 ≥ 20 日均量 × 1.0（至少不萎缩）
    volume_ratio = features.get("volume_ratio", 1)
    if volume_ratio < 1.0:
        reasons.append(f"量能萎缩(vol_ratio={volume_ratio:.2f}<1.0)")

    # 3. 基本面底线：ROE > 8% 且 EPS > 0
    roe = to_float(fin.get("roe", 0))
    eps = to_float(fin.get("eps", 0))
    if roe <= 8 or eps <= 0:
        reasons.append(f"基本面差(ROE={roe:.1f}, EPS={eps})")

    # 4. (#4) 资金流向确认：近 5 日大单净流入 ≥ 3 日
    flow_pass, flow_reason = _check_fund_flow(quote, features, flow_data)
    if not flow_pass:
        reasons.append(flow_reason)

    return (len(reasons) == 0, "; ".join(reasons))


def _check_fund_flow(quote: dict, features: dict, flow_data: list = None) -> tuple:
    """(#4) 资金流向确认。

    优先使用主力净流入数据；不可用时降级为"放量日同步上涨"判定。

    Args:
        quote: 行情 dict
        features: 技术指标 dict
        flow_data: 预取的资金流向数据（可选）

    Returns:
        (pass, reason) - pass=True 表示资金确认通过
    """
    # 尝试使用预取的 flow_data
    if flow_data is None:
        flow_data = _fetch_main_flow(quote.get("code", ""))

    if flow_data and len(flow_data) >= 3:
        # 主力净流入确认：近 5 日中 ≥ 3 日为大单净流入
        recent_5 = flow_data[:5]
        positive_days = sum(1 for d in recent_5 if _get_main_net(d) > 0)
        if positive_days >= 3:
            return (True, "")
        return (False, f"资金未确认(近{len(recent_5)}日仅{positive_days}日净流入)")

    # 降级路径：放量日同步上涨判定
    # volume_ratio > 1.2 表示放量，ret20 < 0 表示近期下跌后反弹
    # 量价配合信号 > 0 表示放量日同步上涨
    volume_ratio = features.get("volume_ratio", 1)
    vol_price_signal = features.get("vol_price_signal", 0)

    if volume_ratio > 1.2 and vol_price_signal > 0:
        return (True, "")

    return (
        False,
        f"资金未确认(降级:vol_ratio={volume_ratio:.2f},vol_price={vol_price_signal})",
    )


def _fetch_main_flow(code: str) -> list:
    """获取近 5 日主力资金流向数据。

    Returns:
        每日 dict list（含 main_net 字段），失败返回空 list。
    """
    if not code:
        return []
    try:
        from data.flow import get_stock_flow

        result = get_stock_flow(code, days=5)
        if result and isinstance(result, dict):
            days = result.get("days", [])
            if isinstance(days, list):
                return days
    except Exception:
        pass
    return []


def _get_main_net(day_data) -> float:
    """从日级资金流向数据中提取主力净流入。"""
    if isinstance(day_data, dict):
        return to_float(day_data.get("main_net", 0))
    return 0.0

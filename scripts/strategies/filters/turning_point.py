"""
拐点修复两阶段模型：Stage 1 硬条件过滤 + Stage 2 因子加权打分。

解决问题（review#2）：原 turning_point 与 balanced 区分度不足，
两策略输出大量重叠股票。引入 Stage 1 硬条件显著提高策略专一性。

Stage 1 硬条件（须全部满足）：
  1. 超卖：20 日跌幅 ≤ -10%
  2. 量能恢复：5 日均量 ≥ 20 日均量 × 0.8
  3. 基本面底线：ROE > 5% 且 EPS > 0

通过 Stage 1 的股票进入 Stage 2（复用 balanced 因子加权打分）。
未通过 Stage 1 的股票在 result 中以 rejected=["未通过拐点过滤: <原因>"] 标记。
"""

from common import to_float


def turning_point_filter(quote: dict, fin: dict, features: dict) -> tuple:
    """拐点修复 Stage 1 硬条件过滤。

    Args:
        quote: 行情 dict（含 amount/turnover 等）
        fin: 财务 dict（含 roe/eps 等）
        features: 技术指标 dict（含 ret20/volume_ratio/macd_signal 等）

    Returns:
        (pass, reason) - pass=True 进入 Stage 2 打分；False 写明拒绝原因
    """
    reasons = []

    ret20 = features.get("ret20", 0)
    if ret20 > -10:
        reasons.append(f"未超跌(ret20={ret20:.1f}%>-10%)")

    volume_ratio = features.get("volume_ratio", 1)
    if volume_ratio < 0.8:
        reasons.append(f"量能未恢复(vol_ratio={volume_ratio:.2f}<0.8)")

    roe = to_float(fin.get("roe", 0))
    eps = to_float(fin.get("eps", 0))
    if roe <= 5 or eps <= 0:
        reasons.append(f"基本面差(ROE={roe:.1f}, EPS={eps})")

    return (len(reasons) == 0, "; ".join(reasons))

"""杜邦三因子分解：ROE = 净利率 × 总资产周转率 × 权益乘数。

解决审查 #9（🔴 严重）：原始报告用 0.70 估算总资产周转率，得 30% 与实际
ROE 24.84% 对不上。本模块用真实财务数据计算三因子，并与原始 ROE 对账，
偏差 >1pp 输出 warning，杜绝数值自相矛盾。

数据来源：FinanceRecord.to_dict()（阶段一 1.1 已补齐 total_revenue /
total_liability / total_assets / net_assets / net_margin / debt_ratio）。
"""

from common import to_float

# 对账偏差阈值（百分点）：重建 ROE 与原始 ROE 偏差超过此值标记异常。
# 设 2.0pp 因东财净利率基于营业收入、ROE 基于平均净资产，口径差异本身约 1-2pp。
RECONCILIATION_THRESHOLD_PP = 2.0


def dupont_analysis(fin: dict) -> dict:
    """三因子杜邦分解 + ROE 对账。

    公式：ROE = 净利率(%) × 总资产周转率(次) × 权益乘数
    - 总资产周转率 = 营收 / 总资产
    - 权益乘数 = 总资产 / 净资产
    - 重建 ROE = net_margin × asset_turnover × equity_multiplier（百分比口径）

    Args:
        fin: FinanceRecord.to_dict()，需含以下字段（阶段一 1.1 已采集）：
            - net_margin: 净利率(%)
            - total_revenue: 营业总收入(亿)
            - total_assets: 总资产(亿，计算字段=负债/负债率)
            - net_assets: 净资产(亿，计算字段=总资产-负债)
            - roe: 原始 ROE(%)，用于对账
            可选回退：若 total_assets/net_assets 为 0，尝试用 total_liability +
            debt_ratio 反推。

    Returns:
        {
            "net_margin": float,            # 净利率(%)
            "asset_turnover": float,        # 总资产周转率(次)
            "equity_multiplier": float,     # 权益乘数(倍)
            "roe_original": float,          # 原始 ROE(%)
            "roe_reconstructed": float,     # 重建 ROE(%)
            "reconciliation_error": float,  # 对账偏差(pp)
            "reconciliation_ok": bool,      # 偏差 <= 阈值
            "total_assets": float,          # 总资产(亿)
            "net_assets": float,            # 净资产(亿)
            "warning": str,                 # 异常提示（空字符串=正常）
        }
    """
    net_margin = to_float(fin.get("net_margin", 0))
    total_revenue = to_float(fin.get("total_revenue", 0))
    total_assets = to_float(fin.get("total_assets", 0))
    net_assets = to_float(fin.get("net_assets", 0))
    roe_original = to_float(fin.get("roe", 0))

    # 回退：若 total_assets 未填充，用 负债/负债率 反推
    if total_assets <= 0:
        total_liability = to_float(fin.get("total_liability", 0))
        debt_ratio = to_float(fin.get("debt_ratio", 0))
        if total_liability > 0 and debt_ratio > 0:
            total_assets = total_liability / (debt_ratio / 100.0)

    # 回退：若 net_assets 未填充，用 总资产 - 负债
    if net_assets <= 0 and total_assets > 0:
        total_liability = to_float(fin.get("total_liability", 0))
        if total_liability > 0:
            net_assets = total_assets - total_liability

    warning = ""

    # 数据完整性检查
    if total_revenue <= 0:
        warning = "营收为 0，无法计算总资产周转率"
    if total_assets <= 0:
        warning = (warning + "; " if warning else "") + "总资产为 0，无法分解"
    if net_assets <= 0:
        warning = (warning + "; " if warning else "") + "净资产为 0，无法计算权益乘数"

    # 计算三因子
    asset_turnover = total_revenue / total_assets if total_assets > 0 else 0.0
    equity_multiplier = total_assets / net_assets if net_assets > 0 else 0.0

    # 重建 ROE：net_margin(%) × turnover × multiplier
    # 注意单位：net_margin 是百分比（如 23.63），turnover 和 multiplier 是倍数
    # 结果也是百分比（如 23.63 × 0.533 × 1.862 ≈ 23.45%）
    roe_reconstructed = net_margin * asset_turnover * equity_multiplier

    # 对账
    reconciliation_error = abs(roe_reconstructed - roe_original)
    reconciliation_ok = reconciliation_error <= RECONCILIATION_THRESHOLD_PP
    if reconciliation_ok and not warning:
        warning = ""
    elif not reconciliation_ok:
        warn_msg = (
            f"对账偏差 {reconciliation_error:.2f}pp 超阈值 "
            f"{RECONCILIATION_THRESHOLD_PP}pp（重建 {roe_reconstructed:.2f}% "
            f"vs 原始 {roe_original:.2f}%），请核查数据来源"
        )
        warning = (warning + "; " if warning else "") + warn_msg

    return {
        "net_margin": round(net_margin, 2),
        "asset_turnover": round(asset_turnover, 4),
        "equity_multiplier": round(equity_multiplier, 4),
        "roe_original": round(roe_original, 2),
        "roe_reconstructed": round(roe_reconstructed, 2),
        "reconciliation_error": round(reconciliation_error, 2),
        "reconciliation_ok": reconciliation_ok,
        "total_assets": round(total_assets, 2),
        "net_assets": round(net_assets, 2),
        "warning": warning,
    }

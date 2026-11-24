"""宽基+黄金 sleeve 敞口闸 E₀ 计算（Chief 2026-11-23 拍板固化，零外部依赖）。

背景：E₀ 多次手算出分歧（0.7252 → 1.2999 → 0.7621 → 0.4379）。旧值 0.7252/1.2999
口径不同，0.7621 是三腿（中证1000+科创50+黄金）、11-23 收盘口径；11-24 用户清仓
科创50 后 sleeve 少一腿，生效基准改为**两腿 E₀=0.4379**（操盘/研判独立复算一致）。
根因是 E₀ 全靠手算对账、没带口径元数据。本模块把计算固化成函数，
**强制带四字段元数据：持仓清单 / 基准代码 / 末根日期 / 价格日期**，E₀ 由函数算不许手填。

sleeve 定义（Chief / 操盘 11-24 定案）：只含「宽基 + 黄金」——中证1000、黄金。
科创50 已于 11-24 清仓、深100 更早清仓，个股（广合等）从来不在 sleeve 内。
处分腿卖的就是宽基，触发变量与处分变量同口径才满足 T/A/R 三段式。

公式：E₀ = Σ(w_i × β_i)，w_i = (qty_i × px_i) / total_assets。
阈值是相对的 `E ≥ 当日同口径 E₀`，所以 E₀ 绝对值本身不是开关——但口径必须钉死：
**基准代码、K 线末根日期、账本价格日期必须同一天**，不许 11-20 和 11-23 混算。

反证与边界：
- β 由调用方注入（可来自 industry_beta.compute_beta 或其它），本模块不联网、不读缓存；
  这样测试能锁住固定基准，也避免"仓库算法算出的 β 和手算 β 不同"再次引发口径争议。
- 个股高 β（如广合 4.3、CI [2.93,5.60]）不在 sleeve，不影响本闸；若将来扩到全组合
  口径，必须报区间/稳健 β，不能用假精确点估计。
- 缺失字段一律 None（不填 0）；任一 sleeve 标的缺 β 或缺持仓 → E₀ 为 None、不可启用。
"""
from __future__ import annotations

from datetime import date


# sleeve 默认成员（宽基 + 黄金）；可传入自定义，但必须符合"处分腿同口径"
# 11-24 科创50 清仓后 sleeve 由三腿减为两腿；0.7621 三腿基准作废。
DEFAULT_SLEEVE = ("sz159845", "sz159934")  # 中证1000 / 黄金


def compute_exposure(
    holdings: dict[str, dict],
    total_assets: float | None,
    betas: dict[str, float | None],
    *,
    benchmark: str | None,
    last_bar_date: str | None,
    price_date: str | None,
    beta_method: str | None,
    sleeve: tuple[str, ...] = DEFAULT_SLEEVE,
) -> dict:
    """计算 sleeve 敞口 E₀，强制附带四字段口径元数据 + β 算法来源。

    Args:
        holdings: {code: {"qty": float, "px": float}}，至少覆盖 sleeve 全部标的。
        total_assets: 账本总资产（权威值）；缺失返回不可用。
        betas: {code: beta}，sleeve 各标的的 β（注入，不联网）；缺任一 → 不可用。
        benchmark: 基准指数代码（如 sh000001）——元数据字段 2。
        last_bar_date: K 线末根日期 YYYY-MM-DD——元数据字段 3。
        price_date: 账本价格基准日 YYYY-MM-DD——元数据字段 4。
        beta_method: β 的算法+数据源标识（如 sina_60d_sh000001 / repo_compute_beta）。
            必填——Chief 11-23 补：不写算法名就等于没写口径；同组 β 不同算法会给出
            不同的 E₀（0.7621 vs 0.7625），缺此字段不给 E₀。
        sleeve: sleeve 成员代码元组——元数据字段 1 的一部分。

    Returns:
        dict:
          e0                —— Σ(w×β)；缺字段时为 None（不可启用）
          available         —— e0 是否可用（所有字段齐全且校验通过）
          holdings          —— sleeve 持仓清单 [{code, qty, px, market_value, weight, beta, contribution}]
          benchmark         —— 基准代码（元数据 2）
          last_bar_date     —— K 线末根日期（元数据 3）
          price_date        —— 账本价格基准日（元数据 4）
          beta_method       —— β 算法+数据源标识（缺失不给 E₀）
          sleeve            —— sleeve 成员（元数据 1 的口径定义）
          date_aligned      —— last_bar_date == price_date（口径一致性，False 则禁止启用）
          reason            —— 不可用/口径不齐时的原因

    反证：E₀ 是相对阈值的基准，绝对值变化不改变 `E≥当日同口径E₀` 的触发逻辑；
    但若 last_bar_date ≠ price_date，β 与权重不同日，闸门必须拒绝启用（date_aligned=False）。
    """
    meta = {
        "holdings": list(sleeve),
        "benchmark": benchmark,
        "last_bar_date": last_bar_date,
        "price_date": price_date,
        "beta_method": beta_method,
        "sleeve": list(sleeve),
    }

    def unavailable(reason: str) -> dict:
        return {**meta, "e0": None, "available": False, "date_aligned": False, "reason": reason,
                "detail": []}

    if not total_assets or total_assets <= 0:
        return unavailable("总资产缺失或非正")
    if not benchmark or not last_bar_date or not price_date:
        return unavailable("四字段元数据不全（benchmark/last_bar_date/price_date）")
    if not beta_method:
        return unavailable("缺 beta_method（β 算法+数据源标识），不写算法名等于没写口径")

    date_aligned = last_bar_date == price_date

    detail = []
    e0 = 0.0
    for code in sleeve:
        h = holdings.get(code) or {}
        qty, px = h.get("qty"), h.get("px")
        beta = betas.get(code)
        if qty is None or px is None or px <= 0 or beta is None:
            return unavailable(f"sleeve 标的 {code} 缺 qty/px/beta（缺失不填 0）")
        mv = qty * px
        weight = mv / total_assets
        contribution = weight * beta
        e0 += contribution
        detail.append({
            "code": code, "qty": qty, "px": px, "market_value": round(mv, 2),
            "weight": round(weight, 6), "beta": beta, "contribution": round(contribution, 6),
        })

    return {
        **meta,
        "e0": round(e0, 4),
        "available": True,
        "date_aligned": date_aligned,
        "reason": None if date_aligned else "K 线末根日期 ≠ 账本价格日期，口径不齐禁止启用",
        "detail": detail,
    }


if __name__ == "__main__":
    import json

    # 自检：11-24 清仓科创50 后的两腿回归基准（注入实取 β，非本模块联网计算）
    holdings = {
        "sz159845": {"qty": 50000, "px": 2.415},
        "sz159934": {"qty": 8200, "px": 7.723},
    }
    # β 来源：操盘/研判 2026-11-24 实取（sina 日 K，共同窗 2026-08-24~11-24，n=60，
    # 指数与标的末根同为 11-24）；E₀=0.4379，逐项贡献中证1000 0.3771 + 黄金 0.0608。
    # 账本 _meta.updated=2026-11-24T21:42、price_date=11-24、总资产 709527.92。
    betas = {"sz159845": 2.2157, "sz159934": 0.6810}
    r = compute_exposure(
        holdings, 709527.92, betas,
        benchmark="sh000001", last_bar_date="2026-11-24", price_date="2026-11-24",
        beta_method="sina_60d_sh000001",
    )
    print(json.dumps(r, ensure_ascii=False, indent=1))

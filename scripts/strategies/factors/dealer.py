"""庄股识别（独立走势+毛刺+反复破位+小市值）。

策略定义：独立走势，毛刺较多，反复破位，有上下影线，不跟大盘涨跌，几十亿市值。

核心复用：
- industry_beta.compute_beta 的 R²/beta 判断独立走势（R²低=不被大盘解释=独立）
- shadow_stats 影线占比判断毛刺
- volatility.compute_atr 判断振幅

依赖: industry_beta (compute_beta), technical.shadow_stats, technical.volatility
"""

import logging

from common import to_float
from technical.shadow_stats import shadow_ratio_stats
from technical.volatility import compute_atr

logger = logging.getLogger(__name__)

# 默认阈值
_DEFAULT_CAP_RANGE = [20, 150]
_DEFAULT_R2_MAX = 0.2
_DEFAULT_BETA_ABS_MAX = 0.5
_DEFAULT_SHADOW_PCT_THRESHOLD = 40
_DEFAULT_SCORE_THRESHOLD = 60


def detect_dealer_stock(code, quote, records, closes, highs, lows):
    """识别庄股（四维打分 0-100）。

    Args:
        code: 股票代码
        quote: 行情快照 dict（含 circulating_cap 亿）
        records: KlineBar dict 列表（含 open/high/low/close）
        closes/highs/lows: 并行价格序列

    Returns:
        dict: {
            "is_dealer": bool,
            "score": int,              # 0-100
            "reasons": list[str],
            "independence": str,       # 独立走势判定
            "shadow_pct": float,       # 长影线占比%
            "market_cap": float,       # 流通市值（亿）
            "r_squared": float|None,   # R²
            "beta": float|None,        # beta
        }
    """
    # 加载配置阈值
    try:
        from config.loader import ConfigLoader

        cap_range = ConfigLoader.get(
            "limits.yaml", "dealer_stock.cap_range", _DEFAULT_CAP_RANGE
        )
        r2_max = ConfigLoader.get(
            "limits.yaml", "dealer_stock.r_squared_max", _DEFAULT_R2_MAX
        )
        beta_abs_max = ConfigLoader.get(
            "limits.yaml", "dealer_stock.beta_abs_max", _DEFAULT_BETA_ABS_MAX
        )
        shadow_pct_threshold = ConfigLoader.get(
            "limits.yaml",
            "dealer_stock.shadow_pct_threshold",
            _DEFAULT_SHADOW_PCT_THRESHOLD,
        )
        score_threshold = ConfigLoader.get(
            "limits.yaml", "dealer_stock.score_threshold", _DEFAULT_SCORE_THRESHOLD
        )
    except Exception:
        cap_range = _DEFAULT_CAP_RANGE
        r2_max = _DEFAULT_R2_MAX
        beta_abs_max = _DEFAULT_BETA_ABS_MAX
        shadow_pct_threshold = _DEFAULT_SHADOW_PCT_THRESHOLD
        score_threshold = _DEFAULT_SCORE_THRESHOLD

    circulating_cap = to_float(quote.get("circulating_cap", 0)) if quote else 0

    reasons = []
    score = 0
    r_squared = None
    beta = None
    independence = "未知"

    # ── 维度1：独立走势（35分）──
    # 复用 industry_beta.compute_beta，R²低=独立走势
    try:
        from industry_beta import compute_beta

        beta_result = compute_beta(code, window=60)
        r_squared = beta_result.get("r_squared")
        beta = beta_result.get("beta")

        if r_squared is not None and beta is not None:
            beta_abs = abs(beta)
            if r_squared < 0.1 and beta_abs < 0.3:
                score += 35
                independence = "极独立(R²<0.1,|β|<0.3)"
                reasons.append(f"独立走势(R²={r_squared:.2f},β={beta:.2f})")
            elif r_squared < r2_max and beta_abs < beta_abs_max:
                score += 25
                independence = f"较独立(R²<{r2_max})"
                reasons.append(f"较独立走势(R²={r_squared:.2f})")
            elif r_squared < 0.3:
                score += 15
                independence = "弱独立(R²<0.3)"
            else:
                independence = f"跟随大盘(R²={r_squared:.2f})"
    except Exception as e:
        logger.debug("compute_beta 失败，独立走势维度跳过: %s", e)

    # 独立走势是庄股的必要条件：得分为0则直接返回非庄股
    if score == 0:
        return {
            "is_dealer": False,
            "score": 0,
            "reasons": ["无独立走势特征(跟随大盘)"],
            "independence": independence,
            "shadow_pct": 0,
            "market_cap": round(circulating_cap, 1),
            "r_squared": r_squared,
            "beta": beta,
        }

    # ── 维度2：毛刺/影线（25分）──
    shadow_pct = 0
    shadow_stats = shadow_ratio_stats(records, window=20)
    if shadow_stats:
        shadow_pct = shadow_stats.get("long_shadow_pct", 0)
        avg_body_ratio = shadow_stats.get("avg_body_ratio", 1)

        if shadow_pct > shadow_pct_threshold and avg_body_ratio < 0.3:
            score += 25
            reasons.append(
                f"毛刺多(长影线{shadow_pct:.0f}%+实体小{avg_body_ratio:.1%})"
            )
        elif shadow_pct > shadow_pct_threshold * 0.625:  # 25%
            score += 15
            reasons.append(f"影线较多(长影线{shadow_pct:.0f}%)")

    # ── 维度3：振幅（20分）──
    if highs and lows and closes and len(closes) >= 15:
        atr = compute_atr(highs, lows, closes, period=14)
        last_price = closes[-1]
        if last_price > 0 and atr > 0:
            atr_pct = atr / last_price * 100
            if atr_pct > 4:
                score += 20
                reasons.append(f"高振幅(ATR/价={atr_pct:.1f}%)")
            elif atr_pct > 2.5:
                score += 10
                reasons.append(f"中等振幅(ATR/价={atr_pct:.1f}%)")

    # ── 维度4：市值（20分）──
    cap_low, cap_high = cap_range[0], cap_range[1]
    if cap_low <= circulating_cap <= cap_high:
        score += 20
        reasons.append(f"流通市值{circulating_cap:.0f}亿(庄股典型区间)")
    elif cap_high < circulating_cap <= cap_high * 2:  # 150-300亿
        score += 10
        reasons.append(f"流通市值{circulating_cap:.0f}亿(偏大)")

    is_dealer = score >= score_threshold

    return {
        "is_dealer": is_dealer,
        "score": score,
        "reasons": reasons,
        "independence": independence,
        "shadow_pct": round(shadow_pct, 1),
        "market_cap": round(circulating_cap, 1),
        "r_squared": r_squared,
        "beta": round(beta, 2) if beta is not None else None,
    }

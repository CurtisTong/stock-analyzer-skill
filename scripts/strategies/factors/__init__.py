"""
因子实现：quality / valuation / momentum / liquidity / volatility / dividend / chip。
自动注册到因子注册表。
"""

from .quality import quality_score
from .valuation import valuation_score
from .momentum import momentum_score
from .liquidity import liquidity_score
from .volatility import volatility_score, volatility_from_closes
from .dividend import dividend_score
from .chip import chip_score_static, chip_score_dynamic, chip_details
from .event import event_score
from .analyst import analyst_expectation_score
from .cyclical import cyclical_score, get_cycle_position
from .sentiment import sentiment_score
from .registry import (
    register_factor,
    get_factor_keys,
    compute_factor_correlation_matrix,
    compute_vif,
    decorrelate_factors,
)

# ---------- 自动注册内置因子 ----------

register_factor(
    "quality",
    compute_fn=quality_score,
    phase=1,
    args_style="fin_industry",
    label="质量",
    default_weight=0.30,
)

register_factor(
    "valuation",
    compute_fn=valuation_score,
    phase=1,
    args_style="quote_fin_industry",
    label="估值",
    default_weight=0.20,
)

register_factor(
    "momentum",
    compute_fn=momentum_score,
    phase=2,
    args_style="features_quote",
    label="动量",
    default_weight=0.15,
    requires_kline=True,
)

register_factor(
    "liquidity",
    compute_fn=liquidity_score,
    phase=1,
    args_style="quote",
    label="流动性",
    default_weight=0.05,
)

register_factor(
    "volatility",
    compute_fn=volatility_from_closes,
    phase=2,
    args_style="features_closes_industry",
    label="波动率",
    default_weight=0.15,
    requires_kline=True,
)

register_factor(
    "dividend",
    compute_fn=dividend_score,
    phase=2,
    args_style="quote_fin_industry",
    label="红利",
    default_weight=0.05,
)

register_factor(
    "chip",
    compute_fn=chip_score_static,
    phase=2,
    args_style="code",
    label="筹码",
    default_weight=0.10,
)

register_factor(
    "event",
    compute_fn=event_score,
    phase=1,
    args_style="code",
    label="事件",
    # (#10) 灰度上线 0.05，IC 跟踪 6 个月后决定是否提权
    default_weight=0.05,
)

register_factor(
    "analyst",
    compute_fn=analyst_expectation_score,
    phase=1,
    args_style="quote_fin_industry",
    label="分析师",
    default_weight=0.0,
)

# 周期因子（多因子周期位置矩阵）
# 非周期行业返回中性 50，不影响评分；周期行业按价格/供给/成本三维度评估
register_factor(
    "cyclical",
    compute_fn=cyclical_score,
    phase=1,
    args_style="fin_quote_features_industry_code",
    label="周期",
    default_weight=0.0,  # 默认 0，策略按需配置权重
)

# 情绪因子（v1.26 阶段 1）：个股级情绪强度（连板高度/封板质量/板块热度/活跃度）
# 权重默认 0——先作为参考列可观测可验证，阶段 2 经 OOS 验证后仅给
# growth_momentum 加权（见 docs/design/sentiment-factor-design.md）。
# phase=1：涨停池/炸板池是全市场 2 次 HTTP，与股票池规模无关。
register_factor(
    "sentiment",
    compute_fn=sentiment_score,
    phase=1,
    args_style="code",
    label="情绪",
    default_weight=0.0,
)

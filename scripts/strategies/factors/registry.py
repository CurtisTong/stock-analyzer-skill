"""因子注册表：管理因子定义、计算函数和元数据。

新增因子只需一次 register_factor() 调用，系统自动发现：
  - compute_factor_parts: 全量因子计算
  - compute_phase1_parts: Phase 1 轻量因子
  - normalize_factors_batch: z-score 标准化
  - build_result_row: 结果行字段

示例（新增 ESG 因子）：
    from strategies.factors.registry import register_factor
    register_factor("esg", compute_fn=esg_score, phase=1, args_style="fin_industry")

P2-05 (v2.0): 因子共线性治理
  - compute_factor_correlation_matrix(): Pearson 相关矩阵（诊断）
  - compute_vif(): 方差膨胀因子（诊断，VIF > 10 表示严重共线性）
  - decorrelate_factors(): 残差化去相关变换（可选，保留 9-key 接口）
  - decorrelate 默认关闭，通过 compute_weighted_score_with_norm(decorrelate=True) 启用
"""

import logging
import threading
from enum import Enum
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)


class Phase(int, Enum):
    """因子计算阶段。"""

    PHASE1 = 1  # 不依赖 K 线（轻量，全市场初筛）
    PHASE2 = 2  # 依赖 K 线（精排）


class ArgsStyle(str, Enum):
    """因子计算函数的参数签名风格。

    注册表根据此类型自动构造 kwargs 调用 compute_fn，
    消除每个因子的手动参数适配。
    """

    FIN_INDUSTRY = "fin_industry"  # (fin, industry)
    QUOTE_FIN_INDUSTRY = "quote_fin_industry"  # (quote, fin, industry)
    FEATURES_QUOTE = "features_quote"  # (features, quote)
    QUOTE = "quote"  # (quote,)
    FEATURES_CLOSES_INDUSTRY = "features_closes_industry"  # (closes, industry)
    CODE = "code"  # (code,)
    FIN_QUOTE_FEATURES_INDUSTRY = (
        "fin_quote_features_industry"  # (fin, quote, features, industry)
    )


class FactorDescriptor:
    """因子描述符。"""

    __slots__ = (
        "name",
        "compute_fn",
        "phase",
        "args_style",
        "label",
        "default_weight",
        "requires_kline",
    )

    def __init__(
        self,
        name: str,
        compute_fn: Callable,
        phase: Phase = Phase.PHASE2,
        args_style: ArgsStyle = ArgsStyle.FIN_INDUSTRY,
        label: str = "",
        default_weight: float = 0.0,
        requires_kline: bool = False,
    ):
        self.name = name
        self.compute_fn = compute_fn
        self.phase = phase
        self.args_style = args_style
        self.label = label or name
        self.default_weight = default_weight
        self.requires_kline = requires_kline


# ---------- 全局注册表 ----------

_FACTORS: Dict[str, FactorDescriptor] = {}

# RLock 守护 _FACTORS 全局 dict 的写路径；compute_all_factors / compute_phase_factors
# 在锁内 snapshot，避免并发 register_factor 触发的 RuntimeError
_FACTORS_LOCK = threading.RLock()


def register_factor(
    name: str,
    compute_fn: Callable,
    phase: int = 2,
    args_style: str = "fin_industry",
    label: str = "",
    default_weight: float = 0.0,
    requires_kline: bool = False,
) -> None:
    """注册新因子。

    Args:
        name: 因子名称（如 "quality", "esg"）
        compute_fn: 评分函数，返回 float (0-100)
        phase: 计算阶段（1=不依赖K线，2=依赖K线）
        args_style: 参数签名风格，见 ArgsStyle 枚举
        label: 中文标签
        default_weight: balanced 策略下的默认权重
        requires_kline: 是否需要 K 线数据
    """
    with _FACTORS_LOCK:
        _FACTORS[name] = FactorDescriptor(
            name=name,
            compute_fn=compute_fn,
            phase=Phase(phase),
            args_style=ArgsStyle(args_style),
            label=label or name,
            default_weight=default_weight,
            requires_kline=requires_kline,
        )


def get_factor(name: str) -> FactorDescriptor:
    """获取因子描述符。"""
    with _FACTORS_LOCK:
        if name not in _FACTORS:
            raise KeyError(f"未知因子: {name}，可用: {list(_FACTORS.keys())}")
        return _FACTORS[name]


def list_factors() -> List[str]:
    """列出所有已注册因子名。"""
    with _FACTORS_LOCK:
        return list(_FACTORS.keys())


def list_phase_factors(phase: int) -> List[str]:
    """列出指定阶段的因子名。"""
    with _FACTORS_LOCK:
        return [name for name, desc in _FACTORS.items() if desc.phase.value == phase]


def clear_factors() -> None:
    """清空注册表（仅用于测试隔离）。"""
    with _FACTORS_LOCK:
        _FACTORS.clear()


def get_factor_keys() -> List[str]:
    """获取所有因子名（用于 normalize_factors_batch 等场景）。"""
    with _FACTORS_LOCK:
        return list(_FACTORS.keys())


# ---------- 自动调用器 ----------


def _build_kwargs(
    desc: "FactorDescriptor",
    fin: dict,
    quote: dict,
    features: dict,
    industry: str,
    code: str,
) -> dict:
    """根据 args_style 构造 compute_fn 的 kwargs。"""
    style = desc.args_style
    if style == ArgsStyle.FIN_INDUSTRY:
        return {"fin": fin, "industry": industry}
    if style == ArgsStyle.QUOTE_FIN_INDUSTRY:
        return {"quote": quote, "fin": fin, "industry": industry}
    if style == ArgsStyle.FEATURES_QUOTE:
        return {"features": features, "quote": quote}
    if style == ArgsStyle.QUOTE:
        return {"quote": quote}
    if style == ArgsStyle.FEATURES_CLOSES_INDUSTRY:
        return {"closes": features.get("closes", []), "industry": industry}
    if style == ArgsStyle.CODE:
        return {"code": code}
    if style == ArgsStyle.FIN_QUOTE_FEATURES_INDUSTRY:
        return {"fin": fin, "quote": quote, "features": features, "industry": industry}
    return {}


def compute_all_factors(
    fin, quote, features, industry, code, weights=None
) -> dict:
    """自动调用所有已注册因子，返回 {name: score} dict。

    替代原 compute_factor_parts() 中的硬编码映射。

    Args:
        weights: 策略权重 dict（如 ``{"quality": 0.3, ...}``）。传入时权重为 0 的
                 因子跳过计算（如 event/analyst 含网络请求但无贡献），None 时全量计算。
    """
    result = {}
    degraded = []
    with _FACTORS_LOCK:
        factors_snapshot = list(_FACTORS.items())
    for name, desc in factors_snapshot:
        # P0-12: 权重为 0 的因子跳过计算（event/analyst 含网络请求但贡献为 0）
        if weights is not None and weights.get(name, 0) == 0:
            continue
        kwargs = _build_kwargs(desc, fin, quote, features, industry, code)
        try:
            result[name] = desc.compute_fn(**kwargs)
        except Exception as e:
            logger.warning("因子 %s 计算异常，使用默认分 50: %s", name, e)
            result[name] = 50
            degraded.append(name)
    if degraded:
        logger.warning("以下因子计算失败，已降级为中性分 50: %s", degraded)
    return result


def compute_phase_factors(
    phase, fin, quote, features, industry, code, exclude=None, weights=None
) -> dict:
    """自动调用指定阶段的因子，返回 {name: score} dict。

    替代原 compute_phase1_parts() / compute_phase2_parts() 中的硬编码映射。

    Args:
        exclude: 需跳过的因子名集合（如 Phase 2 跳过 chip 避免无意义的网络请求）。
        weights: 策略权重 dict。传入时权重为 0 的因子跳过计算，None 时全量计算。
    """
    result = {}
    degraded = []
    target = Phase(phase) if isinstance(phase, int) else phase
    skip = set(exclude) if exclude else set()
    with _FACTORS_LOCK:
        factors_snapshot = list(_FACTORS.items())
    for name, desc in factors_snapshot:
        if desc.phase != target:
            continue
        if name in skip:
            continue
        # P0-12: 权重为 0 的因子跳过计算
        if weights is not None and weights.get(name, 0) == 0:
            continue
        kwargs = _build_kwargs(desc, fin, quote, features, industry, code)
        try:
            result[name] = desc.compute_fn(**kwargs)
        except Exception as e:
            logger.warning(
                "因子 %s 计算异常(phase=%d)，使用默认分 50: %s", name, phase, e
            )
            result[name] = 50
            degraded.append(name)
    if degraded:
        logger.warning("Phase%d 以下因子计算失败，已降级: %s", phase, degraded)
    return result


def compute_factor_correlation_matrix(
    factor_scores: dict,
) -> dict:
    """P2-05: 计算因子得分相关矩阵（诊断工具，不改变打分）。

    Args:
        factor_scores: {factor_name: [score1, score2, ...]} 每只股票一个分数

    Returns:
        {factor_name: {other_factor: corr_coef, ...}, ...}
        对角线为 1.0；缺失数据对的相关系数为 None。
    """
    names = list(factor_scores.keys())
    n = len(names)
    matrix = {a: {b: None for b in names} for a in names}
    for a in names:
        matrix[a][a] = 1.0

    for i in range(n):
        for j in range(i + 1, n):
            a, b = names[i], names[j]
            va, vb = factor_scores.get(a) or [], factor_scores.get(b) or []
            if not va or not vb or len(va) != len(vb) or len(va) < 2:
                continue
            ma = sum(va) / len(va)
            mb = sum(vb) / len(vb)
            num = sum((va[k] - ma) * (vb[k] - mb) for k in range(len(va)))
            den_a = sum((va[k] - ma) ** 2 for k in range(len(va))) ** 0.5
            den_b = sum((vb[k] - mb) ** 2 for k in range(len(vb))) ** 0.5
            if den_a > 0 and den_b > 0:
                corr = round(num / (den_a * den_b), 3)
                matrix[a][b] = corr
                matrix[b][a] = corr
    return matrix


def compute_vif(factor_scores: dict) -> dict:
    """P2-05: 计算方差膨胀因子（VIF）。

    VIF_j = 1 / (1 - R²_j)，其中 R²_j 是因子 j 对其他因子的线性回归决定系数。
    VIF > 10 表示严重共线性，VIF > 5 表示中等共线性。

    Args:
        factor_scores: {factor_name: [score1, score2, ...]}

    Returns:
        {factor_name: vif_value}（VIF 越高共线性越严重）
        数据不足时返回 None。
    """
    names = list(factor_scores.keys())
    n_factors = len(names)
    result = {}

    for j, target in enumerate(names):
        y = factor_scores.get(target) or []
        if len(y) < 3:
            result[target] = None
            continue

        # 构建其他因子作为自变量
        others = [names[i] for i in range(n_factors) if i != j]
        X_cols = []
        for o in others:
            col = factor_scores.get(o) or []
            if len(col) == len(y):
                X_cols.append(col)

        if not X_cols:
            result[target] = 1.0  # 无其他因子，无共线性
            continue

        # 简单 OLS: y = a + b1*x1 + ... + bk*xk
        # 用正规方程 (X'X)^-1 X'y
        n = len(y)
        # 设计矩阵：第一列全1（截距），后续为因子列
        X = [[1.0] + [col[i] for col in X_cols] for i in range(n)]
        k = len(X_cols) + 1  # 含截距

        # X'X
        XtX = [[0.0] * k for _ in range(k)]
        for row in X:
            for a in range(k):
                for b in range(k):
                    XtX[a][b] += row[a] * row[b]

        # X'y
        Xty = [0.0] * k
        for i, row in enumerate(X):
            for a in range(k):
                Xty[a] += row[a] * y[i]

        # 解 XtX * beta = Xty（高斯消元）
        beta = _solve_linear(XtX, Xty, k)
        if beta is None:
            # XtX 奇异 = 回归因子完全共线 -> VIF = inf（最大共线性）
            result[target] = float("inf")
            continue

        # 计算 R²
        y_mean = sum(y) / n
        ss_res = sum((y[i] - sum(beta[a] * X[i][a] for a in range(k))) ** 2 for i in range(n))
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        if ss_tot == 0:
            result[target] = None
            continue
        r_squared = max(0.0, 1.0 - ss_res / ss_tot)
        vif = 1.0 / (1.0 - r_squared) if r_squared < 0.9999 else float("inf")
        result[target] = round(vif, 3) if vif != float("inf") else float("inf")

    return result


def _solve_linear(A: list, b: list, n: int) -> list | None:
    """高斯消元法解线性方程组 Ax = b。返回 x 或 None（奇异矩阵）。"""
    # 增广矩阵
    M = [A[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        # 部分主元
        pivot = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot][col]) < 1e-12:
            return None  # 奇异
        M[col], M[pivot] = M[pivot], M[col]
        # 消元
        for r in range(n):
            if r == col:
                continue
            factor = M[r][col] / M[col][col]
            for c in range(col, n + 1):
                M[r][c] -= factor * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def decorrelate_factors(
    parts_list: list, threshold: float = 0.7
) -> list:
    """P2-05: 对批量因子得分做残差化去相关。

    对每对相关系数 > threshold 的因子 (A, B)，从 B 中减去 A 对 B 的线性回归残差，
    消除共线性。保留 9-key 接口，策略权重无需修改。

    残差化方向：低权重因子被高权重因子残差化（保留高权重因子的原始信息）。
    默认 threshold=0.7，仅处理高共线性对。

    Args:
        parts_list: [{factor: score, ...}, ...] 每只股票一个 dict
        threshold: 相关系数阈值，仅处理 > threshold 的因子对

    Returns:
        去相关后的 parts_list（同结构，同顺序）
    """
    if len(parts_list) < 3:
        return parts_list  # 样本不足，不处理

    # 收集每个因子的得分序列
    all_factors = set()
    for p in parts_list:
        all_factors.update(p.keys())
    # 只处理有数值的因子
    factor_names = sorted(
        f for f in all_factors
        if all(isinstance(p.get(f), (int, float)) for p in parts_list)
    )

    if len(factor_names) < 2:
        return parts_list

    factor_scores = {
        f: [p.get(f, 0) for p in parts_list] for f in factor_names
    }
    corr = compute_factor_correlation_matrix(factor_scores)

    # 找出高相关因子对
    decorrelated = {f: list(factor_scores[f]) for f in factor_names}
    processed = set()

    for i, a in enumerate(factor_names):
        for j in range(i + 1, len(factor_names)):
            b = factor_names[j]
            r = corr.get(a, {}).get(b)
            if r is None or abs(r) < threshold:
                continue
            # 残差化 b 对 a：b_new = b - beta * a（保留 a 的原始信息）
            if b in processed:
                continue  # 已被残差化，跳过
            va, vb = decorrelated[a], decorrelated[b]
            ma = sum(va) / len(va)
            mb = sum(vb) / len(vb)
            num = sum((va[k] - ma) * (vb[k] - mb) for k in range(len(va)))
            den = sum((va[k] - ma) ** 2 for k in range(len(va)))
            if den > 0:
                beta = num / den
                # 残差 = b - beta * a，加回 b 的均值保持尺度
                decorrelated[b] = [
                    vb[k] - beta * (va[k] - ma) for k in range(len(vb))
                ]
                processed.add(b)
                logger.debug(
                    "去相关: %s 被 %s 残差化 (r=%.3f, beta=%.3f)", b, a, r, beta
                )

    # 重建 parts_list
    result = []
    for idx, p in enumerate(parts_list):
        new_p = dict(p)
        for f in factor_names:
            if f in decorrelated and f in processed:
                new_p[f] = decorrelated[f][idx]
        result.append(new_p)
    return result

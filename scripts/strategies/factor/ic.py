"""因子 IC（Information Coefficient）计算与持久化。

手写 Spearman rank correlation（无 scipy 依赖）。
按 regime 分桶计算 IC，用于动态调整 overlay 权重。

数据流：
  backtest engine 存 per-factor parts + return_pct + regime
  -> compute_all_factor_ic 按 regime 分桶计算 IC
  -> save_ic 持久化到 data/factor_ic.json
  -> live path 的 compute_overlay_weights 读取 IC 动态调整 multiplier

IC 解读：
  IC > 0：因子有效（高因子分 -> 高收益）
  IC < 0：因子失效或反向（高因子分 -> 低收益）
  IC ≈ 0：因子无预测力

贝叶斯式融合：
  IC > 0 -> 保持基础 multiplier
  IC < 0 -> 线性衰减至 min_mult（0.5）
"""

import json
import logging
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

IC_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "factor_ic.json"


def _rank(values: List[float]) -> List[float]:
    """计算 rank（平均秩处理并列）。"""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _pearson(x: List[float], y: List[float]) -> float:
    """手写 Pearson 相关系数。"""
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = statistics.mean(x), statistics.mean(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = sum((xi - mx) ** 2 for xi in x) ** 0.5
    sy = sum((yi - my) ** 2 for yi in y) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def compute_factor_ic(selections: List[dict], factor: str) -> float:
    """计算单因子 IC（Spearman rank correlation）。

    Args:
        selections: backtest 输出，每条含 parts[factor] 和 return_pct
        factor: 因子名（如 "momentum"）

    Returns:
        IC 值 [-1, 1]，正值表示因子有效
    """
    pairs = []
    for s in selections:
        score = s.get("parts", {}).get(factor)
        ret = s.get("return_pct")
        if score is not None and ret is not None:
            pairs.append((float(score), float(ret)))
    if len(pairs) < 5:
        return 0.0
    scores = [p[0] for p in pairs]
    returns = [p[1] for p in pairs]
    return _pearson(_rank(scores), _rank(returns))


def compute_all_factor_ic(selections: List[dict]) -> Dict[str, float]:
    """计算所有因子的 IC。

    Args:
        selections: backtest 输出列表

    Returns:
        {factor_name: ic_value} dict
    """
    factors = set()
    for s in selections:
        factors.update(s.get("parts", {}).keys())
    return {f: compute_factor_ic(selections, f) for f in factors}


def compute_ic_by_regime(selections: List[dict]) -> Dict[str, Dict[str, float]]:
    """按 regime 分桶计算 IC。

    Args:
        selections: backtest 输出，每条含 regime 字段

    Returns:
        {regime_value: {factor: ic}} dict
    """
    ic_by_regime = {}
    regimes = set(s.get("regime") for s in selections if s.get("regime"))
    for regime_val in regimes:
        regime_selections = [s for s in selections if s.get("regime") == regime_val]
        ic_by_regime[regime_val] = compute_all_factor_ic(regime_selections)
    return ic_by_regime


def ic_to_multiplier(ic: float, base_mult: float, min_mult: float = 0.5) -> float:
    """IC 转换为 overlay multiplier（贝叶斯式融合）。

    IC > 0 -> 保持基础 multiplier
    IC < 0 -> 线性衰减至 min_mult

    Args:
        ic: 因子 IC 值 [-1, 1]
        base_mult: 基础 multiplier（来自 OVERLAY_MATRIX）
        min_mult: 衰减下限（默认 0.5）

    Returns:
        调整后的 multiplier
    """
    if ic >= 0:
        return base_mult
    # IC < 0: 线性衰减到 min_mult
    decay = max(0, 1 + ic)  # ic=-1 -> decay=0, ic=0 -> decay=1
    return max(min_mult, base_mult * decay)


def save_ic(ic_by_regime: Dict[str, Dict[str, float]]):
    """保存 IC 到 data/factor_ic.json（live path 读取）。

    Args:
        ic_by_regime: {regime: {factor: ic}} dict
    """
    try:
        data = {
            "updated": datetime.now().isoformat(),
            "ic": ic_by_regime,
        }
        IC_FILE.parent.mkdir(parents=True, exist_ok=True)
        IC_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("因子 IC 已保存到 %s", IC_FILE)
    except Exception as e:
        logger.warning("因子 IC 保存失败: %s", e)


def load_ic() -> Dict[str, Dict[str, float]]:
    """读取最近 IC。

    Returns:
        {regime: {factor: ic}} dict，文件不存在或损坏返回空 dict
    """
    try:
        if not IC_FILE.exists():
            return {}
        data = json.loads(IC_FILE.read_text(encoding="utf-8"))
        return data.get("ic", {})
    except Exception as e:
        logger.debug("因子 IC 读取失败: %s", e)
        return {}

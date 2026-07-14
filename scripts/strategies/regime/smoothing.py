"""Regime 权重平滑：EMA 混合，避免隔夜跳变。

v2.8 新增。今日实际权重 = alpha × 新 regime 矩阵 + (1-alpha) × 昨日实际权重。
使因子暴露平滑过渡，降低换手率冲击。

v2.9 新增：跨日持久化。实盘路径 persist=True 时，启动加载上次权重，
每次平滑后保存到 data/regime_state.json（7 天 TTL）。

回测路径：在循环中复用 smoother，实现连续平滑（不持久化）。
"""

from typing import Dict, Optional

from config.loader import safe_get


class RegimeSmoother:
    """EMA 权重混合器，缓存上一次的 effective_weights。"""

    def __init__(self, alpha: Optional[float] = None, persist: bool = False):
        """初始化平滑器。

        Args:
            alpha: EMA 混合系数（新权重占比）。None 时从 regime.yaml 读取，默认 0.3。
            persist: v2.9 新增，是否跨日持久化到 data/regime_state.json。
                     实盘路径用 True，回测路径用 False（默认）。
        """
        if alpha is not None:
            self.alpha = alpha
        else:
            self.alpha = safe_get("regime.yaml", "smoothing.alpha", 0.3)
        self._persist = persist
        self._prev_weights: Optional[Dict[str, float]] = None

        # v2.9: 持久化模式下启动时加载上次权重
        if persist:
            from .persistence import load_state

            self._prev_weights = load_state()

    def smooth(
        self,
        regime,
        original_weights: Dict[str, float],
        extreme_drop: bool = False,
        national_team: bool = False,
        ic_multipliers: Dict[str, float] = None,
    ) -> Dict[str, float]:
        """返回平滑后的权重。

        Args:
            regime: RegimeState 枚举值
            original_weights: 策略原权重 dict
            extreme_drop: 是否触发极端跌幅降动量
            national_team: v2.9 是否触发国家队放量信号
            ic_multipliers: v3.0 因子 IC dict，IC<0 时衰减 multiplier

        Returns:
            平滑并归一化后的权重 dict（和 = 1.0）
        """
        from .overlay import compute_overlay_weights

        new_weights = compute_overlay_weights(
            original_weights, regime, extreme_drop, national_team, ic_multipliers
        )

        if self._prev_weights is None:
            # 首次调用：不混合，直接用新权重
            self._prev_weights = new_weights
        else:
            # EMA 混合：alpha × 新 + (1-alpha) × 旧
            blended = {}
            all_keys = set(new_weights) | set(self._prev_weights)
            for k in all_keys:
                new_v = new_weights.get(k, 0)
                prev_v = self._prev_weights.get(k, 0)
                blended[k] = self.alpha * new_v + (1 - self.alpha) * prev_v

            # 重新归一化
            total = sum(blended.values())
            if total > 0:
                blended = {k: round(v / total, 4) for k, v in blended.items()}

            self._prev_weights = blended
            new_weights = blended

        # v2.9: 持久化模式下保存状态
        if self._persist:
            from .persistence import save_state

            save_state(self._prev_weights)

        return new_weights

    def reset(self):
        """重置缓存（新回测开始时调用）。"""
        self._prev_weights = None

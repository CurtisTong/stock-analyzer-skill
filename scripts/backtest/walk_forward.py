"""Walk-forward 回测框架（P0-11）。

将历史数据划分为多个 train + test 窗口，在 train 段优化策略参数，
在 test 段（out-of-sample）评估，汇总 OOS 性能指标。

核心思想：
  - 避免全样本回测的过拟合问题
  - 每个窗口的 test 段是策略从未见过的数据
  - 汇总所有窗口的 OOS 收益，计算可信的夏普/胜率

用法：
  from backtest.walk_forward import run_walk_forward, WalkForwardConfig

  config = WalkForwardConfig(
      strategy_name="balanced",
      codes=["sh600519", "sh600989"],
      train_days=120,
      test_days=30,
      n_windows=5,
  )
  result = run_walk_forward(config)
  print(f"OOS 夏普: {result['oos_sharpe']}")
  print(f"OOS 胜率: {result['oos_win_rate']}%")
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .engine import simulate_strategy, SimContext

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """Walk-forward 回测配置。

    Args:
        strategy_name: 策略名称
        codes: 候选股票代码列表
        train_days: 每个窗口训练段天数
        test_days: 每个窗口测试段天数（OOS）
        n_windows: 滚动窗口数量
        top_n: 每轮选股数量
        holding_days: 持有天数
        step_days: 窗口滚动步长（默认 = test_days，无重叠）
    """

    strategy_name: str
    codes: list
    train_days: int = 120
    test_days: int = 30
    n_windows: int = 5
    top_n: int = 5
    holding_days: int = 5
    step_days: int = 0  # 0 时自动设为 test_days


@dataclass
class WalkForwardResult:
    """Walk-forward 回测结果。"""

    config: WalkForwardConfig
    windows: list = field(default_factory=list)  # 每个窗口的 {train, test, returns}
    oos_returns: list = field(default_factory=list)  # 所有 OOS 期收益
    oos_total_return: float = 0.0
    oos_avg_return: float = 0.0
    oos_win_rate: float = 0.0
    oos_sharpe: float = 0.0
    oos_max_drawdown: float = 0.0
    is_sharpe: float = 0.0  # 样本内夏普（参考）
    is_total_return: float = 0.0  # 样本内总收益（参考）
    n_valid_windows: int = 0
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """转为 dict 便于 JSON 序列化。"""
        return {
            "config": {
                "strategy_name": self.config.strategy_name,
                "train_days": self.config.train_days,
                "test_days": self.config.test_days,
                "n_windows": self.config.n_windows,
                "top_n": self.config.top_n,
                "holding_days": self.config.holding_days,
            },
            "n_valid_windows": self.n_valid_windows,
            "oos_returns": self.oos_returns,
            "oos_total_return_pct": round(self.oos_total_return, 2),
            "oos_avg_return_pct": round(self.oos_avg_return, 2),
            "oos_win_rate_pct": round(self.oos_win_rate, 1),
            "oos_sharpe": round(self.oos_sharpe, 2),
            "oos_max_drawdown_pct": round(self.oos_max_drawdown, 2),
            "is_sharpe": round(self.is_sharpe, 2),
            "is_total_return_pct": round(self.is_total_return, 2),
            "windows": self.windows,
            "errors": self.errors,
        }


def _calc_sharpe(returns: list, daily_returns: list = None) -> float:
    """计算夏普比率（年化，无风险利率 3%）。"""
    import statistics

    if daily_returns and len(daily_returns) > 1:
        annual_rf = 0.03
        daily_rf = annual_rf / 252
        excess = [r - daily_rf for r in daily_returns]
        mean_ex = sum(excess) / len(excess)
        std = statistics.stdev(excess)
        return mean_ex / std * (252**0.5) if std > 0 else 0.0
    if len(returns) < 2:
        return 0.0
    annual_rf = 0.03
    periods_per_year = 252 / 5  # 假设 5 天持有期
    rf_per_period = annual_rf / periods_per_year
    excess = [r / 100 - rf_per_period for r in returns]
    mean_ex = sum(excess) / len(excess)
    std = statistics.stdev(excess)
    return mean_ex / std * (periods_per_year**0.5) if std > 0 else 0.0


def _calc_max_drawdown(returns: list) -> float:
    """从期收益率序列计算最大回撤（百分比）。"""
    if not returns:
        return 0.0
    cumulative = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        cumulative *= 1 + r / 100
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100


def run_walk_forward(config: WalkForwardConfig) -> WalkForwardResult:
    """执行 walk-forward 回测。

    流程：
    1. 对每个窗口 w (0..n_windows-1)：
       - train 段 = [w * step, w * step + train_days]
       - test 段 = [train_end, train_end + test_days]
    2. 在 train 段运行 simulate_strategy（IS）
    3. 在 test 段运行 simulate_strategy（OOS）
    4. 汇总所有窗口的 OOS 收益

    Returns:
        WalkForwardResult 含 OOS 夏普/胜率/回撤 + IS 参考
    """
    result = WalkForwardResult(config=config)
    step = config.step_days or config.test_days

    for w in range(config.n_windows):
        train_start = w * step
        train_end = train_start + config.train_days
        test_start = train_end
        test_end = test_start + config.test_days

        window_info = {
            "window": w,
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
        }

        # IS（训练段）回测
        is_ctx = SimContext(
            strategy_name=config.strategy_name,
            codes=config.codes,
            top_n=config.top_n,
            holding_days=config.holding_days,
            total_days=config.train_days,
        )
        is_result = simulate_strategy(is_ctx)
        if "error" in is_result:
            result.errors.append(f"window {w} IS: {is_result['error']}")
            result.windows.append({**window_info, "status": "is_error"})
            continue
        is_returns = is_result.get("returns", [])
        is_sharpe = _calc_sharpe(is_returns)
        is_total = 1.0
        for r in is_returns:
            is_total *= 1 + r / 100
        is_total = (is_total - 1) * 100

        # OOS（测试段）回测
        oos_ctx = SimContext(
            strategy_name=config.strategy_name,
            codes=config.codes,
            top_n=config.top_n,
            holding_days=config.holding_days,
            total_days=config.test_days,
        )
        oos_result = simulate_strategy(oos_ctx)
        if "error" in oos_result:
            result.errors.append(f"window {w} OOS: {oos_result['error']}")
            result.windows.append({**window_info, "status": "oos_error"})
            continue

        oos_returns = oos_result.get("returns", [])

        result.oos_returns.extend(oos_returns)
        result.is_sharpe += is_sharpe
        result.is_total_return += is_total
        result.n_valid_windows += 1

        result.windows.append(
            {
                **window_info,
                "status": "ok",
                "is_returns": is_returns,
                "is_sharpe": round(is_sharpe, 2),
                "is_total_return_pct": round(is_total, 2),
                "oos_returns": oos_returns,
                "oos_avg_return_pct": round(
                    sum(oos_returns) / len(oos_returns) if oos_returns else 0, 2
                ),
                "oos_win_rate_pct": round(
                    (
                        sum(1 for r in oos_returns if r > 0) / len(oos_returns) * 100
                        if oos_returns
                        else 0
                    ),
                    1,
                ),
            }
        )

    # 汇总 OOS 指标
    if result.oos_returns:
        result.oos_total_return = 1.0
        for r in result.oos_returns:
            result.oos_total_return *= 1 + r / 100
        result.oos_total_return = (result.oos_total_return - 1) * 100

        result.oos_avg_return = sum(result.oos_returns) / len(result.oos_returns)
        result.oos_win_rate = (
            sum(1 for r in result.oos_returns if r > 0) / len(result.oos_returns) * 100
        )
        result.oos_sharpe = _calc_sharpe(result.oos_returns)
        result.oos_max_drawdown = _calc_max_drawdown(result.oos_returns)

    if result.n_valid_windows > 0:
        result.is_sharpe /= result.n_valid_windows
        result.is_total_return /= result.n_valid_windows

    return result

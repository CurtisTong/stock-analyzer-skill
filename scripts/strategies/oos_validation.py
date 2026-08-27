"""策略外样本验证覆盖层。

设计：STRATEGY_VALIDATION 是 registry 默认值（commit-friendly，纯 in_sample
标注）。真跑过 multi_stock_backtest 的结果落到 data/strategy_oos_validation.json
作为运行时覆盖。这样：

1. registry 默认值保持纯净，不会因某次回测而污染 git history
2. 删除 JSON 文件即可让策略"回到"in_sample 默认状态
3. multi_stock_backtest.py 是唯一写 JSON 的入口（避免散落多处写）

OOS 升级条件（multi_stock_backtest.py 与本模块共同约束）：
- 股票池 ≥ 30 只
- win_rate_pct ≥ 50
- total_return_pct > 0
- 输出包含 'oos_verified' 状态 + ISO 时间戳 + 胜率 + 股票池大小

双池验证（v1.21.1）：
- 单池 OOS 结论受池构成影响极大（55 大票池 OOS 正 vs 210 sector 池 OOS 负，
  见 docs/archive/reviews/backtest-philosophy-review-2026-08-26.md §2.4）
- evaluate_multi_pool() 要求全部池都达标才升级 oos_verified，任一池不达标
  保持 in_sample——防止"选一个对自己有利的池"刷验证
"""

import json
from pathlib import Path
from typing import Optional

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
OOS_FILE = PKG_ROOT / "data" / "strategy_oos_validation.json"


def load_oos_overrides() -> dict[str, dict]:
    """读 OOS 覆盖 JSON 文件；不存在或解析失败时返回空 dict。

    Returns:
        {strategy_name: {"validation_status": "oos_verified"|"in_sample",
                        "validation_note": str, "validated_at": str (ISO),
                        "win_rate_pct": float, "n_stocks": int}}
    """
    if not OOS_FILE.exists():
        return {}
    try:
        with open(OOS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_oos_result(
    strategy_name: str,
    *,
    validation_status: str,
    validation_note: str,
    win_rate_pct: float,
    n_stocks: int,
    total_return_pct: float,
    pool_type: str = "default",
    extra: Optional[dict] = None,
) -> None:
    """单条 OOS 验证结果写到 JSON 文件。原子写入避免半截文件污染。

    同一策略多次写入（不同 pool_type）时，结果按池累积到 `pools` 嵌套
    结构，供 evaluate_multi_pool 双池联合判定使用：

        {strategy: {
            "validation_status": ..., "validation_note": ...,
            "validated_at": ...,
            "pools": {pool_type: {"win_rate_pct", "n_stocks", "total_return_pct", ...}},
            ...顶层字段为最近一次写入的值...
        }}

    Args:
        strategy_name: 策略名（registry 已注册）
        validation_status: "oos_verified" | "in_sample"
        validation_note: 提示文本（含胜率/股票池大小/日期）
        win_rate_pct: 外样本胜率
        n_stocks: 股票池大小
        total_return_pct: 累计收益
        pool_type: 池类型标识（default=大池 sector 池 / large=跨板块大票池），
            双池验证时用于区分各池结果
        extra: 可选额外字段（sharpe / max_drawdown 等）
    """
    from datetime import datetime

    OOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    overrides = load_oos_overrides()

    existing = overrides.get(strategy_name, {})
    pools = existing.get("pools", {}) if isinstance(existing, dict) else {}
    pools[pool_type] = {
        "win_rate_pct": round(win_rate_pct, 2),
        "n_stocks": n_stocks,
        "total_return_pct": round(total_return_pct, 2),
        **(extra or {}),
    }

    overrides[strategy_name] = {
        "validation_status": validation_status,
        "validation_note": validation_note,
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "win_rate_pct": round(win_rate_pct, 2),
        "n_stocks": n_stocks,
        "total_return_pct": round(total_return_pct, 2),
        "pool_type": pool_type,
        "pools": pools,
        **(extra or {}),
    }

    tmp = OOS_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(OOS_FILE)


# OOS 升级阈值（与 multi_stock_backtest.py 同步）
OOS_MIN_STOCKS = 30
OOS_MIN_WIN_RATE = 50.0  # 胜率 ≥ 50% 才算可用


def evaluate_oos(win_rate_pct: float, n_stocks: int, total_return_pct: float) -> str:
    """根据外样本回测结果判定状态。

    Returns:
        "oos_verified" if n_stocks >= OOS_MIN_STOCKS and
                       win_rate_pct >= OOS_MIN_WIN_RATE and
                       total_return_pct > 0
        "in_sample" otherwise（含样本数不够 / 胜率不足 / 负收益）
    """
    if (
        n_stocks >= OOS_MIN_STOCKS
        and win_rate_pct >= OOS_MIN_WIN_RATE
        and total_return_pct > 0
    ):
        return "oos_verified"
    return "in_sample"


def evaluate_multi_pool(
    pool_results: dict[str, tuple[float, int, float]],
) -> tuple[str, str]:
    """多池联合判定：全部池达标才升级 oos_verified。

    实测发现单池 OOS 受池构成影响极大（55 大票池 OOS 正 vs
    210 sector 池 OOS 负），单池达标不足以支撑 CLAIM。本函数要求
    **每个池**都满足 evaluate_oos 阈值，任一池不达标即整体 in_sample。

    Args:
        pool_results: {pool_type: (win_rate_pct, n_stocks, total_return_pct)}

    Returns:
        (status, note)。note 标注各池结果，若未全部达标会点名未达标池。
    """
    if not pool_results:
        return "in_sample", "无任何池的 OOS 验证结果"

    statuses = {}
    for pool_type, (win_rate, n_stocks, total_return) in pool_results.items():
        statuses[pool_type] = evaluate_oos(win_rate, n_stocks, total_return)

    all_verified = all(s == "oos_verified" for s in statuses.values())
    if all_verified:
        parts = " / ".join(
            f"{pt} 胜率{wr:.1f}% 收益{tr:+.2f}%"
            for pt, (wr, _, tr) in pool_results.items()
        )
        return "oos_verified", f"✓ 双池 OOS 验证通过：{parts}"

    failed = [pt for pt, s in statuses.items() if s != "oos_verified"]
    return (
        "in_sample",
        f"双池 OOS 验证未全部达标（未达标池：{', '.join(failed)}），保持 in_sample",
    )


def build_oos_note(win_rate_pct: float, n_stocks: int, total_return_pct: float) -> str:
    """生成 OOS 验证 note（含数字 + 阈值提示）。"""
    return (
        f"✓ OOS 验证（{n_stocks} 只股票池）："
        f"胜率 {win_rate_pct:.1f}% / 累计收益 {total_return_pct:+.2f}%"
    )

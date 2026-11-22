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
    universe_fingerprint: str = "",
    extra: Optional[dict] = None,
) -> None:
    """单条 OOS 验证结果写到 JSON 文件。原子写入避免半截文件污染。

    同一策略多次写入（不同 pool_type）时，结果按池累积到 `pools` 嵌套
    结构，供 evaluate_multi_pool 双池联合判定使用：

        {strategy: {
            "validation_status": ..., "validation_note": ...,
            "validated_at": ...,
            "pools": {pool_type: {"win_rate_pct", "n_stocks", "total_return_pct",
                                  "universe_fingerprint", ...}},
            ...顶层字段为最近一次写入的值...
        }}

    universe_fingerprint（v1.31 审查修复）：同一 pool_type 在不同时期
    可能对应不同股票池（sector 池随 refresh_pool 更新、DEFAULT_CODES
    可调整），仅靠 pool_type 字符串无法区分——旧口径结果与新口径结果
    会被静默合并进同一次"双池联合判定"，闸门独立性不成立（旧 JSON 的
    default 池实为 55 只时代、与 large 相同代码的"假双池"）。指纹 = 该池
    代码列表排序后 SHA1 前 8 位，联合判定时用于审计"两池是否同一宇宙"。

    Args:
        strategy_name: 策略名（registry 已注册）
        validation_status: "oos_verified" | "in_sample"
        validation_note: 提示文本（含胜率/股票池大小/日期）
        win_rate_pct: 外样本胜率
        n_stocks: 股票池大小
        total_return_pct: 累计收益
        pool_type: 池类型标识（default=大池 sector 池 / large=跨板块大票池），
            双池验证时用于区分各池结果
        universe_fingerprint: 本次股票池代码列表指纹（sorted SHA1[:8]）
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
        "universe_fingerprint": universe_fingerprint,
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
    if n_stocks >= OOS_MIN_STOCKS and win_rate_pct >= OOS_MIN_WIN_RATE and total_return_pct > 0:
        return "oos_verified"
    return "in_sample"


def _as_code_set(fingerprint: str) -> set[str]:
    """若指纹是代码列表（逗号/竖线/空格分隔），解析为规范化代码集合。

    SHA1 短哈希不含分隔符且 token 不是股票代码 → 返回空集合，走近似哈希判定。
    """
    import re

    tokens = {
        t.strip().lower()
        for t in fingerprint.replace("|", ",").replace(" ", ",").split(",")
        if t.strip()
    }
    if len(tokens) >= 2 and all(re.fullmatch(r"(?:sh|sz|bj)\d{6}", t) for t in tokens):
        return tokens
    return set()


def _fingerprints_overlap(fp_a: str, fp_b: str) -> bool:
    """判定两个池宇宙指纹是否"相同或高度重合"（P1-16 修复）。

    - 完全相同 → 同一宇宙（典型刷分：同一批代码换个 pool_type 跑两次）
    - 代码列表指纹 → Jaccard 重合度 ≥ 0.8 视为高度重合
    - SHA1 短哈希 → 保守近似：8 位十六进制中有 ≥7 位相同（序列相似度 ≥0.875）
      才算高度重合，避免不同哈希因偶然相似被误判
    """
    if fp_a == fp_b:
        return True
    codes_a, codes_b = _as_code_set(fp_a), _as_code_set(fp_b)
    if codes_a and codes_b:
        union = codes_a | codes_b
        return bool(union) and len(codes_a & codes_b) / len(union) >= 0.8
    if len(fp_a) == len(fp_b) >= 6:
        from difflib import SequenceMatcher

        return SequenceMatcher(None, fp_a.lower(), fp_b.lower()).ratio() >= 0.875
    return False


def _fingerprint_collision(pool_fingerprints: dict[str, str]) -> str | None:
    """返回第一个指纹冲突的原因；无冲突返回 None。空指纹忽略（兼容旧记录）。"""
    valid = []
    for pool_type, fp in (pool_fingerprints or {}).items():
        if isinstance(fp, str) and fp.strip():
            valid.append((pool_type, fp.strip()))
    for i, (pt_a, fp_a) in enumerate(valid):
        for pt_b, fp_b in valid[i + 1 :]:
            if fp_a == fp_b:
                return f"{pt_a} 与 {pt_b} 的宇宙指纹相同（{fp_a}）"
            if _fingerprints_overlap(fp_a, fp_b):
                return f"{pt_a} 与 {pt_b} 的宇宙指纹高度重合（{fp_a} / {fp_b}）"
    return None


def evaluate_multi_pool(
    pool_results: dict[str, tuple[float, int, float]],
    pool_fingerprints: dict[str, str] | None = None,
) -> tuple[str, str]:
    """多池联合判定：至少记录 2 个池，且每个池都达标才升级 oos_verified。

    v1.21.1 复盘发现单池 OOS 受池构成影响极大（55 只跨板块大票池 OOS 正 vs
    210 只 sector 池 OOS 负），选一个"对自己有利的池"即可刷出验证，单池
    验证无统计意义。因此：

    - 未记录任何池 → in_sample
    - 仅记录 1 个池 → in_sample（禁止单池升级，v1.23.1 收紧）
    - ≥2 个池但池宇宙指纹相同或高度重合 → in_sample（P1-16 修复：
      同一批代码换个 pool_type 重跑不构成独立验证）
    - ≥2 个池但任一池未达标 → in_sample（note 点名未达标池）
    - ≥2 个池且全部达标 → oos_verified

    Args:
        pool_results: {pool_type: (win_rate_pct, n_stocks, total_return_pct)}
        pool_fingerprints: 可选，{pool_type: 宇宙指纹}。仅用于校验各池是否
            真正独立；不传时保持旧行为（只校验池数与各池指标），兼容旧调用。

    Returns:
        (status, note)。note 标注各池结果，未达标时点名未达标池或指纹冲突。
    """
    if not pool_results:
        return "in_sample", "无任何池的 OOS 验证结果"

    if len(pool_results) < 2:
        names = ", ".join(pool_results)
        return (
            "in_sample",
            f"仅记录 {len(pool_results)} 个池（{names}），单池验证无统计意义，" "需跑第二个池且全部池达标才升级",
        )

    # P1-16：池数达标不代表宇宙独立。此前指纹只被打印，从未参与判定，
    # 同一批代码以 default/large 各跑一次即可"双池通过"。
    if pool_fingerprints:
        collision = _fingerprint_collision(pool_fingerprints)
        if collision:
            return (
                "in_sample",
                f"⚠️ 多池宇宙指纹校验未通过：{collision}；"
                "疑似同一批股票换 pool_type 重跑，双池不独立，强制保持 in_sample",
            )

    statuses = {}
    for pool_type, (win_rate, n_stocks, total_return) in pool_results.items():
        statuses[pool_type] = evaluate_oos(win_rate, n_stocks, total_return)

    all_verified = all(s == "oos_verified" for s in statuses.values())
    if all_verified:
        parts = " / ".join(f"{pt} 胜率{wr:.1f}% 收益{tr:+.2f}%" for pt, (wr, _, tr) in pool_results.items())
        return "oos_verified", f"✓ 双池 OOS 验证通过：{parts}"

    failed = [pt for pt, s in statuses.items() if s != "oos_verified"]
    return (
        "in_sample",
        f"双池 OOS 验证未全部达标（未达标池：{', '.join(failed)}），保持 in_sample",
    )


def build_oos_note(win_rate_pct: float, n_stocks: int, total_return_pct: float) -> str:
    """生成 OOS 验证 note（含数字 + 阈值提示）。"""
    return f"✓ OOS 验证（{n_stocks} 只股票池）：" f"胜率 {win_rate_pct:.1f}% / 累计收益 {total_return_pct:+.2f}%"

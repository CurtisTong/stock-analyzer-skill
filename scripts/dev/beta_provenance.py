"""β 输出口径闸门（errata #19，零外部依赖，可机械执行）。

背景：2026-11-22 策略在同一批 400 根日 K 上把「全部 400−w 个滚动窗口的平均」
标成「最近 w 日 β」，四个窗口 16 个数被 Chief 独立复算才发现（60 日 1.473 vs
真值 1.625）。研判反查确认规律是 `n_ret = 400 − window`——切片方向反了：
代码用 `range(w, len(days))` 取了前 400−w 根，而不是 `[-w:]` 取末 w 根。

本模块把「β 输出必须带 benchmark + codes + window + n，且窗口标签与实际取样一致」
做成校验函数。**混用即报错，不靠人肉对账。**

反证与边界：
- 本模块只校验「元数据自洽」，不联网、不重算 β；真值由调用方注入。
- 窗口一致性有两种口径，必须显式声明 `n_kind`：`returns`（日收益数，末 w+1 根
  K 线产生 w 个收益）或 `closes`（收盘价根数，等于 w+1）。不声明 → 不可用。
- 缺失字段一律 None（不填 0）；任一字段缺失 → ok=False，不出 β 结论。
- 「n == window 但 start_idx != n_bars-window-1」也要拦截：可能在中间窗口取样却
  恰好长度相同，这种错数值会静默通过，只查 n 查不出来。
"""
from __future__ import annotations

REQUIRED_FIELDS = ("benchmark", "codes", "window", "n")


def check_beta_provenance(record: dict) -> dict:
    """校验一条 β 输出的口径元数据。

    Args:
        record: dict，至少含四字段 benchmark / codes / window / n，另可含：
          n_kind     : 'returns' 或 'closes'（默认 None → 不可用）
          n_bars     : 本次取数的 K 线总根数（用于反查切片方向）
          start_idx  : 实际取样起始下标（0-based，含）
          end_idx    : 实际取样结束下标（0-based，含）

    Returns:
        dict: ok / errors / detail / reason；ok=False 时不得使用其中的 β。
    """
    errors: list[str] = []
    detail: dict = {}

    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or value == "" or value == []:
            errors.append(f"缺字段 {field}（不得填 0 或空串占位）")
        else:
            detail[field] = value

    window = record.get("window")
    n = record.get("n")
    n_kind = record.get("n_kind")
    n_bars = record.get("n_bars")

    if n_kind not in ("returns", "closes"):
        errors.append("n_kind 必须是 'returns' 或 'closes'，不声明无法校验窗口")
    else:
        detail["n_kind"] = n_kind
        # 标签与样本数一致：日收益数应等于 window；收盘价根数应等于 window+1
        expected_n = window if n_kind == "returns" else (window + 1 if isinstance(window, int) else None)
        if isinstance(window, int) and isinstance(n, int):
            detail["expected_n"] = expected_n
            if n != expected_n:
                errors.append(
                    f"窗口标签与样本数不符：window={window} {n_kind} 应有 n={expected_n}，实际 n={n}"
                )
                # errata #19 的特征签名：n = 总根数 − window → 切片方向反了
                if isinstance(n_bars, int) and n == n_bars - window:
                    errors.append(
                        f"命中 errata #19 切片反向签名：n={n}={n_bars}−{window}，"
                        "取的是前 400−w 根而非末 w 根"
                    )

    # 有起止下标时验证取样位置，拦截「长度对但取在中间」
    start_idx, end_idx = record.get("start_idx"), record.get("end_idx")
    if isinstance(start_idx, int) and isinstance(end_idx, int) and isinstance(window, int):
        detail["start_idx"] = start_idx
        detail["end_idx"] = end_idx
        actual_len = end_idx - start_idx + 1
        expected_len = window if n_kind == "returns" else window + 1
        if actual_len != expected_len:
            errors.append(f"取样区间长度 {actual_len} ≠ {expected_len}（{n_kind}）")
        if isinstance(n_bars, int) and start_idx != n_bars - expected_len:
            errors.append(
                f"取样起点 {start_idx} 不是末窗口起点 {n_bars - expected_len}；"
                "窗口标签与切片位置不一致"
            )

    ok = not errors
    return {
        "ok": ok,
        "beta_usable": ok,
        "errors": errors,
        "detail": detail,
        "reason": None if ok else "；".join(errors),
    }


def require_beta_provenance(record: dict) -> dict:
    """校验失败直接抛 ValueError，供回测/选股脚本在出口处硬拦截。"""
    result = check_beta_provenance(record)
    if not result["ok"]:
        raise ValueError(result["reason"])
    return result

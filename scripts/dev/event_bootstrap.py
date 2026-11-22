"""事件研究统计工具：有效样本数 + 多重检验校正 + 口径元数据（零外部依赖）。

本文件是这套能力的**仓库权威实现**（Chief 2026-11-22 定案）。
原型 `stock-team/monitor/overlap_audit.py` 保留不搬不删，头部已注明其为原型；
两文件关系按 errata #18「同一主题多份文件互相标注权威/原型」处理。
本文件若有改动，以本文件为准，原型不随之更新。

当前只落三样（Chief 2026-11-22 指定范围）：
1. effective_n()      —— 时间维重叠的有效样本数（n_raw / n_eff / n_overlap）
2. multipletests()    —— Holm-Bonferroni 多重检验校正（method="holm"）
3. with_metadata()    —— 结果附带 benchmark/codes/window/n 四字段口径元数据

**块自助（StationaryBootstrap）暂不落**：策略 2026-11-22 那版跑出零宽度区间，
属明显 bug；待其修好并给出验证后，单独 commit 追加，不带病上线。

口径与反证：
- 事件定义（冷却期 + 过滤条件 + 样本数）n_raw 不同定义不可混谈（errata #15）。
- 只处理「时间维重叠」；同一 regime 内 Δ≥W 的事件经济上仍相关，需 HAC/面板相关，
  本工具未实现，不得据此声称「独立」。
- p 值为 None（缺失）时跳过、结果写 None，绝不填 0——0 会被误读成「高度显著」。
"""
from __future__ import annotations

from collections import defaultdict

_VALID_METHODS = {"holm"}


def effective_n(events: list[tuple[str, int]], W: int) -> dict:
    """时间维重叠的有效样本数。

    Args:
        events: [(code, start_index)]，start_index 为事件起始的交易日序号。
        W: 事件窗口长度（交易日）。同一标的两事件起始间隔 Δ < W 判为重叠、并入同一簇。

    Returns:
        dict: n_raw / n_eff / n_overlap / ratio（n_raw=0 时为 None）/ verdict。
        跨标的同日事件不合并（按标的分别聚类）。

    反证：只处理时间维重叠，不含 HAC；Δ≥W 不代表经济独立（同 regime 仍相关）。
    """
    by_code: dict[str, list[int]] = defaultdict(list)
    for code, i in events:
        by_code[code].append(i)
    n_eff, n_overlap = 0, 0
    for code, idx in by_code.items():
        idx = sorted(idx)
        n_eff += 1
        for a, b in zip(idx, idx[1:]):
            if b - a < W:  # 严格小于才算窗口重叠
                n_overlap += 1
            else:
                n_eff += 1
    n_raw = len(events)
    return {
        "n_raw": n_raw,
        "n_eff": n_eff,
        "n_overlap": n_overlap,
        "ratio": round(n_eff / n_raw, 3) if n_raw else None,  # 缺失用 None，不填 0
        "verdict": _strength(n_raw, n_eff),
    }


def _strength(n_raw: int, n_eff: int) -> str:
    """结论强度分级：机械规则，不掺主观判断。"""
    if n_eff < 15 or n_raw < 15:
        return "不可用/仅案例"
    if n_eff < 30 or n_eff / n_raw < 0.7:
        return "降级用"
    return "可用"


def multipletests(pvals: list[float | None], *, method: str = "holm", alpha: float = 0.05) -> dict:
    """多重检验校正，零依赖实现 statsmodels 的 Holm-Bonferroni step-down。

    Args:
        pvals: 原始 p 值列表；None 表示缺失，跳过检验并在输出对应位置写 None（不填 0）。
        method: 仅支持 "holm"；其他值抛 ValueError，避免静默误用。
        alpha: 显著性水平，默认 0.05。

    Returns:
        dict:
          reject          —— 与输入等长，校正后是否拒绝原假设；缺失位为 None
          pvals_corrected —— 与输入等长，校正后 p 值；缺失位为 None
          method          —— 实际使用的方法
          alpha           —— 显著性水平
          n_tests         —— 参与检验的非缺失 p 值个数

    算法（Holm step-down）：p 升序排列，第 i 个（0-based）校正值 =
    max_{j<=i}((m-j) * p_j)，截断到 1.0；再按原索引还原。

    反证：Holm 控制族错误率（FWER），比 Bonferroni 有力，但仍比 FDR 保守；
    m=1 时校正值等于原值。校正值跨 0 与否取决于 alpha，不能只看点估计。
    """
    if method not in _VALID_METHODS:
        raise ValueError(f"不支持的多重检验方法: {method!r}；当前仅支持 {sorted(_VALID_METHODS)}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha 必须在 (0,1) 区间: {alpha!r}")

    m = sum(1 for p in pvals if p is not None)
    reject: list[bool | None] = [None] * len(pvals)
    corrected: list[float | None] = [None] * len(pvals)
    if m == 0:
        return {"reject": reject, "pvals_corrected": corrected, "method": method,
                "alpha": alpha, "n_tests": 0}

    indexed = sorted(((p, i) for i, p in enumerate(pvals) if p is not None), key=lambda x: x[0])
    running_max = 0.0
    for j, (p, orig_i) in enumerate(indexed):
        running_max = max(running_max, (m - j) * p)
        adj = min(1.0, running_max)
        corrected[orig_i] = adj
        reject[orig_i] = adj < alpha

    return {"reject": reject, "pvals_corrected": corrected, "method": method,
            "alpha": alpha, "n_tests": m}


def with_metadata(result: dict, *, benchmark: str | None, codes: list[str] | None,
                  window: int | None, n: int | None) -> dict:
    """给结果附加口径元数据 benchmark/codes/window/n 四字段。

    这四字段是 2026-11-22「三套 β 排序打架」的根因——当时每套数都没记录
    基准指数、标的集合、窗口、样本数，事后无法判定谁对谁。任何统计结论落盘前
    必须过本函数，缺字段写 None（不填 0 / 空串占位）。

    Args:
        result: 任意统计结果 dict（如 effective_n / multipletests 的输出）。
        benchmark: 基准指数代码（如 sh000001 / sh000300）；未知为 None。
        codes: 标的代码集合；未知为 None。
        window: 统计/事件窗口（交易日）；未知为 None。
        n: 有效样本数；未知为 None。

    Returns:
        原结果 + 四字段（原结果若已有同名字段，以这里显式传入为准）。
    """
    provenance = {"benchmark": benchmark, "codes": codes, "window": window, "n": n}
    return {**result, **provenance}


if __name__ == "__main__":
    import json

    # 自检：17 个无重叠事件（Δ=509, W=250）
    ev = [("S", i * 509) for i in range(17)]
    eff = with_metadata(effective_n(ev, 250), benchmark="sh000001", codes=["S"], window=250, n=17)
    print("effective_n:", json.dumps(eff, ensure_ascii=False))
    # 自检：6 个检验的 Holm 校正
    ht = multipletests([0.0034, 0.01, 0.02, 0.03, 0.04, 0.05], method="holm")
    print("holm:", json.dumps(ht, ensure_ascii=False))

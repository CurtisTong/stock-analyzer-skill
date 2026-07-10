"""
专家校准数据管理。

实现 experts/decide.md §六.2 设计的校准机制：
- 记录 debate 预测（record_prediction）
- 验证历史预测（verify_predictions）
- 计算校准因子（compute_calibration_factor）

数据持久化在项目根目录 data/expert_calibration.json。

校准阈值说明（v2.2.0 起显式文档化）：
- 涨跌判定阈值默认 5.0%（A 股经验值）——超过 5% 视为预测"命中"，
  阈值可在 `scoring.yaml` 的 `calibration.calibration_threshold_pct` 字段覆盖。
- 校准因子范围 [-1, 1]：正值 = 专家实际胜率 > 自身评估，负值 = 反之。
- 无校准数据时 8 位 active 专家 rates=[0.5]*8（legacy 8 人不参与校准），均值 0.5，CV=0，factor=0（保持中性）。
"""

import json
import logging
import os
import statistics
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

# 项目根目录 data/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CALIBRATION_FILE = _PROJECT_ROOT / "data" / "expert_calibration.json"

# legacy 专家名 -> 合并后的 active 专家名。
# 校准数据历史上按 legacy 名记录（buffett/duan_yongping 等），但这些专家
# 已合并进 active 专家（value_institution/emotion_tech/topic_leader）。
# 迁移时将 legacy 记录的 events/correct 合并到对应的 active 记录。
_CALIBRATION_LEGACY_TO_MERGED = {
    "buffett": "value_institution",
    "duan_yongping": "value_institution",
    "chaogu_yangjia": "emotion_tech",
    "zuoshou_xinyi": "emotion_tech",
    "xu_xiang": "topic_leader",
    "zhao_laoge": "topic_leader",
}


def _get_all_expert_names() -> list:
    """从注册表动态获取全部专家名。"""
    from experts.registry import EXPERT_REGISTRY

    return list(EXPERT_REGISTRY.keys())


def _get_calibration_threshold() -> float:
    """从 scoring.yaml 读取校准阈值（v1.7.1 起可配置）。

    Returns:
        涨跌判定阈值（%），默认 5.0（与历史行为一致）
    """
    try:
        from config.loader import ConfigLoader

        cfg = ConfigLoader.load("scoring.yaml")
        return float(cfg.get("calibration", {}).get("calibration_threshold_pct", 5.0))
    except (KeyError, ValueError, TypeError) as e:
        logging.getLogger(__name__).debug("校准阈值配置加载失败，使用默认 5.0%%: %s", e)
        return 5.0


def _empty_data() -> dict:
    return {
        "predictions": [],
        "experts": {
            name: {"events": 0, "correct": 0, "last_updated": None}
            for name in _get_all_expert_names()
        },
    }


def _migrate_legacy_experts(data: dict) -> dict:
    """将 legacy 专家名记录合并到对应的 active 专家名（幂等）。

    校准数据历史上按 legacy 名（buffett/duan_yongping/chaogu_yangjia/
    zuoshou_xinyi/xu_xiang/zhao_laoge）记录，但这些专家已合并进 active 专家
    （value_institution/emotion_tech/topic_leader）。record_prediction 现在写
    active 名，verify_predictions 用 `expert_name in data["experts"]` 过滤，
    若不迁移则新预测的专家校准数据永远不更新（静默数据丢失）。

    合并规则：events/correct 相加，last_updated 取较新者。迁移后删除 legacy 键，
    并写入 ``_migrated`` 标志避免重复迁移。
    """
    if data.get("_migrated"):
        return data

    experts = data.get("experts", {})
    for legacy_name, active_name in _CALIBRATION_LEGACY_TO_MERGED.items():
        legacy = experts.get(legacy_name)
        if legacy is None:
            continue
        active = experts.get(active_name)
        if active is None:
            # active 记录不存在：直接改名
            experts[active_name] = dict(legacy)
        else:
            # 合并 events/correct，取较新的 last_updated
            active["events"] = active.get("events", 0) + legacy.get("events", 0)
            active["correct"] = active.get("correct", 0) + legacy.get("correct", 0)
            lu_active = active.get("last_updated") or ""
            lu_legacy = legacy.get("last_updated") or ""
            active["last_updated"] = max(lu_active, lu_legacy)
        del experts[legacy_name]

    data["experts"] = experts
    data["_migrated"] = True
    return data


def _load() -> dict:
    if _CALIBRATION_FILE.exists():
        try:
            data = json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return _empty_data()
        return _migrate_legacy_experts(data)
    return _empty_data()


def _save(data: dict) -> None:
    _CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _CALIBRATION_FILE.with_suffix(".json.lock")
    lock_fd = None
    try:
        if _HAS_FCNTL:
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        fd, tmp = tempfile.mkstemp(dir=_CALIBRATION_FILE.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _CALIBRATION_FILE)
        except (OSError, TypeError, ValueError) as e:
            logging.getLogger(__name__).debug("校准文件写入失败: %s", e)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


def _normalize_expert_scores(expert_scores: Dict[str, float]) -> Dict[str, float]:
    """将 expert_scores 的键从 legacy 名归一化为 active 名。

    输入可能含 legacy 名（buffett/duan_yongping 等，来自 CLI 或旧版 debate），
    归一化后统一为 active 名，确保 verify_predictions 的 ``in`` 检查能匹配
    data["experts"]（后者经 _migrate_legacy_experts 也为 active 名）。
    同一 active 名多次映射时取较高分（反映较乐观的专家观点）。
    """
    normalized: Dict[str, float] = {}
    for name, score in expert_scores.items():
        active_name = _CALIBRATION_LEGACY_TO_MERGED.get(name, name)
        if active_name in normalized:
            normalized[active_name] = max(normalized[active_name], score)
        else:
            normalized[active_name] = score
    return normalized


def get_kline_return(stock_code: str, start_date: str, end_date: str) -> float:
    """获取股票在 [start_date, end_date] 区间的收益率%（第六轮审查 v2.4.3 新增）。

    作为 verify_predictions 的 get_price_fn 回调实现。基于日线 K 线数据，
    按日期匹配起止日的收盘价计算收益率。匹配不到精确日时取最近的交易日。

    Args:
        stock_code: 股票代码（sh600989 / sz000807）
        start_date: 起始日期（YYYY-MM-DD）
        end_date: 结束日期（YYYY-MM-DD）

    Returns:
        收益率百分比（如 12.5 表示 +12.5%）。数据不可得时抛 ValueError。

    Raises:
        ValueError: K 线数据获取失败或起止日均无匹配
    """
    try:
        from data import get_kline
    except ImportError as e:
        raise ValueError(f"无法导入 data.get_kline: {e}") from e

    # 取足够长的日线覆盖 start_date 到 end_date（最多 120 个交易日）
    bars = get_kline(stock_code, scale=240, datalen=120)
    if not bars:
        raise ValueError(f"获取 {stock_code} K 线数据为空")

    # 按日期索引收盘价
    by_day = {}
    for bar in bars:
        day = getattr(bar, "day", None) or bar.get("day")
        close = getattr(bar, "close", None)
        if close is None:
            close = bar.get("close")
        if day and close is not None:
            by_day[day] = float(close)

    if not by_day:
        raise ValueError(f"{stock_code} K 线数据无有效 day/close 字段")

    sorted_days = sorted(by_day.keys())

    # 匹配起始日：取 >= start_date 的第一个交易日
    start_close = None
    for d in sorted_days:
        if d >= start_date:
            start_close = by_day[d]
            break
    # 匹配结束日：取 <= end_date 的最后一个交易日
    end_close = None
    for d in reversed(sorted_days):
        if d <= end_date:
            end_close = by_day[d]
            break

    if start_close is None or end_close is None or start_close <= 0:
        raise ValueError(f"{stock_code} 在 [{start_date}, {end_date}] 区间无有效价格")

    return (end_close / start_close - 1) * 100


def record_prediction(
    stock_code: str,
    expert_scores: Dict[str, float],
    direction: str,
    composite_score: float = 0.0,
    verify_days: int = 30,
    timestamp: Optional[str] = None,
) -> str:
    """记录一次 debate 预测。

    同日同股的重复记录会覆盖前一次（以最后一次 debate 结果为准）。

    Args:
        stock_code: 股票代码（如 sh600989）
        expert_scores: {expert_name: score} 各专家评分
        direction: 最终方向（强烈看多/看多/中性/看空/强烈看空）
        composite_score: 调整后综合分
        verify_days: 多少天后验证（默认30）
        timestamp: ISO 格式时间戳，默认 now

    Returns:
        预测记录 ID
    """
    ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date = ts[:10]
    verify_after = (
        datetime.strptime(date, "%Y-%m-%d") + timedelta(days=verify_days)
    ).strftime("%Y-%m-%d")

    pred_id = f"pred_{date.replace('-', '')}_{stock_code}"

    # 归一化 expert_scores 键为 active 名（legacy 名 -> merged active 名）
    expert_scores = _normalize_expert_scores(expert_scores)

    data = _load()

    # 去重：同日同股不重复记录
    existing = [p for p in data["predictions"] if p["id"] == pred_id]
    if existing:
        existing[0]["expert_scores"] = expert_scores
        existing[0]["direction"] = direction
        existing[0]["composite_score"] = composite_score
        existing[0]["verify_after"] = verify_after
        _save(data)
        return pred_id

    record = {
        "id": pred_id,
        "stock": stock_code,
        "date": date,
        "direction": direction,
        "composite_score": composite_score,
        "expert_scores": expert_scores,
        "verified": False,
        "verify_after": verify_after,
        "actual_return": None,
        "actual_direction": None,
    }
    data["predictions"].append(record)
    _save(data)
    return pred_id


def verify_predictions(
    days: int = 30,
    get_price_fn=None,
    mark_only: bool = False,
) -> Dict[str, Any]:
    """验证到期的历史预测。

    Args:
        days: 验证窗口天数（与 record_prediction 的 verify_days 对应）
        get_price_fn: 可选的获取股票收益率函数。
            签名: get_price_fn(stock_code, start_date, end_date) -> float (收益率%)
            为 None 时跳过实际收益率计算。
        mark_only: 仅标记到期但不获取价格（无网络环境用）。
            注意：mark_only=True 会将预测标记为 verified 但不更新专家校准数据，
            且无法回滚--后续带 get_price_fn 的验证会跳过已标记记录。

    Returns:
        {"verified": int, "updated_experts": int, "skipped": int, "details": [...]}
    """
    data = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    verified_count = 0
    skipped_count = 0
    details = []

    for pred in data["predictions"]:
        if pred["verified"] or pred["verify_after"] > today:
            continue

        # 计算实际收益率
        actual_return = None
        actual_direction = None
        if get_price_fn is not None:
            try:
                actual_return = get_price_fn(
                    pred["stock"], pred["date"], pred["verify_after"]
                )
                # v1.7.1 起阈值可配置：从 scripts/config/scoring.yaml 读取
                threshold = _get_calibration_threshold()
                if actual_return > threshold:
                    actual_direction = "上涨"
                elif actual_return < -threshold:
                    actual_direction = "下跌"
                else:
                    actual_direction = "横盘"
            except (KeyError, ValueError, TypeError) as e:
                logging.getLogger(__name__).debug(
                    "获取 %s 实际收益率失败: %s", pred["stock"], e
                )

        # 第六轮审查（v2.4.3）修正重验证 bug：
        # 原 get_price_fn=None 时仍置 verified=True，导致预测被永久锁死（无结果）。
        # 现仅在以下情况标记 verified：
        #   1. mark_only=True（显式仅标记，无网络环境）
        #   2. actual_direction is not None（成功获取价格）
        # 否则跳过该预测（skipped），等待后续带 get_price_fn 的验证。
        if not mark_only and actual_direction is None:
            skipped_count += 1
            details.append(
                {
                    "id": pred["id"],
                    "stock": pred["stock"],
                    "direction": pred.get("direction", ""),
                    "actual_return": None,
                    "actual_direction": None,
                    "correct": None,
                    "skipped": True,
                }
            )
            continue

        pred["verified"] = True
        pred["actual_return"] = actual_return
        pred["actual_direction"] = actual_direction
        verified_count += 1

        # 更新专家校准数据：按每位专家自己的分数方向判定
        from experts import direction_from_score

        pred_direction = pred.get("direction", "")

        # 预测级别正确性（用组合方向，保留兼容）
        pred_correct = None
        if actual_direction is not None:
            if pred_direction in ("强烈看多", "看多") and actual_direction == "上涨":
                pred_correct = True
            elif pred_direction in ("看空", "强烈看空") and actual_direction == "下跌":
                pred_correct = True
            elif pred_direction == "中性" and actual_direction == "横盘":
                pred_correct = True
            else:
                pred_correct = False

        for expert_name, score in pred.get("expert_scores", {}).items():
            # expert_name 为 active 名（record_prediction 写入），
            # data["experts"] 键经 _migrate_legacy_experts 也为 active 名，
            # 此 in 检查才能匹配（修复前 legacy 键导致新预测永远不更新）。
            if expert_name in data["experts"]:
                if actual_direction is not None:
                    expert_direction = direction_from_score(score)
                    is_correct = None
                    if (
                        expert_direction in ("强烈看多", "看多")
                        and actual_direction == "上涨"
                    ):
                        is_correct = True
                    elif (
                        expert_direction in ("看空", "强烈看空")
                        and actual_direction == "下跌"
                    ):
                        is_correct = True
                    elif expert_direction == "中性" and actual_direction == "横盘":
                        is_correct = True
                    else:
                        is_correct = False
                    data["experts"][expert_name]["events"] += 1
                    if is_correct:
                        data["experts"][expert_name]["correct"] += 1
                data["experts"][expert_name]["last_updated"] = today

        details.append(
            {
                "id": pred["id"],
                "stock": pred["stock"],
                "direction": pred_direction,
                "actual_return": actual_return,
                "actual_direction": actual_direction,
                "correct": pred_correct,
            }
        )

    _save(data)
    updated = sum(1 for d in details if d.get("correct") is not None)
    return {
        "verified": verified_count,
        "updated_experts": updated,
        "skipped": skipped_count,
        "details": details,
    }


def get_calibration() -> Dict[str, dict]:
    """返回每位专家的校准数据。"""
    data = _load()
    return data.get("experts", {})


def get_pending_predictions() -> List[dict]:
    """返回尚未验证的预测记录。"""
    data = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    return [
        p
        for p in data.get("predictions", [])
        if not p.get("verified") and p.get("verify_after", "") <= today
    ]


def compute_calibration_factor() -> float:
    """计算校准因子（decide.md §六.2 公式）。

    校准因子 = 校准均值 × (1 - min(校准CV, 0.5))，归一化到 [-1, 1]。
    无历史数据时返回 0.0。

    v2.4.1 修正：仅使用 active 专家（8 人）的校准数据，
    legacy 专家（8 人）不参与 debate 也不应稀释校准因子。
    """
    from experts.registry import EXPERT_REGISTRY

    experts = get_calibration()
    rates = []
    active_names = [n for n, p in EXPERT_REGISTRY.items() if p.active]
    for name in active_names:
        rec = experts.get(name, {})
        events = rec.get("events", 0)
        correct = rec.get("correct", 0)
        if events > 0:
            rates.append(correct / events)
        else:
            rates.append(0.5)  # 无历史数据取 0.5

    if not rates:
        return 0.0

    mean_rate = statistics.mean(rates)
    if mean_rate > 0:
        cv = statistics.stdev(rates) / mean_rate if len(rates) > 1 else 0
    else:
        cv = 1.0

    factor = mean_rate * (1 - min(cv, 0.5))
    # 归一化到 [-1, 1]: (factor - 0.5) * 2
    return max(-1.0, min(1.0, (factor - 0.5) * 2))


def get_calibration_report() -> str:
    """生成校准报告（人类可读文本）。"""
    experts = get_calibration()
    factor = compute_calibration_factor()

    lines = ["## 专家校准报告", ""]
    lines.append(f"校准因子: {factor:+.3f} (范围 [-1, 1])")
    lines.append("")
    lines.append("| 专家 | 事件数 | 正确数 | 校准率 |")
    lines.append("|------|--------|--------|--------|")

    for name in _get_all_expert_names():
        rec = experts.get(name, {})
        events = rec.get("events", 0)
        correct = rec.get("correct", 0)
        rate = f"{correct/events:.1%}" if events > 0 else "无数据"
        lines.append(f"| {name} | {events} | {correct} | {rate} |")

    pending = get_pending_predictions()
    if pending:
        lines.append("")
        lines.append(f"### 待验证预测 ({len(pending)} 条)")
        for p in pending[:10]:
            lines.append(
                f"- {p['stock']} ({p['date']}) → {p['direction']} "
                f"(验证日期: {p['verify_after']})"
            )

    return "\n".join(lines)


def compute_group_calibration(group: str) -> float:
    """计算指定组的校准因子（第六轮审查 v2.4.3 新增）。

    与 compute_calibration_factor 相同的公式，但仅用该组 active 专家的校准数据。
    用于定向惩罚低准确率组（如短线组 20%）而非全局平均稀释。

    Args:
        group: "long_term" 或 "short_term"

    Returns:
        校准因子 ∈ [-1, 1]，无数据返回 0.0
    """
    from experts.registry import EXPERT_REGISTRY

    experts = get_calibration()
    rates = []
    for name, profile in EXPERT_REGISTRY.items():
        if not profile.active or profile.group != group:
            continue
        rec = experts.get(name, {})
        events = rec.get("events", 0)
        correct = rec.get("correct", 0)
        if events > 0:
            rates.append(correct / events)
        else:
            rates.append(0.5)

    if not rates:
        return 0.0

    mean_rate = statistics.mean(rates)
    if mean_rate > 0:
        cv = statistics.stdev(rates) / mean_rate if len(rates) > 1 else 0
    else:
        cv = 1.0

    factor = mean_rate * (1 - min(cv, 0.5))
    return max(-1.0, min(1.0, (factor - 0.5) * 2))


__all__ = [
    "record_prediction",
    "verify_predictions",
    "get_calibration",
    "get_pending_predictions",
    "compute_calibration_factor",
    "compute_group_calibration",
    "get_kline_return",
    "get_calibration_report",
]

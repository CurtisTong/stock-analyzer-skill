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
- 无校准数据时 9 位 active 专家 rates=[0.5]*9（legacy 6 人不参与校准），均值 0.5，CV=0，factor=0（保持中性）。
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
    except Exception as e:
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


def _load() -> dict:
    if _CALIBRATION_FILE.exists():
        try:
            return json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return _empty_data()
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
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


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
) -> Dict[str, Any]:
    """验证到期的历史预测。

    Args:
        days: 验证窗口天数（与 record_prediction 的 verify_days 对应）
        get_price_fn: 可选的获取股票收益率函数。
            签名: get_price_fn(stock_code, start_date, end_date) -> float (收益率%)
            为 None 时跳过实际收益率计算，仅标记到期。

    Returns:
        {"verified": int, "updated_experts": int, "details": [...]}
    """
    data = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    verified_count = 0
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
            except Exception as e:
                logging.getLogger(__name__).debug(
                    "获取 %s 实际收益率失败: %s", pred["stock"], e
                )

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
    return {"verified": verified_count, "updated_experts": updated, "details": details}


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
    """
    experts = get_calibration()
    rates = []
    for name in _get_all_expert_names():
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


__all__ = [
    "record_prediction",
    "verify_predictions",
    "get_calibration",
    "get_pending_predictions",
    "compute_calibration_factor",
    "get_calibration_report",
]

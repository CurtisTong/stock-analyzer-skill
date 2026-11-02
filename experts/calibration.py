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

from experts.types import BEARISH_DIRECTIONS, BULLISH_DIRECTIONS, NEUTRAL_DIRECTION

try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

# 项目根目录 data/
# experts/calibration.py 只有 2 层深（experts/ -> 仓库根），
# 用 parent.parent 定位仓库根；parent.parent.parent 会多退一级，
# 把校准数据写到仓库外的同级目录（沙箱内会 PermissionError）。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CALIBRATION_FILE = _PROJECT_ROOT / "data" / "expert_calibration.json"

# v1.24.0：胜率卡片最小样本数。events 低于该值时胜率显示"样本不足"而非百分比，
# 防止小样本胜率（如 3 战 3 胜 = 100%）被过度解读（对标 ai-hedge-fund scorecard 口径）。
MIN_CALIBRATION_SAMPLES = 10

# v1.24.0：按专家角色分桶的验证窗口（自然日），替换统一 30 天窗。
# 用错误时间窗评价专家会让长线视角被短窗噪声误伤（价值机构 30 天胜率无意义），
# 也会给短线视角发放过长免责期。口径对标 ai-hedge-fund 的 per-analyst horizon。
# 长线价值/趋势 120 交易日 ≈ 180 自然日；行业景气/风险预算 60 交易日 ≈ 90；
# 短线题材/情绪/动量 5-10 交易日 ≈ 14 自然日。
EXPERT_HORIZON_DAYS = {
    "lynch": 180,
    "soros": 180,
    "value_institution": 180,
    "sector_specialist": 90,
    "risk_manager": 90,
    "topic_leader": 14,
    "emotion_tech": 14,
    "momentum_trader": 14,
}
# 未知专家名（含 legacy 旧记录回放）回退 30 天，与旧行为一致
DEFAULT_HORIZON_DAYS = 30

# v1.24.0 反思记忆：每位专家滚动保留的教训条数（对标 TradingAgents-CN
# 分层反思——只存"为什么错"的结构化教训，debate 注入近 2 条）
MAX_LESSONS = 5
LESSON_INJECT_LIMIT = 2


def _expert_horizon(name: str) -> int:
    """单个专家的验证窗口（自然日）。"""
    return EXPERT_HORIZON_DAYS.get(name, DEFAULT_HORIZON_DAYS)


def direction_matches(direction: str, actual_direction: str) -> bool:
    """判断方向判断是否与实际走势一致。

    覆盖 7 级方向标签（含"谨慎看多"/"谨慎看空"——vote_engine 的冲突解决
    路径会产出这两个标签，漏掉会让谨慎方向的预测永远记为失败）。

    Args:
        direction: 预测方向标签
        actual_direction: 实际方向（上涨/下跌/横盘）

    Returns:
        是否一致
    """
    if direction in BULLISH_DIRECTIONS:
        return actual_direction == "上涨"
    if direction in BEARISH_DIRECTIONS:
        return actual_direction == "下跌"
    if direction == NEUTRAL_DIRECTION:
        return actual_direction == "横盘"
    return False


def _directional_return(ret: float, expert_direction: str) -> float:
    """按专家方向调整收益符号（slugging 赔率口径）。

    看空专家"赢"意味着股价下跌（原始收益为负）。若直接用带符号收益，
    看空专家的赔率会是负数（实测 -1.60），语义完全错乱。
    此处统一折算为"相对专家方向的收益"：看多取原值，看空取相反数。
    """
    if expert_direction in BEARISH_DIRECTIONS:
        return -ret
    return ret


def _lesson_improvement(expert_name: str, direction: str, actual: str, score: float) -> str:
    """由错误形态生成改进提示（规则式，无 LLM 依赖）。

    按专家所在组（长线/短线）区分措辞：长线错误多为"证伪时滞"，
    短线错误多为"信号衰减过快"，中性错误多为"缺波动率条件"。
    """
    from experts.registry import EXPERT_REGISTRY

    group = ""
    profile = EXPERT_REGISTRY.get(expert_name)
    if profile is not None:
        group = getattr(profile, "group", "")

    if direction == "中性":
        return "中性判断错过单边行情：横盘结论需要波动率/量能条件支撑，条件不足时降为观望并缩短复核周期"

    bullish = direction in BULLISH_DIRECTIONS
    went_down = actual in ("下跌", "横盘")
    if bullish and went_down:
        if group == "short_term":
            return "题材/情绪信号在该窗口内衰减：提高入场门槛（量能/封板质量确认）或缩短持有预期"
        return "低估证伪时滞：检查逻辑兑现所需窗口是否超过自身 horizon，或补充更硬的证伪条件"
    if not bullish and not went_down:
        if group == "short_term":
            return "看空过早：强势标的的趋势惯性超出预期，需等待量价破坏信号再行动"
        return "高估了负面因素权重：重新核验估值/基本面证据是否被短期动量压制"
    return "方向与实际不符：复核打分依据中权重最高的证据项是否仍然成立"


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
    """从注册表动态获取全部专家名（16 份：8 active + 8 legacy）。"""
    from experts.registry import EXPERT_REGISTRY, _ensure_loaded

    _ensure_loaded()  # EXPERT_REGISTRY 为惰性加载，直接 import 时为空
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
    except (KeyError, ValueError, TypeError, ImportError, ModuleNotFoundError) as e:
        # （v1.26.0）白名单补 ImportError：config.loader 位于 scripts/ 下，
        # experts 包对它有隐式 sys.path 依赖——路径未就绪时抛 ModuleNotFoundError，
        # 原白名单不含它，异常会冲出 verify_predictions 整体崩溃。
        logging.getLogger(__name__).debug("校准阈值配置加载失败，使用默认 5.0%%: %s", e)
        return 5.0


def _empty_data() -> dict:
    """空校准数据：仅 8 位 active 专家占位（legacy 不参与校准）。"""
    from experts.registry import EXPERT_REGISTRY, _ensure_loaded

    _ensure_loaded()
    return {
        "predictions": [],
        "experts": {
            name: {"events": 0, "correct": 0, "last_updated": None} for name, p in EXPERT_REGISTRY.items() if p.active
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


def _ensure_active_experts(data: dict) -> dict:
    """只保留 active 专家条目，并为缺失的 active 专家补齐占位（events=0/correct=0）。

    v1.23.1 修复：迁移只处理 legacy 名 → active 名，从未跑过 legacy 的
    active 专家（sector_specialist/risk_manager/momentum_trader）不会自然
    长出条目；而 verify_predictions 用 `expert_name in data["experts"]`
    过滤，缺条目 ⇒ 校准数据对这些专家**永远不更新**（闭环失效）。

    同时把 legacy 占位条目清掉——legacy 8 人已合并迁移（_migrate_legacy_experts
    会删除其键），不参与 debate，也不应出现在校准库/胜率卡片中。

    补齐后：debate 胜率卡片可渲染全部 8 位 active 专家（无历史显示
    "样本不足"而非缺行），到期验证也能给这 3 位专家累计数据。
    """
    from experts.registry import EXPERT_REGISTRY, _ensure_loaded

    _ensure_loaded()  # EXPERT_REGISTRY 为惰性加载，直接 import 时为空
    active_names = {n for n, p in EXPERT_REGISTRY.items() if p.active}
    experts = {n: r for n, r in data.get("experts", {}).items() if n in active_names}
    for name in active_names:
        experts.setdefault(name, {"events": 0, "correct": 0, "last_updated": None})
    data["experts"] = experts
    return data


def _load(strict: bool = False) -> dict:
    """读取校准数据。

    Args:
        strict: True 表示这是**写路径**（record/verify），文件损坏时抛错中止，
            防止后续 _save() 用空结构覆盖历史；False 表示只读路径（报告/因子），
            损坏时降级为空数据并告警，不阻断调用方。
    """
    if _CALIBRATION_FILE.exists():
        try:
            raw = _CALIBRATION_FILE.read_text(encoding="utf-8")
        except OSError:
            return _empty_data()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            # （v1.26.0）文件损坏时不得静默返回空数据——后续任何一次 _save()
            # 都会用空结构覆盖原文件，历史永久丢失且无告警。现在：
            # 1) 把损坏文件备份为 .corrupted-<时间戳>，保留现场可人工修复；
            # 2) 写路径抛错中止（不会覆盖历史），只读路径降级告警。
            backup = _CALIBRATION_FILE.with_suffix(f".corrupted-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            try:
                backup.write_text(raw, encoding="utf-8")
                backup_desc = str(backup)
            except OSError:
                backup_desc = "(备份失败)"  # 备份失败不掩盖原始错误
            logger = logging.getLogger(__name__)
            logger.error(
                "校准文件损坏（%s），已备份至 %s；请人工修复后重试",
                e,
                backup_desc,
            )
            if strict:
                raise ValueError(f"校准文件损坏，已中止写操作以防覆盖历史: {_CALIBRATION_FILE}") from e
            return _empty_data()
        return _ensure_active_experts(_migrate_legacy_experts(data))
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
    """获取股票在 [start_date, end_date] 区间的收益率%（v2.4.3 引入）。

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

    # 取足够长的日线覆盖 start_date 到 end_date。
    # （v1.26.0）：原实现固定 datalen=120（≈168 自然日），而长线专家的
    # horizon 是 180 自然日（≈130 交易日）——K 线覆盖不到窗口起点，
    # "取 >= start_date 的第一个交易日"会落到 13 天之后，窗口被静默缩短，
    # 长线专家的正确/错误判定双向失真（生产 long factor=-0.2886 由此而来）。
    # 现在按实际区间长度换算所需交易日数并留出冗余。
    span_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
    # 自然日 → 交易日：周末约占 2/7，再留 15% 节假日冗余
    required_bars = max(120, int(span_days / 7 * 5 * 1.15) + 30)
    bars = get_kline(stock_code, scale=240, datalen=required_bars)
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
    start_day = None
    start_close = None
    for d in sorted_days:
        if d >= start_date:
            start_day = d
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

    # 覆盖度校验：实际起点若明显晚于请求起点，说明 K 线不足以覆盖整个
    # 窗口（数据源历史长度不够），此时算出的收益率对应的是被缩短的窗口，
    # 会污染校准样本。此时报错让该样本跳过，而不是记入错误方向。
    if start_day is not None:
        actual_span = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_day, "%Y-%m-%d")).days
        if actual_span < span_days * 0.8:
            raise ValueError(
                f"{stock_code} K 线覆盖不足：请求窗口 {span_days} 天，"
                f"实际起点 {start_day}（仅覆盖 {actual_span} 天）"
            )

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
    verify_after = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=verify_days)).strftime("%Y-%m-%d")

    pred_id = f"pred_{date.replace('-', '')}_{stock_code}"

    # 归一化 expert_scores 键为 active 名（legacy 名 -> merged active 名）
    expert_scores = _normalize_expert_scores(expert_scores)

    # v1.24.0 horizon 分桶：每位专家按自己的验证窗口算到期日；
    # 顶层 verify_after 取所有专家中最短窗口（最早到期日），保持旧字段语义可用
    expert_horizons = {
        name: (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=_expert_horizon(name))).strftime("%Y-%m-%d")
        for name in expert_scores
    }
    if expert_horizons:
        verify_after = min(verify_after, min(expert_horizons.values()))

    data = _load(strict=True)

    # 去重：同日同股不重复记录
    existing = [p for p in data["predictions"] if p["id"] == pred_id]
    if existing:
        prev = existing[0]
        prev["expert_scores"] = expert_scores
        prev["direction"] = direction
        prev["composite_score"] = composite_score
        prev["verify_after"] = verify_after
        prev["expert_horizons"] = expert_horizons
        # （v1.26.0）保留已结算状态，不清空。
        # 原实现把 settled_experts 重置为 [] 且 verified=False，但专家的
        # events/correct 计数不回滚——下次 verify 会把同一次预测再结算一遍，
        # 胜率被重复计入（实测 lynch events 1→2）。
        # 触发路径：calibration_backfill import 重复执行、calibration_sync
        # pull 覆盖本地后再次 verify。
        # 已结算的专家保持结算（不重复计数），未结算的按新分数等待结算。
        settled = set(prev.get("settled_experts", []))
        prev["settled_experts"] = sorted(settled & set(expert_scores))
        prev["verified"] = bool(prev.get("verified")) and set(prev["settled_experts"]) >= set(expert_scores)
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
        "expert_horizons": expert_horizons,
        "settled_experts": [],
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
    """验证到期的历史预测（v1.24.0 起按专家 horizon 分桶结算）。

    每位专家按自己的验证窗口（EXPERT_HORIZON_DAYS）独立到期独立结算：
    一条预测里短线专家（14 天）先结算，长线专家（180 天）到期后补结算。
    全部专家结算完毕才置 ``verified=True``。旧记录无 ``expert_horizons``
    字段时沿用顶层 ``verify_after`` 一次性结算，行为与旧版一致。

    Args:
        days: 兼容参数（旧签名保留，实际窗口以记录内 expert_horizons 为准）
        get_price_fn: 可选的获取股票收益率函数。
            签名: get_price_fn(stock_code, start_date, end_date) -> float (收益率%)
            为 None 时跳过实际收益率计算。
        mark_only: 仅标记到期但不获取价格（无网络环境用）。
            注意：mark_only=True 会将到期专家标记为已结算但不更新校准数据，
            且无法回滚--后续带 get_price_fn 的验证会跳过已标记专家。

    Returns:
        {"verified": int, "updated_experts": int, "skipped": int, "details": [...]}
    """
    data = _load(strict=True)
    today = datetime.now().strftime("%Y-%m-%d")
    verified_count = 0
    skipped_count = 0
    details = []

    from experts import direction_from_score

    for pred in data["predictions"]:
        if pred.get("verified"):
            continue

        horizons = pred.get("expert_horizons") or {}
        expert_scores = pred.get("expert_scores", {})
        settled = set(pred.get("settled_experts", []))

        if horizons:
            # 新记录：按专家 horizon 找本轮到期且未结算的专家
            due = {
                name for name, end in horizons.items() if end <= today and name not in settled and name in expert_scores
            }
            if not due:
                continue
            all_experts = {n for n in horizons if n in expert_scores}
        else:
            # 旧记录：无分桶字段，沿用顶层 verify_after 一次性结算
            if pred["verify_after"] > today:
                continue
            due = set(expert_scores)
            all_experts = set(expert_scores)
            horizons = {n: pred["verify_after"] for n in expert_scores}

        # 按验证窗口分组获取实际方向（同一条预测最多 3 种窗口，避免重复拉价）
        direction_by_window: Dict[str, Optional[str]] = {}
        return_by_window: Dict[str, Optional[float]] = {}
        if get_price_fn is not None and not mark_only:
            threshold = _get_calibration_threshold()
            for window_end in sorted({horizons[n] for n in due}):
                try:
                    actual_return = get_price_fn(pred["stock"], pred["date"], window_end)
                    return_by_window[window_end] = actual_return
                    if actual_return > threshold:
                        direction_by_window[window_end] = "上涨"
                    elif actual_return < -threshold:
                        direction_by_window[window_end] = "下跌"
                    else:
                        direction_by_window[window_end] = "横盘"
                except (KeyError, ValueError, TypeError) as e:
                    logging.getLogger(__name__).debug("获取 %s 实际收益率失败: %s", pred["stock"], e)
                    direction_by_window[window_end] = None
                    return_by_window[window_end] = None

        if not mark_only and all(direction_by_window.get(horizons[n]) is None for n in due):
            # 本轮到期专家的价格全部获取失败：跳过等待下次验证（v2.4.3 语义）
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

        # 逐位专家按自己的窗口结算
        for expert_name in sorted(due):
            window_end = horizons[expert_name]
            actual_direction = direction_by_window.get(window_end)
            if expert_name in data["experts"]:
                if actual_direction is not None:
                    expert_direction = direction_from_score(expert_scores[expert_name])
                    is_correct = None
                    is_correct = direction_matches(expert_direction, actual_direction)
                    # （v1.26.0）残缺条目兜底：老数据/手工编辑可能缺 events 键，
                    # 直接 += 会抛 KeyError 中断**整轮 verify**（_save 不执行，
                    # 所有专家零进度）。改为从 0 起算。
                    rec = data["experts"][expert_name]
                    rec["events"] = rec.get("events", 0) + 1
                    if is_correct:
                        rec["correct"] = rec.get("correct", 0) + 1
                        # v1.24.0 slugging 口径（ai-hedge-fund scorecard）：
                        # 赢时结算的平均收益，仅统计方向性判断（中性正确不进入赔率）
                        ret_win = return_by_window.get(window_end)
                        if ret_win is not None and expert_direction not in ("中性",):
                            rec = data["experts"][expert_name]
                            rec["slug_win_sum"] = rec.get("slug_win_sum", 0.0) + _directional_return(
                                ret_win, expert_direction
                            )
                            rec["slug_win_n"] = rec.get("slug_win_n", 0) + 1
                    else:
                        # v1.24.0 反思记忆：错误结算生成结构化教训（滚动保留 MAX_LESSONS 条）
                        lesson = {
                            "date": pred.get("date", ""),
                            "stock": pred.get("stock", ""),
                            "direction": expert_direction,
                            "score": expert_scores[expert_name],
                            "actual_direction": actual_direction,
                            "actual_return": return_by_window.get(window_end),
                            "window_days": _expert_horizon(expert_name),
                            "lesson": (
                                f"预测{expert_direction}({expert_scores[expert_name]:.0f}分)"
                                f"但{_expert_horizon(expert_name)}日窗口实际{actual_direction}"
                                f"（{return_by_window.get(window_end) or 0:+.1f}%）"
                            ),
                            "improvement": _lesson_improvement(
                                expert_name, expert_direction, actual_direction, expert_scores[expert_name]
                            ),
                        }
                        lessons = data["experts"][expert_name].setdefault("lessons", [])
                        lessons.append(lesson)
                        del lessons[:-MAX_LESSONS]
                        # slugging 输侧统计：输时结算的平均收益（方向性判断）
                        ret_loss = return_by_window.get(window_end)
                        if ret_loss is not None and expert_direction not in ("中性",):
                            rec = data["experts"][expert_name]
                            rec["slug_loss_sum"] = rec.get("slug_loss_sum", 0.0) + _directional_return(
                                ret_loss, expert_direction
                            )
                            rec["slug_loss_n"] = rec.get("slug_loss_n", 0) + 1
                data["experts"][expert_name]["last_updated"] = today
            # 只有取价成功（actual_direction 非 None）的专家才标记为已结算：
            # 取价失败时标记 settled 会让该窗口样本永久丢失（不再重试）。
            # mark_only=True 是"无网络环境只标记到期"的有意设计，仍照常标记。
            if actual_direction is not None or mark_only:
                settled.add(expert_name)

        # 主窗口（顶层 verify_after）方向用于预测级 correct 与兼容字段。
        # 多轮结算时顶层窗口可能不在本轮 due 集合内（direction_by_window 只含
        # 本轮窗口），直接取会得到 None → 预测级 actual_return/correct 永久为空、
        # updated_experts 归零。此处回退到本轮最短的可用窗口。
        main_window = pred.get("verify_after") or horizons.get(next(iter(due))) or ""
        if main_window not in direction_by_window:
            available = sorted(w for w in direction_by_window if direction_by_window.get(w) is not None)
            if available:
                main_window = available[0]
        main_direction = direction_by_window.get(main_window)
        main_return = return_by_window.get(main_window)

        fully_settled = all_experts <= settled
        if fully_settled:
            pred["verified"] = True
            pred["actual_return"] = main_return
            pred["actual_direction"] = main_direction
            verified_count += 1

        pred_direction = pred.get("direction", "")
        pred_correct = None
        if main_direction is not None:
            pred_correct = direction_matches(pred_direction, main_direction)

        pred["settled_experts"] = sorted(settled)
        details.append(
            {
                "id": pred["id"],
                "stock": pred["stock"],
                "direction": pred_direction,
                "actual_return": main_return,
                "actual_direction": main_direction,
                "correct": pred_correct,
                "settled_experts": sorted(due),
                "fully_settled": fully_settled,
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
    """返回到期待结算的预测记录。

    v1.24.0 分桶语义：任一专家的验证窗口已到且尚未结算即算 pending
    （一条预测可能短线组已结算、长线组仍待结算）。旧记录沿用 verify_after。
    """
    data = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    pending = []
    for p in data.get("predictions", []):
        if p.get("verified"):
            continue
        horizons = p.get("expert_horizons") or {}
        settled = set(p.get("settled_experts", []))
        if horizons:
            due_exists = any(end <= today and name not in settled for name, end in horizons.items())
        else:
            due_exists = p.get("verify_after", "") <= today
        if due_exists:
            pending.append(p)
    return pending


def _calibration_factor_from_rates(rates: list[float]) -> float:
    """由校准率列表计算校准因子（decide.md §六.2）。

    修正（v2.4.3 后）：
        校准因子 = (mean_rate - 0.5) × 2 × (1 - min(cv, 0.5))
    mean_rate=0.5（无信息）时恒为 0——不因离散度产生负惩罚；
    mean_rate=1.0 且 cv=0 时取 1.0（完全可信），mean_rate=0.0 时取 -0.5。
    """
    if not rates:
        return 0.0
    mean_rate = statistics.mean(rates)
    if mean_rate > 0:
        cv = statistics.stdev(rates) / mean_rate if len(rates) > 1 else 0
    else:
        cv = 1.0
    factor = (mean_rate - 0.5) * 2 * (1 - min(cv, 0.5))
    return max(-1.0, min(1.0, factor))


def _slugging_from_rec(rec: dict) -> float | None:
    """slugging 赔率 = 赢时平均收益 / |输时平均收益|（ai-hedge-fund scorecard）。

    赢/输均为方向性判断（中性正确/错误不进入赔率统计）。
    双侧样本齐全（win_n>0 且 loss_n>0）才返回，否则 None。
    """
    win_n = rec.get("slug_win_n", 0)
    loss_n = rec.get("slug_loss_n", 0)
    if win_n == 0 or loss_n == 0:
        return None
    win_avg = rec.get("slug_win_sum", 0.0) / win_n
    loss_avg = rec.get("slug_loss_sum", 0.0) / loss_n
    if abs(loss_avg) < 1e-9:
        return None
    slug = win_avg / abs(loss_avg)
    return round(slug, 2)


def compute_calibration_factor() -> float:
    """计算校准因子（decide.md §六.2 公式，修正）。

    校准因子 = (校准均值 - 0.5) × 2 × (1 - min(校准CV, 0.5))，归一化到 [-1, 1]。
    无历史数据时返回 0.0。

    v2.4.1 修正：仅使用 active 专家（8 人）的校准数据，
    legacy 专家（8 人）不参与 debate 也不应稀释校准因子。

    v1.26.0：样本门槛与胜率卡片口径对齐（MIN_CALIBRATION_SAMPLES）。
    原实现把"无历史数据"按 0.5 充数参与计算，且不设门槛——1 条样本的
    专家就能把因子推到 ±0.086（信心 ∓0.8 分），而卡片同时显示"样本不足"。
    现在：样本数低于门槛的专家按**中性 0.5** 计入——与"完全无历史数据"
    口径一致，rates 长度恒为 active 专家数（CV 计算稳定），且样本不足的
    专家不会把因子拉偏（其真实胜率不可信，但按 0.5 中性比按真实率更稳）。
    """
    from experts.registry import EXPERT_REGISTRY

    experts = get_calibration()
    rates = []
    active_names = [n for n, p in EXPERT_REGISTRY.items() if p.active]
    for name in active_names:
        rec = experts.get(name, {})
        events = rec.get("events", 0)
        correct = rec.get("correct", 0)
        if events >= MIN_CALIBRATION_SAMPLES:
            rates.append(correct / events)
        else:
            # 无历史数据（events=0）或样本不足（0<events<门槛）：按中性计入
            rates.append(0.5)

    return _calibration_factor_from_rates(rates)


def get_calibration_report() -> str:
    """生成校准报告（人类可读文本）。"""
    experts = get_calibration()
    factor = compute_calibration_factor()

    lines = ["## 专家校准报告", ""]
    lines.append(f"校准因子: {factor:+.3f} (范围 [-1, 1])")
    lines.append("")
    # v1.24.0 赔率列：slugging = 赢时平均收益 / |输时平均收益|（>1 说明赢比输大）
    lines.append("| 专家 | 事件数 | 正确数 | 校准率 | 赔率(slugging) |")
    lines.append("|------|--------|--------|--------|----------------|")

    for name in _get_all_expert_names():
        rec = experts.get(name, {})
        events = rec.get("events", 0)
        correct = rec.get("correct", 0)
        # 与胜率卡片同口径：样本数低于 MIN_CALIBRATION_SAMPLES 不渲染百分比
        if events >= MIN_CALIBRATION_SAMPLES:
            rate = f"{correct/events:.1%}"
        elif events > 0:
            rate = f"样本不足 (n={events})"
        else:
            rate = "无数据"
        slug = _slugging_from_rec(rec)
        slug_str = (
            f"赢{rec.get('slug_win_n', 0)}输{rec.get('slug_loss_n', 0)} · {slug:.2f}"
            if slug is not None
            else "样本不足"
        )
        lines.append(f"| {name} | {events} | {correct} | {rate} | {slug_str} |")

    pending = get_pending_predictions()
    if pending:
        lines.append("")
        lines.append(f"### 待验证预测 ({len(pending)} 条)")
        for p in pending[:10]:
            lines.append(f"- {p['stock']} ({p['date']}) → {p['direction']} " f"(验证日期: {p['verify_after']})")

    return "\n".join(lines)


def compute_group_calibration(group: str) -> float:
    """计算指定组的校准因子（v2.4.3 引入）。

    与 compute_calibration_factor 相同的公式（(mean-0.5)×2×(1-cv)），
    但仅用该组 active 专家的校准数据。用于定向惩罚低准确率组
    （如短线组 20%）而非全局平均稀释。

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
        if events >= MIN_CALIBRATION_SAMPLES:
            rates.append(correct / events)
        else:
            # 无历史数据或样本不足：按中性计入（口径与全局一致）
            rates.append(0.5)

    if not rates:
        return 0.0

    # （v1.26.0）与 compute_calibration_factor 用同一公式：
    #   factor = (mean_rate - 0.5) × 2 × (1 - min(cv, 0.5))
    # 原实现写成 mean_rate × (1-cv) 再 (factor-0.5)×2，等价于少了
    # (1-cv) 的一半——同一份数据下分组因子与全局因子口径不一致，
    # 短线组惩罚被放大（实测 -0.1556 vs -0.5722）。
    return _calibration_factor_from_rates(rates)


def get_lessons(limit: int | None = None) -> Dict[str, list]:
    """获取各专家的反思教训（供 debate 打分环节注入，v1.25）。

    v1.24.0 落地了反思记忆，但教训只被 decide.py 在**投票后**挂到结果里
    渲染——从未进入打分环节。真正的回流需要打分前就能取到教训：
    SKILL.md Step 4 在逐位专家打分前调用本函数（或 `calibration.py lessons`），
    把该专家的近几条错误教训注入其打分上下文。

    Args:
        limit: 每位专家最多返回的教训条数（None = 全部保留的）

    Returns:
        {expert_name: [lesson dict, ...]}（仅含**有教训**的专家）
    """
    calibration = get_calibration()
    out: Dict[str, list] = {}
    for name, rec in calibration.items():
        lessons = rec.get("lessons") or []
        if not lessons:
            continue
        picked = lessons[-limit:] if limit else lessons
        if picked:
            out[name] = list(picked)
    return out


__all__ = [
    "record_prediction",
    "verify_predictions",
    "get_calibration",
    "get_pending_predictions",
    "compute_calibration_factor",
    "compute_group_calibration",
    "get_kline_return",
    "get_calibration_report",
    "get_lessons",
    "direction_matches",
    "MIN_CALIBRATION_SAMPLES",
    "EXPERT_HORIZON_DAYS",
    "DEFAULT_HORIZON_DAYS",
]

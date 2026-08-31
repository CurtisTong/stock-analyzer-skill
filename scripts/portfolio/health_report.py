"""持仓组合纯工具（从 manager.py 拆分）。

health_report / health_report_markdown / check_concentration 下沉到此模块，
供 PortfolioManager 与 Web 层共用，manager 保留同名方法作为 thin wrapper。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

BREAKDOWN_THRESHOLD = 0.95

# 状态类标签白名单：tags[0] 是这类时不当作行业，避免
# 宝丰能源 tags=["T+1待交收","煤化工","能源"] 被错误归类
_STATUS_TAGS = frozenset(
    {
        # 持有期/仓位类
        "T+1待交收",
        "T+1",
        "长线",
        "短线",
        "核心",
        "卫星",
        "底仓",
        "波段",
        "网格",
        "定投",
        "观察",
        "待加仓",
        "长持",
        "永持",
        "待止损",
        "待止盈",
        "已止盈",
        "对冲",
        "套保",
        "金字塔",
        "左侧",
        "右侧",
        # 投资风格类
        "白马",
        "价值",
        "蓝筹",
        "大盘",
        "红利",
        "高股息",
        "成长",
        "主题",
        "概念",
        "题材",
        "赛道",
        "科技",
        "趋势",
        "反转",
        "突破",
        "超跌",
        "低吸",
        "追涨",
        "短线投机",
        "打板",
        "涨停",
        "妖股",
        "壳资源",
        # 状态描述类
        "浮盈",
        "浮亏",
        "止损",
        "止盈",
    }
)

# 行业子标签 → 行业大类映射：合并分散标签到 6 大生态。
# 避免 tags[0]="锂矿/锂业/储能/光伏/新能源/有色" 等被分散成多个行业。
_INDUSTRY_GROUP = {
    # ── 锂/新能源链 ─────────────────────────────────
    "锂电": "锂/新能源",
    "锂矿": "锂/新能源",
    "锂业": "锂/新能源",
    "锂电池": "锂/新能源",
    "锂材料": "锂/新能源",
    "电池": "锂/新能源",
    "动力电池": "锂/新能源",
    "储能电池": "锂/新能源",
    "正极": "锂/新能源",
    "负极": "锂/新能源",
    "隔膜": "锂/新能源",
    "电解液": "锂/新能源",
    "三元": "锂/新能源",
    "磷酸铁锂": "锂/新能源",
    "电池片": "锂/新能源",
    "组件": "锂/新能源",
    "逆变器": "锂/新能源",
    "硅料": "锂/新能源",
    "硅片": "锂/新能源",
    "HJT": "锂/新能源",
    "TOPCon": "锂/新能源",
    "钙钛矿": "锂/新能源",
    "锂电正极": "锂/新能源",
    "新能源": "锂/新能源",
    "光伏": "锂/新能源",
    "储能": "锂/新能源",
    "新能源车": "锂/新能源",
    "新能源ETF": "锂/新能源",
    "钴": "锂/新能源",
    "镍": "锂/新能源",
    "有色": "锂/新能源",  # 锂/镍/钴等同属有色金属，合并到锂/新能源
    "风电": "锂/新能源",
    "核电": "锂/新能源",
    "氢能": "锂/新能源",
    # ── 半导体生态 ─────────────────────────────────
    "半导体": "半导体",
    "PCB": "半导体",
    "封测": "半导体",
    "IC设计": "半导体",
    "晶圆代工": "半导体",
    "光刻机": "半导体",
    "EDA": "半导体",
    "设备": "半导体",
    "材料": "半导体",
    # ── 医药生态 ─────────────────────────────────
    "医药": "医药",
    "创新药": "医药",
    "CRO": "医药",
    "CMO": "医药",
    "CDMO": "医药",
    "医疗器械": "医药",
    "仿制药": "医药",
    "中药": "医药",
    "生物制品": "医药",
    "原料药": "医药",
    # ── 消费生态 ─────────────────────────────────
    "白酒": "消费",
    "食品饮料": "消费",
    "家电": "消费",
    "美妆": "消费",
    "零售": "消费",
    "餐饮": "消费",
    "免税": "消费",
    "医美": "消费",
    "纺织服装": "消费",
    "宠物": "消费",
    # ── 金融生态 ─────────────────────────────────
    "银行": "金融",
    "证券": "金融",
    "保险": "金融",
    "信托": "金融",
    "金融科技": "金融",
    "租赁": "金融",
    "AMC": "金融",
    # ── 资源/周期生态 ─────────────────────────────
    "钢铁": "资源/周期",
    "煤炭": "资源/周期",
    "化工": "资源/周期",
    "建材": "资源/周期",
    "石油": "资源/周期",
    "黄金": "资源/周期",
    "稀土": "资源/周期",
    "铝": "资源/周期",
    "铜": "资源/周期",
    # ── 工业/制造 ─────────────────────────────────
    "海缆": "通信",
    "机器人": "汽零/工业",  # robot → 汽零工业大类
    "机械": "汽零/工业",
    "军工": "军工",
}


def _file_mtime(path: Path) -> str:
    """返回文件 mtime 的 ISO 字符串（健康检查报告用）。"""
    try:
        from datetime import datetime

        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, FileNotFoundError):
        return ""


def _read_regime_state() -> dict:
    """读取 scripts/data/regime_state.json，返回 (regime, updated_at, age_minutes)。

    regime_state.json 实际是权重快照，regime 字段可能不存在；
    age_minutes 用于在 health_report 中判断数据是否过期（> 1h 提示 /market full）。
    """
    from datetime import timezone
    from pathlib import Path

    # scripts/portfolio/manager.py → scripts/
    path = Path(__file__).resolve().parent.parent / "data" / "regime_state.json"
    result: dict[str, Any] = {"regime": None, "updated_at": "", "age_minutes": None}
    try:
        if not path.exists():
            return result
        data = json.loads(path.read_text(encoding="utf-8"))
        updated = data.get("updated", "")
        result["updated_at"] = updated
        if updated:
            # 解析 ISO 时间，计算距今分钟数
            try:
                ts = datetime.fromisoformat(updated)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                result["age_minutes"] = int((now - ts).total_seconds() / 60)
            except ValueError:
                pass
    except (OSError, json.JSONDecodeError):
        pass
    return result


def _fetch_technical_features(positions: list, quotes_map: dict, kline_datalen: int = 60) -> dict:
    """批量调用 technical.py 拉取持仓技术特征（H1 集成）。

    返回 {code: {breakdown: bool, stop_loss_pct: float, support: float}}。
    单只失败不中断整体（按 code 容错）。
    拉取失败时该 code 不会被加入返回 dict（调用方按 absence 视为"无技术信号"）。
    """
    # scripts/technical.py 是顶层模块，scripts/technical/ 是同名包。
    # Python "包优先于同名模块"，直接 import 会拿到包。必须用 importlib
    # 显式加载 scripts/technical.py 顶层文件才能拿到 TechnicalInput / _compute_all。
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "portfolio_technical_top",
        Path(__file__).resolve().parent.parent / "technical.py",
    )
    assert spec is not None and spec.loader is not None
    tech_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tech_mod)
    TechnicalInput = tech_mod.TechnicalInput
    _compute_all = tech_mod._compute_all

    result: dict = {}
    for p in positions:
        code = p.get("code", "")
        if not code:
            continue
        try:
            from data import get_kline

            bars = get_kline(code, 240, kline_datalen, use_cache=True)
            if not bars or len(bars) < 20:
                continue
            closes = [b["close"] for b in bars]
            opens = [b["open"] for b in bars]
            highs = [b["high"] for b in bars]
            lows = [b["low"] for b in bars]
            volumes = [b["volume"] for b in bars]
            quote = quotes_map.get(code, {})
            inp = TechnicalInput(
                closes=closes,
                opens=opens,
                highs=highs,
                lows=lows,
                volumes=volumes,
                records=bars,
                board="",
                quote=quote,
                args=None,
            )
            features = _compute_all(inp)
            # 与 technical.py:330-338 一致：stop_loss_pct<0 意味着破位
            stop_loss_pct = features.get("stop_loss_pct", 0) or 0
            sr = features.get("support_resistance", {}) or {}
            nearest_support = sr.get("nearest_support")
            result[code] = {
                "breakdown": features.get("breakdown", False),
                "stop_loss_pct": stop_loss_pct,
                "nearest_support": nearest_support,
            }
        except Exception:
            # 拉取/计算失败按"无信号"处理，不抛错
            continue
    return result


def health_report(
    manager,
    quotes: Optional[dict] = None,
    breakdown_threshold: float = BREAKDOWN_THRESHOLD,
    top3_limit: float = 0.50,
    top5_limit: float = 0.70,
    industry_limit: float = 0.30,
    single_stock_limit: float = 0.20,
    technical_features: Optional[dict] = None,
    auto_technical: bool = True,
    watch_buy_gap_pct: float = 5.0,
    watch_sell_gap_pct: float = 3.0,
) -> dict:
    """标准化持仓健康检查报告（按 SKILL.md 模板结构）。

    输出结构化 dict，便于 SKILL 渲染与脚本抓取：
        {
            "as_of": "2026-08-07 10:30",         # 行情快照/调用时间（自动兜底）
            "data_mtime": "2026-08-06 16:15",    # 持仓文件 mtime
            "regime": {regime, updated_at, age_minutes},  # 真实市场 regime
            "regime_hint": "...",                # 动态生成（基于 age_minutes）
            "screener_hint": "...",              # 动态生成（基于真实 industry 最大值）
            "position_ratio": {total_assets, position_cost, position_mv,
                               position_ratio, position_ratio_mv, warning},  # 实际总仓位
            "type": "实盘/示例/虚拟",             # 三态
            "totals": {cost, value, pnl, pnl_pct}, # 行情缺失时 pnl_pct=None
            "positions": [...],   # 每只含 breakdown + breakdown_reason
            "watchlist": [...],   # 含 status 字段（5 档分级）
            "breakdown_positions": [...],   # 已破位独立汇总
            "concentration": {single, top3, top5, industry, warnings},
            "warnings": [...],  # 集中度超阈值 + 破位警告
            "risk_rating": "自然语言摘要",        # 不直接拼接 warnings
            "thresholds": {top3, top5, industry, single, breakdown},
        }

    Args:
        quotes: 实时行情 dict，键为代码（用 get_quotes 拉的 Quote.to_dict()）。
                传 None 或 {} 时进入降级模式（pnl_pct=None + 风险评级标注"行情缺失"）。
        breakdown_threshold: 破位判定阈值（默认 0.95 = 成本 -5%）。
        *_limit: 集中度阈值（默认与 experts/risk_manager.md §四 一致）。
        technical_features: 显式传入的 {code: features}，覆盖 auto_technical
                （用于测试或缓存复用）。
        auto_technical: True（默认）自动调 technical.py 拉 60 根日 K 计算
                features.breakdown（SKILL.md:306-307 要求的权威信号）。
                失败按"无信号"容错，单只异常不影响其他。
        watch_buy_gap_pct: 距目标买点 < 此值 = "接近买点"或"到达买点"（默认 5%）。
        watch_sell_gap_pct: 距目标卖点 < 此值 = "接近止损"或"已破止损"（默认 3%）。
    """
    positions = manager.get_positions()
    watchlist = manager.get_watchlist()
    quotes_map = quotes or {}
    # 行情缺失判定：无报价 dict，或任一持仓 code 无对应报价（部分缺失）
    # 原实现仅判 dict 非空，缺行情持仓按 0 市值计入 totals 造成失真
    quotes_missing = not quotes_map or any(p.get("code", "") not in quotes_map for p in positions)
    # H1 集成：自动调 technical.py 拉 features.breakdown
    # auto_technical=True（默认）时，对每只持仓调 technical 拉 60 根日 K
    # 算 nearest_support + breakdown；失败按 absence 容错
    if auto_technical and not technical_features and positions:
        tech_map = _fetch_technical_features(positions, quotes_map)
    else:
        tech_map = technical_features or {}

    # 总成本/市值/盈亏
    total_cost = 0.0
    total_value = 0.0
    breakdown_positions = []
    position_rows = []

    for p in positions:
        code = p.get("code", "")
        name = p.get("name", code)
        cost = float(p.get("cost", 0) or 0)
        qty = int(p.get("quantity", 0) or 0)
        q = quotes_map.get(code, {})
        price = float(q.get("price", 0) or 0) if q else 0.0
        change_pct = float(q.get("change_pct", 0) or 0) if q else 0.0

        cost_value = cost * qty
        mv = price * qty
        pnl = mv - cost_value
        # L17 降级处理：行情缺失时 pnl_pct = None
        # cost=0（未知成本价）时 pnl/pnl_pct 均置 None（guardrail：不计算虚假盈亏）
        pnl_pct = (
            (pnl / cost_value * 100)
            if (cost_value and price > 0)
            else (None if (cost_value and not q) else (None if (cost_value == 0 or price == 0) else 0.0))
        )

        total_cost += cost_value
        total_value += mv

        # H1 破位判定：成本阈值 OR technical.breakdown 权威信号
        cost_breakdown = bool(cost > 0 and price > 0 and price < cost * breakdown_threshold)
        tech_breakdown = bool(tech_map.get(code, {}).get("breakdown", False) if code in tech_map else False)
        breakdown = cost_breakdown or tech_breakdown
        if cost_breakdown and tech_breakdown:
            breakdown_reason = "both"
        elif cost_breakdown:
            breakdown_reason = "cost_5pct"
        elif tech_breakdown:
            breakdown_reason = "support_break"
        else:
            breakdown_reason = ""

        row = {
            "code": code,
            "name": name,
            "tags": p.get("tags", []),
            "price": round(price, 2),
            "cost": round(cost, 2),
            "qty": qty,
            "change_pct": round(change_pct, 2),
            "pnl": round(pnl, 0) if (price > 0 and cost_value > 0) else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "market_value": round(mv, 0) if price > 0 else None,
            "breakdown": breakdown,
            "breakdown_reason": breakdown_reason,
        }
        position_rows.append(row)
        if breakdown:
            breakdown_positions.append(row)

    # L17 行情缺失时 total_pnl_pct = None
    if total_cost and total_value > 0:
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_pnl else 0.0
    else:
        total_pnl = -total_cost if total_cost else 0.0
        total_pnl_pct = None

    # M7 自选股 5 档状态分级
    watch_rows = []
    for w in watchlist:
        code = w.get("code", "")
        name = w.get("name", code)
        q = quotes_map.get(code, {})
        price = float(q.get("price", 0) or 0) if q else 0.0
        tb = float(w.get("target_buy", 0) or 0)
        ts = float(w.get("target_sell", 0) or 0)
        gap_to_buy = round((price - tb) / tb * 100, 2) if tb else None
        gap_to_sell = round((price - ts) / ts * 100, 2) if ts else None
        # 舍入边界：比较用原始值，展示用舍入值（5.004% 舍入 5.0 不应误判"接近"）
        raw_gap_to_buy = (price - tb) / tb * 100 if tb else None
        raw_gap_to_sell = (price - ts) / ts * 100 if ts else None

        # 5 档分级（与 SKILL.md:243-250 模板一致）
        if ts and price > 0 and price <= ts:
            status = "已破止损"
        elif ts and raw_gap_to_sell is not None and 0 < raw_gap_to_sell <= watch_sell_gap_pct:
            status = "接近止损"
        elif tb and price > 0 and price <= tb:
            status = "到达买点"
        elif tb and raw_gap_to_buy is not None and 0 < raw_gap_to_buy <= watch_buy_gap_pct:
            status = "接近买点"
        else:
            status = "观望"

        watch_rows.append(
            {
                "code": code,
                "name": name,
                "price": round(price, 2),
                "target_buy": tb,
                "target_sell": ts,
                "gap_to_buy_pct": gap_to_buy,
                "gap_to_sell_pct": gap_to_sell,
                "status": status,
            }
        )

    # 集中度（复用 check_concentration 的合并映射逻辑）
    # check_concentration 接受 code -> price 映射，需要从 quote_dict 提取
    price_map = {code: q.get("price", 0) for code, q in quotes_map.items() if code != "__as_of__"}
    concentration = manager.check_concentration(
        quotes=price_map,
        top3_limit=top3_limit,
        industry_limit=industry_limit,
        single_stock_limit=single_stock_limit,
    )

    # M3 真实 regime 读取
    regime_info = _read_regime_state()
    regime_age = regime_info.get("age_minutes")
    if regime_age is None or regime_age > 60:
        regime_hint = (
            f"regime_state.json 数据缺失或过期 {regime_age} 分钟，"
            f"建议先 /market full 拉取最新市场状态（market_anchor 输出更准）"
        )
    else:
        regime_hint = f"regime_state.json 更新于 {regime_age} 分钟前，" f"建议先 /market full 拉取最新市场状态"

    # M4 动态 screener_hint：基于真实 industry 最大值
    industry_dist = concentration.get("details", {}).get("industry", {})
    if industry_dist:
        top_industry = max(industry_dist.items(), key=lambda x: x[1])
        ind_name, ind_pct = top_industry
        if ind_pct > industry_limit * 100:
            # 找对应行业大类推荐的 screener 策略
            strategy_map = {
                "锂/新能源": "value",
                "半导体": "growth",
                "医药": "quality",
                "消费": "dividend",
                "金融": "value",
                "资源/周期": "mean_reversion",
                "通信": "growth",
                "煤化工": "value",
            }
            strategy = strategy_map.get(ind_name, "quality_value")
            screener_hint = (
                f"⚠️ {ind_name} 占比 {ind_pct:.1f}% > {int(industry_limit*100)}%，"
                f"建议 /screener --strategy {strategy} 筛低相关防御板块，"
                f"再叠加 /market 强弱板块确认"
            )
        else:
            screener_hint = (
                f"组合行业分布合理（最大 {ind_name} {ind_pct:.1f}% ≤ " f"{int(industry_limit*100)}%），无需强制调仓"
            )
    else:
        screener_hint = "暂无持仓数据，screener 联动待定"

    # M8 risk_rating 改自然语言摘要
    warnings = list(concentration.get("warnings", []))
    if breakdown_positions:
        warnings.insert(
            0,
            f"⚠️ {len(breakdown_positions)} 只标的破位：" f"{', '.join(r['name'] for r in breakdown_positions)}",
        )
    if not warnings:
        risk_rating = "组合处于安全区间"
    else:
        # 摘要句：取最重要 2 条 + 破位 + 集中度超限 各保留 1 条
        breakdown_warning = next((w for w in warnings if "破位" in w), "")
        conc_warnings = [w for w in warnings if "破位" not in w]
        top_conc = conc_warnings[0] if conc_warnings else ""
        parts = []
        if breakdown_warning:
            parts.append(breakdown_warning)
        if top_conc:
            parts.append(top_conc)
        if len(conc_warnings) > 1:
            parts.append(f"等 {len(conc_warnings)} 项集中度超阈值")
        risk_rating = "；".join(parts) if parts else "组合处于安全区间"

    # L17 行情缺失时降级标注
    if quotes_missing:
        risk_rating = f"⚠️ 行情缺失（仅基于成本口径）| {risk_rating}"

    # L10: as_of 用 datetime.now() 兜底，保证 SKILL 模板的
    # "📊 我的持仓 (YYYY-MM-DD HH:MM)" 时间戳位始终有值。
    # 优先用 quotes_map["__as_of__"] 哨兵键（上游可显式传入行情快照时间），
    # 其次用调用时刻（本地时间），最后用文件 mtime。

    explicit_as_of = quotes_map.get("__as_of__") if quotes_map else None
    if explicit_as_of:
        as_of = explicit_as_of
    else:
        fallback_mtime = _file_mtime(manager._path)
        as_of = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if not fallback_mtime else fallback_mtime

    return {
        "as_of": as_of,
        "data_mtime": _file_mtime(manager._path),
        "regime": regime_info,
        "regime_hint": regime_hint,
        "screener_hint": screener_hint,
        "position_ratio": manager.compute_total_position_ratio(
            {
                code: float(q.get("price", 0) or 0)
                for code, q in quotes_map.items()
                if isinstance(q, dict) and q.get("price")
            }
            if quotes_map
            else None
        ),
        "totals": {
            "cost": round(total_cost, 0),
            "value": round(total_value, 0) if not quotes_missing else None,
            "pnl": round(total_pnl, 0) if not quotes_missing else None,
            "pnl_pct": (round(total_pnl_pct, 2) if total_pnl_pct is not None else None),
        },
        "type": manager.portfolio_type,
        "positions": position_rows,
        "watchlist": watch_rows,
        "breakdown_positions": breakdown_positions,
        "concentration": concentration,
        "warnings": warnings,
        "risk_rating": risk_rating,
        "thresholds": {
            "top3": int(top3_limit * 100),
            "top5": int(top5_limit * 100),
            "industry": int(industry_limit * 100),
            "single": int(single_stock_limit * 100),
            "breakdown": f"成本×{breakdown_threshold:.2f}",
        },
    }


def health_report_markdown(report: dict) -> str:
    """将 health_report() 结构化输出渲染成 SKILL 模板一致的 Markdown。

    对应 skills/portfolio/SKILL.md:223-280 模板：
    - 标题：📊 我的持仓 (as_of)
    - 时间戳双行：as_of + data_mtime
    - 持仓一览表格
    - 自选股表格
    - 集中度
    - 风险评级
    - 破位独立汇总
    - 数据护栏条 + 免责声明
    """
    lines: list[str] = []

    # 标题 + 双时间戳
    type_label = report.get("type", "持仓")
    as_of = report.get("as_of", "")
    data_mtime = report.get("data_mtime", "")
    lines.append(f"## 📊 我的{type_label}（{as_of}）")
    if data_mtime and data_mtime != as_of:
        lines.append(f"_持仓快照截至 {data_mtime}_")
    lines.append("")

    # 集中度 + 风险评级（顶部）
    conc = report.get("concentration", {}).get("details", {})
    industry = conc.get("industry", {})
    industry_str = " ".join(f"{k} {v:.1f}%" for k, v in sorted(industry.items(), key=lambda x: -x[1]))
    if industry_str:
        lines.append(f"**板块分布**: {industry_str}")
    thresholds = report.get("thresholds", {})
    if thresholds:
        lines.append(
            f"（集中度阈值：前3大 ≤ {thresholds.get('top3', 50)}% / "
            f"前5大 ≤ {thresholds.get('top5', 70)}% / "
            f"单一行业 ≤ {thresholds.get('industry', 30)}% / "
            f"单标的 ≤ {thresholds.get('single', 20)}%；"
            f"破位={thresholds.get('breakdown', '成本×0.95')}）"
        )
    risk_rating = report.get("risk_rating", "")
    if risk_rating:
        lines.append(f"**风险评级**: {risk_rating}")
    lines.append("")

    # 总成本/市值/盈亏
    totals = report.get("totals", {})
    if totals.get("pnl_pct") is not None:
        lines.append(
            f"总成本 {totals.get('cost') or 0:,.0f} | "
            f"总市值 {totals.get('value') or 0:,.0f} | "
            f"总盈亏 {totals.get('pnl') or 0:+,.0f} "
            f"({totals.get('pnl_pct') or 0:+.2f}%)"
        )
    else:
        # 行情缺失
        lines.append(f"总成本 {totals.get('cost', 0):,.0f} | " f"总市值 ⚠️ 行情缺失 | 总盈亏 ⚠️ 行情缺失")
    lines.append("")

    # 破位独立汇总（如果存在）
    breakdown = report.get("breakdown_positions", [])
    if breakdown:
        lines.append(f"### ⚠️ 已破位标的（{len(breakdown)} 只）")
        lines.append("")
        lines.append("| 股票 | 代码 | 现价 | 盈亏% | 破位原因 |")
        lines.append("|---|---|---|---|---|")
        for r in breakdown:
            lines.append(
                f"| {r['name']} | {r['code']} | {r['price']} | "
                f"{r['pnl_pct']:+.2f}% | {r.get('breakdown_reason', '')} |"
            )
        lines.append("")

    # 持仓一览
    positions = report.get("positions", [])
    if positions:
        lines.append("### 持仓一览")
        lines.append("")
        lines.append("| 股票 | 现价 | 今日% | 盈亏% | 状态 |")
        lines.append("|---|---|---|---|---|")
        for r in positions:
            status = "⚠️ 破位" if r.get("breakdown") else "🟢 健康"
            pnl_pct_str = f"{r['pnl_pct']:+.2f}%" if r.get("pnl_pct") is not None else "N/A"
            change_str = f"{r.get('change_pct', 0):+.2f}%" if r.get("change_pct") is not None else "N/A"
            lines.append(f"| {r['name']} | {r['price']} | {change_str} | " f"{pnl_pct_str} | {status} |")
        lines.append("")

    # 自选股
    watchlist = report.get("watchlist", [])
    if watchlist:
        lines.append("### 自选股")
        lines.append("")
        lines.append("| 股票 | 现价 | 距买点 | 距卖点 | 状态 |")
        lines.append("|---|---|---|---|---|")
        status_emoji = {
            "已破止损": "🔴",
            "接近止损": "🟡",
            "到达买点": "🟢",
            "接近买点": "🟡",
            "观望": "⚪",
        }
        for w in watchlist:
            gb = f"{w['gap_to_buy_pct']:+.1f}%" if w.get("gap_to_buy_pct") is not None else "—"
            gs = f"{w['gap_to_sell_pct']:+.1f}%" if w.get("gap_to_sell_pct") is not None else "—"
            status = w.get("status", "观望")
            emoji = status_emoji.get(status, "⚪")
            lines.append(f"| {w['name']} | {w['price']} | {gb} | {gs} | " f"{emoji} {status} |")
        lines.append("")

    # 操作建议（来自 hints）
    regime_hint = report.get("regime_hint", "")
    screener_hint = report.get("screener_hint", "")
    if regime_hint or screener_hint:
        lines.append("### 上下游联动")
        lines.append("")
        if regime_hint:
            lines.append(f"- 📊 **regime**: {regime_hint}")
        if screener_hint:
            lines.append(f"- 🔍 **screener**: {screener_hint}")
        lines.append("")

    # 数据护栏条
    lines.append("---")
    regime_age = report.get("regime", {}).get("age_minutes")
    regime_str = f"regime_state {regime_age}分钟前" if regime_age is not None else "regime_state 未知"
    lines.append(f"📅 行情 {as_of} | 持仓 {data_mtime or 'N/A'} | {regime_str}")
    lines.append("🔌 数据源：tencent（行情）+ portfolio.json（持仓）")
    lines.append("📜 免责声明：本工具非证券投资咨询业务持牌机构，输出为数据汇总与个人研判参考，不构成投资建议。")

    return "\n".join(lines)


def risk_summary(self, quotes: dict = None, confidence: float = 0.95) -> str:
    """持仓组合 VaR 风险摘要（v1.16.0 thin wrapper → portfolio.analytics.risk_summary）。"""
    from portfolio.analytics import risk_summary as _risk_summary

    return _risk_summary(self, quotes=quotes, confidence=confidence)


def attribution_report(self, quotes: dict = None, period: str = "1M") -> str:
    """组合 Brinson 归因报告（v1.16.0 thin wrapper → portfolio.analytics.attribution_report）。"""
    from portfolio.analytics import attribution_report as _attribution_report

    return _attribution_report(self, quotes=quotes, period=period)


def advisory_rebalance(self, target_ratio: float = 1.0, quotes: dict = None) -> list:
    """调仓建议（v1.16.0 thin wrapper → portfolio.rebalance.advisory_rebalance）。"""
    from portfolio.rebalance import advisory_rebalance as _advisory_rebalance

    return _advisory_rebalance(self, target_ratio=target_ratio, quotes=quotes)

    # ---------- 导入导出 ----------


def export_codes(self) -> list:
    """导出所有持仓代码列表（兼容旧接口）。"""
    return [p["code"] for p in manager.get_positions()]


def check_concentration(
    manager,
    single_stock_limit: float = 0.20,
    top3_limit: float = 0.50,
    top5_limit: float = 0.70,
    industry_limit: float = 0.30,
    quotes: dict = None,
) -> dict:
    """检查持仓集中度。

    Args:
        single_stock_limit: 单一标的上限（默认 20%）
        top3_limit: 前 3 大持仓上限（默认 50%）
        top5_limit: 前 5 大持仓上限（默认 70%）
        industry_limit: 单一行业上限（默认 30%）
        quotes: 可选 {code: current_price} 行情映射。提供时按市值（现价×数量）
            计算集中度，否则回退到成本口径。

    Returns:
        {"warnings": [str], "details": {"single": {...}, "top3": {...}, "top5": {...}, "industry": {...}}}
    """
    positions = manager.get_positions()
    if not positions:
        return {"warnings": [], "details": {}}

    def _value(p) -> float:
        # 优先用市值（现价×数量），无行情时回退成本口径
        if quotes and p["code"] in quotes:
            price = quotes[p["code"]] or 0
            return price * p.get("quantity", 0)
        return p.get("cost", 0) * p.get("quantity", 0)

    total_value = sum(_value(p) for p in positions)
    if total_value <= 0:
        return {"warnings": [], "details": {}}

    warnings = []
    details = {}

    # 单一标的集中度
    stock_pcts = []
    for p in positions:
        value = _value(p)
        pct = value / total_value
        stock_pcts.append({"code": p["code"], "name": p.get("name", ""), "pct": pct})
    stock_pcts.sort(key=lambda x: x["pct"], reverse=True)

    if stock_pcts:
        top1 = stock_pcts[0]
        details["single"] = {
            "code": top1["code"],
            "pct": round(top1["pct"] * 100, 1),
        }
        if top1["pct"] > single_stock_limit:
            warnings.append(
                f"单一标的集中度 {top1['pct']*100:.1f}% > {single_stock_limit*100:.0f}%"
                f"（{top1['name'] or top1['code']}）"
            )

    # 前 3 大持仓集中度
    top3_value = sum(s["pct"] for s in stock_pcts[:3])
    details["top3"] = {"pct": round(top3_value * 100, 1)}
    if top3_value > top3_limit:
        warnings.append(f"前3大持仓集中度 {top3_value*100:.1f}% > {top3_limit*100:.0f}%")

    # 前 5 大持仓集中度（SKILL.md guardrail：前5大 ≤ 70%）
    top5_value = sum(s["pct"] for s in stock_pcts[:5])
    details["top5"] = {"pct": round(top5_value * 100, 1)}
    if top5_value > top5_limit:
        warnings.append(f"前5大持仓集中度 {top5_value*100:.1f}% > {top5_limit*100:.0f}%")

    # 行业集中度
    industry_values = {}
    for p in positions:
        # 从 tags 中提取行业标签：先过滤状态类标签，
        # 再尝试合并到行业大类（如"锂电/锂矿/锂业" → "锂/新能源"）。
        tags = p.get("tags", [])
        industry_tags = [t for t in tags if t not in manager._STATUS_TAGS]
        if industry_tags:
            raw = industry_tags[0]
            industry = manager._INDUSTRY_GROUP.get(raw, raw)
        elif tags:
            industry = tags[0]  # 全部是状态标签时的兜底
        else:
            industry = "未分类"
        value = _value(p)
        industry_values[industry] = industry_values.get(industry, 0) + value

    industry_pcts = {k: v / total_value for k, v in industry_values.items()}
    details["industry"] = {k: round(v * 100, 1) for k, v in industry_pcts.items()}

    for ind, pct in industry_pcts.items():
        if pct > industry_limit:
            warnings.append(f"行业集中度 {ind}: {pct*100:.1f}% > {industry_limit*100:.0f}%")

    return {"warnings": warnings, "details": details}

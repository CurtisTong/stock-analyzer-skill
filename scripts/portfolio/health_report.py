"""持仓组合纯工具（从 manager.py 拆分）。

health_report / health_report_markdown / check_concentration 下沉到此模块，
供 PortfolioManager 与 Web 层共用，manager 保留同名方法作为 thin wrapper。
"""

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from common.exceptions.silent_fallback import log_silent_fallback

logger = logging.getLogger(__name__)

BREAKDOWN_THRESHOLD = 0.95

# 持仓止损参考线（展示口径，仅用于标注，不生成仓位建议；操盘口径见 experts/risk_manager.md）
POSITION_STOP_LOSS_REF_PCT = -8.0


def _limit_pct_for(code: str, name: str = "") -> float:
    """返回该标的当日涨跌停幅度（%）。

    A 股制度：主板 ±10%、创业板/科创板 ±20%、北交所 ±30%、ST ±5%。
    仅用于"当日是否可能无法成交"的粗判，不替代交易所数据；判不准时按主板处理。
    """
    if "ST" in (name or "").upper():
        return 4.8
    bare = code.lower()
    for prefix in ("sh", "sz", "bj"):
        if bare.startswith(prefix):
            bare = bare[2:]
            break
    if code.lower().startswith("bj") or bare.startswith(("8", "4", "920")):
        return 29.8
    if bare.startswith(("30", "68")):
        return 19.8
    return 9.8


def _tradeable_hint(code: str, name: str, quote: dict) -> str:
    """触发价当日是否可能无法成交（涨跌停 / 一字板 / 停牌）。

    只依据调用方给的行情字段推断，缺字段不臆测；返回空字符串表示无异常证据。
    """
    try:
        price = float(quote.get("price", 0) or 0)
    except (TypeError, ValueError):
        return ""
    if price <= 0:
        return "当日可能无法成交（无报价，可能停牌）"
    change = quote.get("change_pct")
    if change is None:
        return ""
    try:
        change = float(change)
    except (TypeError, ValueError):
        return ""
    if abs(change) < _limit_pct_for(code, name) - 0.2:
        return ""
    high, low = quote.get("high"), quote.get("low")
    try:
        if high is not None and low is not None and float(high) == float(low):
            return "当日可能无法成交（一字板）"
    except (TypeError, ValueError):
        pass
    return "当日可能无法成交（涨跌停）"

# 状态类标签白名单：tags[0] 是这类时不当作行业，避免
# 宝丰能源 tags=["T+1待交收","煤化工","能源"] 被错误归类
# 状态标签/行业大类映射以 manager._STATUS_TAGS / manager._INDUSTRY_GROUP 为唯一事实源
# （本文件曾复制一份但从未被引用，2026-11-02 审查清除）


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


def _fetch_protections(positions: list, initial_capital: float | None, position_pnl_pct: float | None = None) -> dict:
    """计算组合保护机制三件套（回撤熔断/连亏熔断/冷却期）。

    v1.24.0 落地了 guardrails 模块但从未接入任何生产路径——用户在
    /portfolio 看不到任何保护提示。此处接入 health_report：
    交易日志缺失时返回空 dict（无历史 ≠ 安全，只是无数据）。

    Args:
        positions: 当前持仓（用于冷却期代码检查）
        initial_capital: 账户初始资金（回撤按权益口径计算时需要）
        position_pnl_pct: 当前持仓整体盈亏%（并入权益曲线，避免持仓浮亏时回撤看不到亏损）

    Returns:
        guardrails.check_protections 的输出；无交易记录时返回 {}
    """
    try:
        from portfolio.guardrails import check_protections
        from portfolio.trade_log import TradeLog

        trades = TradeLog().query()
        if not trades:
            return {}
        cooldown_codes = [p.get("code", "") for p in positions if p.get("code")]
        # 注意：这里只读。熔断状态的写入点在 crud._record_trade_log（清仓落账），
        # 报告生成器不得有写副作用（实测会污染状态文件并造成跨测试污染）。
        return check_protections(
            trades,
            position_pnl_pct=position_pnl_pct,
            cooldown_codes=cooldown_codes,
            initial_capital=initial_capital or None,
        )
    except Exception as e:  # 保护机制是附加信息，失败不应影响健康报告主体
        log_silent_fallback("health_report._fetch_protections", e)
        logger.debug("保护机制检查失败: %s", e)
        return {}


def _account_initial_capital(manager) -> tuple[Optional[float], str]:
    """取账户初始资金（review P2 回撤口径）。

    统一用落盘的 ``manager._data['total_assets']``，不再把"当前持仓成本"
    当初始资金（两者口径不一致会产生 969% 假回撤）。缺失/非法时返回
    (None, "missing")，由调用方显式标注降级，而不是无声退化。
    """
    data = getattr(manager, "_data", None) or {}
    try:
        value = data.get("total_assets")
        number = float(value)
        if math.isfinite(number) and number > 0:
            return number, "total_assets"
    except (TypeError, ValueError, OverflowError, AttributeError):
        pass
    return None, "missing"


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
        except Exception as exc:
            log_silent_fallback("health_report._fetch_technical_features", exc)
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
            "positions": [...],   # 每只含 breakdown + breakdown_reason + stop_loss_ref_pct（-8% 展示参考）
            "watchlist": [...],   # 含 status / range_valid / tradeable_hint（未持仓不判"已破止损"）
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
        watch_buy_gap_pct: 距目标买点 < 此值 = "接近买点"（默认 5%）。
        watch_sell_gap_pct: 距目标卖点 < 此值 = "接近目标卖出价"（默认 3%）。

    自选股状态口径（未持仓标的没有成本价，一律不判"已破止损"）：
        price <= target_buy                  → "到达买点（需技术确认）"（触发只是必要条件）
        target_buy < price < target_sell      → "区间内观察"
        price >= target_sell                 → "到达目标卖出价"
        target_sell <= target_buy            → "价位设置异常"（显式标注，不猜结论）
    触发价可能不可成交时，行内 tradeable_hint 标注涨跌停/一字板/停牌。
    """
    positions = manager.get_positions()
    watchlist = manager.get_watchlist()
    quotes_map = quotes or {}
    # 行情缺失判定：无报价 dict、缺 code，或报价存在但 price<=0（review P2）。
    # 原实现只按"code 是否在 quotes_map"判断，price=0 时把全部成本记成真实
    # 亏损（pnl=-总成本），风险评级与盈亏全部失真。
    # 缺报价分两档：整批缺失（failed）vs 部分标的缺失（degraded，市值/盈亏仍必须 None）
    def _quote_price(code: str) -> float:
        q = quotes_map.get(code, {})
        try:
            price = float(q.get("price", 0) or 0) if isinstance(q, dict) else 0.0
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return price if math.isfinite(price) else 0.0

    missing_quote_codes = [
        code
        for p in positions
        if (code := p.get("code", "")) and (code not in quotes_map or _quote_price(code) <= 0)
    ]
    quotes_all_missing = not quotes_map or (bool(positions) and len(missing_quote_codes) == len(positions))
    quotes_missing = quotes_all_missing or bool(missing_quote_codes)
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
        # review P1-26：非有限报价按缺失处理，禁止 NaN 流进 JSON/盈亏
        if not math.isfinite(price):
            price = 0.0
        if not math.isfinite(change_pct):
            change_pct = 0.0

        # review P2：price<=0 / 非有限价一律视为无有效报价——pnl/pnl_pct 置 None，
        # 不把成本当成"真实亏损"。cost=0（未知成本价）同理不计算虚假盈亏。
        valid_price = price > 0 and math.isfinite(price)
        cost_value = cost * qty
        mv = price * qty if valid_price else 0.0
        pnl = (mv - cost_value) if valid_price else None
        pnl_pct = (pnl / cost_value * 100) if (valid_price and cost_value) else None

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
            "pnl": round(pnl, 0) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "market_value": round(mv, 0) if valid_price else None,
            "breakdown": breakdown,
            "breakdown_reason": breakdown_reason,
            "stop_loss_ref_pct": POSITION_STOP_LOSS_REF_PCT,
        }
        position_rows.append(row)
        if breakdown:
            breakdown_positions.append(row)

    # L17 行情缺失时 total_pnl_pct = None
    # review P2：price<=0 已计入 missing_quote_codes——此时不得把总成本
    # 记成"真实亏损"（pnl=-总成本），totals 统一输出 None（降级口径）。
    if quotes_missing:
        total_pnl = 0.0
        total_pnl_pct = None
    elif total_cost and total_value > 0:
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_pnl else 0.0
    else:
        total_pnl = -total_cost if total_cost else 0.0
        total_pnl_pct = None

    # 自选股状态分级（未持仓标的，不判"已破止损"）
    # target_sell 是目标卖出价（区间上沿），不是止损价；止损只对有成本价的持仓生效。
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
        # 卖点 ≤ 买点 = 价位设置反了：显式标注，不猜结论
        range_valid = not (tb and ts and ts <= tb)

        if not range_valid:
            status = "价位设置异常"
        elif price <= 0:
            # 有自选但没报价：观望，不臆测能否成交
            status = "观望"
        elif tb and price <= tb:
            # 触发只是必要条件：A 股还需大盘风偏 / 板块强度 / 个股技术确认
            status = "到达买点（需技术确认）"
        elif tb and raw_gap_to_buy is not None and 0 < raw_gap_to_buy <= watch_buy_gap_pct:
            status = "接近买点"
        elif ts and price >= ts:
            status = "到达目标卖出价"
        elif ts and raw_gap_to_sell is not None and -watch_sell_gap_pct <= raw_gap_to_sell < 0:
            status = "接近目标卖出价"
        elif tb or ts:
            status = "区间内观察"
        else:
            status = "观望"

        over_target_sell = round((price - ts) / ts * 100, 2) if (ts and price > ts) else None
        # 可成交性：单只缺报价 = 很可能停牌（要标注）；整批行情缺失属降级，不臆测停牌
        if code in quotes_map:
            tradeable = _tradeable_hint(code, name, q)
        elif quotes_map:
            tradeable = "当日可能无法成交（无报价，可能停牌）"
        else:
            tradeable = ""

        watch_rows.append(
            {
                "code": code,
                "name": name,
                "price": round(price, 2),
                "target_buy": tb,
                "target_sell": ts,
                "gap_to_buy_pct": gap_to_buy,
                "gap_to_sell_pct": gap_to_sell,
                "over_target_sell_pct": over_target_sell,
                "range_valid": range_valid,
                "tradeable_hint": tradeable,
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
            # （值必须来自 screener 的合法策略集：balanced/quality_value/
            #   growth_momentum/defensive/turning_point/ma_volume_momentum，
            #   旧表 value/growth/dividend/mean_reversion 会直接 argparse 报错）
            strategy_map = {
                "锂/新能源": "quality_value",
                "半导体": "growth_momentum",
                "医药": "quality_value",
                "消费": "defensive",
                "金融": "quality_value",
                "资源/周期": "turning_point",
                "通信": "growth_momentum",
                "煤化工": "quality_value",
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

    # 保护机制三件套（回撤熔断/连亏熔断/冷却期）——v1.24.0 落地但未接线，
    # 此处接入：交易日志缺失时静默跳过（无历史不代表安全，只是无数据）。
    # review P2（回撤口径）：初始资金统一取落盘 total_assets，不再用
    # total_cost（持仓成本）——两者口径不一致会算出荒谬的假回撤。
    # total_pnl_pct 为当前持仓浮动盈亏——并入权益曲线，回撤才能反映浮亏。
    initial_capital, capital_source = _account_initial_capital(manager)
    protections = _fetch_protections(positions, initial_capital, total_pnl_pct)
    if protections:
        protections["capital_basis"] = capital_source

    # M8 risk_rating 改自然语言摘要
    warnings = list(concentration.get("warnings", []))
    if breakdown_positions:
        warnings.insert(
            0,
            f"⚠️ {len(breakdown_positions)} 只标的破位：" f"{', '.join(r['name'] for r in breakdown_positions)}",
        )
    if protections and not protections.get("all_clear", True):
        warnings.append(f"🛡️ {protections.get('summary', '保护机制触发')}")
    # review P2：初始资金缺失必须显式标注降级，不能无声用成本口径冒充权益口径
    if protections and capital_source == "missing":
        warnings.append(
            "⚠️ 回撤口径降级：portfolio.json 缺少 total_assets，回撤按累计利润估算（非真实权益回撤）"
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
        # 修复：as_of 是行情快照时间，优先用调用时刻（本地时间）。
        # 原实现 mtime 优先，持仓文件最后修改时间被当作行情时间戳，
        # 用户未改持仓时报告误显示旧日期。文件 mtime 仅作最后兜底。
        as_of = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not as_of:
            as_of = _file_mtime(manager._path)

    report = {
        "as_of": as_of,
        "data_mtime": _file_mtime(manager._path),
        "regime": regime_info,
        "regime_hint": regime_hint,
        "screener_hint": screener_hint,
        "protections": protections,
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

    # P0-4a 数据完整性信封：行情缺失 → 缺失域字段置 None（不许 0 占位），并降结论强度
    from common import data_quality as dq

    return dq.envelope(
        report,
        required=("quote",),
        field_map={"quote": ()},
        conclusion_keys=(),
        failed=("quote",) if quotes_all_missing else (),
        degraded=("quote",) if (missing_quote_codes and not quotes_all_missing) else (),
        row_stats={"quote": (len(missing_quote_codes), len(positions))} if positions else None,
    )


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

    # P0-4a：数据完整性首行固定在任何标题与结论之前
    from common import data_quality as dq

    lines.append(dq.render_header(report.get("data_quality")))
    lines.append("")

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

    # 保护机制三件套（回撤熔断/连亏熔断/冷却期）
    protections = report.get("protections") or {}
    if protections:
        lines.append("### 🛡️ 保护机制")
        lines.append("")
        dd = protections.get("drawdown") or {}
        losses = protections.get("losses") or {}
        if dd.get("message"):
            emoji = "🔴" if dd.get("triggered") else "🟢"
            lines.append(f"- {emoji} 回撤熔断: {dd['message']}")
        if losses.get("message"):
            emoji = "🔴" if losses.get("triggered") else "🟢"
            lines.append(f"- {emoji} 连亏熔断: {losses['message']}")
        for code, c in (protections.get("cooldowns") or {}).items():
            lines.append(f"- 🔴 冷却期: {c.get('message', code)}")
        lines.append("")

    # 破位独立汇总（如果存在）
    breakdown = report.get("breakdown_positions", [])
    if breakdown:
        lines.append(f"### ⚠️ 已破位标的（{len(breakdown)} 只）")
        lines.append("")
        lines.append("| 股票 | 代码 | 现价 | 盈亏% | 破位原因 |")
        lines.append("|---|---|---|---|---|")
        for r in breakdown:
            # review P1-27：技术破位 + 无行情时 pnl_pct=None，
            # 直接 {:+.2f} 会 TypeError 让 /portfolio health 崩溃；
            # 与下方持仓一览（689 行）一致做 None 判断。
            pnl_pct_str = f"{r['pnl_pct']:+.2f}%" if r.get("pnl_pct") is not None else "N/A"
            lines.append(
                f"| {r['name']} | {r['code']} | {r['price']} | "
                f"{pnl_pct_str} | {r.get('breakdown_reason', '')} |"
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
        # 止损参考线只做展示：止损仅对有成本价的持仓生效，本报告不生成仓位建议
        lines.append(f"_止损参考线 {POSITION_STOP_LOSS_REF_PCT:+.0f}%（展示口径，不构成投资建议）_")
        lines.append("")

    # 自选股
    watchlist = report.get("watchlist", [])
    if watchlist:
        lines.append("### 自选股")
        lines.append("")
        lines.append("| 股票 | 现价 | 距买点 | 距卖点 | 状态 |")
        lines.append("|---|---|---|---|---|")
        status_emoji = {
            "到达买点（需技术确认）": "🟢",
            "接近买点": "🟡",
            "区间内观察": "⚪",
            "接近目标卖出价": "🟡",
            "到达目标卖出价": "🟠",
            "价位设置异常": "⚠️",
            "观望": "⚪",
        }
        for w in watchlist:
            gb = f"{w['gap_to_buy_pct']:+.1f}%" if w.get("gap_to_buy_pct") is not None else "—"
            gs = f"{w['gap_to_sell_pct']:+.1f}%" if w.get("gap_to_sell_pct") is not None else "—"
            status = w.get("status", "观望")
            emoji = status_emoji.get(status, "⚪")
            hint = f" ⚠️ {w['tradeable_hint']}" if w.get("tradeable_hint") else ""
            lines.append(f"| {w['name']} | {w['price']} | {gb} | {gs} | " f"{emoji} {status}{hint} |")
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


SUMMARY_MAX_LINES = 40


def health_summary_markdown(report: dict) -> str:
    """单屏摘要（≤ SUMMARY_MAX_LINES 行）：结论 + 需要处理 + 下一步。

    与 health_report_markdown 的全量模板互补：`/portfolio health` 默认走本函数，
    `--full` 才展开持仓表/自选股/保护机制明细。定位上默认入口只回答
    "我的持仓现在有没有问题、我要做什么"，详细数据留给显式展开。
    """
    lines: list[str] = []
    type_label = report.get("type", "持仓")
    as_of = report.get("as_of", "")
    lines.append(f"## 📊 我的{type_label}（{as_of}）")
    lines.append("")

    risk_rating = report.get("risk_rating", "")
    lines.append(f"**结论**: {risk_rating or '—'}")

    totals = report.get("totals", {})
    if totals.get("pnl_pct") is not None:
        lines.append(
            f"**盈亏**: 总成本 {totals.get('cost') or 0:,.0f} | "
            f"总市值 {totals.get('value') or 0:,.0f} | "
            f"{totals.get('pnl') or 0:+,.0f} ({totals.get('pnl_pct') or 0:+.2f}%)"
        )
    else:
        lines.append("**盈亏**: ⚠️ 行情缺失，仅成本口径可用")

    positions = report.get("positions", [])
    changes = [p for p in positions if p.get("change_pct") is not None]
    if changes:
        up = sum(1 for p in changes if p["change_pct"] > 0)
        down = sum(1 for p in changes if p["change_pct"] < 0)
        worst = min(changes, key=lambda p: p["change_pct"])
        drag = f"{worst['name']} {worst['change_pct']:+.2f}%"
        lines.append(f"**今日**: 涨 {up} / 跌 {down}，最大拖累 {drag}")
    lines.append("")

    warnings = report.get("warnings") or []
    lines.append(f"### 需要处理（{len(warnings)}）")
    lines.append("")
    if warnings:
        for w in warnings[:3]:
            lines.append(f"- {w}")
        if len(warnings) > 3:
            lines.append(f"- …另 {len(warnings) - 3} 项，见 `--full`")
    else:
        lines.append("- 无，组合在阈值内")
    lines.append("")

    focus = report.get("breakdown_positions") or positions
    next_hint = "`/portfolio health --full` 看全量明细"
    if focus:
        next_hint += f" · `/stock {focus[0]['code']} quick` 看个股"
    lines.append(f"**下一步**: {next_hint}")
    lines.append("")

    lines.append("---")
    regime_age = report.get("regime", {}).get("age_minutes")
    regime_str = f"regime_state {regime_age}分钟前" if regime_age is not None else "regime_state 未知"
    lines.append(f"📅 行情 {as_of} | 持仓 {report.get('data_mtime') or 'N/A'} | {regime_str}")
    lines.append("📜 免责声明：本工具非证券投资咨询业务持牌机构，输出为数据汇总与个人研判参考，不构成投资建议。")

    return "\n".join(lines)


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

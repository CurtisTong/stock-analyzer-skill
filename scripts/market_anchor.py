#!/usr/bin/env python3
"""
市场环境锚定编排器（v2.5.0 新增）。

聚合大盘状态 + 市场宽度 + 板块 ETF 强度 + 个股 vs 板块 RPS，为 /stock 的
full / debate / technical 三个模式统一提供前置"市场环境锚定"数据。

设计原则：
1. 复用优先：detect_market_state / market_breadth / sector_etf_strength 都已存在，
   不重写，import 调用。
2. 优雅降级：每个数据源独立 try/except，任一失败只影响对应字段，不阻塞主流程。
3. 双输出：JSON（供 LLM/编排器消费）+ Markdown（供终端阅读）。

用法:
  market_anchor.py sh600519                  # 单股全量（Markdown）
  market_anchor.py sh600519 -j               # JSON
  market_anchor.py sh600519 --no-sector      # 跳过板块（technical 模式用）
  market_anchor.py sh600519 -j --no-sector   # 仅大盘 + 宽度（轻量）
"""

import json
import sys
import argparse
import statistics
from pathlib import Path
from datetime import datetime

# 确保 scripts/ 在 import 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import Any  # mypy: Any 用于 run-time 动态 dict

from data import get_quotes, get_kline, get_northbound_flow  # noqa: E402 多源数据层

# 复用：直接 import，不重写
from experts.market_detector import detect_market_state  # noqa: E402
import market_breadth  # noqa: E402  get_market_breadth()
import sector_etf_strength  # noqa: E402  analyze()
from technical.moving_average import ma_system  # noqa: E402
from technical.volatility import compute_atr  # noqa: E402  ATR
from macro_indicators import (
    fetch_all as fetch_macro_all,
)  # noqa: E402  宏观+杠杆+估值桥

# v2.6.0 新增：行业 beta + 组合相关性
from industry_beta import compute_beta, select_index_by_size  # noqa: E402
from portfolio_correlation import compute_full_portfolio_correlation  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# 数据采集：大盘 + 宽度 + 板块
# ═══════════════════════════════════════════════════════════════


def _fetch_index_snapshot(index_code: str = "sh000300") -> dict | None:
    """获取大盘指数实时行情（用于 detect_market_state 的 index_quote 入参）。

    Returns:
        dict 含 price / change_pct / pe_percentile，失败返回 None。
    """
    try:
        quotes = get_quotes([index_code], use_cache=True)
        if not quotes:
            return None
        q = quotes[0]
        if not q or not q.has_basic_data():
            return None
        return {
            "code": q.code,
            "name": q.name,
            "price": q.price,
            "prev_close": getattr(q, "prev_close", None),
            "change_pct": q.change_pct,
            "pe": getattr(q, "pe", None),
            "pe_percentile": 50,  # 缺省中位数
        }
    except Exception as e:
        print(f"[market_anchor] 大盘拉取失败: {e}", file=sys.stderr)
        return None


def _fetch_index_kline(index_code: str = "sh000300", datalen: int = 30) -> dict | None:
    """获取大盘指数日 K 线，用于 detect_market_state 的 kline_data 入参。

    Returns:
        dict 含 closes / ma20 / volumes，失败返回 None。
    """
    try:
        klines = get_kline(index_code, scale=240, datalen=datalen)
        if not klines:
            return None
        closes = [k.close for k in klines]
        volumes = [k.volume for k in klines]
        ma20 = sum(closes[-20:]) / min(len(closes), 20) if closes else 0
        return {
            "closes": closes,
            "volumes": volumes,
            "ma20": round(ma20, 2),
        }
    except Exception as e:
        print(f"[market_anchor] 大盘 K 线拉取失败: {e}", file=sys.stderr)
        return None


def _fetch_breadth() -> dict | None:
    """获取市场宽度（涨跌家数 + 涨跌停家数）。复用 market_breadth.get_market_breadth()。

    Returns:
        dict 含 up_count / down_count / limit_up_count / limit_down_count
            / advance_ratio / new_high_low_ratio 等，失败返回 None。
    """
    try:
        breadth = market_breadth.get_market_breadth()
        # 转换为 detect_market_state 期望的格式
        up = breadth.get("up_count", 0)
        down = breadth.get("down_count", 0)
        total = up + down
        advance_ratio = up / total if total > 0 else 0.5
        return {
            "up_count": up,
            "down_count": down,
            "limit_up_count": breadth.get("limit_up_count", 0),
            "limit_down_count": breadth.get("limit_down_count", 0),
            "up_ratio": breadth.get("up_ratio", 0),
            "advance_ratio": round(advance_ratio, 3),
            "new_high_low_ratio": 1.0,  # 缺省 1.0（detect_market_state 会按中位处理）
            "margin_ratio": 0,  # 缺省 0
        }
    except Exception as e:
        print(f"[market_anchor] 市场宽度拉取失败: {e}", file=sys.stderr)
        return None


# ═══════════════════════════════════════════════════════════════
# v2.5.x 新增维度：多时间框架 / 宏观-估值桥 / 杠杆-反身性 / 流动性+波动率 / 情绪周期
# ═══════════════════════════════════════════════════════════════


def _compute_multi_timeframe(index_code: str = "sh000300") -> dict | None:
    """多时间框架动量（大盘指数）：MA20/60/250 + 5/20 日动量 + ATR14 + vs MA 偏离度。

    复用 technical.moving_average.ma_system() 和 technical.volatility.compute_atr()。

    Returns:
        dict: {ma20, ma60, ma250, ma_alignment, ret_5d_pct, ret_20d_pct,
               atr_14, vs_ma20_pct, vs_ma60_pct, vs_ma250_pct, data_quality}
        任一字段缺失都标记为 None + degraded。
    """
    try:
        # 拉 datalen=250 的日 K（sina fetcher 支持 1024，足够）
        klines = get_kline(index_code, scale=240, datalen=250)
        if not klines:
            return {"data_quality": {"degraded_fields": ["multi_timeframe"]}}

        closes = [k.close for k in klines if k.close > 0]
        highs = [k.high for k in klines if k.high > 0]
        lows = [k.low for k in klines if k.low > 0]

        if len(closes) < 20:
            return {
                "data_quality": {
                    "degraded_fields": ["multi_timeframe.insufficient_data"]
                }
            }

        # 复用 ma_system
        mas = ma_system(closes)
        last = closes[-1]

        # 5 日 / 20 日 动量（涨幅 %）
        ret_5d = (last / closes[-6] - 1) if len(closes) >= 6 else None
        ret_20d = (last / closes[-21] - 1) if len(closes) >= 21 else None

        # 复用 ATR
        atr_14 = compute_atr(highs, lows, closes, period=14)

        # vs 各 MA 偏离度（%）
        def _vs_ma(ma_val):
            if ma_val is None or ma_val == 0:
                return None
            return round((last / ma_val - 1) * 100, 2)

        degraded = []
        for key, val in [
            ("ma20", mas.get("ma20")),
            ("ma60", mas.get("ma60")),
            ("ma250", mas.get("ma250")),
            ("alignment", mas.get("alignment")),
            ("atr_14", atr_14 if atr_14 > 0 else None),
        ]:
            if val is None:
                degraded.append(f"multi_timeframe.{key}")

        # ma_system 对 alignment 是字符串而非数字，独立校验
        if mas.get("alignment") == "数据不足":
            degraded.append("multi_timeframe.alignment")

        return {
            "ma20": mas.get("ma20"),
            "ma60": mas.get("ma60"),
            "ma250": mas.get("ma250"),
            "ma_alignment": mas.get("alignment"),
            "ret_5d_pct": round(ret_5d * 100, 2) if ret_5d is not None else None,
            "ret_20d_pct": round(ret_20d * 100, 2) if ret_20d is not None else None,
            "atr_14": round(atr_14, 2) if atr_14 > 0 else None,
            "vs_ma20_pct": _vs_ma(mas.get("ma20")),
            "vs_ma60_pct": _vs_ma(mas.get("ma60")),
            "vs_ma250_pct": _vs_ma(mas.get("ma250")),
            "data_quality": {"degraded_fields": degraded},
        }
    except Exception as e:
        print(f"[market_anchor] 多时间框架计算失败: {e}", file=sys.stderr)
        return {"data_quality": {"degraded_fields": ["multi_timeframe"]}}


def _fetch_macro_anchor() -> dict | None:
    """宏观 + 杠杆 + 估值桥（透出 macro_indicators.fetch_all）。

    内部对每个 fetch_* 调用独立 try/except（macro_indicators 已做）。

    Returns:
        dict: {macro, leverage, valuation_bridge, data_quality}
    """
    try:
        return fetch_macro_all()
    except Exception as e:
        print(f"[market_anchor] 宏观拉取失败: {e}", file=sys.stderr)
        return {
            "macro": {},
            "leverage": {},
            "valuation_bridge": {},
            "data_quality": {"degraded_fields": ["macro_anchor"]},
        }


def _fetch_liquidity_volatility(
    stock_code: str | None, index_code: str = "sh000300"
) -> dict | None:
    """流动性 + 波动率。

    - 大盘 ATR14 + 60 日年化波动率（复用 detector 公式）
    - 个股 20 日均成交额（亿元）+ 流动性比率（日均成交额/流通市值 %）

    Returns:
        dict: {sh300_atr_14, sh300_annualized_vol_pct,
               stock_avg_amount_20d_yi, stock_liquidity_ratio_pct, data_quality}
    """
    out: dict[str, Any] = {
        "sh300_atr_14": None,
        "sh300_annualized_vol_pct": None,
        "stock_avg_amount_20d_yi": None,
        "stock_liquidity_ratio_pct": None,
        "data_quality": {"degraded_fields": []},
    }
    degraded = []

    # 大盘 ATR + 年化波动率
    try:
        index_klines = get_kline(index_code, scale=240, datalen=60)
        if index_klines and len(index_klines) >= 20:
            sh_closes = [k.close for k in index_klines if k.close > 0]
            sh_highs = [k.high for k in index_klines if k.high > 0]
            sh_lows = [k.low for k in index_klines if k.low > 0]
            sh_atr = compute_atr(sh_highs, sh_lows, sh_closes, period=14)
            if sh_atr > 0:
                out["sh300_atr_14"] = round(sh_atr, 2)
            else:
                degraded.append("liquidity.sh300_atr")

            # 60 日年化波动率（复用 detector.py:53-59 公式）
            returns = []
            for i in range(1, len(sh_closes)):
                if sh_closes[i - 1] > 0:
                    returns.append((sh_closes[i] - sh_closes[i - 1]) / sh_closes[i - 1])
            if len(returns) >= 2:
                daily_std = statistics.stdev(returns)
                annualized_vol = daily_std * (252**0.5) * 100
                out["sh300_annualized_vol_pct"] = round(annualized_vol, 2)
            else:
                degraded.append("liquidity.sh300_vol")
        else:
            degraded.append("liquidity.index_kline")
    except Exception as e:
        print(f"[market_anchor] 大盘波动率计算失败: {e}", file=sys.stderr)
        degraded.append("liquidity.index")

    # 个股 20 日均成交额 + 流动性比率（仅在 stock_code 提供时）
    if stock_code:
        try:
            stock_klines = get_kline(stock_code, scale=240, datalen=20)
            if stock_klines:
                # 优先用 amount（精确），降级到 volume*close/100（估算）
                amounts_yi = [
                    k.amount / 1e8 for k in stock_klines if k.amount and k.amount > 0
                ]
                if amounts_yi:
                    avg_amount = statistics.mean(amounts_yi)
                    source_tag = "amount"
                else:
                    # sina fetcher amount 字段常为 0，用 volume × close 估算
                    # A 股 volume 单位是"手"（100 股），close 是元
                    # amount(元) ≈ volume(手) × 100 × close(元) / 1e8 = 亿元
                    est_amounts = [
                        (k.volume * k.close * 100) / 1e8
                        for k in stock_klines
                        if k.volume > 0 and k.close > 0
                    ]
                    if est_amounts:
                        avg_amount = statistics.mean(est_amounts)
                        source_tag = "volume*close(估算)"
                    else:
                        avg_amount = None
                        source_tag = None

                if avg_amount:
                    out["stock_avg_amount_20d_yi"] = round(avg_amount, 2)
                    out["stock_amount_source"] = source_tag

                    # 流动性比率 = 日均成交额(亿元) / 流通市值(亿元) × 100%
                    stock_quotes = get_quotes([stock_code], use_cache=True)
                    if stock_quotes:
                        q = stock_quotes[0]
                        if q and q.has_basic_data():
                            total_cap_yi = getattr(q, "total_cap", 0) or 0
                            if total_cap_yi > 0 and avg_amount > 0:
                                ratio = (avg_amount / total_cap_yi) * 100
                                out["stock_liquidity_ratio_pct"] = round(ratio, 4)
                            else:
                                degraded.append("liquidity.total_cap")
                        else:
                            degraded.append("liquidity.stock_quote")
                    else:
                        degraded.append("liquidity.stock_quote")
                else:
                    degraded.append("liquidity.stock_amount")
            else:
                degraded.append("liquidity.stock_kline")
        except Exception as e:
            print(f"[market_anchor] 个股流动性计算失败: {e}", file=sys.stderr)
            degraded.append("liquidity.stock")

    out["data_quality"]["degraded_fields"] = degraded
    return out


def _fetch_emotion_phase(breadth: dict | None) -> str | None:
    """情绪周期阶段（透出 market_breadth.get_market_state）。

    Returns:
        str: "主升" | "退潮" | "震荡" | "冰点" | "unknown"
    """
    if not breadth:
        return None
    try:
        result = market_breadth.get_market_state(breadth)
        return result.get("state", "unknown")
    except Exception as e:
        print(f"[market_anchor] 情绪周期判定失败: {e}", file=sys.stderr)
        return None


# ═══════════════════════════════════════════════════════════════
# v2.6.0 新增：行业 beta + 组合相关性
# ═══════════════════════════════════════════════════════════════


def _fetch_industry_beta(stock_code: str | None) -> dict | None:
    """透出 industry_beta.compute_beta + 动态选基准指数。

    动态基准（按流通市值）：
    - > 500 亿   -> sh000300 (沪深 300)
    - > 100 亿   -> sh000905 (中证 500)
    - 否则       -> sh000852 (中证 1000)
    """
    if not stock_code:
        return None
    try:
        index_code = select_index_by_size(stock_code)
        result = compute_beta(stock_code, index_code=index_code, window=60)
        if result is None:
            return {"data_quality": {"degraded_fields": ["industry_beta"]}}
        return {
            **result,
            "index_selection": "dynamic(市值驱动)",
        }
    except Exception as e:
        print(f"[market_anchor] beta 计算失败: {e}", file=sys.stderr)
        return {"data_quality": {"degraded_fields": ["industry_beta"]}}


def _fetch_portfolio_correlation(stock_code: str | None) -> dict | None:
    """透出组合相关性矩阵 + 个股 vs 持仓组合。

    与 /portfolio skill 联动：
    - 持仓为空 -> portfolio_empty=true（不算降级）
    - 持仓非空 -> 输出矩阵 + 高相关对 + 个股 vs 组合
    """
    try:
        return compute_full_portfolio_correlation(stock_code=stock_code, window=60)
    except Exception as e:
        print(f"[market_anchor] 组合相关性失败: {e}", file=sys.stderr)
        return {"data_quality": {"degraded_fields": ["portfolio_correlation"]}}


# ═══════════════════════════════════════════════════════════════
# v2.7.0 新增：北向资金边际定价者 + 题材轮动强度
# ═══════════════════════════════════════════════════════════════


def _fetch_northbound_pricer(days: int = 20) -> dict | None:
    """北向资金边际定价者（N 日累计净流入 + 近 5 日斜率方向）。

    复用 data.get_northbound_flow("", days=N) + briefing.py 算法。
    原始单位万元，统一 /1e4 转亿元。

    Returns:
        dict:
          {
            "days": 20,
            "total_net_yi": 125.3,      # N 日累计净流入（亿元）
            "total_net_sh_yi": 80.5,    # 沪股通
            "total_net_sz_yi": 44.8,    # 深股通
            "latest_day_net_yi": 15.2,  # 最近一日
            "recent_5d_net_yi": 45.6,   # 近 5 日累计
            "recent_5d_slope": "流入",  # 流入/流出/持平
            "direction": "持续流入",    # 综合方向
            "interpretation": "...",
            "data_quality": {"degraded_fields": [...]}
          }
    """
    degraded = []
    try:
        flow_data = get_northbound_flow("", days=days)
        if not flow_data:
            degraded.append("northbound.flow_data")
            return {
                "days": days,
                "total_net_yi": None,
                "total_net_sh_yi": None,
                "total_net_sz_yi": None,
                "latest_day_net_yi": None,
                "recent_5d_net_yi": None,
                "recent_5d_slope": "unknown",
                "direction": "unknown",
                "interpretation": "北向资金数据缺失",
                "data_quality": {"degraded_fields": degraded},
            }

        # 累计净流入（万元 -> 亿元）
        total_net_wan = sum(d.get("net_buy", 0) for d in flow_data)
        total_sh_wan = sum(d.get("sh_net", 0) for d in flow_data)
        total_sz_wan = sum(d.get("sz_net", 0) for d in flow_data)
        total_net_yi = round(total_net_wan / 1e4, 2)
        total_sh_yi = round(total_sh_wan / 1e4, 2)
        total_sz_yi = round(total_sz_wan / 1e4, 2)

        # 最近一日
        latest = flow_data[-1]
        latest_net_yi = round(latest.get("net_buy", 0) / 1e4, 2)

        # 近 5 日累计 + 斜率方向
        recent_5d = flow_data[-5:] if len(flow_data) >= 5 else flow_data
        recent_5d_net_wan = sum(d.get("net_buy", 0) for d in recent_5d)
        recent_5d_net_yi = round(recent_5d_net_wan / 1e4, 2)

        if recent_5d_net_yi > 10:
            recent_5d_slope = "流入"
        elif recent_5d_net_yi < -10:
            recent_5d_slope = "流出"
        else:
            recent_5d_slope = "持平"

        # 综合方向：20 日累计 + 5 日斜率
        if total_net_yi > 0 and recent_5d_slope == "流入":
            direction = "持续流入"
        elif total_net_yi < 0 and recent_5d_slope == "流出":
            direction = "持续流出"
        elif recent_5d_slope in ("流入", "流出"):
            direction = "震荡"  # 长期与短期不一致
        else:
            direction = "震荡"

        interpretation = _interpret_northbound(total_net_yi, recent_5d_slope, direction)

        if len(flow_data) < days:
            degraded.append(f"northbound.insufficient_days({len(flow_data)}/{days})")

        return {
            "days": days,
            "actual_days": len(flow_data),
            "total_net_yi": total_net_yi,
            "total_net_sh_yi": total_sh_yi,
            "total_net_sz_yi": total_sz_yi,
            "latest_day_net_yi": latest_net_yi,
            "recent_5d_net_yi": recent_5d_net_yi,
            "recent_5d_slope": recent_5d_slope,
            "direction": direction,
            "interpretation": interpretation,
            "data_quality": {"degraded_fields": degraded},
        }
    except Exception as e:
        print(f"[market_anchor] 北向资金拉取失败: {e}", file=sys.stderr)
        return {
            "days": days,
            "total_net_yi": None,
            "direction": "unknown",
            "interpretation": f"异常: {type(e).__name__}",
            "data_quality": {"degraded_fields": ["northbound_pricer"]},
        }


def _interpret_northbound(total_yi: float, slope: str, direction: str) -> str:
    """北向资金解读。"""
    if direction == "持续流入":
        return f"北向持续流入（{total_yi:.1f} 亿元），边际定价者看多"
    if direction == "持续流出":
        return f"北向持续流出（{total_yi:.1f} 亿元），边际定价者看空"
    if slope == "流入":
        return f"北向短期回流（{total_yi:.1f} 亿元），关注持续性"
    if slope == "流出":
        return f"北向短期流出（{total_yi:.1f} 亿元），警惕外资减仓"
    return f"北向资金震荡（{total_yi:.1f} 亿元），方向不明"


def _fetch_sector_rotation(window: int = 5) -> dict | None:
    """题材轮动强度（透出 sector_etf_strength.compute_rotation_strength）。"""
    try:
        return sector_etf_strength.compute_rotation_strength(window=window)
    except Exception as e:
        print(f"[market_anchor] 题材轮动计算失败: {e}", file=sys.stderr)
        return {"data_quality": {"degraded_fields": ["sector_rotation"]}}


# ═══════════════════════════════════════════════════════════════
# 顶层编排
# ═══════════════════════════════════════════════════════════════


def analyze(
    stock_code: str | None = None,
    fetch_sector: bool = True,
    index_code: str = "sh000300",
    fetch_portfolio: bool = True,
    fetch_rotation: bool = True,
    fetch_northbound: bool = True,
) -> dict:
    """一次性返回"市场环境锚定"完整数据。

    Args:
        stock_code: 可选。提供时输出 stock_sector_compare + industry_beta + vs_portfolio。
        fetch_sector: 是否拉板块 ETF（technical 模式可关）。
        fetch_portfolio: 是否拉组合相关性（v2.6.0；/portfolio skill 关闭时可关）。
        fetch_rotation: 是否拉题材轮动（v2.7.0）。
        fetch_northbound: 是否拉北向资金（v2.7.0）。
        index_code: 大盘指数代码，默认 sh000300 沪深300。

    Returns:
        dict，含 as_of / regime / index_change_pct / breadth / sector_strength
            / stock_sector_compare / data_quality。
        任一字段缺失都标记为 null 并加入 degraded_fields。
    """
    as_of = datetime.now().isoformat(timespec="seconds")
    degraded = []

    # 1. 大盘指数行情 + K 线
    index_quote = _fetch_index_snapshot(index_code)
    if not index_quote:
        degraded.append("index")
    index_kline = _fetch_index_kline(index_code)
    if not index_kline:
        degraded.append("index_kline")

    # 2. 市场宽度
    breadth = _fetch_breadth()
    if not breadth:
        degraded.append("breadth")

    # 3. 调用 detect_market_state 判定 regime（复用现有逻辑，不重写）
    # 缺数据时 detect_market_state 内部默认返回"防御型"（v2.4.3 fail-safe）
    regime_result = {}
    try:
        regime_result = detect_market_state(
            index_quote=index_quote,
            kline_data=index_kline,
            breadth_data=breadth,
        )
        # 缺数据时强制 confidence=low（不冒泡）
        confidence = "high" if not degraded else "low"
    except Exception as e:
        print(f"[market_anchor] detect_market_state 失败: {e}", file=sys.stderr)
        regime_result = {
            "state": "防御型",
            "long_weight": 0.65,
            "short_weight": 0.35,
            "reason": "数据缺失默认防御型（fail-safe）",
        }
        confidence = "low"
        if "regime" not in degraded:
            degraded.append("regime")

    regime_state = regime_result.get("state", "防御型")
    # 枚举映射到英文 enum（与 schema 一致）
    regime_enum = {
        "牛市": "bull",
        "熊市": "bear",
        "震荡": "sideways",
        "冰点": "panic",
        "亢奋": "euphoria",
        "防御型": "defensive",
    }.get(regime_state, "unknown")

    # 4. 板块 ETF 强度（可选）
    sector_payload = None
    if fetch_sector:
        try:
            sector_payload = sector_etf_strength.analyze(
                stock_code=stock_code,
                fetch_index=False,  # 已在大盘里拉过，避免重复
            )
        except Exception as e:
            print(f"[market_anchor] 板块拉取失败: {e}", file=sys.stderr)
            degraded.append("sector")

    # 5. v2.5.x 新增：多时间框架动量
    multi_tf = _compute_multi_timeframe(index_code)
    if multi_tf and multi_tf.get("data_quality", {}).get("degraded_fields"):
        degraded.extend(multi_tf["data_quality"]["degraded_fields"])

    # 6. v2.5.x 新增：宏观 + 杠杆 + 估值桥
    macro_payload = _fetch_macro_anchor()
    if macro_payload and macro_payload.get("data_quality", {}).get("degraded_fields"):
        degraded.extend(macro_payload["data_quality"]["degraded_fields"])

    # 7. v2.5.x 新增：流动性 + 波动率
    liq_vol = _fetch_liquidity_volatility(stock_code, index_code)
    if liq_vol and liq_vol.get("data_quality", {}).get("degraded_fields"):
        degraded.extend(liq_vol["data_quality"]["degraded_fields"])

    # 8. v2.5.x 新增：情绪周期阶段
    emotion_phase = _fetch_emotion_phase(breadth)
    if not emotion_phase:
        degraded.append("emotion_phase")

    # 9. v2.6.0 新增：行业 beta（动态选基准）
    industry_beta_payload = None
    if stock_code:
        industry_beta_payload = _fetch_industry_beta(stock_code)
        if industry_beta_payload and industry_beta_payload.get("data_quality", {}).get(
            "degraded_fields"
        ):
            degraded.extend(industry_beta_payload["data_quality"]["degraded_fields"])

    # 10. v2.6.0 新增：组合相关性（与 /portfolio skill 联动）
    portfolio_corr_payload = None
    if fetch_portfolio:
        portfolio_corr_payload = _fetch_portfolio_correlation(stock_code)
        if portfolio_corr_payload and portfolio_corr_payload.get(
            "data_quality", {}
        ).get("degraded_fields"):
            degraded.extend(portfolio_corr_payload["data_quality"]["degraded_fields"])

    # 11. v2.7.0 新增：题材轮动强度
    rotation_payload = None
    if fetch_rotation:
        rotation_payload = _fetch_sector_rotation(window=5)
        if rotation_payload and rotation_payload.get("data_quality", {}).get(
            "degraded_fields"
        ):
            degraded.extend(rotation_payload["data_quality"]["degraded_fields"])

    # 12. v2.7.0 新增：北向资金边际定价者
    northbound_payload = None
    if fetch_northbound:
        northbound_payload = _fetch_northbound_pricer(days=20)
        if northbound_payload and northbound_payload.get("data_quality", {}).get(
            "degraded_fields"
        ):
            degraded.extend(northbound_payload["data_quality"]["degraded_fields"])

    # 13. 组装输出
    return {
        "as_of": as_of,
        "regime": regime_enum,
        "regime_label_zh": regime_state,
        "regime_confidence": confidence,
        "regime_reason": regime_result.get("reason", ""),
        "long_weight": regime_result.get("long_weight"),
        "short_weight": regime_result.get("short_weight"),
        "index_code": index_code,
        "index_change_pct": (
            round(index_quote["change_pct"], 2) if index_quote else None
        ),
        "breadth": breadth,
        "sector_strength": (
            {
                "etfs": sector_payload["etfs"] if sector_payload else [],
                "top": sector_payload["strong_sectors"] if sector_payload else [],
                "bottom": sector_payload["weak_sectors"] if sector_payload else [],
                "data_quality": (
                    sector_payload["data_quality"] if sector_payload else None
                ),
            }
            if fetch_sector
            else None
        ),
        "stock_sector_compare": (
            sector_payload["stock_sector_compare"] if sector_payload else None
        ),
        # v2.5.x 新增 5 个字段
        "multi_timeframe": multi_tf,
        "macro": macro_payload.get("macro") if macro_payload else None,
        "leverage": macro_payload.get("leverage") if macro_payload else None,
        "valuation_bridge": (
            macro_payload.get("valuation_bridge") if macro_payload else None
        ),
        "liquidity_volatility": liq_vol,
        "emotion_phase": emotion_phase,
        # v2.6.0 新增 2 个字段
        "industry_beta": industry_beta_payload,
        "portfolio_correlation": portfolio_corr_payload,
        # v2.7.0 新增 2 个字段
        "sector_rotation": rotation_payload,
        "northbound_pricer": northbound_payload,
        "data_quality": {
            "index_ok": index_quote is not None,
            "index_kline_ok": index_kline is not None,
            "breadth_ok": breadth is not None,
            "sector_ok": sector_payload is not None,
            "multi_timeframe_ok": multi_tf is not None
            and not multi_tf.get("data_quality", {}).get("degraded_fields"),
            "macro_ok": macro_payload is not None
            and not macro_payload.get("data_quality", {}).get("degraded_fields"),
            "liquidity_ok": liq_vol is not None
            and not liq_vol.get("data_quality", {}).get("degraded_fields"),
            "emotion_phase_ok": emotion_phase is not None,
            "industry_beta_ok": industry_beta_payload is not None
            and not industry_beta_payload.get("data_quality", {}).get(
                "degraded_fields"
            ),
            "portfolio_correlation_ok": portfolio_corr_payload is not None
            and not portfolio_corr_payload.get("data_quality", {}).get(
                "degraded_fields"
            ),
            "sector_rotation_ok": rotation_payload is not None
            and not rotation_payload.get("data_quality", {}).get("degraded_fields"),
            "northbound_ok": northbound_payload is not None
            and not northbound_payload.get("data_quality", {}).get("degraded_fields"),
            "degraded_fields": degraded,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Markdown 格式化
# ═══════════════════════════════════════════════════════════════


def _md_regime_emoji(regime: str) -> str:
    return {
        "bull": "🟢",
        "bear": "🔴",
        "sideways": "🟡",
        "panic": "⚠️",
        "euphoria": "🔥",
        "defensive": "🛡️",
        "unknown": "❓",
    }.get(regime, "❓")


def to_markdown(payload: dict) -> str:
    """生成"市场环境锚定"小节的 Markdown 输出。"""
    lines = []
    regime_zh = payload["regime_label_zh"]
    regime_en = payload["regime"]
    emoji = _md_regime_emoji(regime_en)
    conf = payload["regime_confidence"]
    idx_chg = payload["index_change_pct"]

    lines.append("## 📊 市场环境锚定")
    lines.append("")
    lines.append(
        f"{emoji} **市场状态**: {regime_zh} ({conf}) — {payload['regime_reason']}"
    )
    if idx_chg is not None:
        lines.append(f"📈 **大盘指数**: {payload['index_code']} 当日 {idx_chg:+.2f}%")
    else:
        lines.append("📈 **大盘指数**: ⚠️ 数据缺失")

    b = payload.get("breadth") or {}
    if b:
        lines.append(
            f"🌐 **市场宽度**: 上涨 {b.get('up_count', 0)} 家 / 下跌 {b.get('down_count', 0)} 家"
        )
        lines.append(
            f"        涨停 {b.get('limit_up_count', 0)} 家 / 跌停 {b.get('limit_down_count', 0)} 家"
        )
    else:
        lines.append("🌐 **市场宽度**: ⚠️ 数据缺失")

    ss = payload.get("sector_strength")
    if ss and ss.get("etfs"):
        top_names = []
        for code in ss["top"][:3]:
            etf = next((e for e in ss["etfs"] if e["code"] == code), None)
            if etf and etf.get("change_pct") is not None:
                top_names.append(f"{etf['name']} {etf['change_pct']:+.2f}%")
        bottom_names = []
        for code in ss["bottom"][:3]:
            etf = next((e for e in ss["etfs"] if e["code"] == code), None)
            if etf and etf.get("change_pct") is not None:
                bottom_names.append(f"{etf['name']} {etf['change_pct']:+.2f}%")
        if top_names:
            lines.append(f"🔥 **强势板块**: {', '.join(top_names)}")
        if bottom_names:
            lines.append(f"💀 **弱势板块**: {', '.join(bottom_names)}")

    comp = payload.get("stock_sector_compare")
    if comp:
        lines.append("")
        lines.append(f"### 🎯 个股 vs 板块 vs 大盘 ({comp['stock_code']})")
        if comp.get("stock_sectors"):
            lines.append(f"- 所属板块: {', '.join(comp['stock_sectors'])}")
        if comp.get("matched_etf_name"):
            lines.append(
                f"- 匹配 ETF: {comp['matched_etf']} {comp['matched_etf_name']}"
            )
        if comp.get("stock_change_pct") is not None:
            lines.append(f"- 个股涨跌: {comp['stock_change_pct']:+.2f}%")
        if comp.get("sector_change_pct") is not None:
            lines.append(f"- 板块涨跌: {comp['sector_change_pct']:+.2f}%")
        if comp.get("index_change_pct") is not None:
            lines.append(f"- 大盘涨跌: {comp['index_change_pct']:+.2f}%")
        if comp.get("rps_vs_sector") is not None:
            lines.append(f"- RPS vs 板块: {comp['rps_vs_sector']:+.2f}pp")
        if comp.get("rps_vs_index") is not None:
            lines.append(f"- RPS vs 大盘: {comp['rps_vs_index']:+.2f}pp")
        lines.append(f"- **结论**: {comp['verdict']}")
        if comp.get("data_quality", {}).get("degraded_fields"):
            lines.append(
                f"- ⚠️ 降级字段: {', '.join(comp['data_quality']['degraded_fields'])}"
            )

    # v2.5.x 新增：多时间框架
    mtf = payload.get("multi_timeframe")
    if mtf and (mtf.get("ma20") or mtf.get("ma60") or mtf.get("ma250")):
        lines.append("")
        lines.append(f"### 📐 多时间框架动量 ({payload['index_code']})")
        ma20 = mtf.get("ma20")
        ma60 = mtf.get("ma60")
        ma250 = mtf.get("ma250")
        alignment = mtf.get("ma_alignment", "unknown")
        lines.append(
            f"- MA20: {ma20 or 'N/A'} | MA60: {ma60 or 'N/A'} | MA250: {ma250 or 'N/A'}"
        )
        lines.append(f"- 排列状态: {alignment}")
        ret5 = mtf.get("ret_5d_pct")
        ret20 = mtf.get("ret_20d_pct")
        if ret5 is not None:
            lines.append(f"- 5 日动量: {ret5:+.2f}%")
        if ret20 is not None:
            lines.append(f"- 20 日动量: {ret20:+.2f}%")
        atr = mtf.get("atr_14")
        if atr:
            lines.append(f"- ATR14: {atr}")
        vs_ma250 = mtf.get("vs_ma250_pct")
        if vs_ma250 is not None:
            lines.append(f"- vs MA250: {vs_ma250:+.2f}%（年线偏离度）")

    # v2.5.x 新增：宏观-估值桥
    macro = payload.get("macro")
    leverage = payload.get("leverage")
    val_bridge = payload.get("valuation_bridge")
    if macro or leverage or val_bridge:
        lines.append("")
        lines.append("### 🌐 宏观-估值桥 / 杠杆-反身性")
        if macro:
            tnx = macro.get("treasury_10y_pct")
            usdx = macro.get("usd_index")
            cny = macro.get("usd_cny")
            vix = macro.get("vix")
            gold = macro.get("gold_usd_oz")
            brent = macro.get("brent_oil_usd")
            lithium = macro.get("lithium_carbonate_cny_t")
            if tnx is not None:
                lines.append(f"- 10Y 美债: {tnx}%")
            if usdx is not None:
                lines.append(f"- 美元指数: {usdx}")
            if cny is not None:
                lines.append(f"- USDCNH: {cny}")
            if vix is not None:
                lines.append(f"- VIX: {vix}")
            if gold is not None:
                lines.append(f"- 黄金(oz): ${gold}")
            if brent is not None:
                lines.append(f"- 布伦特: ${brent}")
            if lithium is not None:
                lines.append(f"- 碳酸锂: ¥{lithium}/吨")
        if leverage:
            mg = leverage.get("margin_balance_total_yi")
            mg_chg = leverage.get("margin_change_5d_pct")
            if mg is not None:
                lines.append(f"- 两市两融余额: {mg} 亿元（5 日 {mg_chg}%）")
            for k, label in [
                ("if_main_basis_pts", "IF 基差"),
                ("ic_main_basis_pts", "IC 基差"),
                ("ih_main_basis_pts", "IH 基差"),
            ]:
                v = leverage.get(k)
                if v is not None:
                    lines.append(f"- {label}: {v} 点")
        if val_bridge:
            erp = val_bridge.get("erp_sh300_pct")
            if erp is not None:
                lines.append(f"- 沪深 300 ERP: {erp}%")

    # v2.5.x 新增：流动性 + 波动率
    lv = payload.get("liquidity_volatility")
    if lv:
        lines.append("")
        lines.append("### 💧 流动性 + 波动率")
        sh_atr = lv.get("sh300_atr_14")
        sh_vol = lv.get("sh300_annualized_vol_pct")
        stock_amt = lv.get("stock_avg_amount_20d_yi")
        stock_liq = lv.get("stock_liquidity_ratio_pct")
        if sh_atr:
            lines.append(f"- 沪深 300 ATR14: {sh_atr}")
        if sh_vol is not None:
            lines.append(f"- 沪深 300 年化波动率: {sh_vol}%")
        if stock_amt is not None:
            lines.append(f"- 个股 20 日均成交额: {stock_amt} 亿元")
        if stock_liq is not None:
            lines.append(f"- 个股流动性比率: {stock_liq}%（日均成交/流通市值）")

    # v2.5.x 新增：情绪周期阶段
    ep = payload.get("emotion_phase")
    if ep:
        lines.append("")
        phase_emoji = {
            "主升": "🔥",
            "退潮": "💀",
            "震荡": "🟡",
            "冰点": "⚠️",
            "unknown": "❓",
        }.get(ep, "❓")
        lines.append(f"### {phase_emoji} 情绪周期阶段: **{ep}**")

    # v2.6.0 新增：行业 beta
    ib = payload.get("industry_beta")
    if ib and ib.get("beta") is not None:
        lines.append("")
        lines.append(
            f"### 📈 行业 beta ({ib.get('stock_code', '')} vs {ib.get('index_code', '')})"
        )
        lines.append(f"- beta: {ib['beta']}（{ib.get('interpretation', '')}）")
        if ib.get("alpha_annual") is not None:
            lines.append(f"- 年化 alpha: {ib['alpha_annual'] * 100:.2f}%")
        if ib.get("r_squared") is not None:
            lines.append(f"- R²: {ib['r_squared']}（拟合优度）")
        if ib.get("volatility_pct") is not None:
            lines.append(f"- 个股年化波动率: {ib['volatility_pct']}%")
        lines.append(
            f"- 窗口: {ib.get('window', 60)} 日（{ib.get('n_observations', 0)} 个观测值）"
        )
        lines.append(f"- 基准选择: {ib.get('index_selection', 'dynamic')}")

    # v2.6.0 新增：组合相关性
    pc = payload.get("portfolio_correlation")
    if pc:
        lines.append("")
        lines.append("### 🎯 组合相关性（与 /portfolio 联动）")
        if pc.get("portfolio_empty"):
            lines.append(f"- {pc.get('interpretation', '无持仓')}")
        else:
            codes = pc.get("portfolio_codes", [])
            lines.append(
                f"- 持仓数: {len(codes)} 只 ({', '.join(codes[:3])}{'...' if len(codes) > 3 else ''})"
            )
            avg = pc.get("avg_pairwise_corr")
            if avg is not None:
                lines.append(f"- 平均两两相关性: {avg}")
            hp = pc.get("high_corr_pairs", [])
            if hp:
                lines.append(f"- 高相关对 (>=0.7): {len(hp)} 对")
                for pair in hp[:3]:
                    lines.append(f"  - {pair[0]} <-> {pair[1]}: {pair[2]}")
            lines.append(f"- 解读: {pc.get('interpretation', '')}")
            vp = pc.get("vs_portfolio")
            if vp and vp.get("vs_portfolio_avg_corr") is not None:
                lines.append(
                    f"- 个股 vs 组合: {vp['vs_portfolio_avg_corr']}（{vp.get('diversification_benefit', '')}）"
                )

    # v2.7.0 新增：题材轮动强度
    sr = payload.get("sector_rotation")
    if sr:
        lines.append("")
        lines.append(f"### 🔄 题材轮动强度（{sr.get('window', 5)} 日）")
        strength = sr.get("rotation_strength")
        if strength is not None:
            lines.append(f"- 轮动强度: {strength}（平均位次差，>3=剧烈）")
        if sr.get("rotation_std") is not None:
            lines.append(f"- 位次差标准差: {sr['rotation_std']}")
        risers = sr.get("biggest_risers", [])
        if risers:
            riser_str = ", ".join(f"{r[1]} +{-r[2]}" for r in risers[:3])
            lines.append(f"- 位次上升: {riser_str}")
        fallers = sr.get("biggest_fallers", [])
        if fallers:
            faller_str = ", ".join(f"{f[1]} -{f[2]}" for f in fallers[:3])
            lines.append(f"- 位次下降: {faller_str}")
        lines.append(f"- 解读: {sr.get('interpretation', '')}")

    # v2.7.0 新增：北向资金边际定价者
    nb = payload.get("northbound_pricer")
    if nb:
        lines.append("")
        lines.append(f"### 🌏 北向资金边际定价者（{nb.get('days', 20)} 日）")
        total = nb.get("total_net_yi")
        if total is not None:
            lines.append(
                f"- 累计净流入: {total} 亿元（沪 {nb.get('total_net_sh_yi')} / 深 {nb.get('total_net_sz_yi')}）"
            )
        if nb.get("latest_day_net_yi") is not None:
            lines.append(f"- 最近一日: {nb['latest_day_net_yi']} 亿元")
        if nb.get("recent_5d_net_yi") is not None:
            lines.append(
                f"- 近 5 日累计: {nb['recent_5d_net_yi']} 亿元（{nb.get('recent_5d_slope', '')}）"
            )
        lines.append(f"- 方向: {nb.get('direction', 'unknown')}")
        lines.append(f"- 解读: {nb.get('interpretation', '')}")

    dq = payload["data_quality"]
    if dq["degraded_fields"]:
        lines.append("")
        lines.append(f"⚠️ **数据降级**: {', '.join(dq['degraded_fields'])}")
    lines.append("")
    lines.append(
        f"📊 数据时间戳: {payload['as_of']} | 数据源: quote.py / market_breadth.py / sector_etf_strength.py / technical.moving_average / technical.volatility / macro_indicators"
    )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="市场环境锚定编排器")
    parser.add_argument("stock_code", nargs="?", help="股票代码（如 sh600519），可选")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument(
        "--no-sector", action="store_true", help="跳过板块拉取（technical 模式用）"
    )
    parser.add_argument(
        "--no-portfolio", action="store_true", help="跳过组合相关性（v2.6.0）"
    )
    parser.add_argument(
        "--no-rotation", action="store_true", help="跳过题材轮动（v2.7.0）"
    )
    parser.add_argument(
        "--no-northbound", action="store_true", help="跳过北向资金（v2.7.0）"
    )
    parser.add_argument(
        "--index", default="sh000300", help="大盘指数代码（默认 sh000300）"
    )
    args = parser.parse_args()

    payload = analyze(
        stock_code=args.stock_code,
        fetch_sector=not args.no_sector,
        fetch_portfolio=not args.no_portfolio,
        fetch_rotation=not args.no_rotation,
        fetch_northbound=not args.no_northbound,
        index_code=args.index,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(payload))


if __name__ == "__main__":
    main()

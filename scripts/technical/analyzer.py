"""技术指标计算器（TechnicalInput + _compute_all）。

从 technical.py 下沉：供 technical.py CLI 与 portfolio/manager.py 共用，
避免 manager 用 importlib 加载顶层模块的同名包 hack。
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from common import (
    board_type,
    normalize_quote_code,
    normalize_finance_code,
    to_float,
)
from kline import fetch as fetch_kline
from quote import fetch_batch

# 从 technical 包导入所有公开函数（显式导入，避免通配符污染命名空间）
from technical.core import _parse_records, filter_records
from technical.moving_average import ma_system
from technical.macd import macd_full
from technical.kdj import kdj_full
from technical.boll import bollinger
from technical.rsi import rsi_features
from technical.volume import volume_analysis
from technical.candlestick import detect_candle_patterns
from technical.trend import (
    support_resistance,
    box_detection,
    breakout_check,
    wave_state,
)
from technical.astock import limit_analysis
from technical.bamboo import bamboo_node
from technical.ma_stop import ma_stop_buy
from technical.scoring import (
    composite_score,
    detect_market_environment,
    _market_weight_adjustments,
)
from technical.report import render_report, render_quick
from technical.moving_average import incremental_ma


@dataclass
class TechnicalInput:
    """_compute_all 的参数封装。"""

    closes: list
    opens: list
    highs: list
    lows: list
    volumes: list
    records: list
    board: str
    quote: dict
    args: object = None


def _compute_all(inp: TechnicalInput):
    """计算所有技术指标。args 为 CLI 参数，用于控制可选模块。"""
    closes = inp.closes
    highs = inp.highs
    lows = inp.lows
    volumes = inp.volumes
    records = inp.records
    board = inp.board
    quote = inp.quote
    args = inp.args
    features = {}

    # M3: 统一过滤零值记录，确保 records（供形态/涨跌停/缠论/战法使用）
    # 与 _parse_records 解析出的 OHLCV 数组索引对齐
    records = filter_records(records)

    features["ma_system"] = ma_system(closes)
    features["macd"] = macd_full(closes)
    features["kdj"] = kdj_full(closes, highs, lows, board=board)
    features["bollinger"] = bollinger(closes) or {}
    features["rsi"] = rsi_features(closes)
    features["volume"] = volume_analysis(closes, volumes) or {}
    features["patterns"] = detect_candle_patterns(records)
    features["support_resistance"] = support_resistance(closes, highs, lows, features["ma_system"])
    features["box"] = box_detection(highs, lows, closes)
    # 突破检测：目标是现价下方最近的摆动高点（"突破前高"），
    # 而非 nearest_resistance（恒在现价上方，传入会导致突破分支不可达）。
    breakout_target = features["support_resistance"].get("breakout_target")
    features["breakout"] = breakout_check(closes, highs, volumes, breakout_target) if breakout_target else {}
    features["wave"] = wave_state(closes, highs, lows)
    features["limit_analysis"] = limit_analysis(records, board, quote)
    features["bamboo"] = bamboo_node(highs, lows, closes) or {}
    features["ma_stop_buy"] = ma_stop_buy(closes, highs, lows, features["ma_system"]) or {}

    # ── 可选增强模块（--classify 时启用）──
    do_classify = args and getattr(args, "classify", False)

    # 均线序列（供本土战法使用）— O(N) 增量计算
    mas = {f"ma{p}": incremental_ma(closes, p) for p in [5, 10, 20, 60]}

    # 本土战法（始终运行，计算成本低）
    try:
        from strategies.patterns import detect_all_local_patterns, PatternInput

        local_result = detect_all_local_patterns(
            PatternInput(
                records=records,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                mas=mas,
                code=quote.get("code", ""),
            )
        )
        features["local_patterns"] = local_result
    except Exception:
        logger.debug("本土战法计算失败", exc_info=True)
        features["local_patterns"] = {
            "patterns": [],
            "summary": "本土战法计算失败",
            "count": 0,
        }

    # 个股分类（需要财务数据）
    fin_record = None
    if do_classify:
        try:
            from classifier import classify_stock

            try:
                from finance import fetch as fetch_finance

                fn_code = normalize_finance_code(quote.get("code", ""))
                fin_data = fetch_finance(fn_code)
                fin_record = fin_data[0] if fin_data else None
            except Exception as e:
                logger.debug("财务数据获取失败: %s", e)
            features["classification"] = classify_stock(fin_record, quote, records)
        except Exception as e:
            logger.debug("个股分类计算失败: %s", e)
            features["classification"] = {
                "type": "普通股",
                "confidence": "低",
                "reasons": ["分类计算失败"],
                "priority_indicators": [],
                "deprioritized": [],
            }

    # 缠论分析（需要较长K线历史）
    do_chan = do_classify and not (args and getattr(args, "no_chan", False))
    if do_chan and len(records) >= 30:
        try:
            from chan import chan_full_analysis

            features["chan_theory"] = chan_full_analysis(records)
        except Exception as e:
            logger.debug("缠论计算失败: %s", e)
            features["chan_theory"] = {"valid": False, "error": "缠论计算失败"}
    else:
        features["chan_theory"] = {
            "valid": False,
            "error": "未启用" if not do_classify else "数据不足",
        }

    # 估值数据（供 signals.py 估值信号使用）
    pe = to_float(quote.get("pe"))
    pb = to_float(quote.get("pb"))
    # 行业识别：用于 PE 行业相对分位与估值评分
    try:
        from classifier import profile_stock

        industry = profile_stock(quote).get("industry", "默认")
    except Exception as e:
        logger.debug("行业识别失败，使用默认行业: %s", e)
        industry = "默认"
    # PE 行业相对分位 — 统一实现（strategies.factors.score_utils.pe_percentile，
    # 与 stock_analysis.py 同源，修复双实现不一致：亏损股 85 vs 50）
    from strategies.factors.score_utils import pe_percentile

    pe_pct = pe_percentile(pe, industry)
    # PEG
    growth = to_float(quote.get("net_profit_yoy", 0))
    peg = (pe / growth) if (pe > 0 and growth > 0) else 0
    features["valuation"] = {
        "pe": pe,
        "pb": pb,
        "pe_percentile": round(pe_pct, 1),
        "peg": round(peg, 2),
    }
    # 估值因子评分（供 scoring.py composite_score 使用，与 stock_analysis.py 同源）。
    # 修复：原实现直接把 pe_pct 当评分，方向与"便宜=高分"相反（昂贵股反而得分更高），
    # 且与 stock_analysis.py 的 strategies.factors.valuation.valuation_score 不一致。
    try:
        from strategies.factors.valuation import valuation_score

        features["valuation_score"] = valuation_score(quote, fin_record or {}, industry)
    except Exception as e:
        logger.debug("估值评分失败，使用中性 50: %s", e)
        features["valuation_score"] = 50

    # 市场环境
    if do_classify:
        market_index = getattr(args, "market_index", None)
        if market_index:
            try:
                idx_quotes = fetch_batch([normalize_quote_code(market_index)])
                idx_quote = idx_quotes[0] if idx_quotes else None
                features["market_environment"] = detect_market_environment(idx_quote)
            except Exception as e:
                logger.debug("市场指数获取失败，使用默认检测: %s", e)
                features["market_environment"] = detect_market_environment()
        else:
            features["market_environment"] = detect_market_environment()
    else:
        features["market_environment"] = {
            "state": "震荡",
            "confidence": "低",
            "signals": ["未启用市场检测"],
            "weight_adjustments": _market_weight_adjustments("震荡"),
        }

    return features

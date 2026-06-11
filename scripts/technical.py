#!/usr/bin/env python3
"""
兼容入口：import technical 包后转发 CLI。
用法:
  technical.py sh600989                    # 完整技术分析报告
  technical.py sh600989 --quick            # 快速摘要
  technical.py sh600989 --scale 60         # 60分钟K线
  technical.py sh600989 -j                 # JSON 输出
  technical.py sh600989 --quick -j         # JSON 快速摘要
  technical.py sh600989 --classify         # 含个股分类+缠论+本土战法+市场自适应
  technical.py sh600989 --classify --no-chan  # 跳过缠论
"""
import argparse
import json
import sys
from datetime import datetime

from common import (
    board_type,
    clamp,
    normalize_quote_code,
    normalize_finance_code,
    to_float,
)
from kline import fetch as fetch_kline
from quote import fetch_batch

# 从 technical 包导入所有公开函数
from technical import *  # noqa: F401,F403
from technical.core import _parse_records
from technical.moving_average import ma_system, _MA_PERIODS
from technical.macd import macd_full
from technical.kdj import kdj_full
from technical.boll import bollinger
from technical.rsi import rsi_features
from technical.volume import volume_analysis
from technical.candlestick import detect_candle_patterns
from technical.trend import support_resistance, box_detection, breakout_check, wave_state
from technical.astock import limit_analysis
from technical.scoring import (
    composite_score,
    detect_market_environment,
    _market_weight_adjustments,
)
from technical.report import render_report, render_quick
from technical.core import sma


def _compute_all(closes, opens, highs, lows, volumes, records, board, quote, args=None):
    """计算所有技术指标。args 为 CLI 参数，用于控制可选模块。"""
    features = {}

    features["ma_system"] = ma_system(closes)
    features["macd"] = macd_full(closes)
    features["kdj"] = kdj_full(closes, highs, lows, board=board)
    features["bollinger"] = bollinger(closes) or {}
    features["rsi"] = rsi_features(closes)
    features["volume"] = volume_analysis(closes, volumes) or {}
    features["patterns"] = detect_candle_patterns(records)
    features["support_resistance"] = support_resistance(closes, highs, lows, features["ma_system"])
    features["box"] = box_detection(highs, lows, closes)
    nearest_r = features["support_resistance"].get("nearest_resistance")
    features["breakout"] = breakout_check(closes, highs, volumes, nearest_r) if nearest_r else {}
    features["wave"] = wave_state(closes, highs, lows)
    features["limit_analysis"] = limit_analysis(records, board, quote)

    # ── 可选增强模块（--classify 时启用）──
    do_classify = args and getattr(args, "classify", False)

    # 均线序列（供本土战法使用）
    mas = {}
    for p in [5, 10, 20, 60]:
        mas[f"ma{p}"] = [sma(closes[:i + 1], p) if i + 1 >= p else closes[i]
                         for i in range(len(closes))]

    # 本土战法（始终运行，计算成本低）
    try:
        from patterns_local import detect_all_local_patterns
        local_result = detect_all_local_patterns(records, closes, highs, lows, volumes, mas,
                                                  code=quote.get("code", ""))
        features["local_patterns"] = local_result
    except Exception:
        features["local_patterns"] = {"patterns": [], "summary": "本土战法计算失败", "count": 0}

    # 个股分类（需要财务数据）
    if do_classify:
        try:
            from classifier import classify_stock
            fin_record = None
            try:
                from finance import fetch as fetch_finance
                fn_code = normalize_finance_code(quote.get("code", ""))
                fin_data = fetch_finance(fn_code)
                fin_record = fin_data[0] if fin_data else None
            except Exception:
                pass
            features["classification"] = classify_stock(fin_record, quote, records)
        except Exception:
            features["classification"] = {"type": "普通股", "confidence": "低",
                                           "reasons": ["分类计算失败"], "priority_indicators": [],
                                           "deprioritized": []}

    # 缠论分析（需要较长K线历史）
    do_chan = do_classify and not (args and getattr(args, "no_chan", False))
    if do_chan and len(records) >= 30:
        try:
            from chan import chan_full_analysis
            features["chan_theory"] = chan_full_analysis(records)
        except Exception:
            features["chan_theory"] = {"valid": False, "error": "缠论计算失败"}
    else:
        features["chan_theory"] = {"valid": False, "error": "未启用" if not do_classify else "数据不足"}

    # 市场环境
    if do_classify:
        market_index = getattr(args, "market_index", None)
        if market_index:
            try:
                idx_quotes = fetch_batch([normalize_quote_code(market_index)])
                idx_quote = idx_quotes[0] if idx_quotes else None
                features["market_environment"] = detect_market_environment(idx_quote)
            except Exception:
                features["market_environment"] = detect_market_environment()
        else:
            features["market_environment"] = detect_market_environment()
    else:
        features["market_environment"] = {"state": "震荡", "confidence": "低",
                                           "signals": ["未启用市场检测"],
                                           "weight_adjustments": _market_weight_adjustments("震荡")}

    return features


def main():
    parser = argparse.ArgumentParser(description="A 股纯技术分析")
    parser.add_argument("code", help="证券代码，如 sh600989")
    parser.add_argument("--scale", "-s", type=int, default=240, help="K线周期: 240=日K, 60=60分钟, 30=30分钟, 15=15分钟, 5=5分钟")
    parser.add_argument("--quick", "-q", action="store_true", help="快速摘要模式")
    parser.add_argument("--json", "-j", action="store_true", help="JSON 输出")
    parser.add_argument("--datalen", type=int, default=250, help="K线数量（默认250）")
    parser.add_argument("--classify", action="store_true", help="启用个股分类+缠论+本土战法+市场自适应")
    parser.add_argument("--no-chan", action="store_true", help="跳过缠论分析（仅与 --classify 配合）")
    parser.add_argument("--market-index", type=str, default=None, help="市场环境参考指数（默认无，如 sh000001）")
    args = parser.parse_args()

    code = normalize_quote_code(args.code)
    board = board_type(code)

    # 获取数据
    records = fetch_kline(code, args.scale, args.datalen)
    if not records:
        sys.exit(f"❌ 无法获取 {code} 的 K 线数据")

    quotes = fetch_batch([code])
    quote = quotes[0] if quotes else {}
    if not quote:
        sys.exit(f"❌ 无法获取 {code} 的实时行情")

    # 解析数值
    closes, opens, highs, lows, volumes = _parse_records(records)
    if len(closes) < 10:
        sys.exit(f"❌ {code} K 线数据不足（需≥10根，当前{len(closes)}）")

    # 计算所有指标
    features = _compute_all(closes, opens, highs, lows, volumes, records, board, quote, args)

    # 综合评分（自适应）
    stock_type = "普通股"
    market_state = None
    if args.classify:
        classification = features.get("classification") or {}
        stock_type = classification.get("type", "普通股")
        market_env = features.get("market_environment") or {}
        market_state = market_env.get("state")
    score = composite_score(features, stock_type=stock_type, market_state=market_state)

    # 元数据
    price_num = to_float(quote.get("price"))
    meta = {
        "code": code,
        "name": quote.get("name", ""),
        "price": quote.get("price", "-"),
        "price_num": price_num,
        "change_pct": quote.get("change_pct", "-"),
        "board": board,
        "scale": args.scale,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    # 查找止损位
    sr = features.get("support_resistance", {})
    nearest_support = sr.get("nearest_support")
    if nearest_support and price_num > 0:
        features["stop_loss_pct"] = round((price_num - nearest_support) / price_num * 100, 1)

    if args.json:
        feature_keys = {"ma_system", "macd", "kdj", "bollinger", "rsi", "volume",
                        "patterns", "support_resistance", "box", "breakout", "wave",
                        "limit_analysis"}
        if args.classify:
            feature_keys.update({"classification", "chan_theory", "local_patterns", "market_environment"})
        output = {
            "meta": meta,
            "score": score,
            "features": {k: v for k, v in features.items() if k in feature_keys},
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    elif args.quick:
        print(render_quick(features, score, meta))
    else:
        print(render_report(features, score, {}, meta))


if __name__ == "__main__":
    main()

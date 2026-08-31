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
import logging
import sys
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

from common.cli_base import create_parser, handle_errors
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

from technical.analyzer import TechnicalInput, _compute_all


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = create_parser(description="A 股纯技术分析")
    parser.add_argument("code", help="证券代码，如 sh600989")
    parser.add_argument(
        "--scale",
        "-s",
        type=int,
        default=240,
        help="K线周期: 240=日K, 60=60分钟, 30=30分钟, 15=15分钟, 5=5分钟",
    )
    parser.add_argument("--quick", "-q", action="store_true", help="快速摘要模式")
    parser.add_argument("--datalen", type=int, default=250, help="K线数量（默认250）")
    parser.add_argument("--classify", action="store_true", help="启用个股分类+缠论+本土战法+市场自适应")
    parser.add_argument("--no-chan", action="store_true", help="跳过缠论分析（仅与 --classify 配合）")
    parser.add_argument(
        "--market-index",
        type=str,
        default=None,
        help="市场环境参考指数（默认无，如 sh000001）",
    )
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
    features = _compute_all(
        TechnicalInput(
            closes=closes,
            opens=opens,
            highs=highs,
            lows=lows,
            volumes=volumes,
            records=records,
            board=board,
            quote=quote,
            args=args,
        )
    )

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

    # 查找止损位 + 破位检测
    # 若 nearest_support >= 现价，表明股价已跌破该支撑（破位），止损位已失效。
    # 此时 stop_loss_pct 为负值，breakdown=True 供 JSON 输出和下游消费。
    sr = features.get("support_resistance", {})
    nearest_support = sr.get("nearest_support")
    if nearest_support and price_num > 0:
        stop_pct = round((price_num - nearest_support) / price_num * 100, 1)
        features["stop_loss_pct"] = stop_pct
        features["breakdown"] = nearest_support >= price_num

    if args.json_output:
        feature_keys = {
            "ma_system",
            "macd",
            "kdj",
            "bollinger",
            "rsi",
            "volume",
            "patterns",
            "support_resistance",
            "box",
            "breakout",
            "wave",
            "limit_analysis",
            "bamboo",
            "ma_stop_buy",
            "stop_loss_pct",
            "breakdown",
        }
        if args.classify:
            feature_keys.update(
                {
                    "classification",
                    "chan_theory",
                    "local_patterns",
                    "market_environment",
                }
            )
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

"""
报告渲染。
无内部依赖。
"""


def _fmt(val, default="-"):
    return str(val) if val is not None else default


def _render_header(meta):
    """渲染报告头部。"""
    lines = []
    lines.append("═" * 72)
    lines.append(
        f"  {meta['name']} ({meta['code']})  现价: {meta['price']}  "
        f"涨跌: {meta['change_pct']}%  板块: {meta['board']}  时间: {meta['timestamp']}"
    )
    lines.append("═" * 72)
    return lines


def _render_score_section(features, score):
    """渲染综合评分段落。"""
    sr = features.get("support_resistance", {})
    lines = []
    lines.append(f"\n## 综合评分: {score['score']}/100 -- {score['grade']}")
    if score["buy_signals"]:
        lines.append(f"  买入信号: {', '.join(score['buy_signals'])}")
    if score["sell_signals"]:
        lines.append(f"  卖出信号: {', '.join(score['sell_signals'])}")
    if sr.get("nearest_support"):
        lines.append(
            f"  关键支撑: {sr['nearest_support']}  关键阻力: {sr.get('nearest_resistance', '-')}"
        )
    return lines


def _render_ma_section(ma):
    """渲染均线段落。"""
    lines = []
    lines.append("\n## 均线系统")
    ma_parts = []
    for p in [5, 10, 20, 60, 120, 250]:
        v = ma.get(f"ma{p}")
        if v is not None:
            ma_parts.append(f"MA{p}: {v}")
    lines.append(f"  {', '.join(ma_parts)}")
    lines.append(
        f"  排列: {ma.get('alignment', '-')}  |  粘合度: {ma.get('convergence_desc', '-')}"
    )
    return lines


def _render_macd_section(macd):
    """渲染 MACD 段落。"""
    lines = []
    lines.append("\n## MACD")
    lines.append(
        f"  DIF: {_fmt(macd.get('dif'))}  DEA: {_fmt(macd.get('dea'))}  BAR: {_fmt(macd.get('macd_bar'))}"
    )
    lines.append(
        f"  信号: {macd.get('signal_desc', '-')}  |  柱趋势: {macd.get('bar_trend', '-')}"
    )
    if macd.get("divergence"):
        lines.append(f"  背离: **{macd['divergence']}**")
    return lines


def _render_kdj_section(kdj):
    """渲染 KDJ 段落。"""
    lines = []
    lines.append("\n## KDJ")
    lines.append(
        f"  K: {_fmt(kdj.get('k'))}  D: {_fmt(kdj.get('d'))}  J: {_fmt(kdj.get('j'))}"
    )
    lines.append(f"  信号: {kdj.get('signal', '-')}")
    if kdj.get("钝化"):
        lines.append("  ⚠ KDJ钝化中，超买超卖信号暂停参考")
    return lines


def _render_boll_section(boll):
    """渲染 BOLL 段落。"""
    lines = []
    lines.append("\n## BOLL")
    lines.append(
        f"  上轨: {_fmt(boll.get('upper'))}  中轨: {_fmt(boll.get('mid'))}  下轨: {_fmt(boll.get('lower'))}"
    )
    lines.append(
        f"  带宽: {boll.get('bandwidth_desc', '-')}  |  价格: {boll.get('position_desc', '-')}"
    )
    return lines


def _render_rsi_section(rsi_data):
    """渲染 RSI 段落。"""
    lines = []
    lines.append("\n## RSI")
    zone = rsi_data.get("zone_desc", "")
    rsi_val = rsi_data.get("rsi", 50)
    lines.append(f"  RSI-{rsi_data.get('period', 14)}: {rsi_val} ({zone})")
    return lines


def _render_volume_section(vol):
    """渲染量能段落。"""
    lines = []
    lines.append("\n## 成交量")
    lines.append(
        f"  量比: {_fmt(vol.get('volume_ratio'))} ({vol.get('volume_ratio_desc', '-')})"
    )
    lines.append(f"  量价: {vol.get('volume_price', '-')}")
    if vol.get("obv_divergence"):
        lines.append(f"  OBV: {vol['obv_divergence']}")
    return lines


def _render_candlestick_section(patterns):
    """渲染 K 线形态段落。"""
    lines = []
    if patterns:
        lines.append("\n## K线形态")
        for p in patterns:
            lines.append(f"  {p['position']} [{p['date']}] {p['type']}")
    else:
        lines.append("\n## K线形态\n  (无明显形态)")
    return lines


def _render_classification_section(features):
    """渲染个股分类段落。"""
    classification = features.get("classification")
    if not classification:
        return []
    lines = []
    lines.append("\n## 个股分类")
    lines.append(
        f"  类型: {classification['type']} (置信度: {classification['confidence']})"
    )
    if classification.get("reasons"):
        lines.append(f"  依据: {'; '.join(classification['reasons'])}")
    if classification.get("priority_indicators"):
        lines.append(
            f"  推荐指标: {', '.join(classification['priority_indicators'])}"
        )
    return lines


def _render_chan_section(features):
    """渲染缠论分析段落。"""
    chan = features.get("chan_theory") or {}
    if not chan.get("valid"):
        return []
    lines = []
    lines.append("\n## 缠论分析")
    lines.append(
        f"  处理后K线: {chan.get('merged_count', '-')}/{chan.get('original_count', '-')}"
        f" (合并率{chan.get('merge_ratio_pct', '-')}%)"
    )
    lines.append(
        f"  分型: {chan.get('fenxing_count', 0)} (顶{chan.get('top_fenxing', 0)}/底{chan.get('bottom_fenxing', 0)})"
        f"  →  笔: {chan.get('bi_count', 0)} (↑{chan.get('up_bi', 0)} ↓{chan.get('down_bi', 0)})"
        f"  →  线段: {chan.get('xianduan_count', 0)}"
    )
    zs_list = chan.get("zhongshu_list", [])
    if zs_list:
        zs_desc = "; ".join(f"[{z['zd']}-{z['zg']}]" for z in zs_list[-2:])
        lines.append(f"  中枢({chan.get('zhongshu_count', 0)}): {zs_desc}")
    beichi = chan.get("beichi", {})
    if beichi.get("summary"):
        lines.append(f"  背驰: {beichi['summary']}")
    maidain = chan.get("maidian", {})
    buy_pts = maidain.get("buy_points", [])
    sell_pts = maidain.get("sell_points", [])
    if buy_pts:
        bp_desc = "; ".join(
            bp["type"] + "(" + bp.get("confidence", "") + ")" for bp in buy_pts
        )
        lines.append(f"  买点: {bp_desc}")
    if sell_pts:
        sp_desc = "; ".join(
            sp["type"] + "(" + sp.get("confidence", "") + ")" for sp in sell_pts
        )
        lines.append(f"  卖点: {sp_desc}")
    if not buy_pts and not sell_pts:
        lines.append("  买卖点: 当前无明确缠论买卖点")
    lines.append(f"  当前位置: {chan.get('current_position', '-')}")
    return lines


def _render_local_patterns_section(features):
    """渲染 A 股本土战法段落。"""
    local_p = features.get("local_patterns") or {}
    if not local_p.get("patterns") and not local_p:
        return []
    lines = []
    if local_p.get("patterns"):
        lines.append("\n## A股本土战法")
        for lp in local_p["patterns"]:
            icon = "↑" if lp["type"] == "看涨" else "↓"
            lines.append(f"  {icon} {lp['name']} ({lp['confidence']}): {lp['desc']}")
            # 展示量化指标
            metrics = lp.get("metrics", {})
            if metrics:
                vol_ratio = metrics.get("vol_ratio", 0)
                total_decline = metrics.get("total_decline", 0)
                rebound_ratio = metrics.get("rebound_ratio", 0)
                if vol_ratio > 0:
                    detail_parts = []
                    if vol_ratio > 0:
                        detail_parts.append(f"量比{vol_ratio:.1f}x")
                    if total_decline != 0:
                        detail_parts.append(f"跌幅{total_decline:.1f}%")
                    if rebound_ratio > 0:
                        detail_parts.append(f"反弹{rebound_ratio:.0f}%")
                    if detail_parts:
                        lines.append(f"    → {' | '.join(detail_parts)}")
        lines.append(f"  {local_p.get('summary', '')}")
    elif local_p:
        lines.append(f"\n## A股本土战法\n  {local_p.get('summary', '未检测到形态')}")
    return lines


def _render_market_env_section(features):
    """渲染市场环境自适应段落。"""
    market_env = features.get("market_environment") or {}
    if not market_env.get("state") or market_env["state"] == "震荡":
        return []
    lines = []
    lines.append("\n## 市场环境自适应")
    lines.append(
        f"  市场状态: {market_env['state']} (置信度: {market_env.get('confidence', '-')})"
    )
    adj_info = market_env.get("weight_adjustments", {})
    if adj_info.get("desc"):
        lines.append(f"  权重调整: {adj_info['desc']}")
    return lines


def _render_support_resistance_section(sr):
    """渲染支撑与阻力段落。"""
    lines = []
    lines.append("\n## 支撑与阻力")
    lines.append(f"  {'支撑位':<10} {'来源':<8} {'强度'}")
    for s in sr.get("supports", []):
        lines.append(f"  {s['level']:<10} {s['source']:<8} {s['strength']}")
    lines.append(f"  {'阻力位':<10} {'来源':<8} {'强度'}")
    for r in sr.get("resistances", []):
        lines.append(f"  {r['level']:<10} {r['source']:<8} {r['strength']}")
    return lines


def _render_trend_section(features):
    """渲染趋势结构段落。"""
    wave = features.get("wave", "")
    box = features.get("box")
    breakout = features.get("breakout", {})
    lines = []
    lines.append("\n## 趋势结构")
    lines.append(f"  波浪状态: {wave}")
    if box:
        lines.append(
            f"  箱体: {box['top']}-{box['bottom']} 震荡 (幅度{box['range_pct']}%, {box['days']}日)"
        )
    if breakout and breakout.get("status", "未突破") != "未突破":
        lines.append(f"  突破: {breakout.get('status')}")
    return lines


def _render_limit_section(features):
    """渲染 A 股特化（涨跌停/连板）段落。"""
    limit_data = features.get("limit_analysis") or {}
    if not limit_data:
        return []
    lines = []
    lines.append("\n## A股特化分析")
    lines.append(
        f"  板块制度: {limit_data.get('board', '-')} (涨跌停{limit_data.get('limit_ratio', 10)}%)"
    )
    lines.append(
        f"  涨跌停价: 涨停{limit_data.get('limit_up_price', '-')} / 跌停{limit_data.get('limit_down_price', '-')}"
    )
    lines.append(f"  当前状态: {limit_data.get('board_status', '-')}")
    if limit_data.get("limit_streak", 0) > 0:
        lines.append(
            f"  连板: {limit_data.get('limit_streak')}连板 ({limit_data.get('streak_type')})"
        )
        if limit_data.get("streak_volume"):
            lines.append(f"  连板量能: {limit_data['streak_volume']}")
    if limit_data.get("t1_risk"):
        lines.append(f"  ⚠ {limit_data['t1_risk']}")
    return lines


def _render_risk_section(features, meta):
    """渲染风险提示/仓位参考段落。"""
    sr = features.get("support_resistance", {})
    lines = []
    lines.append("\n## 仓位参考（技术面）")
    price_num = meta.get("price_num", 0)
    nearest_support = sr.get("nearest_support")
    if nearest_support and price_num > 0:
        stop_pct = round((price_num - nearest_support) / price_num * 100, 1)
        lines.append(f"  止损位: {nearest_support} (距现价 -{abs(stop_pct)}%)")
    nearest_resistance = sr.get("nearest_resistance")
    if nearest_resistance and price_num > 0:
        tp_pct = round((nearest_resistance - price_num) / price_num * 100, 1)
        lines.append(f"  止盈位: {nearest_resistance} (距现价 +{tp_pct}%)")
    lines.append("  纯技术视角，不构成投资建议。需结合基本面、市场环境综合判断。")
    return lines


def render_report(features, score, signals, meta):
    """完整技术分析报告。

    P2-12: 段落顺序改为列表驱动（RenderSection 抽象），便于未来配置化。
    渲染函数签名统一为 (features, score, signals, meta) -> list[str]，
    或仅 (features, score, signals, meta, **kwargs) 兼容其他签名。
    """
    lines = []

    # 提取子结构
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    kdj = features.get("kdj") or {}
    boll = features.get("bollinger") or {}
    rsi_data = features.get("rsi", {})
    vol = features.get("volume") or {}
    sr = features.get("support_resistance", {})
    patterns = features.get("patterns", [])

    # 头部
    lines.extend(_render_header(meta))

    # 综合评分
    lines.extend(_render_score_section(features, score))

    # 各技术指标段落（P2-12: 列表驱动，便于调整顺序）
    sections = [
        lambda: _render_ma_section(ma),
        lambda: _render_macd_section(macd),
        lambda: _render_kdj_section(kdj),
        lambda: _render_boll_section(boll),
        lambda: _render_volume_section(vol),
        lambda: _render_rsi_section(rsi_data),
        lambda: _render_candlestick_section(patterns),
        lambda: _render_classification_section(features),
        lambda: _render_chan_section(features),
        lambda: _render_local_patterns_section(features),
        lambda: _render_market_env_section(features),
        lambda: _render_support_resistance_section(sr),
        lambda: _render_trend_section(features),
        lambda: _render_limit_section(features),
    ]
    for section_fn in sections:
        lines.extend(section_fn())

    # 风险提示
    lines.extend(_render_risk_section(features, meta))

    lines.append("═" * 72)
    return "\n".join(lines)


def render_quick(features, score, meta):
    """快速技术摘要。"""
    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    vol = features.get("volume") or {}
    sr = features.get("support_resistance", {})
    limit_data = features.get("limit_analysis") or {}

    lines = []
    lines.append(f"## 技术面快扫: {meta['name']} ({meta['code']})")
    lines.append(
        f"现价: {meta['price']} | 涨跌: {meta['change_pct']}% | 板块: {meta['board']} | {meta['timestamp']}"
    )
    lines.append("")
    lines.append(f"评分: {score['score']}/100 ({score['grade']})")
    lines.append(f"趋势: {ma.get('alignment', '-')}")
    macd_icon = (
        "↑金叉"
        if macd.get("signal") == 1
        else "↓死叉" if macd.get("signal") == -1 else "→"
    )
    lines.append(f"MACD: {macd_icon} | {macd.get('bar_trend', '-')}")
    if macd.get("divergence"):
        lines.append(f"  ⚠ {macd['divergence']}")
    lines.append(
        f"量能: {vol.get('volume_ratio_desc', '-')} | {vol.get('volume_price', '-')}"
    )
    lines.append(
        f"支撑: {sr.get('nearest_support', '-')} | 阻力: {sr.get('nearest_resistance', '-')}"
    )
    if limit_data and limit_data.get("limit_streak", 0) > 0:
        lines.append(
            f"连板: {limit_data['limit_streak']}板 ({limit_data.get('board_status')})"
        )
    if score["buy_signals"]:
        lines.append(f"买入: {', '.join(score['buy_signals'])}")
    if score["sell_signals"]:
        lines.append(f"卖出: {', '.join(score['sell_signals'])}")
    lines.append("⚠ 纯技术视角，不构成投资建议")
    return "\n".join(lines)

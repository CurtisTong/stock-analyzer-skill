"""
综合评分引擎和市场环境检测。
依赖: common (to_float, clamp), signals (_generate_signals)
"""

from common import clamp, to_float
from config.loader import safe_get

from .signals import _generate_signals


def _scoring_config(key: str = None, default=None):
    """获取评分配置，安全回退。"""
    if key is None:
        return safe_get("scoring.yaml")
    return safe_get("scoring.yaml", key, default)


# P1-15: 各子评分函数的理论上限（用于归一化到 [0,100]）。
# 提取为模块级常量，便于发现和维护。可通过 scoring.yaml 的 score_max 覆盖。
# 这些值必须与 _score_* 函数的实际满分（clamp 上限）保持同步。
_SCORE_MAX_DEFAULT = {
    "ma": 30,  # _score_ma: ma_base(20) × type_w(1.3 蓝筹) × adj(1.4 牛市) ≈ 36 → clamp 30
    "macd": 20,  # _score_macd: clamp(macd_score, 0, 20)
    "kdj": 15,  # _score_kdj: clamp(kdj_score, 0, 15)
    "boll": 15,  # _score_boll: clamp 0-15
    "rsi": 15,  # _score_rsi: clamp 0-15
    "volume": 20,  # _score_volume: clamp 0-20
    "pattern": 25,  # _score_patterns: 累加多种形态，上限 ~25
    "chan": 15,  # _score_chan: clamp 0-15
    "local": 10,  # _score_local: clamp 0-10（允许负分，见 _SCORE_LOCAL_MIN/MAX）
    "limit": 15,  # _score_limit: 涨跌停/连板信号，clamp 0-15
    "chip": 10,  # chip 允许负分（下限 -5），归一化时特殊处理
    "valuation": 100,  # 估值因子（PE/PB/PEG/PS），满分 100
}

# P1: _score_local 允许负分（看跌形态如三阳一阴），归一化按 chip 同口径处理。
# 原实现 clamp(0,10) 会吞掉负分，导致纯看跌形态对评分无惩罚。
_SCORE_LOCAL_MIN = -5
_SCORE_LOCAL_MAX = 10


def _get_score_max() -> dict:
    """获取子评分上限配置（scoring.yaml 可覆盖，默认 _SCORE_MAX_DEFAULT）。"""
    cfg = _scoring_config("score_max") or {}
    merged = dict(_SCORE_MAX_DEFAULT)
    for k, v in cfg.items():
        if k in merged:
            try:
                merged[k] = float(v)
            except (TypeError, ValueError):
                pass
    return merged


# 个股类型 × 指标权重矩阵（YAML 默认值，行为与历史硬编码版本完全一致）
_STOCK_TYPE_WEIGHTS_DEFAULT = {
    "题材股": {
        "ma": 0.6,
        "macd": 0.5,
        "kdj": 0.5,
        "boll": 0.8,
        "rsi": 1.0,
        "volume": 1.3,
        "pattern": 1.5,
        "limit": 1.5,
        "chan": 0.5,
        "chip": 0.8,
        "valuation": 0.3,  # 题材股估值权重低，以情绪/技术为主
    },
    "蓝筹股": {
        "ma": 1.3,
        "macd": 1.1,
        "kdj": 0.4,
        "boll": 1.2,
        "rsi": 0.9,
        "volume": 0.8,
        "pattern": 0.7,
        "limit": 0.3,
        "chan": 0.8,
        "chip": 1.3,
        "valuation": 1.5,  # 蓝筹股估值权重高，PE/PB/股息率是核心
    },
    "强成长股": {
        "ma": 0.9,
        "macd": 1.3,
        "kdj": 0.4,
        "boll": 1.2,
        "rsi": 0.9,
        "volume": 1.2,
        "pattern": 0.8,
        "limit": 0.5,
        "chan": 0.7,
        "chip": 1.0,
        "valuation": 0.8,  # 成长股用 PEG 而非绝对 PE，权重适中
    },
    "周期股": {
        "ma": 0.6,
        "macd": 1.3,
        "kdj": 1.2,
        "boll": 1.0,
        "rsi": 0.9,
        "volume": 0.9,
        "pattern": 0.7,
        "limit": 0.4,
        "chan": 1.3,
        "chip": 1.1,
        "valuation": 1.0,  # 周期股用 PB/商品价格，权重中等
    },
    "稳成长股": {
        "ma": 1.2,
        "macd": 1.1,
        "kdj": 0.5,
        "boll": 1.0,
        "rsi": 1.0,
        "volume": 0.9,
        "pattern": 1.0,
        "limit": 0.3,
        "chan": 0.8,
        "chip": 1.2,
        "valuation": 1.3,  # 稳成长股估值是重要参考
    },
    "防御股": {
        "ma": 0.8,
        "macd": 0.9,
        "kdj": 0.6,
        "boll": 1.1,
        "rsi": 1.1,
        "volume": 0.7,
        "pattern": 0.7,
        "limit": 0.3,
        "chan": 0.9,
        "chip": 1.0,
        "valuation": 1.4,  # 防御股估值+股息率是核心
    },
    "普通股": {
        "ma": 1.0,
        "macd": 1.0,
        "kdj": 1.0,
        "boll": 1.0,
        "rsi": 1.0,
        "volume": 1.0,
        "pattern": 1.0,
        "limit": 1.0,
        "chan": 1.0,
        "chip": 1.0,
        "valuation": 1.0,  # 普通股估值等权
    },
}


def _get_stock_type_weights(stock_type: str) -> dict:
    """从 YAML 读取个股类型权重；缺失时回退硬编码默认。"""
    cfg = _scoring_config("stock_type_weights") or {}
    if stock_type in cfg:
        row = dict(cfg[stock_type])
        # 补全可能缺失的 chip / valuation 字段（向后兼容旧 YAML）。
        # Bug 2 修复：原仅补 chip，valuation 缺失时 type_w.get("valuation") 返回 None，
        # 导致 valuation 权重默认 1.0 进分子却不进分母（total_weight），
        # 评分被异常放大。现与 chip 同等补全。
        defaults = _STOCK_TYPE_WEIGHTS_DEFAULT.get(
            stock_type, _STOCK_TYPE_WEIGHTS_DEFAULT["普通股"]
        )
        for field in ("chip", "valuation"):
            if field not in row:
                row[field] = defaults.get(field, 1.0)
        return row
    return _STOCK_TYPE_WEIGHTS_DEFAULT.get(
        stock_type, _STOCK_TYPE_WEIGHTS_DEFAULT["普通股"]
    )


def _score_ma(alignment: str, type_w: dict, adj: dict, alignment_scores: dict) -> float:
    """均线评分（上限 30）。"""
    ma_base = alignment_scores.get(alignment, 7)
    ma_score = (
        ma_base
        * type_w["ma"]
        * (adj.get("trend_following", 1.0) if alignment == "多头排列" else 1.0)
    )
    return clamp(ma_score, 0, 30)


def _score_macd(macd: dict, type_w: dict, adj: dict) -> float:
    """MACD 评分（上限 20）。"""
    macd_signal = macd.get("signal", 0)
    bar_trend = macd.get("bar_trend", "")
    divergence = macd.get("divergence", "")
    # 从 scoring.yaml 读取评分档位，支持配置热更新
    scores = _scoring_config("macd_scores") or {}
    macd_base = scores.get("中性", 7)
    if macd_signal == 1 and "放大" in bar_trend:
        macd_base = scores.get("金叉放大", 15)
    elif macd_signal == 1:
        macd_base = scores.get("金叉", 10)
    elif macd_signal == -1:
        macd_base = scores.get("死叉", 3)
    macd_score = macd_base * type_w["macd"]
    if divergence == "底背离(看涨)":
        macd_score += 8 * adj.get("divergence_bottom", 1.0)
    elif divergence == "顶背离(看跌)":
        macd_score -= 8 * adj.get("overbought", 1.0)
    return clamp(macd_score, 0, 20)


def _score_kdj(kdj: dict, type_w: dict, adj: dict, vol_signal: int = 0) -> float:
    """KDJ 评分（上限 15）。辅助信号：仅在震荡市/盘整时生效，其他市场降权。

    Args:
        vol_signal: 量价信号（-1=放量下跌, 0=中性, 1=放量上涨），用于下跌趋势降权
    """
    market_state_for_kdj = adj.get("trend_following", 1.0)
    kdj_active = market_state_for_kdj < 1.0  # 震荡/熊市时 KDJ 更有效
    kdj_weight = 5 if kdj.get("钝化") else (10 if kdj_active else 5)
    kdj_sig = kdj.get("signal", "")

    # 下跌趋势降权：放量下跌时，超卖信号不可靠
    trend_penalty = 0.5 if vol_signal == -1 else 1.0

    # 按关键词匹配评分（支持组合信号如"金叉+超卖"、"死叉+超买"等）
    if "金叉" in kdj_sig and "超卖" in kdj_sig:
        kdj_base = kdj_weight * trend_penalty  # 下跌趋势中超卖金叉降权
    elif "金叉" in kdj_sig:
        kdj_base = kdj_weight * 0.8
    elif "死叉" in kdj_sig and "超买" in kdj_sig:
        kdj_base = kdj_weight * 0.1
    elif "死叉" in kdj_sig:
        kdj_base = kdj_weight * 0.2
    elif "超卖" in kdj_sig:
        kdj_base = kdj_weight * 0.6 * trend_penalty  # 下跌趋势中超卖降权
    elif "超买" in kdj_sig:
        kdj_base = kdj_weight * 0.3
    else:
        kdj_base = kdj_weight * 0.45
    kdj_score = kdj_base * type_w["kdj"]
    return clamp(kdj_score, 0, 15)


def _score_boll(boll: dict, type_w: dict) -> float:
    """布林带评分（上限 15）。"""
    pos = boll.get("position", 0.5)
    bw = boll.get("bandwidth_desc", "")
    boll_base = 7
    if pos < 0.3:
        boll_base = 10 if "收窄" in bw else 6
    elif 0.3 <= pos <= 0.7:
        boll_base = 7
    elif pos > 0.7:
        boll_base = 4
    return clamp(boll_base * type_w["boll"], 0, 15)


def _score_rsi(rsi_data: dict, type_w: dict, vol_signal: int = 0) -> float:
    """RSI 评分（无独立上限，纳入总分）。

    Args:
        vol_signal: 量价信号（-1=放量下跌, 0=中性, 1=放量上涨），用于下跌趋势降权
    """
    rsi = rsi_data.get("rsi", 50)

    # 下跌趋势降权：放量下跌时，超卖信号不可靠
    trend_penalty = 0.6 if vol_signal == -1 else 1.0

    rsi_base = 7
    if rsi < 20:
        rsi_base = 12 * trend_penalty  # 极度超卖（<20），反弹概率最高
    elif 20 <= rsi < 30:
        rsi_base = 10 * trend_penalty  # 深度超卖，反弹概率较高
    elif 30 <= rsi <= 40:
        rsi_base = 8 * trend_penalty  # 超卖区，反弹机会较好
    elif 40 < rsi <= 60:
        rsi_base = 7
    elif 60 < rsi <= 70:
        rsi_base = 5
    elif rsi > 70:
        rsi_base = 3
    return clamp(rsi_base * type_w["rsi"], 0, 15)


def _score_volume(vol: dict, type_w: dict) -> float:
    """成交量评分（上限 20）。"""
    vp_signal = vol.get("volume_price_signal", 0)
    vr = vol.get("volume_ratio", 1)
    vol_base = 7
    if vp_signal == 1:
        vol_base = 12
    elif vp_signal == -1:
        vol_base = 3
    vol_score = vol_base * type_w["volume"]
    # 极低量仅在量价中性或看涨时加分（放量下跌时不加分）
    # Bug 4 修复：加分项需乘 type_w，与基础分保持口径一致，避免对低权重类型
    # （如蓝筹股 volume=0.8）地量加分相对占比被放大。
    if vr < 0.3 and vp_signal >= 0:
        vol_score += 3 * type_w["volume"]
    return clamp(vol_score, 0, 20)


def _score_patterns(patterns: list, type_w: dict, adj: dict) -> float:
    """K线形态评分（上限 25）。"""
    bullish_patterns = ["早晨之星", "阳包阴", "锤子线", "红三兵", "假阴真阳"]
    bearish_patterns = ["黄昏之星", "阴包阳", "倒锤子", "三只乌鸦", "假阳真阴"]
    pattern_score = 7
    for p in patterns:
        ptype = p.get("type", "")
        if any(b in ptype for b in bullish_patterns):
            pattern_score = max(pattern_score, 13)
        if any(b in ptype for b in bearish_patterns):
            pattern_score = min(pattern_score, 3)
    return clamp(
        pattern_score * type_w["pattern"] * adj.get("bullish_bias", 1.0), 0, 25
    )


def _score_chan(chan_data: dict, type_w: dict, adj: dict) -> float:
    """缠论加分项（上限 15）。

    问题 5 修复：补乘 type_w["chan"]，与其他子评分口径一致，
    让缠论评分的动态范围随股票类型权重缩放（周期股 chan=1.3 vs 题材股 chan=0.5）。
    """
    chan_bonus = 0
    if chan_data.get("valid"):
        maidain = chan_data.get("maidian", {})
        buy_points = maidain.get("buy_points", [])
        for bp in buy_points:
            bpt = bp.get("type", "")
            if bpt == "一买":
                chan_bonus += 10 * adj.get("buy_point_1", 1.0)
            elif bpt == "二买":
                chan_bonus += 5
            elif bpt == "三买":
                chan_bonus += 8 * adj.get("buy_point_3", 1.0)
        beichi = chan_data.get("beichi", {})
        if beichi.get("summary", "").startswith("检测到底背驰"):
            chan_bonus += 8 * adj.get("divergence_bottom", 1.0)
    chan_score = chan_bonus * type_w.get("chan", 1.0)
    return clamp(chan_score, 0, 15)


def _score_limit(limit_data: dict, type_w: dict, adj: dict) -> float:
    """涨跌停/连板信号评分（上限 15）。

    Bug 1 修复：原 type_w 含 limit 权重但 raw/normalized 缺 limit 子项，
    导致权重只进分母不进分子（题材股评分被稀释 16.7%）。
    本函数将 features["limit_analysis"] 纳入评分，让 limit 真正参与分子。

    评分逻辑：
    - 连板数越高越强（首板5、二板8、高位板10、妖股12），缩量加速额外加分
    - 封涨停/翘板为正，封跌停/炸板为负
    - 趋势跟随市场（牛市）加权，亢奋市场降权（警惕反转）
    """
    if not limit_data or not isinstance(limit_data, dict):
        return 0.0

    limit_bonus = 0.0
    streak_type = limit_data.get("streak_type", "无连板")
    board_status = limit_data.get("board_status", "正常交易")
    streak_volume = limit_data.get("streak_volume", "")

    # 连板加分：连板数越高，趋势延续信号越强
    if "首板" in streak_type:
        limit_bonus += 5
    elif "二板" in streak_type:
        limit_bonus += 8
    elif "高位" in streak_type:
        limit_bonus += 10
    elif "妖股" in streak_type:
        limit_bonus += 12  # 高位妖股趋势极强但风险也高

    # 连板量能配合：缩量加速（惜售）加分，放量分歧（换手加大）减分
    if "缩量加速" in streak_volume:
        limit_bonus += 3
    elif "放量分歧" in streak_volume:
        limit_bonus -= 2

    # 涨跌停状态
    if "封涨停" in board_status:
        limit_bonus += 3 * adj.get("breakout", 1.0)
    elif "翘板" in board_status:  # 跌停打开，反转信号
        limit_bonus += 2 * adj.get("divergence_bottom", 1.0)
    elif "封跌停" in board_status:
        limit_bonus -= 3
    elif "炸板" in board_status:  # 涨停打开，弱势信号
        limit_bonus -= 2

    # 亢奋市场对连板降权（警惕高位反转）
    limit_bonus *= adj.get("breakout", 1.0)

    limit_score = limit_bonus * type_w.get("limit", 1.0)
    # 允许小幅负分（封跌停/炸板惩罚），但下限 -3 避免过度拖累总分
    return clamp(limit_score, -3, 15)


def _score_local(local_patterns_data: dict) -> float:
    """本土战法加分（上限 10）。

    v2 优化：三阴一阳使用量化指标（量比、跌幅、反弹比例）动态评分。
    """
    local_bonus = 0
    for lp in local_patterns_data.get("patterns", []):
        pname = lp.get("name", "")
        pconf = lp.get("confidence", "中")
        metrics = lp.get("metrics", {})
        bonus = 0

        if pname == "老鸭头":
            bonus = 8
        elif pname == "美人肩":
            bonus = 6
        elif pname == "三阴一阳":
            # 基础分
            bonus = 5
            # 量比加分（核心因子，回测验证胜率提升显著）
            vol_ratio = metrics.get("vol_ratio", 0)
            if vol_ratio >= 1.5:
                bonus += 2
            elif vol_ratio >= 1.2:
                bonus += 1
            # 跌幅控制加分（小幅下跌后反弹更可靠）
            total_decline = abs(metrics.get("total_decline", 0))
            if total_decline < 3:
                bonus += 1
            # 反弹比例加分（中等反弹最佳）
            rebound = metrics.get("rebound_ratio", 0)
            if 20 <= rebound <= 50:
                bonus += 1
        elif pname == "三阳一阴":
            # 看跌信号扣分
            vol_ratio = metrics.get("vol_ratio", 0)
            bonus = -5 if vol_ratio >= 1.5 else -3
        elif pname == "涨停双响炮":
            bonus = 7
        elif pname == "底部首板":
            bonus = 6
        elif pname == "双针探底":
            bonus = 5

        # 置信度调整
        if pconf == "高":
            bonus *= 1.2
        elif pconf == "低":
            bonus *= 0.5

        local_bonus += bonus

    # Bug 3 修复：原 clamp(0,10) 会吞掉看跌形态（三阳一阴）的负分，
    # 导致纯看跌场景对评分无惩罚。现允许负分（下限 _SCORE_LOCAL_MIN=-5），
    # 归一化时按 chip 同口径 (val - min) / (max - min) * 100 处理。
    return clamp(local_bonus, _SCORE_LOCAL_MIN, _SCORE_LOCAL_MAX)


def _score_chip(chip_data: dict, type_w: dict) -> float:
    """资金面加分项（上限 +10，下限 -5）。"""
    chip_bonus = 0

    # 融资融券信号（上限 3 分）
    margin = chip_data.get("margin") or {}
    if margin.get("rzjme_5d", 0) > 0:  # 近5日融资净买入为正
        chip_bonus += 2
        if margin.get("rzjme_trend", "") == "连续增加":
            chip_bonus += 1
    elif margin.get("rzjme_5d", 0) < 0:
        chip_bonus -= 1  # 允许负分

    # 股东户数信号（上限 3 分）
    holders = chip_data.get("holders") or {}
    if holders.get("concentration", "") == "持续集中":
        chip_bonus += 3
    elif holders.get("concentration", "") == "提升":
        chip_bonus += 2
    elif holders.get("concentration", "") == "分散":
        chip_bonus -= 1  # 允许负分

    # 筹码分布信号（4分）- Phase 3 实现
    # chip_dist = chip_data.get("chip_dist") or {}
    # profit_ratio = chip_dist.get("profit_ratio", 50)
    # if 40 <= profit_ratio <= 60:
    #     chip_bonus += 2
    # elif profit_ratio > 80:
    #     chip_bonus -= 1
    # elif profit_ratio < 20:
    #     chip_bonus -= 1
    # conc = chip_dist.get("concentration_90", 20)
    # if conc < 10:
    #     chip_bonus += 2
    # elif conc < 15:
    #     chip_bonus += 1

    chip_score = chip_bonus * type_w.get("chip", 1.0)
    # 资金面允许负分惩罚，故下限为 -5 而非 0
    return clamp(chip_score, -5, 10)


def composite_score(
    features, stock_type="普通股", market_state=None, market_breadth=None
):
    """自适应多指标共振评分 0-100，按个股类型和市场环境调整权重。

    采用加权平均法：各子评分先归一化到 [0, 100]，再按类型权重加权平均，
    确保总分严格在 0-100 范围内，无需 clamp 截断。

    Args:
        features: 技术指标特征
        stock_type: 股票类型
        market_state: 市场状态（牛市/熊市/震荡/冰点/亢奋）
        market_breadth: 市场宽度数据（可选）
    """
    type_w = _get_stock_type_weights(stock_type)
    adj = _market_weight_adjustments(market_state or "震荡")

    alignment_scores = _scoring_config("alignment_scores") or _ALIGNMENT_SCORES_DEFAULT

    ma = features.get("ma_system", {})
    macd = features.get("macd") or {}
    kdj = features.get("kdj") or {}
    boll = features.get("bollinger") or {}
    rsi_data = features.get("rsi", {})
    vol = features.get("volume") or {}
    patterns = features.get("patterns", [])

    # 获取量价信号，用于下跌趋势降权
    vol_signal = vol.get("volume_price_signal", 0)

    # 各子评分的理论上限（用于归一化）
    # P1-15: 提取为模块级 _SCORE_MAX_DEFAULT，可通过 scoring.yaml 的 score_max 覆盖。
    # 若 _score_* 的评分逻辑变更（如新增 pattern 扣分项），需同步更新 _SCORE_MAX_DEFAULT
    # 或在 scoring.yaml 的 score_max 中覆盖，否则归一化会饱和或欠饱和。
    _SCORE_MAX = _get_score_max()

    # 计算各子评分原始值
    raw = {
        "ma": _score_ma(ma.get("alignment", ""), type_w, adj, alignment_scores),
        "macd": _score_macd(macd, type_w, adj),
        "kdj": _score_kdj(kdj, type_w, adj, vol_signal),
        "boll": _score_boll(boll, type_w),
        "rsi": _score_rsi(rsi_data, type_w, vol_signal),
        "volume": _score_volume(vol, type_w),
        "pattern": _score_patterns(patterns, type_w, adj),
        "chan": _score_chan(features.get("chan_theory") or {}, type_w, adj),
        "local": _score_local(features.get("local_patterns") or {}),
        "limit": _score_limit(features.get("limit_analysis"), type_w, adj),
        "chip": _score_chip(features.get("chip") or {}, type_w),
        # 估值因子评分（0-100），None 时用中性 50（与下游 max_val=100 兼容）
        "valuation": features.get("valuation_score") or 50,
    }

    # 市场宽度惩罚（徐翔、赵老哥、养家建议）
    breadth_penalty = 0
    if market_breadth:
        limit_up = market_breadth.get("limit_up_count", 0)
        limit_down = market_breadth.get("limit_down_count", 0)
        continuous_height = market_breadth.get("continuous_limit_height", 0)

        # 退潮期惩罚：涨停家数<20家
        if limit_up < 20 and limit_up > 0:
            breadth_penalty += 5

        # 冰点期惩罚：跌停>50家
        if limit_down > 50:
            breadth_penalty += 10

        # 接力生态恶化惩罚：连板高度<2板
        if continuous_height <= 2 and continuous_height > 0:
            breadth_penalty += 3

    # 归一化各子评分到 [0, 100]
    # chip / local / limit 允许负分，按 (val - min) / (max - min) * 100 归一化
    normalized = {}
    for key, val in raw.items():
        max_val = _SCORE_MAX[key]
        if key == "chip":
            # chip 范围 [-5, 10]，归一化到 [0, 100]
            normalized[key] = clamp((val + 5) / 15 * 100, 0, 100)
        elif key == "local":
            # local 范围 [_SCORE_LOCAL_MIN(-5), _SCORE_LOCAL_MAX(10)]，归一化到 [0, 100]
            span = _SCORE_LOCAL_MAX - _SCORE_LOCAL_MIN
            normalized[key] = clamp((val - _SCORE_LOCAL_MIN) / span * 100, 0, 100)
        elif key == "limit":
            # limit 范围 [-3, 15]，归一化到 [0, 100]
            normalized[key] = clamp((val + 3) / 18 * 100, 0, 100)
        else:
            normalized[key] = clamp(val / max_val * 100, 0, 100) if max_val > 0 else 0

    # 加权平均：score = sum(normalized_i × weight_i) / sum(weight_i)
    total_weight = sum(type_w.values())
    if total_weight > 0:
        score = (
            sum(normalized[k] * type_w.get(k, 1.0) for k in normalized) / total_weight
        )
    else:
        score = sum(normalized.values()) / len(normalized)

    # 应用市场宽度惩罚（按比例扣分，保持 0-100 范围）
    score = clamp(score - breadth_penalty, 0, 100)

    if score >= 80:
        grade = "强烈看多"
    elif score >= 75:
        grade = "偏多(强)"  # 模糊区间：75-80
    elif score >= 60:
        grade = "偏多"
    elif score >= 55:
        grade = "中性(偏多)"  # 模糊区间：55-65
    elif score >= 40:
        grade = "中性"
    elif score >= 35:
        grade = "中性(偏空)"  # 模糊区间：35-45
    elif score >= 20:
        grade = "偏空"
    elif score >= 15:
        grade = "偏空(强)"  # 模糊区间：15-25
    else:
        grade = "强烈看空"

    buy_signals, sell_signals, structured_signals = _generate_signals(
        features, market_breadth
    )

    return {
        "score": round(score, 1),
        "grade": grade,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "structured_signals": structured_signals,
    }


def detect_market_environment(index_quote=None, recent_quotes=None):
    """
    检测当前市场环境（牛市/熊市/震荡/冰点/亢奋）。
    优先使用大盘数据（涨跌停家数），不可得时用指数技术指标推断。
    支持多日窗口判断，避免单日噪声。

    Args:
        index_quote: 大盘指数行情 dict（可选）
        recent_quotes: 近期大盘行情列表（可选，用于多日均值判断）

    Returns:
        {
            "state": "牛市"|"熊市"|"震荡"|"冰点"|"亢奋",
            "confidence": "高"|"中"|"低",
            "signals": [...],
            "weight_adjustments": {...},
        }
    """
    state = "震荡"
    confidence = "低"
    signals = []

    if index_quote and isinstance(index_quote, dict):
        _price = to_float(index_quote.get("price"))
        change_pct = to_float(index_quote.get("change_pct"))
        turnover = to_float(index_quote.get("turnover"))

        # 多日窗口：用近期数据的均值平滑单日噪声
        has_multi_day = bool(recent_quotes and len(recent_quotes) > 1)
        if has_multi_day:
            recent_changes = [to_float(q.get("change_pct")) for q in recent_quotes]
            recent_turnovers = [to_float(q.get("turnover")) for q in recent_quotes]
            avg_change = sum(recent_changes) / len(recent_changes)
            avg_turnover = sum(recent_turnovers) / len(recent_turnovers)
            window_days = len(recent_quotes)
            signals.append(f"近{window_days}日均涨跌{avg_change:.2f}%")
        else:
            avg_change = change_pct
            avg_turnover = turnover

        # 用多日均值判断趋势
        if avg_change > 1.5:
            state = "牛市"
            if avg_change > 2.5:
                confidence = "高" if has_multi_day else "中"
            else:
                confidence = "中" if has_multi_day else "低"
            if not has_multi_day:
                signals.append(f"单日大涨(均值{avg_change:.1f}%,趋势待确认)")
            else:
                signals.append(f"持续上涨(均值{avg_change:.1f}%)")
        elif avg_change < -1.5:
            state = "熊市"
            if avg_change < -2.5:
                confidence = "高" if has_multi_day else "中"
            else:
                confidence = "中" if has_multi_day else "低"
            if not has_multi_day:
                signals.append(f"单日大跌(均值{avg_change:.1f}%,趋势待确认)")
            else:
                signals.append(f"持续下跌(均值{avg_change:.1f}%)")
        elif avg_change > 0.5:
            state = "牛市"
            confidence = "低"
            signals.append(f"温和上涨(均值{avg_change:.1f}%)")
        elif avg_change < -0.5:
            state = "熊市"
            confidence = "低"
            signals.append(f"温和下跌(均值{avg_change:.1f}%)")
        else:
            signals.append(f"窄幅震荡(均值{avg_change:.1f}%)")

        # 用当日数据补充极端信号
        if change_pct > 2:
            signals.append(f"当日大涨{change_pct:.1f}%")
        elif change_pct < -2:
            signals.append(f"当日大跌{change_pct:.1f}%")

        if avg_turnover > 5:
            signals.append("高换手率")
            if state == "牛市":
                state = "亢奋"
                signals.append("亢奋信号")
        elif avg_turnover < 0.5:
            signals.append("极度缩量")
            if state in ("熊市", "震荡"):
                state = "冰点"
                signals.append("冰点信号")
    else:
        signals.append("大盘数据缺失，默认震荡")

    # 市场 → 信号权重调整
    adjustments = _market_weight_adjustments(state)

    return {
        "state": state,
        "confidence": confidence,
        "signals": signals,
        "weight_adjustments": adjustments,
    }


def _market_weight_adjustments(state):
    """市场环境 → 信号权重因子。v1.3.2：从 config/scoring.yaml::market_weights 加载。"""
    cfg = _scoring_config("market_weights") or {}
    if state in cfg:
        return cfg[state]
    return _MARKET_WEIGHT_ADJUSTMENTS_DEFAULT.get(
        state, _MARKET_WEIGHT_ADJUSTMENTS_DEFAULT["震荡"]
    )


_ALIGNMENT_SCORES_DEFAULT = {
    "多头排列": 20,
    "交叉震荡": 12,
    "空头排列": 3,
    "数据不足": 7,
}


_MARKET_WEIGHT_ADJUSTMENTS_DEFAULT = {
    "牛市": {
        "bullish_bias": 1.3,
        "trend_following": 1.4,
        "breakout": 1.3,
        "divergence_bottom": 0.5,
        "buy_point_1": 0.5,
        "buy_point_3": 1.3,
        "overbought": 0.8,
        "desc": "牛市：趋势跟随加权，底背离/一买降权",
    },
    "熊市": {
        "bullish_bias": 1.5,
        "trend_following": 0.6,
        "breakout": 0.6,
        "divergence_bottom": 1.5,
        "buy_point_1": 1.5,
        "buy_point_3": 0.5,
        "overbought": 1.3,
        "desc": "熊市：反转信号加权，追涨信号降权",
    },
    "震荡": {
        "bullish_bias": 1.0,
        "trend_following": 0.8,
        "breakout": 0.8,
        "divergence_bottom": 1.2,
        "buy_point_1": 1.1,
        "buy_point_3": 1.2,
        "overbought": 1.0,
        "desc": "震荡：反转+区间交易加权，趋势信号降权",
    },
    "冰点": {
        "bullish_bias": 1.8,
        "trend_following": 0.3,
        "breakout": 0.4,
        "divergence_bottom": 1.8,
        "buy_point_1": 2.0,
        "buy_point_3": 0.3,
        "overbought": 1.5,
        "desc": "冰点：极度超卖反转加权，趋势信号大幅降权",
    },
    "亢奋": {
        "bullish_bias": 0.6,
        "trend_following": 0.5,
        "breakout": 0.5,
        "divergence_bottom": 0.4,
        "buy_point_1": 0.3,
        "buy_point_3": 0.5,
        "overbought": 0.3,
        "desc": "亢奋：全面保守，警惕反转",
    },
}

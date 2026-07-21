"""
个股分析业务流程 (Business 层)。

聚合技术分析、财务分析、缠论分析等模块，提供统一的分析入口。

P2-21: StockAnalysisService 基本无状态（仅 min_kline_days 常量），
现提供模块级 analyze() 快捷入口，无需实例化即可调用。
StockAnalysisService 类保留向后兼容，内部委托给模块函数。
"""

import logging
from typing import Dict, Any

from common import get_shared_executor
from common.exceptions import ValidationError
from common.validators import normalize_code, validate_code
from data import get_quote, get_kline, get_finance
from classifier import profile_stock

logger = logging.getLogger(__name__)

# 缠论分析最少需要 30 根 K 线
_MIN_KLINE_DAYS = 30


class StockAnalysisService:
    """个股分析服务。

    P2-21: 该类基本无状态，min_kline_days 已提升为模块常量。
    保留类以兼容现有调用方（stock.py 实例化使用），推荐新代码直接用
    模块级 ``analyze()`` 入口。
    """

    def __init__(self):
        self.min_kline_days = _MIN_KLINE_DAYS

    def analyze(
        self,
        code: str,
        include_technical: bool = True,
        include_finance: bool = True,
        include_chan: bool = True,
        finance_periods: int = 4,
    ) -> Dict[str, Any]:
        """完整分析一只股票（委托模块级 _analyze）。

        Args:
            finance_periods: 财务数据期数（默认 4；full/debate 模式传 8 以覆盖累计同比 vs
                单季度同比的口径差异，详见 2026-07-09 宝丰能源复盘）。
        """
        return _analyze(
            code,
            include_technical=include_technical,
            include_finance=include_finance,
            include_chan=include_chan,
            finance_periods=finance_periods,
        )


def _normalize_code(code: str) -> str:
    """标准化股票代码。"""
    if not validate_code(code):
        raise ValidationError("code", code, "格式无效")
    return normalize_code(code)


def _analyze(
    code: str,
    include_technical: bool = True,
    include_finance: bool = True,
    include_chan: bool = True,
    finance_periods: int = 4,
) -> Dict[str, Any]:
    """完整分析一只股票。

    Args:
        code: 股票代码
        include_technical: 是否包含技术分析
        include_finance: 是否包含财务分析
        include_chan: 是否包含缠论分析
        finance_periods: 财务期数（4 = 最近四季；8 = full/debate 推荐）

    Returns:
        分析结果字典
    """
    # 验证输入
    code = _normalize_code(code)

    result = {
        "code": code,
        "name": "",
        "price": 0,
        "change_pct": 0,
        "data_warnings": [],
        # P0-02: 数据来源元信息（供 stock.py footer 使用，避免回退 now_str/硬编码源名）
        "data_sources": [],
        "data_failed": [],
        "data_time": "",
    }

    # 1. 并行获取三类数据 + 大盘指数行情（无依赖关系，可同时拉取）
    ex = get_shared_executor()
    f_quote = ex.submit(get_quote, code)
    f_kline = ex.submit(get_kline, code, 240, 240)
    f_finance = (
        ex.submit(get_finance, code, periods=finance_periods)
        if include_finance
        else None
    )
    # P1-17: 并行拉取上证指数行情，用于 detect_market_environment
    f_index = ex.submit(get_quote, "sh000001")

    try:
        quote = f_quote.result(timeout=15)
    except Exception as e:
        logger.warning("获取行情失败 %s: %s", code, e)
        result["data_warnings"].append(
            f"⚠ 行情数据获取失败（{type(e).__name__}），以下分析可能不完整"
        )
        result["data_failed"].append("行情")
        quote = None
    else:
        if quote:
            result["data_sources"].append("行情")
    try:
        kline = f_kline.result(timeout=30)
    except Exception as e:
        logger.warning("获取K线失败 %s: %s", code, e)
        result["data_warnings"].append(
            f"⚠ K线数据获取失败（{type(e).__name__}），技术面分析将跳过"
        )
        result["data_failed"].append("K线")
        kline = None
    else:
        if kline:
            result["data_sources"].append("K线")
    try:
        finance = f_finance.result(timeout=45) if f_finance else None
    except Exception as e:
        logger.warning("获取财务数据失败 %s: %s", code, e)
        result["data_warnings"].append(
            f"⚠ 财务数据获取失败（{type(e).__name__}），基本面分析将跳过"
        )
        result["data_failed"].append("财务")
        finance = None
    else:
        if finance:
            result["data_sources"].append("财务")
    # 大盘指数行情（P1-17: 不再用个股 quote 当指数 quote）
    index_quote = None
    try:
        index_quote = f_index.result(timeout=15)
    except Exception as e:
        logger.debug("获取大盘指数行情失败: %s", e)

    # P0-02: 提取数据时间戳（优先用 quote.fetch_time，无则用 K线最后一根 day）
    if quote and getattr(quote, "fetch_time", ""):
        result["data_time"] = quote.fetch_time
    elif kline and len(kline) > 0:
        last_day = getattr(kline[-1], "day", "")
        if last_day:
            result["data_time"] = last_day

    # 2. 行情和画像
    if quote:
        result["name"] = quote.name
        result["price"] = quote.price
        result["change_pct"] = quote.change_pct
        result["profile"] = profile_stock(
            quote.to_dict(),
            fetcher_industry=getattr(quote, "industry", "") or "",
        )

    # 3. K线分析
    if not kline or len(kline) < 10:
        logger.warning(f"K线数据不足: {code}")
        result["warning"] = "K线数据不足"
        result["data_warnings"].append(
            f"⚠ K线数据不足（{len(kline) if kline else 0}根，需≥10根），技术面分析将跳过"
        )
    else:
        result["kline_count"] = len(kline)

        if include_technical:
            result["technical"] = _analyze_technical(kline)

        if include_chan and len(kline) >= _MIN_KLINE_DAYS:
            result["chan"] = _analyze_chan([b.to_dict() for b in kline])

    # 4. 财务数据
    if finance:
        result["finance"] = _extract_finance_summary(finance[0].to_dict())
    elif include_finance:
        result["data_warnings"].append("⚠ 财务数据不可用，基本面分析将跳过")

    # 5. 综合评分
    if "technical" in result and "profile" in result:
        quote_dict = quote.to_dict() if quote else {}
        # P1-17: 传入真实大盘指数行情（sh000001），而非个股 quote
        result["score"] = _calculate_composite_score(
            result, quote_dict, index_quote=index_quote
        )

    return result


def _analyze_technical(kline: list) -> dict:
    """技术分析（接收 KlineBar 对象列表）。"""
    from technical.pipeline import compute_indicators
    from technical import ma_system, kdj_full, bollinger, detect_candle_patterns

    indicators = compute_indicators(kline)
    # 与 screening_service.compute_features 保持一致：过滤 close=0 的无效记录
    closes = [c for c in indicators.get("closes", []) if c > 0]
    highs = [b.high for b in kline if b.high > 0]
    lows = [b.low for b in kline if b.low > 0]

    result = {}
    ma = ma_system(closes)
    result["ma"] = ma.get("alignment", "数据不足")
    result["macd_signal"] = indicators.get("macd_signal", 0)
    result["macd_divergence"] = ""

    kdj = kdj_full(closes, highs, lows) or {}
    result["kdj"] = kdj.get("signal", "")

    boll = bollinger(closes)
    result["boll_position"] = boll.get("position", 0.5)
    result["rsi"] = indicators.get("rsi", 50)
    result["volume_signal"] = indicators.get("vol_price_signal", 0)

    patterns = detect_candle_patterns([b.to_dict() for b in kline])
    result["patterns"] = patterns[:5] if patterns else []

    return result


def _analyze_chan(kline: list) -> dict:
    """缠论分析。"""
    from chan import chan_full_analysis

    try:
        return chan_full_analysis(kline)
    except (ValueError, KeyError, RuntimeError, TypeError) as e:
        logger.warning(f"缠论分析失败: {e}")
        return {"error": str(e)}


def _extract_finance_summary(fin: dict) -> dict:
    """提取财务摘要。

    WP2: 缺数据字段保持 None（不再默认 0），让下游明确感知"未披露"。
    stock.py 等渲染层有 _f2 / _f_brief 守卫处理 None。
    """
    return {
        "eps": fin.get("eps"),
        "roe": fin.get("roe"),
        "net_profit_yoy": fin.get("net_profit_yoy"),
        "revenue_yoy": fin.get("revenue_yoy"),
        "gross_margin": fin.get("gross_margin"),
        "debt_ratio": fin.get("debt_ratio"),
    }


def _calculate_composite_score(
    result: dict, quote_dict: dict = None, index_quote=None
) -> dict:
    """计算综合评分（注入市场环境状态）。"""
    from technical import composite_score
    from technical.scoring import detect_market_environment
    from common import to_float

    tech = result.get("technical", {})
    profile = result.get("profile", {})
    fin = result.get("finance", {})

    features = {
        "ma_system": {"alignment": tech.get("ma", "数据不足")},
        "macd": {
            "signal": tech.get("macd_signal", 0),
            "divergence": tech.get("macd_divergence", ""),
        },
        "kdj": {"signal": tech.get("kdj", "")},
        "bollinger": {"position": tech.get("boll_position", 0.5)},
        "rsi": {"rsi": tech.get("rsi", 50)},
        "volume": {"volume_price_signal": tech.get("volume_signal", 0)},
        "patterns": tech.get("patterns", []),
    }

    # 估值数据注入（反追涨杀跌）
    if quote_dict:
        from strategies.factors.score_utils import pe_percentile
        from strategies.factors.valuation import valuation_score

        pe = to_float(quote_dict.get("pe"))
        pb = to_float(quote_dict.get("pb"))
        industry = profile.get("industry", "默认")
        pe_pct = pe_percentile(pe, industry)
        # PEG：用净利同比增速（net_profit_yoy）。
        # 注：FinanceRecord 暂无 3 年 CAGR 字段（多期绝对值未采集），
        # 故用单期 yoy 近似；未来补全多期数据后再升级为 3 年 CAGR。
        # WP2: net_profit_yoy 可能为 None（缺数据）—— to_float 会安全返回 0.0
        growth = to_float(fin.get("net_profit_yoy"))
        peg = (pe / growth) if (pe > 0 and growth is not None and growth > 0) else 0
        features["valuation"] = {
            "pe": pe,
            "pb": pb,
            "pe_percentile": round(pe_pct, 1),
            "peg": round(peg, 2),
        }
        # 估值因子评分纳入综合评分（v2.3.0 修正：估值不再与技术面脱节）
        features["valuation_score"] = valuation_score(quote_dict, fin, industry)

    # 检测市场环境：复用已获取的大盘行情，避免重复请求
    market_state = "震荡"
    try:
        if index_quote is None:
            index_quote = get_quote("sh000001")
        if index_quote:
            env = detect_market_environment(index_quote.to_dict())
            market_state = env.get("state", "震荡")
            logger.debug(
                "市场环境: %s (置信度: %s)", market_state, env.get("confidence")
            )
    except Exception as e:
        logger.debug("获取大盘行情失败，使用默认市场环境: %s", e)

    stock_type = profile.get("type", "普通股")
    score_result = composite_score(
        features, stock_type=stock_type, market_state=market_state
    )

    return score_result


# P2-21: 模块级快捷入口，无需实例化 StockAnalysisService
def analyze(
    code: str,
    include_technical: bool = True,
    include_finance: bool = True,
    include_chan: bool = True,
    finance_periods: int = 4,
) -> Dict[str, Any]:
    """完整分析一只股票（模块级快捷入口，等价于 StockAnalysisService().analyze()）。

    Args:
        finance_periods: 财务数据期数（默认 4；full/debate 模式传 8）
    """
    return _analyze(
        code,
        include_technical=include_technical,
        include_finance=include_finance,
        include_chan=include_chan,
        finance_periods=finance_periods,
    )


__all__ = ["StockAnalysisService", "analyze"]

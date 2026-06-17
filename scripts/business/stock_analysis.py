"""
个股分析业务流程 (Business 层)。

聚合技术分析、财务分析、缠论分析等模块，提供统一的分析入口。
"""

import logging
from typing import Optional, Dict, Any, List

from common.exceptions import InsufficientDataError, ValidationError
from common.validators import normalize_code, validate_code
from data import get_quote, get_kline, get_finance
from classifier import profile_stock

logger = logging.getLogger(__name__)


class StockAnalysisService:
    """个股分析服务。"""

    def __init__(self):
        self.min_kline_days = 30  # 缠论分析最少需要30根K线

    def analyze(
        self,
        code: str,
        include_technical: bool = True,
        include_finance: bool = True,
        include_chan: bool = True,
    ) -> Dict[str, Any]:
        """
        完整分析一只股票。

        Args:
            code: 股票代码
            include_technical: 是否包含技术分析
            include_finance: 是否包含财务分析
            include_chan: 是否包含缠论分析

        Returns:
            分析结果字典
        """
        # 验证输入
        code = self._normalize_code(code)

        result = {
            "code": code,
            "name": "",
            "price": 0,
            "change_pct": 0,
        }

        # 1. 获取实时行情
        quote = get_quote(code)
        if quote:
            result["name"] = quote.name
            result["price"] = quote.price
            result["change_pct"] = quote.change_pct

        # 2. 行业和类型画像
        if quote:
            result["profile"] = profile_stock(quote.to_dict())

        # 3. K线数据
        kline = get_kline(code, scale=240, datalen=120)
        if not kline or len(kline) < 10:
            logger.warning(f"K线数据不足: {code}")
            result["warning"] = "K线数据不足"
        else:
            result["kline_count"] = len(kline)

            # 技术分析
            if include_technical:
                result["technical"] = self._analyze_technical(kline)

            # 缠论分析
            if include_chan and len(kline) >= self.min_kline_days:
                result["chan"] = self._analyze_chan([b.to_dict() for b in kline])

        # 4. 财务数据
        if include_finance:
            finance = get_finance(code)
            if finance:
                result["finance"] = self._extract_finance_summary(finance[0].to_dict())

        # 5. 综合评分
        if "technical" in result and "profile" in result:
            quote_dict = quote.to_dict() if quote else {}
            result["score"] = self._calculate_composite_score(result, quote_dict)

        return result

    def _normalize_code(self, code: str) -> str:
        """标准化股票代码。"""
        if not validate_code(code):
            raise ValidationError("code", code, "格式无效")
        return normalize_code(code)

    def _analyze_technical(self, kline: list) -> dict:
        """技术分析（接收 KlineBar 对象列表）。"""
        from technical.pipeline import compute_indicators
        from technical import ma_system, kdj_full, bollinger, detect_candle_patterns

        indicators = compute_indicators(kline)
        closes = indicators.get("closes", [])
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

    def _analyze_chan(self, kline: list) -> dict:
        """缠论分析。"""
        from chan import chan_full_analysis

        try:
            return chan_full_analysis(kline)
        except (ValueError, KeyError, RuntimeError, TypeError) as e:
            logger.warning(f"缠论分析失败: {e}")
            return {"error": str(e)}

    def _extract_finance_summary(self, fin: dict) -> dict:
        """提取财务摘要。"""
        return {
            "eps": fin.get("eps", 0),
            "roe": fin.get("roe", 0),
            "net_profit_yoy": fin.get("net_profit_yoy", 0),
            "revenue_yoy": fin.get("revenue_yoy", 0),
            "gross_margin": fin.get("gross_margin", 0),
            "debt_ratio": fin.get("debt_ratio", 0),
        }

    def _calculate_composite_score(self, result: dict, quote_dict: dict = None) -> dict:
        """计算综合评分。"""
        from technical import composite_score
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
            pe = to_float(quote_dict.get("pe"))
            pb = to_float(quote_dict.get("pb"))
            if pe > 0:
                try:
                    from strategies.thresholds import get_industry_threshold

                    industry = profile.get("industry", "默认")
                    pe_low = get_industry_threshold(industry, "pe_undervalued", 15)
                    pe_mid = get_industry_threshold(industry, "pe_reasonable", 25)
                    pe_high = get_industry_threshold(industry, "pe_expensive", 40)
                except Exception:
                    pe_low, pe_mid, pe_high = 15, 25, 40
                if pe <= pe_low:
                    pe_pct = 15
                elif pe <= pe_mid:
                    pe_pct = 15 + (pe - pe_low) / (pe_mid - pe_low) * 35
                elif pe <= pe_high:
                    pe_pct = 50 + (pe - pe_mid) / (pe_high - pe_mid) * 30
                else:
                    pe_pct = min(95, 80 + (pe - pe_high) / pe_high * 20)
            else:
                pe_pct = 50
            growth = to_float(fin.get("net_profit_yoy", 0))
            peg = (pe / growth) if (pe > 0 and growth > 0) else 0
            features["valuation"] = {
                "pe": pe,
                "pb": pb,
                "pe_percentile": round(pe_pct, 1),
                "peg": round(peg, 2),
            }

        stock_type = profile.get("type", "普通股")
        score_result = composite_score(features, stock_type=stock_type)

        return score_result


__all__ = ["StockAnalysisService"]

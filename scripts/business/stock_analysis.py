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
    
    def analyze(self, code: str, include_technical: bool = True, 
                include_finance: bool = True, include_chan: bool = True) -> Dict[str, Any]:
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
            kline_dicts = [b.to_dict() for b in kline]
            result["kline_count"] = len(kline_dicts)
            
            # 技术分析
            if include_technical:
                result["technical"] = self._analyze_technical(kline_dicts)
            
            # 缠论分析
            if include_chan and len(kline) >= self.min_kline_days:
                result["chan"] = self._analyze_chan(kline_dicts)
        
        # 4. 财务数据
        if include_finance:
            finance = get_finance(code)
            if finance:
                result["finance"] = self._extract_finance_summary(finance[0].to_dict())
        
        # 5. 综合评分
        if "technical" in result and "profile" in result:
            result["score"] = self._calculate_composite_score(result)
        
        return result
    
    def _normalize_code(self, code: str) -> str:
        """标准化股票代码。"""
        if not validate_code(code):
            raise ValidationError("code", code, "格式无效")
        return normalize_code(code)
    
    def _analyze_technical(self, kline: List[dict]) -> dict:
        """技术分析。"""
        from technical import (
            ma_system, macd_full, kdj_full, bollinger, 
            rsi_features, volume_analysis, detect_candle_patterns
        )
        
        closes = [k["close"] for k in kline if k.get("close", 0) > 0]
        highs = [k["high"] for k in kline if k.get("high", 0) > 0]
        lows = [k["low"] for k in kline if k.get("low", 0) > 0]
        volumes = [k["volume"] for k in kline if k.get("volume", 0) > 0]
        
        result = {}
        
        # 均线系统
        ma = ma_system(closes)
        result["ma"] = ma.get("alignment", "数据不足")
        
        # MACD
        macd = macd_full(closes) or {}
        result["macd_signal"] = macd.get("signal", 0)
        result["macd_divergence"] = macd.get("divergence", "")
        
        # KDJ
        kdj = kdj_full(closes)
        result["kdj"] = kdj.get("signal", "")
        
        # BOLL
        boll = bollinger(closes)
        result["boll_position"] = boll.get("position", 0.5)
        
        # RSI
        rsi = rsi_features(closes)
        result["rsi"] = rsi.get("rsi", 50)
        
        # 成交量
        vol = volume_analysis(closes, volumes)
        result["volume_signal"] = vol.get("volume_price_signal", 0)
        
        # K线形态
        patterns = detect_candle_patterns(kline)
        result["patterns"] = patterns[:5] if patterns else []
        
        return result
    
    def _analyze_chan(self, kline: List[dict]) -> dict:
        """缠论分析。"""
        from chan import chan_full_analysis
        
        try:
            analysis = chan_full_analysis(kline)
            return analysis
        except Exception as e:
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
    
    def _calculate_composite_score(self, result: dict) -> dict:
        """计算综合评分。"""
        from technical import composite_score, detect_market_environment
        
        tech = result.get("technical", {})
        profile = result.get("profile", {})
        
        features = {
            "ma_system": {"alignment": tech.get("ma", "数据不足")},
            "macd": {"signal": tech.get("macd_signal", 0), "divergence": tech.get("macd_divergence", "")},
            "kdj": {"signal": tech.get("kdj", "")},
            "bollinger": {"position": tech.get("boll_position", 0.5)},
            "rsi": {"rsi": tech.get("rsi", 50)},
            "volume": {"volume_price_signal": tech.get("volume_signal", 0)},
            "patterns": tech.get("patterns", []),
        }
        
        stock_type = profile.get("type", "普通股")
        score_result = composite_score(features, stock_type=stock_type)
        
        return score_result


__all__ = ["StockAnalysisService"]

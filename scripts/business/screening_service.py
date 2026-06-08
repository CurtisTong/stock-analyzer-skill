"""
选股服务 (Business 层)。

提供选股筛选的业务逻辑，与 CLI 层解耦。
"""
import logging
from typing import List, Dict, Any, Optional

from common import to_float, normalize_quote_code, board_type
from common.exceptions import InsufficientDataError, ValidationError
from common.validators import validate_code
from data import get_quote, get_quotes, get_kline, get_finance
from classifier import infer_industry
from strategies import (
    STRATEGIES, 
    quality_score, 
    valuation_score, 
    momentum_score, 
    liquidity_score,
    volatility_from_closes
)
from strategies.thresholds import get_industry_threshold

logger = logging.getLogger(__name__)


class ScreeningService:
    """选股服务。"""
    
    def __init__(self):
        self.default_strategy = "balanced"
        self.max_workers = 8
    
    def screen(
        self, 
        codes: List[str], 
        strategy: str = "balanced",
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        选股筛选。
        
        Args:
            codes: 股票代码列表
            strategy: 策略名称
            filters: 筛选条件
            
        Returns:
            筛选结果列表
        """
        filters = filters or {}
        
        # 验证策略
        if strategy not in STRATEGIES:
            logger.warning(f"未知策略 {strategy}，使用默认策略")
            strategy = self.default_strategy
        
        # 标准化代码
        normalized_codes = []
        for c in codes:
            try:
                if validate_code(c):
                    normalized_codes.append(normalize_quote_code(c))
            except ValidationError:
                logger.warning(f"跳过无效代码: {c}")
        
        if not normalized_codes:
            return []
        
        # 获取行情数据
        quotes = get_quotes(normalized_codes)
        quote_map = {q.code: q for q in quotes}
        
        # 预获取财务数据
        fin_cache = self._prefetch_finance(normalized_codes)
        
        # 分析每只股票
        results = []
        for code in normalized_codes:
            quote = quote_map.get(code)
            if not quote:
                continue
            
            try:
                stock_result = self._analyze_stock(
                    code, 
                    quote, 
                    fin_cache.get(code, []),
                    strategy,
                    filters
                )
                if stock_result:
                    results.append(stock_result)
            except Exception as e:
                logger.warning(f"分析失败 {code}: {e}")
                continue
        
        # 排序
        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        
        return results
    
    def _prefetch_finance(self, codes: List[str]) -> Dict[str, List[dict]]:
        """预获取财务数据。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from data import get_finance
        from common import normalize_finance_code
        
        results = {}
        
        def fetch_one(code):
            try:
                records = get_finance(normalize_finance_code(code))
                return code, [r.to_dict() for r in records]
            except Exception:
                return code, []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = {ex.submit(fetch_one, c): c for c in codes}
            for future in as_completed(futures):
                try:
                    code, data = future.result()
                    results[code] = data
                except Exception:
                    pass
        
        return results
    
    def _analyze_stock(
        self, 
        code: str, 
        quote, 
        fin_records: List[dict],
        strategy: str,
        filters: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """分析单只股票。"""
        quote_dict = quote.to_dict()
        fin = fin_records[0] if fin_records else {}
        
        # 行业分类
        industry = infer_industry(quote_dict.get("name", ""), code)
        
        # 硬过滤
        rejected = self._hard_filter(quote_dict, fin, filters)
        if rejected:
            return {
                "code": code,
                "name": quote_dict.get("name", ""),
                "score": 0,
                "rejected": rejected,
            }
        
        # 计算因子得分
        features = self._compute_features(code)
        
        weights = STRATEGIES[strategy]
        parts = {
            "quality": quality_score(fin, industry),
            "valuation": valuation_score(quote_dict, fin, industry),
            "momentum": momentum_score(features, quote_dict),
            "liquidity": liquidity_score(quote_dict),
            "volatility": volatility_from_closes(features.get("closes", []), industry),
        }
        
        total = sum(
            parts.get(k, 0) * weights.get(k, 0) 
            for k in set(parts) | set(weights) 
            if k != "label"
        )
        
        return {
            "code": code,
            "name": quote_dict.get("name", ""),
            "board": board_type(code),
            "industry": industry,
            "score": round(total, 1),
            "quality": round(parts["quality"], 1),
            "valuation": round(parts["valuation"], 1),
            "momentum": round(parts["momentum"], 1),
            "liquidity": round(parts["liquidity"], 1),
            "volatility": round(parts["volatility"], 1),
            "price": quote_dict.get("price"),
            "change_pct": quote_dict.get("change_pct"),
            "pe": quote_dict.get("pe"),
            "pb": quote_dict.get("pb"),
            "roe": fin.get("roe", "-"),
            "profit_growth": fin.get("net_profit_yoy", "-"),
            "ret20": round(features.get("ret20", 0), 1),
            "trend": "上升" if features.get("trend", 0) > 0 else "下降" if features.get("trend", 0) < 0 else "震荡",
            "rsi": features.get("rsi", 50),
            "macd_signal": features.get("macd_signal", 0),
            "rejected": [],
        }
    
    def _compute_features(self, code: str) -> dict:
        """计算技术指标特征。"""
        import statistics
        from technical import macd_full, rsi_features
        from data import get_kline
        
        bars = get_kline(code, scale=240, datalen=240)
        closes = [b.close for b in bars if b.close > 0]
        volumes = [b.volume for b in bars if b.volume > 0]
        
        if len(closes) < 10:
            return {"trend": 0, "ret20": 0, "rsi": 50, "macd_signal": 0}
        
        # 趋势
        ma10 = statistics.mean(closes[-10:])
        ma20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else statistics.mean(closes)
        trend = 1 if closes[-1] > ma10 > ma20 else (-1 if closes[-1] < ma10 < ma20 else 0)
        
        # 20日收益率
        base = closes[-21] if len(closes) >= 21 else closes[0]
        ret20 = (closes[-1] / base - 1) * 100 if base else 0
        
        # RSI
        rsi_data = rsi_features(closes)
        rsi = rsi_data.get("rsi", 50)
        
        # MACD
        macd = macd_full(closes) or {}
        macd_signal = macd.get("signal", 0)
        
        return {
            "trend": trend,
            "ret20": ret20,
            "rsi": rsi,
            "macd_signal": macd_signal,
            "closes": closes,
        }
    
    def _hard_filter(self, quote: dict, fin: dict, filters: dict) -> List[str]:
        """硬过滤。"""
        reasons = []
        name = quote.get("name", "")
        code = quote.get("code", "")
        bd = board_type(code)
        
        # ST 检测
        if name.upper().startswith(("ST", "*ST")):
            reasons.append("ST风险")
        
        # 最低市值
        min_cap = filters.get("min_cap", 40)
        if bd == "创业板" or bd == "科创板":
            min_cap = min_cap * 0.6
        elif bd == "北交所":
            min_cap = min_cap * 0.4
        
        if to_float(quote.get("total_cap", 0)) < min_cap:
            reasons.append(f"市值<{min_cap}亿")
        
        # 最低成交额
        min_amount = filters.get("min_amount", 5000)
        if to_float(quote.get("amount", 0)) < min_amount:
            reasons.append(f"成交额<{min_amount}万")
        
        # 排除亏损
        if filters.get("exclude_loss") and to_float(fin.get("eps", 0)) <= 0:
            reasons.append("EPS<=0")
        
        return reasons


__all__ = ["ScreeningService"]

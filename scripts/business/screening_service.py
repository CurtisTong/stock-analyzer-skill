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

# 尝试加载 config（可选；缺失时回退到硬编码默认）
try:
    from config import get_limit_config
    _USE_CONFIG = True
except ImportError:
    _USE_CONFIG = False


def _limit(key: str, default):
    """读取 limits.yaml 中的阈值；无 config 时回退到硬编码默认。"""
    if _USE_CONFIG:
        return get_limit_config(key, default)
    return default


def _board_limit(board: str) -> float:
    """获取板块涨跌停限制（%）。"""
    return _limit(f"board_limits.{board}", {
        "主板": 9.5, "创业板": 19.5, "科创板": 19.5, "北交所": 29.5,
    }.get(board, 9.5))


def _min_survival_cap(board: str) -> float:
    """获取板块最低生存市值（亿），低于此视为退市风险。"""
    return _limit(f"min_survival_cap.{board}", {
        "主板": 3, "创业板": 2, "科创板": 2, "北交所": 1,
    }.get(board, 3))


def _goodwill_threshold() -> float:
    return _limit("goodwill_ratio_warning", 30)


def _pledge_threshold() -> float:
    return _limit("pledge_ratio_warning", 70)


def _st_prefixes() -> list:
    return _limit("st_prefixes", ["ST", "*ST"])


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
        # quote.code 是纯数字（如 "600519"），normalized_codes 带 sh/sz 前缀
        # 用 normalize_quote_code 做反向映射，保证 lookup 命中
        quote_map = {normalize_quote_code(q.code): q for q in quotes}

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

        # 涨跌停过滤：T+1 下当日无法交易
        bd = board_type(code)
        limit = _board_limit(bd)
        if abs(to_float(quote_dict.get("change_pct", 0))) >= limit:
            return {
                "code": code,
                "name": quote_dict.get("name", ""),
                "score": 0,
                "rejected": ["涨跌停限制"],
            }

        return {
            "code": code,
            "name": quote_dict.get("name", ""),
            "board": bd,
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
            "roe": fin.get("roe", fin.get("ROEJQ", "-")),
            "profit_growth": fin.get("net_profit_yoy", fin.get("PARENTNETPROFITTZ", "-")),
            "ret20": round(features.get("ret20", 0), 1),
            "trend": "上升" if features.get("trend", 0) > 0 else "下降" if features.get("trend", 0) < 0 else "震荡",
            "rsi": features.get("rsi", 50),
            "macd_signal": features.get("macd_signal", 0),
            "vol_price": self._vol_price_signal_desc(features.get("vol_price_signal", 0)),
            "rejected": [],
        }

    @staticmethod
    def _vol_price_signal_desc(signal: int) -> str:
        return "配合" if signal > 0 else "背离" if signal < 0 else "中性"

    def _compute_features(self, code: str) -> dict:
        """计算技术指标特征。"""
        import statistics
        from technical import macd_full, rsi_features
        from data import get_kline

        bars = get_kline(code, scale=240, datalen=240)
        closes = [b.close for b in bars if b.close > 0]
        volumes = [b.volume for b in bars if b.volume > 0]

        if len(closes) < 10:
            return {"trend": 0, "ret20": 0, "rsi": 50, "macd_signal": 0, "vol_price_signal": 0}

        # 趋势
        ma10 = statistics.mean(closes[-10:])
        ma20 = statistics.mean(closes[-20:]) if len(closes) >= 20 else statistics.mean(closes)
        trend = 1 if closes[-1] > ma10 > ma20 else (-1 if closes[-1] < ma10 < ma20 else 0)

        # 20日收益率
        base = closes[-21] if len(closes) >= 21 else closes[0]
        ret20 = (closes[-1] / base - 1) * 100 if base else 0

        # 量比
        recent_vol = statistics.mean(volumes[-5:]) if len(volumes) >= 5 else 0
        base_vol = statistics.mean(volumes[-20:-5]) if len(volumes) >= 20 else recent_vol
        volume_ratio = recent_vol / base_vol if base_vol else 1

        # RSI
        rsi_data = rsi_features(closes)
        rsi = rsi_data.get("rsi", 50)
        rsi_signal = rsi_data.get("signal", 0)

        # MACD
        macd = macd_full(closes) or {}
        macd_signal = macd.get("signal", 0)

        # 量价关系
        vol_price_signal = self._volume_price_features(closes, volumes)

        return {
            "trend": trend,
            "ret20": ret20,
            "ma10": ma10,
            "ma20": ma20,
            "volume_ratio": volume_ratio,
            "macd_signal": macd_signal,
            "rsi": round(rsi, 1),
            "rsi_signal": rsi_signal,
            "vol_price_signal": vol_price_signal,
            "closes": closes,
        }

    @staticmethod
    def _volume_price_features(closes, volumes):
        """量价关系分析。signal: 1=配合良好, 0=中性, -1=背离警报。"""
        if len(closes) < 6 or len(volumes) < 6:
            return 0
        mid = len(closes) // 2
        recent_close = closes[-mid:]
        prev_close = closes[:mid]
        recent_vol = volumes[-mid:]
        prev_vol = volumes[:mid]
        import statistics
        price_chg = statistics.mean(recent_close) / max(statistics.mean(prev_close), 0.01) - 1
        # vol_chg 未直接使用，保留以备扩展
        _ = statistics.mean(recent_vol) / max(statistics.mean(prev_vol), 0.01) - 1
        last3_close = closes[-3:]
        last3_vol = volumes[-3:]
        price_up = statistics.mean(last3_close) > statistics.mean(closes)
        vol_up = statistics.mean(last3_vol) > statistics.mean(volumes)
        if price_up and vol_up:
            return 1
        elif not price_up and not vol_up:
            return 1
        elif price_up and not vol_up:
            return -1
        elif not price_up and vol_up:
            return -1
        return 0

    def _hard_filter(self, quote: dict, fin: dict, filters: dict) -> List[str]:
        """硬过滤。

        Args:
            quote: 行情 dict（含 total_cap/amount/change_pct/code/name）
            fin: 财务 dict（兼容标准化字段名与东财原始字段名）
            filters: 筛选条件 dict，支持：
                - min_amount (float, 万元): 最低成交额
                - min_cap (float, 亿): 最低市值
                - exclude_loss (bool): 剔除 EPS<=0
        """
        reasons = []
        name = quote.get("name", "")
        code = quote.get("code", "")
        bd = board_type(code)

        # ST 检测：A 股 ST 标记在名称开头，用前缀匹配
        upper_name = name.upper()
        if any(upper_name.startswith(p) for p in _st_prefixes()):
            reasons.append("ST风险")

        # 退市风险：市值过小
        min_survival_cap = _min_survival_cap(bd)
        if 0 < to_float(quote.get("total_cap")) < min_survival_cap:
            reasons.append(f"市值<{min_survival_cap}亿(退市风险)")

        # 连续亏损检测
        eps = to_float(fin.get("eps", fin.get("EPSJB")))
        if eps < 0:
            reasons.append("EPS<0(亏损)")

        # 商誉减值风险（无数据时跳过）
        goodwill_ratio = to_float(fin.get("goodwill_ratio", fin.get("GOODWILL_RATIO", 0)))
        if goodwill_ratio > _goodwill_threshold():
            reasons.append(f"商誉/总资产>{goodwill_ratio:.0f}%(减值风险)")

        # 股权质押率过高
        pledge_ratio = to_float(fin.get("pledge_ratio", fin.get("PLEDGE_RATIO", 0)))
        if pledge_ratio > _pledge_threshold():
            reasons.append(f"质押率>{pledge_ratio:.0f}%(爆仓风险)")

        # 板块差异化阈值
        base_min_amount = filters.get("min_amount", 5000)
        base_min_cap = filters.get("min_cap", 40)
        if _USE_CONFIG:
            board_min_amount = {
                "主板": base_min_amount,
                "创业板": _limit("min_amount.创业板", 3000),
                "科创板": _limit("min_amount.科创板", 3000),
                "北交所": _limit("min_amount.北交所", 1000),
            }
            board_min_cap = {
                "主板": base_min_cap,
                "创业板": _limit("min_total_cap.创业板", 20),
                "科创板": _limit("min_total_cap.科创板", 20),
                "北交所": _limit("min_total_cap.北交所", 10),
            }
        else:
            board_min_amount = {
                "主板": base_min_amount,
                "创业板": base_min_amount * 0.7,
                "科创板": base_min_amount * 0.7,
                "北交所": base_min_amount * 1.5,
            }
            board_min_cap = {
                "主板": base_min_cap,
                "创业板": base_min_cap * 0.6,
                "科创板": base_min_cap * 0.6,
                "北交所": base_min_cap * 0.4,
            }
        min_amt = board_min_amount.get(bd, base_min_amount)
        min_cap = board_min_cap.get(bd, base_min_cap)

        if to_float(quote.get("amount")) / 10000 < min_amt:
            reasons.append(f"成交额<{min_amt:.0f}万")
        if to_float(quote.get("total_cap")) < min_cap:
            reasons.append(f"市值<{min_cap:.0f}亿")

        # 涨跌停过滤：T+1 下当日无法交易
        change_pct = abs(to_float(quote.get("change_pct", 0)))
        if change_pct >= _board_limit(bd):
            reasons.append("涨跌停限制")

        # 排除亏损（来自 filters）
        if filters.get("exclude_loss") and eps <= 0:
            reasons.append("EPS<=0")

        return reasons


__all__ = ["ScreeningService"]

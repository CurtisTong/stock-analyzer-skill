"""akshare 财务数据源（需要 akshare 包）。

stock_financial_abstract 返回转置结构（指标在行、报告期在列），
本 fetcher 负责转置为"每期一个 dict"的标准结构，兼容 FINANCE_FIELD_MAP 映射。
"""

import logging

from common import BaseFetcher, plain_code
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False


class AkshareFinanceFetcher(BaseFetcher):
    """akshare 财务数据源 (优先级 3) - 需要安装 akshare 包。"""

    def __init__(self):
        super().__init__("akshare_finance", priority=3)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_AKSHARE:
            return None
        try:
            plain = plain_code(code)
            df = ak.stock_financial_abstract(symbol=plain)
            if df is None or df.empty:
                return None

            # stock_financial_abstract 返回转置结构：
            #   行 = 指标（归母净利润/营业总收入/...），列 = 报告期（20260331/...）
            # 需转置为"每期一个 dict"，key=指标名（中文），value=数值
            periods = kwargs.get("periods", 4)
            date_cols = [
                c for c in df.columns if c not in ("选项", "指标") and len(str(c)) == 8
            ]
            date_cols = date_cols[:periods]  # 取最近 N 期

            result = []
            for col in date_cols:
                record = {"REPORT_DATE": f"{col[:4]}-{col[4:6]}-{col[6:8]}"}
                for _, row in df.iterrows():
                    indicator = row.get("指标", "")
                    value = row.get(col)
                    if indicator and value is not None:
                        record[indicator] = value
                record["source"] = "akshare"
                result.append(record)

            return result if result else None
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("akshare_finance 获取失败 %s: %s", code, e)
            return None

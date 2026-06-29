"""efinance 财务数据源（需要 efinance 包）。"""

import logging


from common import BaseFetcher

logger = logging.getLogger(__name__)

try:
    import efinance as ef

    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False


class EfinanceFinanceFetcher(BaseFetcher):
    """efinance 财务数据源 (优先级 5) - 需要安装 efinance 包。"""

    def __init__(self):
        super().__init__("efinance_finance", priority=5)

    def fetch(self, code: str, **kwargs) -> list | None:
        if not HAS_EFINANCE:
            return None
        try:
            plain = code.lstrip("shszSHSZbjBJ")
            df = ef.stock.get_quote_history(plain, klt=101, count=4)
            if df is None or df.empty:
                return None
            # 将最近几季行情数据转为财务字段格式（兼容 _dict_to_finance）
            result = []
            for _, row in df.iterrows():
                result.append(
                    {
                        "REPORT_DATE": str(row.get("日期", ""))[:10],
                        "EPSJB": str(row.get("每股收益", 0)),
                        "ROEJQ": str(row.get("净资产收益率", 0)),
                        "TOTALOPERATEREVETZ": str(row.get("营业总收入同比增长率", 0)),
                        "PARENTNETPROFITTZ": str(row.get("归母净利润同比增长率", 0)),
                        "XSMLL": str(row.get("销售毛利率", 0)),
                        "XSJLL": str(row.get("销售净利率", 0)),
                        "ZCFZL": str(row.get("资产负债率", 0)),
                        "BPS": str(row.get("每股净资产", 0)),
                        "MGJYXJJE": str(row.get("每股经营现金流", 0)),
                        "source": "efinance",
                    }
                )
            return result if result else None
        except Exception as e:
            logger.debug("efinance_finance 获取失败 %s: %s", code, e)
            return None

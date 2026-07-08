"""东方财富筹码相关数据源（融资融券、股东户数、十大流通股东）。"""

import json
import logging
from datetime import datetime, timedelta

from common import BaseFetcher, http_get, to_float, to_int, strip_prefix

logger = logging.getLogger(__name__)


# 融资融券 API (datacenter-web)
MARGIN_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get?report=RPT_MARGIN_TRADE_STATISTICS&columns=ALL&filter=(SECURITY_CODE%3D%27{code}%27)(TRADE_DATE%3E%3D%27{start}%27)&pageSize={days}&sortColumns=TRADE_DATE&sortTypes=-1"

# F10 股东研究 API（包含股东户数和十大流通股东）
F10_SHAREHOLDER_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax?code={secid}"

# 机构类型关键词
_INSTITUTION_KEYWORDS = [
    "基金",
    "QFII",
    "社保",
    "券商",
    "保险",
    "信托",
    "银行",
    "证券",
    "资产管理",
    "投资公司",
]


class MarginFetcher(BaseFetcher):
    """融资融券数据源。"""

    def __init__(self):
        super().__init__("margin", priority=5)

    def fetch(self, code: str, **kwargs) -> list | None:
        """获取融资融券近期数据。

        Args:
            code: 股票代码（如 sh600989, 600989）
            kwargs: days=20 获取天数

        Returns:
            融资融券数据列表，失败返回 None
        """
        days = kwargs.get("days", 20)
        # 提取纯数字代码（支持 sh/sz/bj 前缀，大小写无关）
        pure_code = strip_prefix(code)
        # 考虑节假日：交易日约占自然日的 50%，故向前多取一倍天数确保覆盖
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        url = MARGIN_URL.format(code=pure_code, start=start_date, days=days)

        # NetworkError / RateLimitError 不在此捕获，由 DataFetcherManager 统一处理故障转移
        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"MarginFetcher JSON 解析失败: {code}, {e}")
            return None

        if not data or data.get("success") is not True:
            logger.debug(f"MarginFetcher API 返回失败: {code}")
            return None

        result = []
        for item in data.get("result", {}).get("data", []):
            try:
                result.append(
                    {
                        "date": str(item.get("TRADE_DATE", ""))[:10],
                        "code": pure_code,
                        "rzye": to_float(item.get("RZYE")),  # 融资余额
                        "rqye": to_float(item.get("RQYE")),  # 融券余额
                        "rzmre": to_float(item.get("RZMRE")),  # 融资买入额
                        "rzche": to_float(item.get("RZCHE")),  # 融资偿还额
                        "rzjme": to_float(item.get("RZJME")),  # 融资净买入额
                        "rqmcl": to_float(item.get("RQMCL")),  # 融券卖出量
                        "rqchl": to_float(item.get("RQCHL")),  # 融券偿还量
                        "rqjmg": to_float(item.get("RQJMG")),  # 融券净卖出量
                        "rqyl": to_float(item.get("RQYL")),  # 融券余量
                    }
                )
            except Exception as e:
                logger.warning(f"MarginFetcher 数据转换异常: {item}, {e}")
                continue

        return result if result else None


def _get_secid(code: str) -> str:
    """将股票代码转换为 secid 格式（如 SH600989）。"""
    code = code.strip()
    if code.startswith(("sh", "sz", "SH", "SZ")):
        return code.upper()
    # 纯数字代码，根据首位判断交易所
    if code.startswith(("6", "9")):
        return f"SH{code}"
    else:
        return f"SZ{code}"


class HolderFetcher(BaseFetcher):
    """股东户数数据源（使用 F10 接口）。"""

    def __init__(self):
        super().__init__("holder", priority=5)

    def fetch(self, code: str, **kwargs) -> list | None:
        """获取股东户数数据。

        Args:
            code: 股票代码
            kwargs: periods=4 获取期数

        Returns:
            股东户数数据列表，失败返回 None
        """
        periods = kwargs.get("periods", 4)
        secid = _get_secid(code)

        url = F10_SHAREHOLDER_URL.format(secid=secid)

        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"HolderFetcher JSON 解析失败: {code}, {e}")
            return None

        if not isinstance(data, dict) or "gdrs" not in data:
            logger.debug(f"HolderFetcher 无 gdrs 数据: {code}")
            return None

        gdrs_list = data.get("gdrs", [])
        if not gdrs_list:
            return None

        # 按日期降序排序（确保最新的在前），避免依赖 API 返回顺序
        gdrs_list = sorted(
            gdrs_list, key=lambda x: str(x.get("END_DATE", "")), reverse=True
        )

        result = []
        prev_holder_num = 0

        for item in gdrs_list[:periods]:
            try:
                holder_num = to_int(item.get("HOLDER_TOTAL_NUM"))
                avg_amount = to_float(item.get("AVG_FREE_SHARES"))
                holder_num_change = to_float(item.get("TOTAL_NUM_RATIO"))
                hold_focus = str(item.get("HOLD_FOCUS", ""))

                # 集中度评级（保持东方财富原始语义）
                # "非常集中"/"比较集中" -> 集中；"相对集中" -> 一般；"比较分散"/"非常分散" -> 分散
                # 无字段时返回 "未知"，避免误认为"持平"
                if not hold_focus or hold_focus == "None":
                    concentration = "未知"
                elif hold_focus in ("非常集中", "比较集中"):
                    concentration = "集中"
                elif hold_focus in ("相对集中",):
                    concentration = "一般"
                elif hold_focus in ("非常分散", "比较分散"):
                    concentration = "分散"
                else:
                    concentration = "持平"

                result.append(
                    {
                        "end_date": str(item.get("END_DATE", ""))[:10],
                        "code": secid[2:],
                        "holder_num": holder_num,
                        "avg_amount": avg_amount,
                        "holder_num_change": holder_num_change,
                        "prev_holder_num": prev_holder_num,
                        "concentration": concentration,
                    }
                )

                prev_holder_num = holder_num
            except Exception as e:
                logger.warning(f"HolderFetcher 数据转换异常: {item}, {e}")
                continue

        return result if result else None


class TopHolderFetcher(BaseFetcher):
    """十大流通股东数据源（使用 F10 接口）。"""

    def __init__(self):
        super().__init__("top_holder", priority=5)

    def fetch(self, code: str, **kwargs) -> list | None:
        """获取十大流通股东数据。

        Args:
            code: 股票代码
            kwargs: 未使用

        Returns:
            十大流通股东数据列表，失败返回 None
        """
        secid = _get_secid(code)

        url = F10_SHAREHOLDER_URL.format(secid=secid)

        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"TopHolderFetcher JSON 解析失败: {code}, {e}")
            return None

        if not isinstance(data, dict) or "sdltgd" not in data:
            logger.debug(f"TopHolderFetcher 无 sdltgd 数据: {code}")
            return None

        sdltgd_list = data.get("sdltgd", [])
        if not sdltgd_list:
            return None

        # 按日期降序排序，确保最新一期在最前面
        sdltgd_list = sorted(
            sdltgd_list, key=lambda x: str(x.get("END_DATE", "")), reverse=True
        )

        # 获取最新一期的日期
        latest_date = str(sdltgd_list[0].get("END_DATE", ""))[:10]

        result = []
        for item in sdltgd_list:
            # 只取最新一期
            item_date = str(item.get("END_DATE", ""))[:10]
            if item_date != latest_date:
                continue

            try:
                holder_name = str(item.get("HOLDER_NAME", ""))
                holder_type = str(item.get("SHARES_TYPE", "流通A股"))

                # 判断是否为机构
                is_institution = any(kw in holder_name for kw in _INSTITUTION_KEYWORDS)

                # 变动类型：从独立状态字段获取，辅以变化量数值判断
                change_type_raw = str(item.get("CHANGE_TYPE", "")).strip()
                hold_num_change = (
                    to_float(item.get("HOLD_NUM_CHANGE", 0)) / 10000
                )  # 转万股

                if change_type_raw:
                    # API 返回了独立的变动类型字段（如"新进"/"增持"/"减持"/"不变"）
                    change_type = change_type_raw
                    change_num = hold_num_change
                elif hold_num_change > 0:
                    change_type = "增持"
                    change_num = hold_num_change
                elif hold_num_change < 0:
                    change_type = "减持"
                    change_num = hold_num_change
                else:
                    # 变化量为 0 且无状态字段：可能是新进（首期无对比基准）或不变
                    # 检查是否有持股但上期无数据的标识
                    if str(item.get("HOLD_NUM_CHANGE", "")).strip() in (
                        "",
                        "0",
                        "None",
                    ):
                        change_type = "不变"
                    else:
                        change_type = "新进"
                    change_num = 0

                result.append(
                    {
                        "end_date": item_date,
                        "rank": to_int(item.get("HOLDER_RANK")),
                        "holder_name": holder_name,
                        "holder_type": holder_type,
                        "hold_num": to_float(item.get("HOLD_NUM")) / 10000,  # 转万股
                        "hold_ratio": to_float(item.get("HOLD_NUM_RATIO")),
                        "change": change_num,
                        "change_type": change_type,
                        "is_institution": is_institution,
                    }
                )
            except Exception as e:
                logger.warning(f"TopHolderFetcher 数据转换异常: {item}, {e}")
                continue

        return result if result else None


__all__ = ["MarginFetcher", "HolderFetcher", "TopHolderFetcher"]

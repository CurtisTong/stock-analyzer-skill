"""同花顺行情数据源。"""

import logging


from common import BaseFetcher, http_get, to_float

logger = logging.getLogger(__name__)

# 同花顺行情 API（公开接口）
THS_URL = "https://d.10jqka.com.cn/v6/line/hs_{market}_{code}/01/last.js"


def _to_ths_params(code: str) -> tuple[str, str]:
    """转换为同花顺参数：(market, code)。
    market: 1=上海, 0=深圳
    """
    code = code.strip().upper()
    if code.startswith("SH"):
        return "1", code[2:]
    elif code.startswith("SZ"):
        return "0", code[2:]
    # 纯数字代码
    if code.startswith("6"):
        return "1", code
    return "0", code


def _parse_quote(text: str, code: str) -> dict | None:
    """解析同花顺行情数据。"""
    try:
        # 同花顺返回格式：quote({...})
        import json

        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= 0:
            return None
        data = json.loads(text[start:end])
        # 提取最新价格
        items = data.get("data", "").split(";")
        if not items:
            return None
        last_item = items[-1].split(",")
        if len(last_item) < 5:
            return None
        # 格式：日期,开,高,低,收,量
        return {
            "code": code,
            "name": "",
            "price": to_float(last_item[4]) if len(last_item) > 4 else 0,
            "open": to_float(last_item[1]) if len(last_item) > 1 else 0,
            "high": to_float(last_item[2]) if len(last_item) > 2 else 0,
            "low": to_float(last_item[3]) if len(last_item) > 3 else 0,
            "prev_close": 0,
            "volume": to_float(last_item[5]) if len(last_item) > 5 else 0,
            "amount": 0,
            "source": "ths",
        }
    except Exception as e:
        logger.debug("ths 解析失败 %s: %s", code, e)
        return None


class ThsQuoteFetcher(BaseFetcher):
    """同花顺行情数据源 (优先级 3)。

    注意：当前使用 K 线接口（v6/line）获取数据，返回的是最近一个完成 K 线的
    收盘价而非实时价格。因此优先级设为较低，仅作为其他实时源均不可用时的后备。
    盘中数据请以腾讯/东财/新浪等实时源为准。
    """

    def __init__(self):
        super().__init__("ths_quote", priority=3)

    def fetch(self, code: str, **kwargs) -> dict | None:
        # P0-12: 透传前先标准化为规范 sh/sz/bj+6位 格式
        from common import normalize_quote_code
        canonical = normalize_quote_code(code)
        market, stock_code = _to_ths_params(canonical)
        url = THS_URL.format(market=market, code=stock_code)
        try:
            raw = http_get(url, timeout=10)
            text = raw.decode("utf-8", errors="ignore")
            result = _parse_quote(text, canonical)
            if result:
                # 输出 code 统一为 sh/sz/bj+6位 格式（与其它 fetcher 一致）
                result["code"] = canonical
            return result
        except Exception as e:
            logger.debug("ths_quote 获取失败 %s: %s", code, e)
            return None

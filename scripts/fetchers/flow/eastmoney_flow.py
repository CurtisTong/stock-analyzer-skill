"""东方财富资金流向数据源（北向资金、个股主力净流入）。"""

import json

from common import BaseFetcher, http_get, to_secid, to_float

# 北向资金 API
# 注意：自 2024 年监管限制实时披露后，kamt.kline 接口的北向资金净流入字段
# (s2n/n2s) 已下线，替代字段 hk2sh/hk2sz 返回的是静态快照值（多日相同，非每日净流入），
# dataapi 的 FUND_INFLOW/NET_DEAL_AMT 等净流入字段也均为 None。
# 北向资金每日净流入已无公开数据源，fetch() 直接返回 None 降级。
NORTHBOUND_URL = "https://push2his.eastmoney.com/api/qt/kamt.kline/get?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55,f56&klt=101&lmt={days}"

# 个股资金流向 API
STOCK_FLOW_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&lmt={days}"


class NorthboundFlowFetcher(BaseFetcher):
    """北向资金数据源。"""

    def __init__(self):
        super().__init__("northbound_flow", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取北向资金近期数据。code 参数忽略，返回市场整体数据。

        注意：原 kamt.kline 接口的 s2n/n2s（沪深股通净流入）字段已下线，
        替代字段 hk2sh/hk2sz 返回的是静态快照值（多日相同，非每日净流入），
        且 dataapi 的 FUND_INFLOW/NET_DEAL_AMT 等净流入字段也均为 None。
        自 2024 年监管限制实时披露后，北向资金每日净流入已无公开数据源，
        故此处返回 None，交由上层降级（sina 同样不可用，最终返回空列表）。
        """
        return None


class StockFlowFetcher(BaseFetcher):
    """个股资金流向数据源。"""

    def __init__(self):
        super().__init__("stock_flow", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        """获取个股近期资金流向。"""
        days = kwargs.get("days", 10)
        secid = to_secid(code)
        url = STOCK_FLOW_URL.format(secid=secid, days=days)
        raw = http_get(url, timeout=self.timeout, max_retries=self.retry)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data or data.get("rc") != 0 or "data" not in data:
            return None

        klines = data["data"].get("klines", [])
        if not klines:
            return None

        result = {"type": "stock_flow", "code": code, "days": []}
        for line in klines:
            parts = line.split(",")
            if len(parts) >= 10:
                result["days"].append(
                    {
                        "date": parts[0],
                        "main_net": to_float(parts[1]),  # 主力净流入
                        "main_pct": to_float(parts[2]),  # 主力净占比%
                        "super_net": to_float(parts[3]),  # 超大单净流入
                        "super_pct": to_float(parts[4]),  # 超大单净占比%
                        "big_net": to_float(parts[5]),  # 大单净流入
                        "big_pct": to_float(parts[6]),  # 大单净占比%
                        "mid_net": to_float(parts[7]),  # 中单净流入
                        "mid_pct": to_float(parts[8]),  # 中单净占比%
                        "small_net": to_float(parts[9]),  # 小单净流入
                        "small_pct": to_float(parts[10]) if len(parts) > 10 else 0,
                    }
                )

        # 计算近 N 日汇总
        recent = result["days"][-min(5, len(result["days"])) :]
        result["summary"] = {
            "main_net_5d": sum(d["main_net"] for d in recent),
            "super_net_5d": sum(d["super_net"] for d in recent),
            "big_net_5d": sum(d["big_net"] for d in recent),
        }

        return result


__all__ = ["NorthboundFlowFetcher", "StockFlowFetcher"]

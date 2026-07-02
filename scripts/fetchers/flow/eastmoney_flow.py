"""东方财富资金流向数据源（北向资金、个股主力净流入）。"""

import json

from common import BaseFetcher, http_get, to_secid, to_float

# 北向资金 API
NORTHBOUND_URL = "https://push2his.eastmoney.com/api/qt/kamt.kline/get?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55,f56&klt=101&lmt={days}"

# 个股资金流向 API
STOCK_FLOW_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&lmt={days}"


class NorthboundFlowFetcher(BaseFetcher):
    """北向资金数据源。"""

    def __init__(self):
        super().__init__("northbound_flow", priority=5)

    def fetch(self, code: str = "", **kwargs) -> dict | None:
        """获取北向资金近期数据。code 参数忽略，返回市场整体数据。"""
        days = kwargs.get("days", 10)
        url = NORTHBOUND_URL.format(days=days)
        raw = http_get(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not data or data.get("rc") != 0:
            return None

        result = {"type": "northbound", "days": []}
        # 沪股通
        sh_data = data.get("data", {}).get("s2n", [])
        # 深股通
        sz_data = data.get("data", {}).get("n2s", [])

        # 按 date 合并沪/深股通，避免按索引对齐导致的天数不一致/错位
        # （某日可能只有沪股通开通，或两接口返回天数不同）
        merged = {}  # {date: {sh_buy, sh_sell, sh_net, sz_buy, sz_sell, sz_net, total_net}}

        # 解析沪股通
        for line in sh_data:
            parts = line.split(",")
            if len(parts) >= 4:
                d = merged.setdefault(parts[0], {})
                d["sh_buy"] = to_float(parts[1])  # 沪股通买入（万元）
                d["sh_sell"] = to_float(parts[2])  # 沪股通卖出
                d["sh_net"] = to_float(parts[3])  # 沪股通净买入

        # 解析深股通并合并到同一日期
        for line in sz_data:
            parts = line.split(",")
            if len(parts) >= 4:
                d = merged.setdefault(parts[0], {})
                d["sz_buy"] = to_float(parts[1])  # 深股通买入
                d["sz_sell"] = to_float(parts[2])  # 深股通卖出
                d["sz_net"] = to_float(parts[3])  # 深股通净买入

        # 计算每个日期的 total_net，并按日期升序输出
        for date in sorted(merged.keys()):
            d = merged[date]
            sh_net = d.get("sh_net", 0)
            sz_net = d.get("sz_net", 0)
            d["total_net"] = sh_net + sz_net
            d["date"] = date
            result["days"].append(d)

        return result


class StockFlowFetcher(BaseFetcher):
    """个股资金流向数据源。"""

    def __init__(self):
        super().__init__("stock_flow", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        """获取个股近期资金流向。"""
        days = kwargs.get("days", 10)
        secid = to_secid(code)
        url = STOCK_FLOW_URL.format(secid=secid, days=days)
        raw = http_get(url)
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

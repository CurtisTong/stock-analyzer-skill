"""
市场情绪温度计。

计算市场情绪指数，帮助判断市场状态：
- 冰点（0-30）：极度恐慌，可能是底部
- 低迷（30-45）：市场冷清
- 平衡（45-65）：正常状态
- 亢奋（65-80）：情绪高涨
- 疯狂（80-100）：极度贪婪，可能是顶部

用法：
    python3 scripts/technical/sentiment.py
    python3 scripts/technical/sentiment.py --json
"""

import json
import os
import sys
from datetime import datetime
from urllib.parse import urlencode

from common import http_get

_EASTMONEY_UT = os.getenv(
    "EASTMONEY_UT_TOKEN",
    "fa5fd1943c7b386f172d6893dbbd4dc1",
)

# ═══════════════════════════════════════════════════════════════
# 市场数据获取
# ═══════════════════════════════════════════════════════════════


def _http_get_json(url: str, params: dict | None = None) -> dict:
    """GET 请求并解析 JSON。"""
    if params:
        url = f"{url}?{urlencode(params)}"
    raw = http_get(url, timeout=15)
    if isinstance(raw, bytes):
        return json.loads(raw)
    return raw


class MarketDataFetcher:
    """市场数据获取器。"""

    def get_limit_data(self) -> dict:
        """获取涨跌停数据。

        Returns:
            {
                "limit_up_count": int,      # 涨停家数
                "limit_down_count": int,    # 跌停家数
                "continuous_limit_height": int,  # 连板高度
                "broken_limit_rate": float, # 炸板率
            }
        """
        try:
            # 使用东方财富接口获取涨停数据
            url = "https://push2ex.eastmoney.com/getTopicZTPool"
            params = {
                "ut": _EASTMONEY_UT,
                "dpt": "wz.ztzt",
                "date": datetime.now().strftime("%Y%m%d"),
            }
            data = _http_get_json(url, params=params)

            pool = data.get("data", {}).get("pool", [])
            limit_up_count = len(pool)

            # 计算连板高度
            continuous_height = 0
            for item in pool:
                height = item.get("lbc", 0)  # 连板数
                if height > continuous_height:
                    continuous_height = height

            # 计算炸板率（需要另一个接口）
            broken_rate = self._get_broken_rate()

            return {
                "limit_up_count": limit_up_count,
                "limit_down_count": self._get_limit_down_count(),
                "continuous_limit_height": continuous_height,
                "broken_limit_rate": broken_rate,
            }
        except Exception as e:
            print(f"获取涨跌停数据失败: {e}", file=sys.stderr)
            return {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "continuous_limit_height": 0,
                "broken_limit_rate": 0,
            }

    def _get_limit_down_count(self) -> int:
        """获取跌停家数。"""
        try:
            url = "https://push2ex.eastmoney.com/getTopicDTPool"
            params = {
                "ut": _EASTMONEY_UT,
                "dpt": "wz.ztzt",
                "date": datetime.now().strftime("%Y%m%d"),
            }
            data = _http_get_json(url, params=params)
            pool = data.get("data", {}).get("pool", [])
            return len(pool)
        except Exception:
            return 0

    def _get_broken_rate(self) -> float:
        """获取炸板率。"""
        try:
            url = "https://push2ex.eastmoney.com/getTopicZTPool"
            params = {
                "ut": _EASTMONEY_UT,
                "dpt": "wz.ztzt",
                "date": datetime.now().strftime("%Y%m%d"),
            }
            data = _http_get_json(url, params=params)

            pool = data.get("data", {}).get("pool", [])
            if not pool:
                return 0

            # 统计炸板次数
            broken_count = 0
            for item in pool:
                if item.get("zbc", 0) > 0:  # 炸板次数
                    broken_count += 1

            return (broken_count / len(pool)) * 100 if pool else 0
        except Exception:
            return 0

    def get_margin_data(self) -> dict:
        """获取两融数据。

        Returns:
            {
                "margin_balance": float,  # 两融余额（亿）
            }
        """
        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "reportName": "RPTA_WEB_RZRQ_LJMX",
                "columns": "ALL",
                "sortColumns": "DATE",
                "sortTypes": "-1",
                "pageSize": 1,
            }
            data = _http_get_json(url, params=params)

            result = data.get("result", {})
            records = result.get("data", [])

            if records:
                margin_balance = records[0].get("RZYE", 0) / 1e8  # 转换为亿
                return {"margin_balance": margin_balance}

            return {"margin_balance": 0}
        except Exception as e:
            print(f"获取两融数据失败: {e}", file=sys.stderr)
            return {"margin_balance": 0}


# ═══════════════════════════════════════════════════════════════
# 情绪计算
# ═══════════════════════════════════════════════════════════════


class SentimentCalculator:
    """市场情绪计算器。"""

    # 权重配置
    WEIGHTS = {
        "limit_up": 0.30,  # 涨停家数
        "continuous_height": 0.25,  # 连板高度
        "broken_rate": 0.20,  # 炸板率
        "margin_balance": 0.25,  # 两融余额
    }

    def calculate(self, market_data: dict) -> dict:
        """计算情绪指数。

        Args:
            market_data: 市场数据
                - limit_up_count: 涨停家数
                - continuous_limit_height: 连板高度
                - broken_limit_rate: 炸板率
                - margin_balance: 两融余额（亿）

        Returns:
            {
                "score": int,           # 情绪分数 0-100
                "level": str,           # 情绪等级
                "components": dict,     # 各指标得分
                "interpretation": str,  # 解读
            }
        """
        # 计算各指标得分
        limit_up_score = self._calc_limit_up_score(market_data.get("limit_up_count", 0))
        height_score = self._calc_height_score(
            market_data.get("continuous_limit_height", 0)
        )
        broken_score = self._calc_broken_score(market_data.get("broken_limit_rate", 0))
        margin_score = self._calc_margin_score(market_data.get("margin_balance", 0))

        # 加权计算总分
        total_score = (
            limit_up_score * self.WEIGHTS["limit_up"]
            + height_score * self.WEIGHTS["continuous_height"]
            + broken_score * self.WEIGHTS["broken_rate"]
            + margin_score * self.WEIGHTS["margin_balance"]
        )

        total_score = max(0, min(100, int(total_score)))

        # 计算等级
        level = self._calc_level(total_score)

        # 生成解读
        interpretation = self._generate_interpretation(total_score, level, market_data)

        return {
            "score": total_score,
            "level": level,
            "components": {
                "limit_up": {
                    "value": market_data.get("limit_up_count", 0),
                    "score": limit_up_score,
                    "weight": self.WEIGHTS["limit_up"],
                },
                "continuous_height": {
                    "value": market_data.get("continuous_limit_height", 0),
                    "score": height_score,
                    "weight": self.WEIGHTS["continuous_height"],
                },
                "broken_rate": {
                    "value": market_data.get("broken_limit_rate", 0),
                    "score": broken_score,
                    "weight": self.WEIGHTS["broken_rate"],
                },
                "margin_balance": {
                    "value": market_data.get("margin_balance", 0),
                    "score": margin_score,
                    "weight": self.WEIGHTS["margin_balance"],
                },
            },
            "interpretation": interpretation,
        }

    def _calc_limit_up_score(self, count: int) -> int:
        """计算涨停家数得分。"""
        if count > 100:
            return 90
        elif count > 80:
            return 80
        elif count > 60:
            return 70
        elif count > 40:
            return 60
        elif count > 20:
            return 50
        elif count > 10:
            return 40
        else:
            return 30

    def _calc_height_score(self, height: int) -> int:
        """计算连板高度得分。"""
        if height >= 7:
            return 90
        elif height >= 5:
            return 75
        elif height >= 4:
            return 65
        elif height >= 3:
            return 55
        elif height >= 2:
            return 45
        else:
            return 35

    def _calc_broken_score(self, rate: float) -> int:
        """计算炸板率得分（炸板率高=情绪不稳定=扣分）。"""
        if rate > 50:
            return 30
        elif rate > 40:
            return 40
        elif rate > 30:
            return 50
        elif rate > 20:
            return 60
        elif rate > 10:
            return 70
        else:
            return 80

    def _calc_margin_score(self, balance: float) -> int:
        """计算两融余额得分（亿）。"""
        if balance > 19000:
            return 85
        elif balance > 18000:
            return 75
        elif balance > 17000:
            return 65
        elif balance > 16000:
            return 55
        elif balance > 15000:
            return 45
        else:
            return 35

    def _calc_level(self, score: int) -> str:
        """计算情绪等级。"""
        if score >= 80:
            return "疯狂"
        elif score >= 65:
            return "亢奋"
        elif score >= 45:
            return "平衡"
        elif score >= 30:
            return "低迷"
        else:
            return "冰点"

    def _generate_interpretation(self, score: int, level: str, data: dict) -> str:
        """生成情绪解读。"""
        interpretations = []

        # 基础解读
        level_desc = {
            "疯狂": "市场极度贪婪，需警惕回调风险",
            "亢奋": "市场情绪高涨，短线机会较多",
            "平衡": "市场情绪正常，可正常操作",
            "低迷": "市场冷清，可寻找被低估的机会",
            "冰点": "市场极度恐慌，可能是底部区域",
        }
        interpretations.append(level_desc.get(level, ""))

        # 涨停家数解读
        limit_up = data.get("limit_up_count", 0)
        if limit_up > 80:
            interpretations.append(f"涨停家数 {limit_up} 家，市场赚钱效应强")
        elif limit_up < 20:
            interpretations.append(f"涨停家数仅 {limit_up} 家，市场赚钱效应弱")

        # 连板高度解读
        height = data.get("continuous_limit_height", 0)
        if height >= 5:
            interpretations.append(f"连板高度 {height} 板，短线情绪亢奋")
        elif height <= 2:
            interpretations.append(f"连板高度仅 {height} 板，短线情绪低迷")

        # 炸板率解读
        broken_rate = data.get("broken_limit_rate", 0)
        if broken_rate > 40:
            interpretations.append(f"炸板率 {broken_rate:.0f}%，市场分歧大")

        return "；".join(interpretations)


def format_sentiment(result: dict) -> str:
    """格式化情绪指数输出。"""
    score = result["score"]
    level = result["level"]
    components = result["components"]
    interpretation = result["interpretation"]

    # 生成温度计条
    bar_length = 20
    filled = int(score / 100 * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)

    # 等级颜色标记
    level_icon = {
        "疯狂": "🔴",
        "亢奋": "🟠",
        "平衡": "🟡",
        "低迷": "🔵",
        "冰点": "🟣",
    }.get(level, "⚪")

    lines = [
        f"🌡️ 市场情绪温度计",
        "",
        f"情绪指数：{score}/100（{level_icon} {level}）",
        f"[{bar}] {score}%",
        "",
        "## 指标明细",
        "",
        f"- 涨停家数：{components['limit_up']['value']}（得分 {components['limit_up']['score']}）",
        f"- 连板高度：{components['continuous_height']['value']} 板（得分 {components['continuous_height']['score']}）",
        f"- 炸板率：{components['broken_rate']['value']:.0f}%（得分 {components['broken_rate']['score']}）",
        f"- 两融余额：{components['margin_balance']['value']:.0f} 亿（得分 {components['margin_balance']['score']}）",
        "",
        "## 情绪解读",
        "",
        interpretation,
    ]

    return "\n".join(lines)


def main():
    """主入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="市场情绪温度计")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    # 获取市场数据
    fetcher = MarketDataFetcher()
    market_data = fetcher.get_limit_data()
    margin_data = fetcher.get_margin_data()
    market_data.update(margin_data)

    # 计算情绪指数
    calculator = SentimentCalculator()
    result = calculator.calculate(market_data)

    # 输出
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_sentiment(result))


if __name__ == "__main__":
    main()

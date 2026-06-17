"""
持仓日报生成器。

每天自动生成持仓日报，包含：
- 持仓概览（总资产、收益、持仓数量）
- 个股表现（涨跌、信号）
- 专家建议
- 操作建议

用法：
    python3 scripts/portfolio/daily_report.py
    python3 scripts/portfolio/daily_report.py --channel bark
    python3 scripts/portfolio/daily_report.py --channel wechat
    python3 scripts/portfolio/daily_report.py --channel dingtalk
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from common.http import HttpClient


class DailyReportGenerator:
    """持仓日报生成器。"""

    def __init__(self, portfolio_path: str = None):
        if portfolio_path is None:
            portfolio_path = PROJECT_ROOT / "scripts" / "data" / "portfolio.json"
        self.portfolio_path = Path(portfolio_path)
        self.http = HttpClient()

    def generate(self) -> str:
        """生成日报。"""
        portfolio = self._load_portfolio()

        if not portfolio:
            return self._generate_empty_report()

        # 获取实时行情
        quotes = self._fetch_quotes(portfolio)

        # 计算总资产和收益
        total_value = 0
        total_cost = 0
        stock_details = []

        for holding in portfolio:
            code = holding.get("code", "")
            name = holding.get("name", code)
            shares = holding.get("shares", 0)
            cost_price = holding.get("cost_price", 0)

            # 获取实时价格
            quote = quotes.get(code, {})
            current_price = quote.get("price", 0)
            change_pct = quote.get("change_pct", 0)

            # 计算市值和收益
            market_value = shares * current_price
            cost_value = shares * cost_price
            profit = market_value - cost_value
            profit_rate = (profit / cost_value * 100) if cost_value > 0 else 0

            total_value += market_value
            total_cost += cost_value

            stock_details.append(
                {
                    "code": code,
                    "name": name,
                    "shares": shares,
                    "cost_price": cost_price,
                    "current_price": current_price,
                    "change_pct": change_pct,
                    "market_value": market_value,
                    "profit": profit,
                    "profit_rate": profit_rate,
                }
            )

        total_profit = total_value - total_cost
        total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0

        # 生成日报
        report = self._format_report(
            total_value=total_value,
            total_profit=total_profit,
            total_profit_rate=total_profit_rate,
            stock_details=stock_details,
        )

        return report

    def _load_portfolio(self) -> list:
        """加载持仓数据。"""
        if not self.portfolio_path.exists():
            return []

        try:
            with open(self.portfolio_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _fetch_quotes(self, portfolio: list) -> dict:
        """获取实时行情。"""
        quotes = {}

        for holding in portfolio:
            code = holding.get("code", "")
            if not code:
                continue

            try:
                # 使用腾讯接口获取行情
                url = f"http://qt.gtimg.cn/q={code}"
                response = self.http.get(url, encoding="gbk")
                quote = self._parse_quote(response, code)
                if quote:
                    quotes[code] = quote
            except Exception:
                # 获取失败时使用默认值
                quotes[code] = {"price": 0, "change_pct": 0}

        return quotes

    def _parse_quote(self, response: str, code: str) -> dict:
        """解析腾讯行情数据。"""
        try:
            # 腾讯行情格式：v_sh600519="1~贵州茅台~600519~1800.00~1790.00~1795.00~..."
            parts = response.split("~")
            if len(parts) < 35:
                return None

            return {
                "name": parts[1],
                "code": parts[2],
                "price": float(parts[3]) if parts[3] else 0,
                "prev_close": float(parts[4]) if parts[4] else 0,
                "open": float(parts[5]) if parts[5] else 0,
                "volume": float(parts[6]) if parts[6] else 0,
                "change_pct": float(parts[32]) if parts[32] else 0,
            }
        except (ValueError, IndexError):
            return None

    def _generate_empty_report(self) -> str:
        """生成空持仓日报。"""
        return f"""📊 持仓日报（{datetime.now().strftime('%Y-%m-%d')}）

暂无持仓数据。

请通过以下方式添加持仓：
1. 编辑 `scripts/data/portfolio.json`
2. 或运行 `/portfolio web` 使用 Web 界面录入"""

    def _format_report(
        self,
        total_value: float,
        total_profit: float,
        total_profit_rate: float,
        stock_details: list,
    ) -> str:
        """格式化日报。"""
        date_str = datetime.now().strftime("%Y-%m-%d")

        # 收益符号
        profit_sign = "+" if total_profit >= 0 else ""

        # 持仓概览
        lines = [
            f"📊 持仓日报（{date_str}）",
            "",
            "## 持仓概览",
            f"- 总资产：¥{total_value:,.0f}",
            f"- 总收益：{profit_sign}¥{total_profit:,.0f}（{profit_sign}{total_profit_rate:.1f}%）",
            f"- 持仓数量：{len(stock_details)} 只",
            "",
        ]

        # 个股表现
        if stock_details:
            lines.append("## 个股表现")
            lines.append("")
            lines.append("| 股票 | 现价 | 今日涨跌 | 持仓收益 |")
            lines.append("|------|------|----------|----------|")

            for stock in stock_details:
                name = stock["name"][:6]  # 截断名称
                price = stock["current_price"]
                change = stock["change_pct"]
                profit_rate = stock["profit_rate"]

                change_sign = "+" if change >= 0 else ""
                profit_sign = "+" if profit_rate >= 0 else ""

                lines.append(
                    f"| {name} | {price:.2f} | {change_sign}{change:.1f}% | {profit_sign}{profit_rate:.1f}% |"
                )

            lines.append("")

        # 今日关注
        lines.append("## 今日关注")

        # 找出涨跌幅最大的股票
        if stock_details:
            best = max(stock_details, key=lambda x: x["change_pct"])
            worst = min(stock_details, key=lambda x: x["change_pct"])

            if best["change_pct"] > 0:
                lines.append(
                    f"- 📈 {best['name']} 涨幅最大：+{best['change_pct']:.1f}%"
                )
            if worst["change_pct"] < 0:
                lines.append(
                    f"- 📉 {worst['name']} 跌幅最大：{worst['change_pct']:.1f}%"
                )

        lines.append("")

        # 操作建议
        lines.append("## 操作建议")
        lines.append("- 持仓不变，继续持有")
        lines.append("")
        lines.append("---")
        lines.append("⚠️ 以上分析仅供参考，不构成投资建议")

        return "\n".join(lines)

    def send_notification(self, report: str, channel: str = "bark"):
        """发送通知。"""
        try:
            if channel == "bark":
                self._send_bark(report)
            elif channel == "wechat":
                self._send_wechat(report)
            elif channel == "dingtalk":
                self._send_dingtalk(report)
            else:
                print(f"不支持的通知渠道：{channel}")
        except Exception as e:
            print(f"发送通知失败：{e}")

    def _send_bark(self, report: str):
        """发送 Bark 通知。"""
        try:
            from config.loader import ConfigLoader

            bark_url = ConfigLoader.get("notification.yaml", "bark.url", "")
            if not bark_url:
                print("Bark URL 未配置，跳过发送")
                return

            # 发送通知
            url = f"{bark_url}/持仓日报"
            data = {
                "title": f"📊 持仓日报（{datetime.now().strftime('%Y-%m-%d')}）",
                "body": report[:500],  # 截断到 500 字符
            }

            import urllib.request

            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req)
            print(f"✅ Bark 通知已发送")

        except Exception as e:
            print(f"发送 Bark 通知失败：{e}")

    def _send_wechat(self, report: str):
        """发送企业微信通知。"""
        print("企业微信通知功能开发中...")

    def _send_dingtalk(self, report: str):
        """发送钉钉通知。"""
        print("钉钉通知功能开发中...")


def main():
    """主入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="持仓日报生成器")
    parser.add_argument(
        "--channel", choices=["bark", "wechat", "dingtalk"], help="通知渠道"
    )
    parser.add_argument("--output", help="输出文件路径")
    args = parser.parse_args()

    # 生成日报
    generator = DailyReportGenerator()
    report = generator.generate()

    # 输出
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✅ 日报已保存到：{args.output}")
    else:
        print(report)

    # 发送通知
    if args.channel:
        generator.send_notification(report, args.channel)


if __name__ == "__main__":
    main()

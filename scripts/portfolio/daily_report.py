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
import logging
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from common import http_get
from common.parsers import parse_tencent_line


class DailyReportGenerator:
    """持仓日报生成器。"""

    def __init__(self, portfolio_path: str = None):
        if portfolio_path is None:
            portfolio_path = PROJECT_ROOT / "scripts" / "data" / "portfolio.json"
        self.portfolio_path = Path(portfolio_path)

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
            # 兼容 v2 格式（quantity/cost）和旧格式（shares/cost_price）
            quantity = holding.get("quantity") or holding.get("shares", 0)
            cost = holding.get("cost") or holding.get("cost_price", 0)

            # 获取实时价格
            quote = quotes.get(code, {})
            current_price = quote.get("price", 0)
            change_pct = quote.get("change_pct", 0)

            # 计算市值和收益
            market_value = quantity * current_price
            cost_value = quantity * cost
            profit = market_value - cost_value
            profit_rate = (profit / cost_value * 100) if cost_value > 0 else 0

            total_value += market_value
            total_cost += cost_value

            stock_details.append(
                {
                    "code": code,
                    "name": name,
                    "quantity": quantity,
                    "cost": cost,
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
        """加载持仓数据（兼容 v1/v2 格式）。"""
        if not self.portfolio_path.exists():
            return []

        try:
            with open(self.portfolio_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

        # v2 格式：{"version": 2, "positions": [...]}
        if isinstance(data, dict) and "positions" in data:
            return data["positions"]
        # v1 格式：[...] 平铺列表
        if isinstance(data, list):
            return data
        return []

    def _parse_quote(self, response: str, code: str) -> dict:
        """解析腾讯行情数据（兼容旧测试接口）。"""
        rec = parse_tencent_line(response)
        if rec:
            return {
                "name": rec.get("name", ""),
                "code": rec.get("code", code),
                "price": float(rec.get("price", 0) or 0),
                "prev_close": float(rec.get("prev_close", 0) or 0),
                "open": float(rec.get("open", 0) or 0),
                "change_pct": float(rec.get("change_pct", 0) or 0),
            }
        # 回退：手动解析短格式（测试构造的 35 字段格式）
        try:
            if "=" in response and '"' in response:
                payload = response.split('"', 1)[1].rstrip('";\n')
            else:
                payload = response.strip('"')
            parts = payload.split("~")
            if len(parts) >= 33:
                return {
                    "name": parts[1],
                    "code": parts[2],
                    "price": float(parts[3]) if parts[3] else 0,
                    "prev_close": float(parts[4]) if parts[4] else 0,
                    "open": float(parts[5]) if parts[5] else 0,
                    "change_pct": float(parts[32]) if parts[32] else 0,
                }
        except (ValueError, IndexError):
            pass
        return None

    def _fetch_quotes(self, portfolio: list) -> dict:
        """获取实时行情（使用腾讯接口）。"""
        quotes = {}
        codes = [h.get("code", "") for h in portfolio if h.get("code")]
        if not codes:
            return quotes

        # 批量请求（腾讯支持逗号分隔）
        batch_size = 15
        for i in range(0, len(codes), batch_size):
            batch = codes[i : i + batch_size]
            url = f"https://qt.gtimg.cn/q={','.join(batch)}"
            try:
                raw = http_get(url, timeout=10)
                text = raw.decode("gbk", errors="replace")
                for line in text.strip().split(";"):
                    line = line.strip()
                    if not line:
                        continue
                    rec = parse_tencent_line(line)
                    if rec and rec.get("code"):
                        code = rec["code"]
                        # 补充交易所前缀
                        for orig in batch:
                            if orig.lower().endswith(code.lower()):
                                code = orig.lower()
                                break
                        quotes[code] = {
                            "name": rec.get("name", ""),
                            "price": float(rec.get("price", 0) or 0),
                            "change_pct": float(rec.get("change_pct", 0) or 0),
                        }
            except Exception as e:
                logging.getLogger(__name__).debug("批量行情获取失败: %s", e)
                for code in batch:
                    quotes[code] = {"price": 0, "change_pct": 0}

        return quotes

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

"""
策略信号监控模块

实时监控股票池，检测 MA10/MA21 金叉 + 放量突破信号
支持推送通知（Bark/企微/钉钉）

依赖：
- scripts/strategies/patterns/ma_volume_strategy.py
- scripts/monitor/alert_engine.py
"""

import sys
import os
import json
from datetime import datetime

# 添加 scripts 目录到路径
scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from common import to_float
from strategies.patterns.ma_volume_strategy import (
    detect_ma_volume_signal,
    get_strategy_params,
)


def calc_ma(closes, period):
    """计算简单移动平均线"""
    if len(closes) < period:
        return []
    result = []
    for i in range(period - 1, len(closes)):
        result.append(sum(closes[i - period + 1 : i + 1]) / period)
    return result


def scan_stock_pool(
    stock_pool, kline_data_dict, ma_short=10, ma_long=21, vol_threshold=2.5
):
    """
    扫描股票池，检测策略信号

    Args:
        stock_pool: 股票代码列表
        kline_data_dict: {code: kline_data} 字典
        ma_short: 短期均线周期
        ma_long: 长期均线周期
        vol_threshold: 成交量阈值

    Returns:
        list: 信号列表
    """
    all_signals = []

    for code in stock_pool:
        if code not in kline_data_dict:
            continue

        data = kline_data_dict[code]
        if len(data) < ma_long + 5:
            continue

        closes = [to_float(r.get("close")) for r in data]
        volumes = [to_float(r.get("volume")) for r in data]

        # 检测信号
        signals = detect_ma_volume_signal(
            data, closes, volumes, ma_short, ma_long, vol_threshold
        )

        # 只保留最近 3 天的信号
        recent_signals = [s for s in signals if s["idx"] >= len(data) - 3]

        for signal in recent_signals:
            signal["code"] = code
            signal["stock_name"] = data[0].get("name", code)
            all_signals.append(signal)

    return all_signals


def format_signal_report(signals, stock_name_dict=None):
    """
    格式化信号报告

    Args:
        signals: 信号列表
        stock_name_dict: {code: name} 股票名称字典

    Returns:
        str: 格式化的报告
    """
    if not signals:
        return "📊 策略信号监控：未检测到信号"

    report = []
    report.append("📊 策略信号监控")
    report.append("=" * 50)
    report.append(f"扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"检测到 {len(signals)} 个信号")
    report.append("")

    # 按置信度排序
    signals.sort(key=lambda x: x.get("strength", 0), reverse=True)

    for i, signal in enumerate(signals, 1):
        code = signal.get("code", "")
        name = signal.get("stock_name", code)
        if stock_name_dict and code in stock_name_dict:
            name = stock_name_dict[code]

        confidence = signal.get("confidence", "中")
        desc = signal.get("desc", "")
        date = signal.get("date", "")
        strength = signal.get("strength", 0)

        # 置信度图标
        icon = "🔴" if confidence == "高" else "🟡" if confidence == "中" else "⚪"

        report.append(f"{icon} {i}. {name}({code})")
        report.append(f"   日期：{date}")
        report.append(f"   信号：{desc}")
        report.append(f"   置信度：{confidence} (强度: {strength})")
        report.append("")

    # 添加策略说明
    report.append("-" * 50)
    report.append("📌 策略说明：")
    report.append("  • MA10/MA21 金叉 + 放量 2.5x 突破")
    report.append("  • 预期胜率：60-70%")
    report.append("  • 预期收益：+3-5%")
    report.append("  • 止损：-5% | 持有期：5 天")

    return "\n".join(report)


def format_signal_json(signals):
    """
    格式化信号为 JSON

    Args:
        signals: 信号列表

    Returns:
        dict: JSON 格式的信号数据
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "signal_count": len(signals),
        "signals": [
            {
                "code": s.get("code", ""),
                "name": s.get("stock_name", ""),
                "date": s.get("date", ""),
                "type": s.get("type", ""),
                "desc": s.get("desc", ""),
                "confidence": s.get("confidence", ""),
                "strength": s.get("strength", 0),
                "conditions": s.get("conditions", []),
            }
            for s in signals
        ],
        "strategy": get_strategy_params(),
    }


def generate_alert_message(signals):
    """
    生成推送消息

    Args:
        signals: 信号列表

    Returns:
        str: 推送消息
    """
    if not signals:
        return None

    # 只推送高置信度信号
    high_confidence = [s for s in signals if s.get("confidence") == "高"]
    if not high_confidence:
        return None

    msg = []
    msg.append("🚨 策略信号提醒")
    msg.append(f"检测到 {len(high_confidence)} 个高置信度信号：")

    for s in high_confidence[:3]:  # 最多推送 3 个
        code = s.get("code", "")
        name = s.get("stock_name", code)
        desc = s.get("desc", "")
        msg.append(f"• {name}({code}): {desc}")

    msg.append("")
    msg.append("📌 策略：MA10/MA21 + 放量 2.5x")
    msg.append("⏰ 有效期：5 天 | 止损：-5%")

    return "\n".join(msg)


# 命令行测试
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("用法: python3 strategy_signals.py <stock1> [stock2] ...")
        print("示例: python3 strategy_signals.py sh600989 sh600519 sz300750")
        sys.exit(1)

    from kline import fetch as fetch_kline
    from common import normalize_quote_code

    stock_pool = sys.argv[1:]
    kline_data_dict = {}

    print("正在获取 K 线数据...")
    for code in stock_pool:
        normalized = normalize_quote_code(code)
        try:
            data = fetch_kline(normalized, 240, 250)
            kline_data_dict[normalized] = data
            print(f"  ✓ {normalized}: {len(data)} 条数据")
        except Exception as e:
            print(f"  ✗ {normalized}: {e}")

    print("\n正在扫描信号...")
    signals = scan_stock_pool(list(kline_data_dict.keys()), kline_data_dict)

    # 输出报告
    print("\n" + format_signal_report(signals))

    # 输出 JSON
    print("\n" + "=" * 50)
    print("JSON 输出：")
    print(json.dumps(format_signal_json(signals), ensure_ascii=False, indent=2))

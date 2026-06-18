"""
市场宽度分析脚本。

计算市场宽度指标：
- 涨停家数/跌停家数
- 涨跌比（上涨家数/下跌家数）
- 强势股比例（涨幅>5%的股票比例）
- 弱势股比例（跌幅>5%的股票比例）

用法：
    python3 scripts/market_breadth.py
    python3 scripts/market_breadth.py --json
"""

import json
import sys
import os

# 添加scripts目录到pythonpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.http import http_get


def get_market_breadth() -> dict:
    """获取市场宽度数据。

    Returns:
        {
            "limit_up_count": int,      # 涨停家数
            "limit_down_count": int,    # 跌停家数
            "continuous_limit_height": int,  # 连板高度
            "broken_limit_rate": float, # 炸板率
            "total_stocks": int,        # 总股票数
            "up_count": int,            # 上涨家数
            "down_count": int,          # 下跌家数
            "up_ratio": float,          # 涨跌比（上涨家数/下跌家数）
        }
    """
    try:
        # 1. 获取涨跌家数（从指数API）
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = (
            "fltt=2&invt=2"
            "&fields=f104,f105,f106"
            "&secids=1.000001,0.399001"  # 上证指数, 深证成指
        )
        full_url = f"{url}?{params}"

        response = http_get(full_url, timeout=15)
        data = json.loads(response)

        if data.get("rc") != 0 or not data.get("data"):
            print(f"指数API返回错误: {data}", file=sys.stderr)
            return _default_result()

        indices = data["data"].get("diff", [])
        if len(indices) < 2:
            print(f"指数数据不足: {len(indices)}", file=sys.stderr)
            return _default_result()

        # 合并上证和深证数据
        sh = indices[0]  # 上证指数
        sz = indices[1]  # 深证成指

        up_count = sh.get("f104", 0) + sz.get("f104", 0)
        down_count = sh.get("f105", 0) + sz.get("f105", 0)
        flat_count = sh.get("f106", 0) + sz.get("f106", 0)
        total_stocks = up_count + down_count + flat_count

        # 计算涨跌比
        up_ratio = up_count / down_count if down_count > 0 else 0

        # 2. 获取涨跌停数据（从sentiment模块）
        limit_data = get_limit_data()

        return {
            "limit_up_count": limit_data.get("limit_up_count", 0),
            "limit_down_count": limit_data.get("limit_down_count", 0),
            "continuous_limit_height": limit_data.get("continuous_limit_height", 0),
            "broken_limit_rate": limit_data.get("broken_limit_rate", 0),
            "total_stocks": total_stocks,
            "up_count": up_count,
            "down_count": down_count,
            "up_ratio": round(up_ratio, 2),
        }

    except Exception as e:
        print(f"获取市场宽度数据失败: {e}", file=sys.stderr)
        return _default_result()


def get_limit_data() -> dict:
    """获取涨跌停数据（使用sentiment.py的实现）。

    Returns:
        {
            "limit_up_count": int,      # 涨停家数
            "limit_down_count": int,    # 跌停家数
            "continuous_limit_height": int,  # 连板高度
            "broken_limit_rate": float, # 炸板率
        }
    """
    try:
        # 导入sentiment模块
        from technical.sentiment import MarketDataFetcher

        fetcher = MarketDataFetcher()
        return fetcher.get_limit_data()
    except Exception as e:
        print(f"获取涨跌停数据失败: {e}", file=sys.stderr)
        return {
            "limit_up_count": 0,
            "limit_down_count": 0,
            "continuous_limit_height": 0,
            "broken_limit_rate": 0,
        }


def _default_result() -> dict:
    """返回默认结果。"""
    return {
        "limit_up_count": 0,
        "limit_down_count": 0,
        "continuous_limit_height": 0,
        "broken_limit_rate": 0,
        "total_stocks": 0,
        "up_count": 0,
        "down_count": 0,
        "up_ratio": 0,
    }


def get_market_state(breadth: dict) -> dict:
    """根据市场宽度判断市场状态。

    Args:
        breadth: 市场宽度数据

    Returns:
        {
            "state": str,           # 市场状态
            "confidence": str,      # 置信度
            "signals": list,        # 信号列表
        }
    """
    signals = []
    limit_up = breadth.get("limit_up_count", 0)
    limit_down = breadth.get("limit_down_count", 0)
    continuous_height = breadth.get("continuous_limit_height", 0)
    broken_rate = breadth.get("broken_limit_rate", 0)
    up_ratio = breadth.get("up_ratio", 0)

    # 涨停家数判断（徐翔建议）
    if limit_up < 20:
        signals.append(f"涨停家数仅{limit_up}家，市场赚钱效应弱（退潮期信号）")
        state = "退潮"
    elif limit_up > 80:
        signals.append(f"涨停家数{limit_up}家，市场赚钱效应强（主升期信号）")
        state = "主升"
    else:
        signals.append(f"涨停家数{limit_up}家，市场情绪中性")
        state = "震荡"

    # 跌停家数判断（养家建议）
    if limit_down > 50:
        signals.append(f"跌停家数{limit_down}家，市场极度恐慌（冰点期信号）")
        state = "冰点"
    elif limit_down > 30:
        signals.append(f"跌停家数{limit_down}家，市场亏钱效应强（退潮期信号）")
        if state == "震荡":
            state = "退潮"

    # 连板高度判断（赵老哥建议）
    if continuous_height >= 5:
        signals.append(f"连板高度{continuous_height}板，短线情绪亢奋")
    elif continuous_height <= 2:
        signals.append(f"连板高度仅{continuous_height}板，接力生态恶化")

    # 炸板率判断
    if broken_rate > 40:
        signals.append(f"炸板率{broken_rate:.0f}%，市场分歧大")

    # 涨跌比判断
    if up_ratio > 2:
        signals.append(f"涨跌比{up_ratio}，市场普涨")
    elif up_ratio < 0.5:
        signals.append(f"涨跌比{up_ratio}，市场普跌")
    else:
        signals.append(f"涨跌比{up_ratio}，市场分化")

    # 综合判断
    if state == "冰点":
        confidence = "高"
    elif state in ("退潮", "主升"):
        confidence = "中"
    else:
        confidence = "低"

    return {
        "state": state,
        "confidence": confidence,
        "signals": signals,
    }


def format_breadth(breadth: dict, market_state: dict) -> str:
    """格式化市场宽度输出。"""
    lines = [
        "📊 市场宽度分析",
        "",
        "## 涨跌停数据",
        "",
        f"- 涨停家数：{breadth.get('limit_up_count', 0)} 家",
        f"- 跌停家数：{breadth.get('limit_down_count', 0)} 家",
        f"- 连板高度：{breadth.get('continuous_limit_height', 0)} 板",
        f"- 炸板率：{breadth.get('broken_limit_rate', 0):.0f}%",
        "",
        "## 涨跌家数",
        "",
        f"- 上涨家数：{breadth.get('up_count', 0)} 家",
        f"- 下跌家数：{breadth.get('down_count', 0)} 家",
        f"- 涨跌比：{breadth.get('up_ratio', 0)}",
        f"- 总股票数：{breadth.get('total_stocks', 0)} 家",
        "",
        "## 市场状态",
        "",
        f"- 状态：{market_state['state']}",
        f"- 置信度：{market_state['confidence']}",
        "",
        "## 信号",
        "",
    ]

    for signal in market_state["signals"]:
        lines.append(f"- {signal}")

    return "\n".join(lines)


def main():
    """主入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="市场宽度分析")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    # 获取市场宽度数据
    breadth = get_market_breadth()

    # 判断市场状态
    market_state = get_market_state(breadth)

    # 输出
    if args.json:
        result = {
            "breadth": breadth,
            "market_state": market_state,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_breadth(breadth, market_state))


if __name__ == "__main__":
    main()

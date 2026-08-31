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

# ---------- 市场宽度状态枚举（新增）----------
# 集中所有市场宽度状态常量,避免散落字符串
STATE_ICE = "冰点"  # 极度恐慌
STATE_RETREAT = "退潮"  # 亏钱效应强
STATE_RALLY = "主升"  # 赚钱效应强
STATE_OSCILLATE = "震荡"  # 中性

# 数据降级时使用(涨跌比定性)
STATE_BIAS_STRONG = "偏强(宽度)"
STATE_BIAS_WEAK = "偏弱(宽度)"
STATE_BIAS_NEUTRAL = "震荡(宽度)"

# 置信度
CONFIDENCE_HIGH = "高"
CONFIDENCE_MID = "中"
CONFIDENCE_LOW = "低"


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

        result = {
            "limit_up_count": limit_data.get("limit_up_count", 0),
            "limit_down_count": limit_data.get("limit_down_count", 0),
            "continuous_limit_height": limit_data.get("continuous_limit_height", 0),
            "broken_limit_rate": limit_data.get("broken_limit_rate", 0),
            "total_stocks": total_stocks,
            "up_count": up_count,
            "down_count": down_count,
            "up_ratio": round(up_ratio, 2),
        }
        # 透传降级标记（sentiment.py 在 token 未配置/接口异常时设置）
        if limit_data.get("_degraded"):
            result["_degraded"] = True
            result["_degraded_reason"] = limit_data.get("_degraded_reason", "涨跌停数据降级")
        return result

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
            "_degraded": True,
            "_degraded_reason": f"get_limit_data 异常: {e}",
        }


def _default_result() -> dict:
    """返回默认结果（指数 API 异常兜底，标记为降级）。"""
    return {
        "limit_up_count": 0,
        "limit_down_count": 0,
        "continuous_limit_height": 0,
        "broken_limit_rate": 0,
        "total_stocks": 0,
        "up_count": 0,
        "down_count": 0,
        "up_ratio": 0,
        "_degraded": True,
        "_degraded_reason": "市场宽度整体拉取失败（指数 API 异常）",
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
            "degraded": bool,       # 涨跌停数据是否降级
        }
    """
    signals = []
    limit_up = breadth.get("limit_up_count", 0)
    limit_down = breadth.get("limit_down_count", 0)
    continuous_height = breadth.get("continuous_limit_height", 0)
    broken_rate = breadth.get("broken_limit_rate", 0)
    up_ratio = breadth.get("up_ratio", 0)

    # 涨跌停数据降级时：改用涨跌比定性，state 标记"(宽度)"后缀
    # 全零且无降级标记（非交易日空数据路径）同样视为降级，避免误报退潮
    if breadth.get("_degraded") or (limit_up == 0 and limit_down == 0):
        reason = breadth.get("_degraded_reason", "涨跌停数据降级")
        signals.append(f"⚠️ {reason}，按涨跌比定性")
        if up_ratio > 2:
            state = STATE_BIAS_STRONG
            signals.append(f"涨跌比 {up_ratio}，市场普涨，宽度偏强")
        elif up_ratio < 0.5:
            state = STATE_BIAS_WEAK
            signals.append(f"涨跌比 {up_ratio}，市场普跌，宽度偏弱")
        else:
            state = STATE_BIAS_NEUTRAL
            signals.append(f"涨跌比 {up_ratio}，市场分化")
        signals.append("⚠️ 涨跌停/连板/炸板率数据降级，情绪状态待确认")
        return {
            "state": state,
            "confidence": CONFIDENCE_LOW,
            "signals": signals,
            "degraded": True,
        }

    # 统一市场状态判定：委托 market_detector.classify_market_state（唯一权威），
    # 映射为情绪周期词汇（牛市→主升、熊市→退潮）。
    from experts.market_detector import classify_market_state as _classify

    _unified = _classify(
        index_quote=None,
        change_pct=None,
        limit_up=limit_up,
        limit_down=limit_down,
        up_ratio=up_ratio,
    )
    _unified_map = {
        "牛市": STATE_RALLY,
        "熊市": STATE_RETREAT,
        "震荡": STATE_OSCILLATE,
        "冰点": STATE_ICE,
        "亢奋": STATE_RALLY,
        "防御型": STATE_OSCILLATE,
    }
    state = _unified_map.get(_unified, STATE_OSCILLATE)

    # 涨停家数补充信号（徐翔建议；不覆盖统一判定，仅作证据）
    if limit_up < 20:
        signals.append(f"涨停家数仅{limit_up}家，市场赚钱效应弱（退潮期信号）")
    elif limit_up > 80:
        signals.append(f"涨停家数{limit_up}家，市场赚钱效应强（主升期信号）")
    else:
        signals.append(f"涨停家数{limit_up}家，市场情绪中性")

    # 跌停家数判断（养家建议）
    if limit_down > 50:
        signals.append(f"跌停家数{limit_down}家，市场极度恐慌（冰点期信号）")
        state = STATE_ICE
    elif limit_down > 30:
        signals.append(f"跌停家数{limit_down}家，市场亏钱效应强（退潮期信号）")
        if state == STATE_OSCILLATE:
            state = STATE_RETREAT

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
    if state == STATE_ICE:
        confidence = CONFIDENCE_HIGH
    elif state in (STATE_RETREAT, STATE_RALLY):
        confidence = CONFIDENCE_MID
    else:
        confidence = CONFIDENCE_LOW

    # v1.x 软警告：涨跌停数据合理性校验。
    # 仅追加后缀与 warning，不改变 state 与 confidence，避免破坏现有调用方。
    total_stocks = breadth.get("total_stocks", 0)
    soft_warning = _soft_validate_limits(
        limit_up=limit_up,
        limit_down=limit_down,
        total_stocks=total_stocks,
        up_count=breadth.get("up_count", 0),
        down_count=breadth.get("down_count", 0),
    )
    if soft_warning:
        signals.append(soft_warning)
        # 仅在震荡状态下追加"(待确认)"后缀，不改变其他状态
        if state == STATE_OSCILLATE:
            state = STATE_OSCILLATE + "(待确认)"

    return {
        "state": state,
        "confidence": confidence,
        "signals": signals,
        "degraded": False,
    }


def _soft_validate_limits(limit_up: int, limit_down: int, total_stocks: int, up_count: int, down_count: int) -> str:
    """软校验涨跌停数据合理性。

    v1.x 改进：解决"涨停74/跌停0"这类数据虽非降级但仍有疑问时无提示的问题。
    仅返回 warning 字符串，无问题返回空串。
    """
    warnings = []
    # 1. total_stocks 合理性（A 股全市场约 5300 只）
    if total_stocks and not (4500 <= total_stocks <= 5500):
        warnings.append(f"⚠️ 总股票数 {total_stocks} 偏离合理区间(4500-5500)")
    # 2. 涨跌停与总股票一致性
    if total_stocks and (limit_up + limit_down) > total_stocks:
        warnings.append(f"⚠️ 涨跌停家数({limit_up+limit_down})超过总股票数")
    # 3. 涨跌家数合理性（up + down 应近似 total_stocks）
    if total_stocks and up_count and down_count:
        ratio = (up_count + down_count) / total_stocks
        if ratio < 0.5:
            warnings.append(f"⚠️ 涨跌家数覆盖 {ratio:.1%}，可能含大量停牌/新上市")
    # 4. 极端 0 信号：跌停=0 且涨停<10 表示数据可能未拉取到
    if limit_down == 0 and limit_up < 10 and total_stocks > 4500:
        warnings.append(f"⚠️ 涨停仅 {limit_up}、跌停为 0，涨跌停数据可能不完整")
    return " | ".join(warnings) if warnings else ""


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

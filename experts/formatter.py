"""决策输出格式化。"""

from typing import Dict, List

from experts import direction_from_score


def format_debate_output(result: dict) -> str:
    """格式化 debate 输出（decide.md §四 格式）。"""
    lines = []

    lines.append("## 专家圆桌投票结果")
    lines.append(
        f"**市场状态**: {result['market_state']} | "
        f"**长线权重**: {result['long_weight']:.0%} | "
        f"**短线权重**: {result['short_weight']:.0%}"
    )
    lines.append("")

    # 评分表
    lines.append("| 专家 | 评分 | 方向 | 核心理由 |")
    lines.append("|------|------|------|----------|")
    for r in result.get("expert_results", []):
        name = r.get("display_name", r.get("name", "?"))
        score = r.get("score", 0)
        direction = r.get("direction", direction_from_score(score))
        reason = r.get("reason", "-")
        lines.append(f"| {name} | {score} | {direction} | {reason} |")

    lines.append("")

    # 分组汇总
    lines.append("## 分组汇总")
    lv = result["long_votes"]
    sv = result["short_votes"]
    lines.append(
        f"- 长线组平均: {result['long_avg']}分 | "
        f"看多{lv['bull']}票 / 看空{lv['bear']}票"
    )
    lines.append(
        f"- 短线组平均: {result['short_avg']}分 | "
        f"看多{sv['bull']}票 / 看空{sv['bear']}票"
    )
    lines.append(f"- 调整后综合分: {result['composite_score']}/100")
    lines.append(f"- **最终方向: {result['direction']}**")
    lines.append(f"- 信心指数: {result['confidence']}/100")
    lines.append("")

    # 风险提示
    if result.get("risk_notes"):
        lines.append("## 风险提示")
        for note in result["risk_notes"]:
            lines.append(f"- {note}")
        lines.append("")

    # 仓位建议
    pos = result.get("position", {})
    lines.append("## 仓位建议")
    lines.append(
        f"- 推荐仓位: {pos.get('position_pct', 0)}% ({pos.get('recommendation', '-')})"
    )
    lines.append(f"- 止损位: {pos.get('stop_loss', '-')}")
    lines.append(f"- 分步建仓: {pos.get('steps', '-')}")

    # 特殊备注
    if result.get("notes"):
        lines.append("")
        lines.append("### 特殊规则触发")
        for note in result["notes"]:
            lines.append(f"- {note}")

    # 校准胜率卡片
    try:
        from experts.calibration import get_calibration, get_calibration_report

        calibration = get_calibration()
        has_data = any(v.get("events", 0) > 0 for v in calibration.values())
        if has_data:
            lines.append("")
            lines.append("## 📊 专家校准胜率")
            lines.append("")
            lines.append("| 专家 | 事件数 | 正确数 | 胜率 |")
            lines.append("|------|--------|--------|------|")
            for name, rec in calibration.items():
                events = rec.get("events", 0)
                correct = rec.get("correct", 0)
                rate = f"{correct/events:.0%}" if events > 0 else "样本不足"
                lines.append(f"| {name} | {events} | {correct} | {rate} |")
    except Exception:
        pass  # 校准数据不可用时静默跳过

    return "\n".join(lines)


def format_debate_card(result: dict) -> str:
    """格式化专家投票卡片（简洁版）。

    输出示例：
    ┌─────────────────────────────────────────────┐
    │  专家投票结果                                 │
    ├─────────────────────────────────────────────┤
    │  ██████████████████████░░░░░░  75% 买入 (6)  │
    │  ████████░░░░░░░░░░░░░░░░░░░░  12.5% 持有 (1)│
    │  ████████░░░░░░░░░░░░░░░░░░░░  12.5% 卖出 (1)│
    ├─────────────────────────────────────────────┤
    │  综合建议：买入 | 信心：78%                    │
    │  核心分歧：索罗斯看空宏观风险                   │
    └─────────────────────────────────────────────┘
    """
    expert_results = result.get("expert_results", [])
    total = len(expert_results)
    if total == 0:
        return "暂无专家投票数据"

    # 统计投票
    buy_count = sum(1 for r in expert_results if r.get("score", 0) >= 60)
    hold_count = sum(1 for r in expert_results if 40 <= r.get("score", 0) < 60)
    sell_count = sum(1 for r in expert_results if r.get("score", 0) < 40)

    buy_pct = buy_count / total * 100
    hold_pct = hold_count / total * 100
    sell_pct = sell_count / total * 100

    # 生成进度条（30 字符宽）
    bar_width = 30
    buy_bar = "█" * int(buy_pct / 100 * bar_width)
    hold_bar = "█" * int(hold_pct / 100 * bar_width)
    sell_bar = "█" * int(sell_pct / 100 * bar_width)

    # 填充到固定宽度
    buy_bar = buy_bar.ljust(bar_width, "░")
    hold_bar = hold_bar.ljust(bar_width, "░")
    sell_bar = sell_bar.ljust(bar_width, "░")

    # 找出分歧点
    dissent = _find_dissent(expert_results)

    # 综合建议
    direction = result.get("direction", "中性")
    confidence = result.get("confidence", 50)

    # 构建卡片
    card = f"""┌─────────────────────────────────────────────┐
│  专家投票结果                                 │
├─────────────────────────────────────────────┤
│  {buy_bar}  {buy_pct:5.1f}% 买入 ({buy_count})  │
│  {hold_bar}  {hold_pct:5.1f}% 持有 ({hold_count})│
│  {sell_bar}  {sell_pct:5.1f}% 卖出 ({sell_count})│
├─────────────────────────────────────────────┤
│  综合建议：{direction} | 信心：{confidence:.0f}%                    │
│  核心分歧：{dissent}                         │
└─────────────────────────────────────────────┘"""

    return card


def _find_dissent(expert_results: list) -> str:
    """找出分歧点。"""
    if not expert_results:
        return "无数据"

    # 找出看空的专家
    dissenters = [r for r in expert_results if r.get("score", 0) < 40]
    if not dissenters:
        return "无分歧"

    # 找出看多的专家
    supporters = [r for r in expert_results if r.get("score", 0) >= 60]
    if not supporters:
        return "一致看空"

    # 提取分歧原因
    names = [r.get("display_name", r.get("name", "?")) for r in dissenters]
    reasons = [r.get("reason", "看空") for r in dissenters]

    # 截断原因（保留前 20 字符）
    reason_short = reasons[0][:20] if reasons else "看空"

    return f"{','.join(names)}看空：{reason_short}"


def format_group_output(result: dict) -> str:
    """格式化单组模式输出（decide.md §七.4）。"""
    group_name = "长线模式" if result["group"] == "long_term" else "短线模式"
    lines = []

    lines.append(f"## 专家圆桌投票结果（{group_name}）")
    lines.append("")

    lines.append("| 专家 | 评分 | 方向 | 核心理由 |")
    lines.append("|------|------|------|----------|")
    for r in result.get("expert_results", []):
        name = r.get("display_name", r.get("name", "?"))
        score = r.get("score", 0)
        direction = r.get("direction", direction_from_score(score))
        reason = r.get("reason", "-")
        lines.append(f"| {name} | {score} | {direction} | {reason} |")

    lines.append("")
    lines.append("## 组内汇总")
    v = result["votes"]
    lines.append(
        f"- 平均分: {result['avg_score']}/100 | 看多{v['bull']}票 / 看空{v['bear']}票"
    )
    lines.append(f"- **最终方向: {result['direction']}**")
    lines.append(f"- 信心指数: {result['confidence']}/100")
    lines.append("")

    if result.get("risk_notes"):
        lines.append("## 风险提示")
        for note in result["risk_notes"]:
            lines.append(f"- {note}")
        lines.append("")

    pos = result.get("position", {})
    lines.append("## 仓位建议")
    lines.append(f"- 推荐仓位: {pos.get('position_pct', 0)}%")
    lines.append(f"- 止损位: {pos.get('stop_loss', '-')}")

    return "\n".join(lines)

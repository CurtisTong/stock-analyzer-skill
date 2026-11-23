# /portfolio

**持仓体检 + 调仓再平衡 + 模拟盘。** 最高频入口：每天 10 分钟就靠 `/portfolio health` 这一次体检。

## 什么时候用

| 你的问题 | 直接输入 |
| --- | --- |
| 我的持仓怎么样 | `/portfolio health` |
| 帮我调仓 / 给点调仓建议 | `/portfolio rebalance` |
| 先练手，不动真钱 | `/portfolio add sh600989 1000 18.50 --virtual` |

## 输出长什么样

项目 demo 的合成演示输出（结构稳定，数值随行情变化）：

```text
🎯 持仓健康，茅台盈利 +2.3%
📊 我的持仓 (2026-06-15 14:30)
贵州茅台  现价 1,652  +0.85%  盈亏 +2,300  🟢 健康
总成本: 165,000 | 总市值: 167,300 | 总盈亏: +2,300 (+1.4%)
📊 数据时间戳: 2026-06-15 14:30 | 数据源: 腾讯行情
📜 本输出为量化研判参考，不构成投资建议，据此操作风险自负
```

> ⚠️ "调仓建议 / 仓位"仅为演示，**仅供参考，不构成投资建议**。

**口语映射**："我买了 XX" / "减仓 XX" / "破位止损" 由 [portfolio-natural](./skill-portfolio-natural.md) 翻译成命令；嫌 CLI 麻烦可用 [portfolio-web](./skill-portfolio-web.md)。

**更多**：[skills/portfolio/SKILL.md](../../skills/portfolio/SKILL.md) · [使用者指南](../user-guide.md)

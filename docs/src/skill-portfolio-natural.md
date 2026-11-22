# /portfolio-natural

**自然语言持仓操作：把口语翻译成 portfolio 命令。** 不用记参数，照平时说话即可。

## 3 条以上典型句式

| 你会这么说 | 映射到 |
| --- | --- |
| "我买了 1000 股宝丰能源" | 新增持仓（sh600989） |
| "加仓 sh600989 500 股" | 加仓 |
| "卖了一半 / 止盈了" | 减仓 |
| "破位止损，清仓 XX" | 清仓 |

你说的话会被翻译成 portfolio 的持仓操作（新增 / 加仓 / 减仓 / 清仓），再由 [portfolio](./skill-portfolio.md) 执行；口语只是入口，不改变计算逻辑。

> ⚠️ 自然语言只负责"翻译"；据此产生的调仓建议**仅供参考，不构成投资建议**。

**更多**：[skills/portfolio-natural/SKILL.md](../../skills/portfolio-natural/SKILL.md) · [使用者指南](../user-guide.md)

# /screener

**6 策略 × 9 因子批量选股 + 股票池初始化。** 低频进阶工具：选股单次收益无法归因，且多数策略外样本未达标，别当收益承诺（见 [strategy-validation.md](../strategy-validation.md)）。

## 什么时候用

| 你的问题 | 直接输入 |
| --- | --- |
| 第一次用，先建池（离线预置） | `/screener init default` |
| 按均衡策略选前 5 只 | `/screener --strategy balanced --top 5` |
| 在白酒板块里挑质量价值股 | `/screener --sector 白酒 --strategy quality_value --top 5` |

## 输出长什么样

项目 demo 的合成演示输出（结构稳定，数值随行情变化）：

```text
🎯 质量价值策略：选出 3 只候选
代码        名称       总分  质量  估值  动量
sh600519   贵州茅台   85    92    78    65
sz000858   五粮液     72    85    68    58
📊 数据时间戳: 2026-06-15 14:30 | 数据源: 腾讯行情, 东方财富财务
```

> ⚠️ 候选池是**研究起点不是买入名单**，仅供参考，不构成投资建议。

**术语**：因子 = 打分用的指标（如估值、质量、动量）；硬过滤 = 先排除 ST、低成交额、低市值标的。详见 [methodology.md](../../methodology.md)。

**更多**：[skills/screener/SKILL.md](../../skills/screener/SKILL.md) · [使用者指南](../user-guide.md)

# /stock-technical

**纯技术面：均线 / MACD / KDJ / BOLL / RSI / 缠论 / 本土战法。** 等价于 `/stock sh600519 technical`；只想看"什么时候买、哪里失效"时用。

## 什么时候用

| 你的问题 | 直接输入 |
| --- | --- |
| 看趋势 / 量价 / 支撑阻力 | `/stock-technical sh600519` |
| 只要快速结论 | `/stock sh600519 technical --quick` |
| 买卖点分类 + 缠论结构 | `/stock sh600519 technical --classify` |

## 输出长什么样

项目 demo 的合成演示输出（结构稳定，数值随行情变化）：

```text
🎯 综合评分 72/100，多头偏强
均线系统: MA20 上行，MA5 > MA20
MACD: 金叉初现，DIF > DEA
KDJ: K=75 D=68 J=89（超买区）
支撑位: 1,620 / 1,580   阻力位: 1,700 / 1,750
📊 数据时间戳: 2026-06-15 14:30 | 数据源: 新浪K线
```

> ⚠️ "支撑 / 阻力 / 买点"是技术参考，**仅供参考，不构成投资建议**。

**术语**：缠论 = 用"走势中枢 + 买卖点"判断转折；本土战法 = 涨停 / 连板等 A 股特色形态；MACD / KDJ / RSI = 从价格算出的技术指标。详见 [methodology.md](../../methodology.md)。

**更多**：[skills/stock-technical/SKILL.md](../../skills/stock-technical/SKILL.md) · [使用者指南](../user-guide.md)

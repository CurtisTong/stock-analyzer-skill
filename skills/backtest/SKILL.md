---
name: backtest
description: 策略回测。触发词：回测一下、策略效果怎么样、哪个策略好、验证选股策略、回测收益、对比策略表现、优化策略权重。验证6种策略的历史胜率/累计收益/夏普/最大回撤等11项指标，支持基准对比和权重优化。
version: 1.19.0
model: glm-5.2
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/backtest.py *)
---

# 策略回测

运行 `scripts/backtest.py` 进行多因子选股策略的历史回测。

## Usage

```text
/backtest                                    # 默认均衡精选策略，60 天回测
/backtest --strategy balanced                # 均衡精选
/backtest --strategy quality_value           # 质量价值
/backtest --strategy growth_momentum         # 成长动量
/backtest --strategy defensive               # 防守低波
/backtest --strategy turning_point           # 拐点修复
/backtest --all                              # 比较所有策略
/backtest --benchmark sh000300               # 对比沪深300基准
/backtest --benchmark sh000300,sh000016      # 多基准对比（沪深300 + 上证50）
/backtest --all --benchmark sh000300         # 所有策略对比基准
/backtest --days 120                         # 回测 120 天
/backtest --top 10                           # 每轮选 10 只
/backtest --codes 600519,000858,300750       # 指定股票池
/backtest --optimize                         # 优化权重（目标最大化夏普比率）
```

## Workflow Coordination

- 上游来自 `screener`：验证选股策略的实际表现。
- 上游来自 `market`：选择"适用市场"匹配的策略进行回测。
- 下游到 `stock`：对回测表现最好的策略 Top 1-3 候选做五层验证。
- 下游到 `portfolio`：根据回测结果决定调仓。

输出包含：11 项核心指标 + 各策略对比 + 优化后权重建议 + 报告尾行时间戳/数据源标记。

## 执行命令

```bash
python3 scripts/backtest.py [参数]
```

## Output Format

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

回测结果包含（11 项指标）：

- **累计收益率**：策略在回测期间的总收益
- **年化收益率**：折算为年化
- **最大回撤**：最大亏损幅度
- **胜率**：正收益轮次占比
- **夏普比率**：风险调整后收益
- **信息比率**（`--benchmark` 模式，多基准支持）：超额收益/跟踪误差，衡量相对基准的主动管理能力；`--benchmark` 接受逗号分隔多个指数，每个基准独立计算并以 `信息比率({基准}): {值}` 输出
- **卡玛比率**：年化收益 / 最大回撤
- **索提诺比率**：年化收益 / 下行波动率（仅惩罚下行波动，区别于夏普的全样本波动）
- **盈亏比**：平均盈利 / 平均亏损
- **年化换手率**：滚动调仓频率
- **分位置胜率**：早期/中期/后期持仓胜率分布
- **各策略对比**（`--all` 模式，含 Sortino 列）
- **报告尾行**：所有模式末尾固定输出 `📅 报告生成: ... | 🔌 数据源: ...`，数据降级时附 `⚠️ 存在数据降级`

输出示例（`--all` 模式）：

```
📊 6 策略 60 日回测对比 (sh000300 基准)

| 策略 | 累计收益 | 年化 | 最大回撤 | 胜率 | 夏普 | 索提诺 | 信息比 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| balanced      | +12.5%  | +76% | -8.2% | 58% | 1.8 | 2.1 | 0.42 |
| quality_value | +15.2%  | +95% | -7.5% | 62% | 2.1 | 2.6 | 0.55 |
| growth_momentum| +18.7% | +120%| -12.3%| 55% | 1.5 | 1.8 | 0.38 |
| defensive     | +6.8%   | +40% | -4.5% | 65% | 1.9 | 2.4 | 0.30 |
| turning_point | +22.3%  | +150%| -15.8%| 52% | 1.3 | 1.5 | 0.45 |
| ma_volume_momentum | +10.1% | +60% | -9.0% | 56% | 1.4 | 1.7 | 0.32 |
| 基准 sh000300 | +10.0%  | -    | -      | -   | -   | -   | -    |

✅ 推荐：当前震荡市，quality_value 风险调整收益最优。
📅 报告生成: 2026-08-06T09:30:00 | 🔌 数据源: akshare, baostock
```

## 策略说明

6 策略定义详见 [`../_shared/references/strategies.md`](../_shared/references/strategies.md)。
回测场景下侧重看 `适用市场` 列选择对应策略。

## Guardrails

**⚠️ 核心限制：**
- 回测使用历史 K 线数据，但财务数据为当前快照（quality 因子有**轻微前瞻偏差**）。
- 回测收益不代表未来表现，仅供参考。
- 默认使用股票池中的股票，可通过 `--codes` 指定。
- `--optimize` 可能过拟合历史数据，建议 cross-validate 后再用于实盘。
- 数据源失败时返回低置信度结论，不臆造历史价格。
- 单次回测结果请至少对比 3 个市场环境（牛/震/熊）下表现再下结论。

## 辅助专家引用

`turning_point` 策略对应 [experts/momentum_trader.md](../../experts/momentum_trader.md)（v2.2.0 利弗莫尔 + 海龟法则）——回测入场/止损/止盈规则应与该人设对齐；策略 × 专家完整映射见 [experts/backtest_mapping.md](../../experts/backtest_mapping.md)。

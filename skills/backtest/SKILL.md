---
name: backtest
description: 策略回测。触发词：回测一下、策略效果怎么样、哪个策略好、验证选股策略、回测收益、对比策略表现、优化策略权重。验证6种策略的历史胜率/总收益/夏普/最大回撤等核心指标，支持基准对比、权重优化与 Walk-forward OOS 验证。
version: 1.33.1
model: glm-5.2
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/backtest.py *) Read(./skills/_shared/references/*.md) Read(./experts/*.md)
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
/backtest --strategy ma_volume_momentum      # 量价动量
/backtest --all                              # 比较所有策略
/backtest --benchmark sh000300               # 对比沪深300基准
/backtest --benchmark sh000300,sh000016      # 多基准对比（沪深300 + 上证50）
/backtest --all --benchmark sh000300         # 所有策略对比基准
/backtest --days 120                         # 回测 120 天
/backtest --top 10                           # 每轮选 10 只
/backtest --codes 600519,000858,300750       # 指定股票池
/backtest --optimize                         # 优化权重（目标最大化夏普比率）
/backtest --walk-forward                     # Walk-forward 滚动窗口 OOS 验证
/backtest --scenarios                        # 牛/震/熊情景分析
/backtest --capital 100000 --commission 0.00025  # 成本参数（v1.25+：本金/佣金/印花税/滑点/最低佣金）
```

## Instructions

使用中文输出。先给结论（推荐策略 + 关键指标），再给数据证据。回测必须运行 `scripts/backtest.py`，不要凭记忆编造历史收益。

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

## Workflow Coordination

- 上游来自 `screener`：验证选股策略的实际表现。
- 上游来自 `market`：选择"适用市场"匹配的策略进行回测。
- 下游到 `stock`：对回测表现最好的策略 Top 1-3 候选做五层验证。
- 下游到 `portfolio`：根据回测结果决定调仓。

输出包含：核心指标 + 各策略对比 + 优化后权重建议 + 报告尾行时间戳/数据源标记。

## 执行命令

```bash
python3 scripts/backtest.py [参数]
```

## Output Format

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

**单策略模式**依次输出（12 行指标 + 收益曲线 + 回撤图；与 CLI 打印逐行对应，不虚构列）：

- **总收益 / 平均收益 / 最大收益 / 最小收益**
- **胜率**：正收益轮次占比
- **夏普比率**：风险调整后收益
- **索提诺比率**：年化收益 / 下行波动率（仅惩罚下行波动）
- **信息比率**（`--benchmark` 模式）：超额收益/跟踪误差；多基准在单策略模式下按 `信息比率({基准}): {值}` 每基准独立一行；样本不足输出 `N/A` 而非 0
- **最大回撤**、**卡玛比率**、**盈亏比**、**年化换手率**、**分位置胜率**（早期/中期/后期）
- 报告尾行：`📅 报告生成: ... | 🔌 数据源: ...`，数据降级时附 `⚠️ 存在数据降级`

**`--all` 模式**表头为 `策略 | 总收益% | 夏普 | 索提诺 | 信息比 | 最大回撤% | 胜率%`（无年化列；基准行在表格下方单独打印，`信息比` 列取第一个基准）：

```
📊 6 策略 60 日回测对比

策略                  总收益%    夏普  索提诺   信息比 最大回撤%   胜率%
--------------------------------------------------------------------------------
balanced              +12.50   1.80    2.10    0.42    -8.20   58.3
quality_value         +15.20   2.10    2.60    0.55    -7.50   61.9
...
--------------------------------------------------------------------------------
基准 sh000300         +10.00      -       -       -       -      -
```

> 注意：年化收益率在引擎内部计算（用于卡玛/索提诺）但不打印；按模板渲染时**不得虚构「年化」列**。`--walk-forward` 的 OOS 窗口原因与 `--scenarios` 的情景收益均为独立输出段。

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

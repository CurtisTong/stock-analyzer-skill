---
name: backtest
description: 多因子选股策略回测，验证 5 种策略（均衡/质量价值/成长动量/防守低波/拐点修复）的历史胜率、累计收益、夏普比率、最大回撤、卡玛比率、盈亏比等 11 项指标。当用户要验证选股策略效果、对比策略表现或调整策略参数时触发。
version: 1.5.0
model: haiku
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
/backtest --days 120                         # 回测 120 天
/backtest --top 10                           # 每轮选 10 只
/backtest --codes 600519,000858,300750       # 指定股票池
/backtest --optimize                         # 优化权重
```

## 执行命令

```bash
python3 scripts/backtest.py [参数]
```

## 输出说明

回测结果包含：

- **累计收益率**：策略在回测期间的总收益
- **年化收益率**：折算为年化
- **最大回撤**：最大亏损幅度
- **胜率**：正收益轮次占比
- **夏普比率**：风险调整后收益
- **各策略对比**（`--all` 模式）

## 策略说明

| 策略            | 特点            | 适用市场      |
| --------------- | --------------- | ------------- |
| balanced        | 均衡五因子      | 通用          |
| quality_value   | 质量+价值权重高 | 震荡/下跌市   |
| growth_momentum | 成长+动量权重高 | 上涨市        |
| defensive       | 低波动+高质量   | 下跌/不确定市 |
| turning_point   | 拐点信号        | 反转行情      |

## 注意事项

**⚠️ 核心限制：** 回测使用历史 K 线数据，但财务数据为当前快照（quality 因子有**轻微前瞻偏差**）。回测收益不代表未来表现，仅供参考。2. 默认使用股票池中的股票，可通过 `--codes` 指定 3. 回测结果仅供参考，不构成投资建议

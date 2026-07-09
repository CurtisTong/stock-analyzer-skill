# 9 个核心 Skill 命令清单

> help skill 的子文件。help 触发时按需加载本文件，不需要把 9 段命令重复加载到主上下文。

## 1. 单股分析 - `/stock`

快速分析个股，支持三种模式：

```text
/stock <股票名称或代码>              # 快速分析（默认）
/stock <股票名称或代码> quick        # 3 分钟快评
/stock <股票名称或代码> full         # 五层完整分析
/stock <股票名称或代码> debate       # 8 人专家圆桌辩论（5 长线 + 3 短线）
/stock <股票名称或代码> debate 长线  # 仅长线 4 人专家
/stock <股票名称或代码> debate 短线  # 仅短线 4 人专家
/stock <股票代码> technical        # 技术分析（原 /technical）
/stock <股票代码> technical quick  # 快速技术扫描
/stock <股票代码> technical full   # 完整报告+缠论+战法
```

**示例**：`/stock 贵州茅台` / `/stock 600519 full` / `/stock sh600989 debate` / `/stock sh600989 technical`

## 2. 大盘复盘 - `/market`

```text
/market              # 完整复盘（默认）
/market quick        # 3 分钟快评
/market intraday     # 分时复盘
```

## 3. 板块分析 - `/sector`

```text
/sector <板块名称>              # 板块全景
/sector <板块名称> compare      # 核心标的对比
/sector <板块名称> stock        # 板块内个股筛选
```

**示例**：`/sector 半导体` / `/sector 新能源 compare`

## 4. 选股策略 - `/screener`

```text
/screener                        # 均衡精选（默认）
/screener --strategy balanced    # 均衡精选
/screener --strategy quality_value  # 质量价值
/screener --strategy growth_momentum  # 成长动量
/screener --strategy defensive   # 防守低波
/screener --strategy turning_point  # 拐点修复
/screener --sector 资源          # 指定板块筛选
/screener init                   # 初始化股票池（原 /stock-init）
/screener init force             # 强制重新初始化
/screener init default           # 使用预置数据（离线可用）
/screener init top 30            # 每板块取 Top 30
```

## 5. 持仓检查 - `/portfolio`

```text
/portfolio              # 健康检查（默认）
/portfolio health       # 健康检查
/portfolio rebalance    # 调仓建议
/portfolio compare      # 持仓对比
```

## 6. 深度研究 - `/research`

整合原 `/financial-analyst` 和 `/investment-researcher`，支持两种子命令：

```text
/research financial <任务描述>    # 财务建模（排雷/杜邦/DCF），原 /financial-analyst
/research report <任务描述>       # 全维度研究报告，原 /investment-researcher
```

**示例**：`/research financial 分析贵州茅台的财务健康状况` / `/research report 研究新能源汽车行业投资机会`

## 7. 策略回测 - `/backtest`

```text
/backtest                        # 默认均衡精选，60 天回测
/backtest --strategy quality_value  # 质量价值策略
/backtest --all                  # 比较所有策略
/backtest --days 120             # 回测 120 天
/backtest --codes 600519,000858  # 指定股票池
```

## 8. 盘中监控 - `/monitor`

```text
/monitor              # 查看监控状态
/monitor start        # 启动监控
/monitor stop         # 停止监控
```

## 进阶场景对照

| 场景           | 推荐 skill                  | 说明                           |
| -------------- | --------------------------- | ------------------------------ |
| 多空分歧大时   | `/stock debate`             | 8 人专家圆桌（5+3）         |
| 估值分歧时     | `/research financial`       | 财务建模、预测、场景分析       |
| 重大投资决策   | `/research report`          | 深度研究、尽调、多维度评估     |
| 验证策略有效性 | `/backtest --all`           | 比较 5 种策略的历史表现        |
| 盘中实时盯盘   | `/monitor start`            | 持仓异动、价格预警推送         |
| 批量选股       | `/screener --sector <板块>` | 指定板块内多因子筛选           |

### Skill 边界

- `/stock`：做**判断**（买/卖/持有），适合交易决策
- `/research financial`：做**建模**（预测/场景/敏感性），适合估值分析
- `/research report`：做**报告**（深度研究/尽调），适合重大决策和存档

## 盘前/盘后 Routine

### 盘前（开盘前）

1. `/market quick` — 了解隔夜消息和市场预期
2. `/portfolio health` — 检查持仓健康状态
3. `/monitor start` — 启动盘中监控

### 盘后（收盘后）

1. `/market` — 完整复盘
2. `/portfolio health` — 检查弱势持仓
3. `/stock <弱势持仓> technical` — 技术面复查
4. `/screener` — 寻找替代候选

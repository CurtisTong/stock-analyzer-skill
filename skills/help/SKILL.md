---
name: help
description: 显示所有可用的股票分析 skills 和使用说明。当用户输入 /help、/stocks、/skills 或询问"有哪些功能"时触发。
---

# Stock Analyzer Skills 帮助

显示所有可用的 A 股分析 skills 和使用说明。

## Usage

```text
/help
/stocks
/skills
```

## 第一次使用

首次使用请按以下步骤：

1. `/stock-init` — 初始化股票池（零配置可用，无需 token）
2. 如需持仓分析，编辑 `scripts/data/portfolio.json` 添加持仓（可选）
3. `/market quick` — 快速了解今日市场状态

完成后即可使用各分析功能。

## 可用的 Skills

### 1. 单股分析 - `/stock`

快速分析个股，支持三种模式：

```text
/stock <股票名称或代码>              # 快速分析（默认）
/stock <股票名称或代码> quick        # 3 分钟快评
/stock <股票名称或代码> full         # 五层完整分析
/stock <股票名称或代码> debate       # 8 人专家圆桌辩论
/stock <股票名称或代码> debate 长线  # 仅长线 4 人专家
/stock <股票名称或代码> debate 短线  # 仅短线 4 人专家
```

**示例：**

- `/stock 贵州茅台`
- `/stock 600519 full`
- `/stock sh600989 debate`

### 2. 大盘复盘 - `/market`

每日大盘复盘，指数+板块+风格+资金+预判：

```text
/market              # 完整复盘（默认）
/market quick        # 3 分钟快评
/market intraday     # 分时复盘
```

### 3. 板块分析 - `/sector`

行业/主题板块全景分析：

```text
/sector <板块名称>              # 板块全景
/sector <板块名称> compare      # 核心标的对比
/sector <板块名称> stock        # 板块内个股筛选
```

**示例：**

- `/sector 半导体`
- `/sector 新能源 compare`

### 4. 选股策略 - `/screener`

多因子策略筛选候选股：

```text
/screener                        # 均衡精选（默认）
/screener --strategy balanced    # 均衡精选
/screener --strategy quality_value  # 质量价值
/screener --strategy growth_momentum  # 成长动量
/screener --strategy defensive   # 防守低波
/screener --strategy turning_point  # 拐点修复
/screener --sector 资源          # 指定板块筛选
```

### 5. 技术分析 - `/technical`

纯技术分析，不做基本面：

```text
/technical <股票代码>            # 完整技术分析
/technical <股票代码> quick      # 快速扫描
/technical <股票代码> full       # 完整报告+缠论+战法
```

**示例：**

- `/technical sh600989`
- `/technical 600519 quick`

### 6. 持仓检查 - `/portfolio`

持仓组合健康检查：

```text
/portfolio              # 健康检查（默认）
/portfolio health       # 健康检查
/portfolio rebalance    # 调仓建议
/portfolio compare      # 持仓对比
```

### 7. 财务分析 - `/financial-analyst`

财务建模和预测：

```text
/financial-analyst <任务描述>
```

**示例：**

- `/financial-analyst 分析贵州茅台的财务健康状况`
- `/financial-analyst 预测宁德时代未来 3 年营收`

### 8. 投资研究 - `/investment-researcher`

市场研究和尽职调查：

```text
/investment-researcher <任务描述>
```

**示例：**

- `/investment-researcher 研究新能源汽车行业投资机会`
- `/investment-researcher 对比亚迪进行尽职调查`

### 9. 初始化股票池 - `/stock-init`

首次安装或刷新各板块前 20 只活跃股票：

```text
/stock-init              # 检测并初始化（已有数据则跳过）
/stock-init force        # 强制重新初始化
/stock-init default      # 使用预置数据（离线可用）
/stock-init top 30       # 每板块取 Top 30
```

**零配置可用：** 内置预置默认股票池数据，无需任何 token 或 API 密钥。首次安装时自动初始化，API 失败时自动 fallback 到预置数据。

### 10. 策略回测 - `/backtest`

验证选股策略的历史胜率和收益：

```text
/backtest                        # 默认均衡精选，60 天回测
/backtest --strategy quality_value  # 质量价值策略
/backtest --all                  # 比较所有策略
/backtest --days 120             # 回测 120 天
/backtest --codes 600519,000858  # 指定股票池
```

### 11. 盘中监控 - `/monitor`

实时监控持仓异动和价格预警：

```text
/monitor              # 查看监控状态
/monitor start        # 启动监控
/monitor stop         # 停止监控
```

## 工作流建议

### 快速选股流程

1. `/market quick` - 了解市场状态
2. `/screener` - 筛选候选股
3. `/stock <候选股> quick` - 快速分析
4. `/technical <候选股>` - 确认买点

### 完整分析流程

1. `/market` - 大盘复盘
2. `/sector <强势板块>` - 板块分析
3. `/screener --sector <板块>` - 板块内选股
4. `/stock <候选股> full` - 五层分析
5. `/technical <候选股>` - 技术确认
6. `/portfolio` - 持仓调整

### 持仓检查流程

1. `/portfolio health` - 检查持仓健康
2. `/market` - 确认市场风格
3. `/technical <弱势持仓>` - 检查是否破位
4. `/screener` - 找替代候选
5. `/portfolio rebalance` - 调仓建议

## 数据来源

- **实时行情**：腾讯财经 `qt.gtimg.cn`
- **财务数据**：东方财富 `emweb.securities.eastmoney.com`
- **K 线数据**：新浪财经 `money.finance.sina.com.cn`
- **公告/研报**：东方财富 `np-anotice-stock.eastmoney.com`

所有数据 API 在国内直连，无须代理。

## 注意事项

1. 所有分析仅供参考，不构成投资建议
2. 涉及实时行情时，脚本会自动获取最新数据
3. 如果脚本不可用，会参考 methodology.md 中的方法论
4. 数据失败时会说明失败的数据源和影响

## 进阶场景

| 场景           | 推荐 skill                  | 说明                           |
| -------------- | --------------------------- | ------------------------------ |
| 多空分歧大时   | `/stock debate`             | 8 人专家圆桌，长线 vs 短线视角 |
| 估值分歧时     | `/financial-analyst`        | 财务建模、预测、场景分析       |
| 重大投资决策   | `/investment-researcher`    | 深度研究、尽调、多维度评估     |
| 验证策略有效性 | `/backtest --all`           | 比较 5 种策略的历史表现        |
| 盘中实时盯盘   | `/monitor start`            | 持仓异动、价格预警推送         |
| 批量选股       | `/screener --sector <板块>` | 指定板块内多因子筛选           |

### Skill 边界说明

- `/stock`：做**判断**（买/卖/持有），适合交易决策
- `/financial-analyst`：做**建模**（预测/场景/敏感性），适合估值分析
- `/investment-researcher`：做**报告**（深度研究/尽调），适合重大决策和存档

## 盘前/盘后 Routine

### 盘前（开盘前）

1. `/market quick` — 了解隔夜消息和市场预期
2. `/portfolio health` — 检查持仓健康状态
3. `/monitor start` — 启动盘中监控

### 盘后（收盘后）

1. `/market` — 完整复盘
2. `/portfolio health` — 检查弱势持仓
3. `/technical <弱势持仓>` — 技术面复查
4. `/screener` — 寻找替代候选

## 获取更多帮助

- 查看 `workflow.md` 了解 9 个 skill 的协作流程
- 查看 `methodology.md` 了解完整投资方法论
- 查看 `README.md` 了解项目结构和安装说明

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

## 工作流建议

### 快速选股流程

1. `/market quick` - 了解市场状态
2. `/screener` - 筛选候选股
3. `/stock <候选股> quick` - 快速分析
4. `/technical <候选股>` - 确认买点

### 完整分析流程

1. `/market` - 大盘复盘
2. `<强势板块>` - 板块分析
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

## 获取更多帮助

- 查看 `workflow.md` 了解 8 个 skill 的协作流程
- 查看 `methodology.md` 了解完整投资方法论
- 查看 `README.md` 了解项目结构和安装说明

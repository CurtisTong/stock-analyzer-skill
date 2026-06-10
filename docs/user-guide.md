# 使用者指南

掌握所有 11 个技能的用法。

## 股票代码格式

支持以下格式输入股票代码：

| 格式        | 示例       | 说明           |
| ----------- | ---------- | -------------- |
| `sh` + 代码 | `sh600519` | 上海证券交易所 |
| `sz` + 代码 | `sz000858` | 深圳证券交易所 |
| 纯数字      | `600519`   | 自动推断交易所 |
| 股票名称    | `贵州茅台` | 按名称模糊匹配 |

## 技能概览

| Skill                 | 命令                                          | 用途           | 模式                               |
| --------------------- | --------------------------------------------- | -------------- | ---------------------------------- |
| stock                 | `/stock <代码或名称> [quick\|full\|debate]`   | 单股分析       | 五层框架¹ + 8人专家圆桌²           |
| market                | `/market [full\|quick\|intraday]`             | 大盘复盘       | 指数+板块+风格+资金                |
| sector                | `/sector <板块> [overview\|compare\|stock]`   | 板块分析       | 标的对比+多空博弈                  |
| portfolio             | `/portfolio [health\|rebalance\|compare]`     | 持仓健康检查   | 涨跌+支撑+风险预警                 |
| screener              | `/screener [--sector 板块] [--strategy 策略]` | 选股策略系统   | 多因子筛选+硬过滤³+候选池          |
| technical             | `/technical <代码> [quick\|full\|classify]`   | 纯技术分析     | 均线+MACD/KDJ/BOLL+缠论⁴+本土战法⁵ |
| stock-init            | `/stock-init [force\|default\|top N]`         | 初始化股票池   | 零配置可用，支持离线模式           |
| financial-analyst     | `/financial-analyst <任务>`                   | 财务分析 agent | 建模+预测+场景分析                 |
| investment-researcher | `/investment-researcher <任务>`               | 投资研究 agent | 市场研究+尽调+估值                 |
| backtest              | `/backtest [--strategy 策略] [--all]`         | 策略回测       | 历史胜率+收益验证                  |
| monitor               | `/monitor [start\|stop]`                      | 盘中监控       | 持仓异动+价格预警推送              |

> **术语说明**：
>
> - ¹ **五层框架**：基本面/估值/技术面/板块/风险收益比，详见 [methodology.md](methodology.md)
> - ² **8人专家圆桌**：长线 4 人（巴菲特/林奇/索罗斯/段永平）+ 短线 4 人（徐翔/赵老哥/炒股养家/作手新一）
> - ³ **硬过滤**：排除 ST 股、低成交额（主板≥5000万、创业板≥3500万）、低市值（主板≥40亿、创业板≥24亿）标的
> - ⁴ **缠论**：基于走势中枢和买卖点的技术分析方法
> - ⁵ **本土战法**：A 股特色 K 线形态（如涨停板、连板、断板等）

## 初始化股票池 (/stock-init)

命令格式：`/stock-init [force|default|top N]`

为 A 股各板块初始化前 20 只活跃股票，供选股、板块分析等 skill 使用。

### 自动初始化（推荐）

```
/stock-init
```

首次运行自动初始化，已有数据时跳过。**零配置可用**：无需任何 token 或 API 密钥。

### 强制刷新

```
/stock-init force
```

强制重新初始化，联网获取最新数据。

### 离线模式

```
/stock-init default
```

使用预置默认数据，不访问 API，适合离线环境。

### 自定义数量

```
/stock-init top 30
```

每板块取 Top 30 只股票（默认 20）。

### 数据源优先级

1. 东方财富 push2 API（联网获取最新数据）
2. 预置默认数据（`sector_stocks.default.json`，离线可用）

无 token 时自动尝试免费访问 API，失败时自动 fallback 到预置数据。

## 单股分析 (/stock)

命令格式：`/stock <代码或名称> [quick|full|debate]`

### quick 模式（3 分钟快评）

```
/stock sh600989 quick
```

返回：基本面+估值+技术面快速评估。

### full 模式（五层分析）

```
/stock sh600989 full
```

返回：五层分析（基本面/估值/技术面/板块/风险收益比）。

### debate 模式（专家辩论）

```
/stock sh600989 debate         # 全模式：8人圆桌（长线4+短线4）
/stock sh600989 debate 长线    # 仅长线4人（巴菲特/林奇/索罗斯/段永平）
/stock sh600989 debate 短线    # 仅短线4人（徐翔/赵老哥/养家/作手新一）
```

返回：五层分析 + 专家圆桌多空辩论 + 最终折中方案。长线/短线子模式仅调用对应组别专家。

## 大盘复盘 (/market)

命令格式：`/market [full|quick|intraday]`

### full 模式（完整复盘）

```
/market full
```

返回：主要指数+板块+风格+资金流向完整分析。

### quick 模式（快评）

```
/market quick
```

返回：主要指数涨跌+最强最弱板块+一句话结论。

### intraday 模式（盘中分时）

```
/market intraday
```

返回：盘中分时复盘。

## 板块分析 (/sector)

命令格式：`/sector <板块> [overview|compare|stock]`

### overview 模式（板块全景）

```
/sector 资源 overview
```

返回：板块全景分析。

### compare 模式（核心标的对比）

```
/sector 资源 compare
```

返回：核心标的横向对比。

### stock 模式（板块内个股深度分析）

```
/sector 资源 stock               # 板块内筛选
/sector 医药 stock 恒瑞医药      # 板块内指定个股深度分析
```

返回：板块内个股筛选或指定个股的五层分析（含板块内横向对比）。

## 持仓管理 (/portfolio)

命令格式：`/portfolio [health|rebalance|compare]`

### 自定义持仓

```bash
cp scripts/data/portfolio_example.json scripts/data/portfolio.json
# 编辑 portfolio.json，修改 codes 字段
```

> **说明**：`/portfolio` 命令读取 `scripts/data/portfolio.json`，如果不存在则回退到 `scripts/data/portfolio_example.json` 作为示例。

### health 模式（健康检查）

```
/portfolio health
```

返回：持仓实时涨跌、仓位/板块集中度、风险预警。

### rebalance 模式（调仓再平衡）

```
/portfolio rebalance
```

返回：调仓建议、再平衡方案。

### compare 模式（持仓对比）

```
/portfolio compare
```

返回：持仓标的对比分析。

## 多因子选股 (/screener)

命令格式：`/screener [--sector 板块] [--strategy 策略]`

### 5 种策略

| 策略            | 市场环境          | 说明     |
| --------------- | ----------------- | -------- |
| balanced        | 震荡/方向不明     | 均衡精选 |
| quality_value   | 价值修复/防守     | 质量价值 |
| growth_momentum | 进攻行情/主线题材 | 成长动量 |
| defensive       | 缩量弱市/避险     | 防守低波 |
| turning_point   | 超跌修复/拐点     | 拐点修复 |

### 参数说明

- `--sector <板块>`：板块名称
- `--strategy <策略>`：策略名称
- `--top <N>`：返回前 N 个候选
- `--codes <代码>`：自定义股票池（逗号分隔）
- `--exclude-loss`：剔除亏损股
- `--json`：JSON 格式输出

### 使用示例

```
/screener --sector 资源 --strategy quality_value --top 5
```

返回：硬过滤结果 + 多因子评分 + 候选池 + 跟踪条件。

## 纯技术分析 (/technical)

命令格式：`/technical <代码> [--quick] [--classify]`

### 快速模式

```
/technical sh600989 --quick
```

返回：趋势、量价、支撑阻力、技术触发和失效条件。

### 完整模式（默认）

```
/technical sh600989
```

返回：完整技术分析（均线/MACD/KDJ/BOLL/缠论/本土战法）。

### 分类模式

```
/technical sh600989 --classify
```

返回：完整分析 + 个股类型分类 + 缠论结构 + 市场环境自适应。

## 财务分析 (/financial-analyst)

命令格式：`/financial-analyst <任务>`

用途：建模、预测、场景分析。

```
/financial-analyst 分析宝丰能源的财务质量
```

## 投资研究 (/investment-researcher)

命令格式：`/investment-researcher <任务>`

用途：市场研究、尽调、估值。

```text
/investment-researcher 宝丰能源投资价值研究
```

## 策略回测 (/backtest)

命令格式：`/backtest [--strategy 策略] [--all] [--days N]`

验证选股策略的历史胜率和收益。

```text
/backtest                            # 默认均衡精选，60 天回测
/backtest --strategy quality_value   # 质量价值策略
/backtest --all                      # 比较所有 5 种策略
/backtest --days 120                 # 回测 120 天
/backtest --codes 600519,000858      # 指定股票池
```

返回：策略胜率、平均收益、最大回撤等统计指标。

## 盘中监控 (/monitor)

命令格式：`/monitor [start|stop]`

实时监控持仓异动和价格预警。

```text
/monitor           # 查看监控状态
/monitor start     # 启动监控
/monitor stop      # 停止监控
```

支持 Bark、企微、钉钉等推送通知。

## 组合使用场景

### 自上而下选股

`market` → `sector` → `screener` → `stock` → `technical` → `portfolio`

1. `market` 给出市场状态：进攻、均衡、防守
2. `sector` 找强弱板块和主题位置
3. `screener` 生成候选池和剔除原因
4. `stock` 对候选股做五层分析
5. `technical` 给买入触发、失效位、支撑阻力
6. `portfolio` 决定是否纳入持仓、替换谁、仓位多少

### 自下而上验证

`stock` → `financial-analyst` → `sector` → `technical` → `portfolio`

适合用户已经给定个股。先判断公司质量和估值，再看板块是否配合，最后确认技术触发。

### 持仓再平衡

`portfolio` → `market` → `technical` → `screener` → `stock`

1. 先找组合风险，再确认市场风格
2. 对弱势持仓跑 `technical` 判破位
3. 用 `screener` 找替代候选，再用 `stock` 精筛

### 深度研究报告

`investment-researcher` 作为总控，按需调用：

- `market`：宏观市场和风格
- `sector`：行业景气和竞争格局
- `financial-analyst`：财务质量、预测、场景
- `stock`：投资结论和风险收益比
- `technical`：交易窗口和失效条件

## 常见问题

### 数据源是否稳定？

数据源依赖外部 API 端点稳定性。如遇变更，修改 `scripts/common.py` 中端点即可。

### 如何处理 API 变更？

1. 检查 `scripts/common.py` 中的端点配置
2. 更新端点 URL
3. 验证数据格式是否变化
4. 更新字段映射

### 如何自定义选股策略？

当前策略权重在 `scripts/config/scoring.yaml` 中定义。如需自定义：

1. 修改策略权重配置
2. 添加新因子定义
3. 更新评分逻辑

### API 返回空数据怎么办？

1. 检查网络连接：`curl -s "https://qt.gtimg.cn/q=sh600519"`
2. 检查股票代码是否正确
3. 尝试其他数据源：系统会自动 fallback 到备用数据源

### 股票名称有多个匹配怎么办？

系统会返回第一个匹配结果。建议使用股票代码（如 `sh600519`）而非名称，避免歧义。

### 为什么某些股票被排除？

选股器默认排除：

- ST 股（风险警示）
- 成交额低于阈值（主板≥5000万，创业板≥3500万）
- 市值低于阈值（主板≥40亿，创业板≥24亿）

如需包含这些股票，可使用 `--codes` 参数手动指定。

## Skill 边界说明

| Skill                    | 定位   | 适用场景         |
| ------------------------ | ------ | ---------------- |
| `/stock`                 | 判断   | 买/卖/持有决策   |
| `/technical`             | 技术面 | 买入时机、止损位 |
| `/financial-analyst`     | 建模   | 估值、预测、场景 |
| `/investment-researcher` | 报告   | 深度研究、存档   |
| `/screener`              | 筛选   | 批量选股、候选池 |
| `/backtest`              | 验证   | 策略历史表现     |

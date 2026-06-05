# 使用者指南

掌握所有 8 个技能的用法。

## 技能概览

| Skill                 | 命令                                          | 用途           | 模式                             |
| --------------------- | --------------------------------------------- | -------------- | -------------------------------- |
| stock                 | `/stock <代码或名称> [quick\|full\|debate]`   | 单股分析       | 五层框架 + 8人专家圆桌           |
| market                | `/market [full\|quick\|intraday]`             | 大盘复盘       | 指数+板块+风格+资金              |
| sector                | `/sector <板块> [overview\|compare\|stock]`   | 板块分析       | 标的对比+多空博弈                |
| portfolio             | `/portfolio [health\|rebalance\|compare]`     | 持仓健康检查   | 涨跌+支撑+风险预警               |
| screener              | `/screener [--sector 板块] [--strategy 策略]` | 选股策略系统   | 多因子筛选+硬过滤+候选池         |
| technical             | `/technical <代码> [quick\|full]`             | 纯技术分析     | 均线+MACD/KDJ/BOLL+缠论+本土战法 |
| financial-analyst     | `/financial-analyst <任务>`                   | 财务分析 agent | 建模+预测+场景分析               |
| investment-researcher | `/investment-researcher <任务>`               | 投资研究 agent | 市场研究+尽调+估值               |

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
cp data/portfolio_example.json data/portfolio.json
# 编辑 portfolio.json，修改 codes 字段
```

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

```
/investment-researcher 宝丰能源投资价值研究
```

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

当前策略权重在 `scripts/screener.py` 中定义。如需自定义：

1. 修改策略权重配置
2. 添加新因子定义
3. 更新评分逻辑

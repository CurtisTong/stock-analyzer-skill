---
name: screener
description: A 股选股策略系统 skill。用于从内置板块库或用户给定股票池中按多因子策略筛选候选股，支持均衡精选、质量价值、成长动量、防守低波、拐点修复；优先运行 scripts/screener.py，并结合 A 股交易制度、流动性、板块轮动和风险约束解释结果。
version: 1.4.1
model: sonnet
allowed-tools: Bash(python3 scripts/*) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/data/sector_stocks.json) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/skills/**)
---

# Screener

A 股选股策略系统：先排雷，再打分，最后给可执行跟踪清单。

## Usage

```text
/screener [--sector 板块] [--strategy balanced|quality_value|growth_momentum|defensive|turning_point] [--top N]
```

也可直接用自然语言触发，例如"按成长动量筛资源板块前 5 名"。

## Instructions

使用中文。先输出入选名单和策略结论，再解释因子分、剔除原因和交易计划。涉及最新行情时必须运行脚本，不要凭记忆选股。

## 共享约定

- 代码前缀：`../_shared/references/code-prefix.md`
- 脚本目录：`../_shared/references/script-catalog.md`

## Workflow Coordination

完整链路见包根目录 `workflow.md`。本 skill 负责把市场/板块判断变成候选池：

- 上游来自 `market`：用 `market_regime` 选择策略。
- 上游来自 `sector`：用板块核心标的作为股票池。
- 下游到 `stock`：对 Top 1-3 候选做五层分析，验证基本面、估值和风险收益比。
- 下游到 `technical`：对候选股确认买点、失效位和量价状态。
- 下游到 `portfolio`：当用户要买入或替换持仓时，传递候选池、剔除原因和仓位上限。

输出必须包含 `strategy`、`candidates`、剔除原因和“观察/可跟踪/暂不参与”分层。

### Step 0: 判断市场环境再选策略

先获取大盘指数和板块 ETF 数据来判断当前市场环境，再选择匹配的策略：

```bash
python3 scripts/quote.py sh000001,sh510300,sh510500,sh518880 -j
```

| 市场信号                   | 推荐策略                   |
| -------------------------- | -------------------------- |
| 沪深300 > MA20 + 量能放大  | `growth_momentum` 进攻态势 |
| 指数横盘 + 板块分化        | `balanced` 均衡精选        |
| 沪深300 < MA20 + 缩量      | `defensive` 防守低波       |
| PE 处于历史低位 + 情绪悲观 | `quality_value` 价值修复   |
| 指数急跌后企稳 + 技术转强  | `turning_point` 拐点修复   |

### Step 1: 运行选股脚本

Claude Code 运行时工作目录即为项目根目录：

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
python3 scripts/screener.py --full-market --strategy balanced --top 20
python3 scripts/screener.py --full-market --sector 创业板 --strategy growth_momentum
```

可选参数：

- `--full-market`：使用全市场股票池（~5000只），而非主题板块池（~140只）。需先运行 `python3 scripts/init_pool.py --full-market` 初始化
- `--full-market --sector 创业板`：全市场模式下只筛选创业板
- `--min-amount 5000`：主板最低成交额（万元），创业板/科创板自动 ×0.7，北交所 ×1.5
- `--min-cap 40`：主板最低市值（亿元），创业板/科创板自动 ×0.6，北交所 ×0.4
- `--exclude-loss`：剔除 EPS<=0 标的

策略含义：

| 策略              | 适用市场          | 核心偏好                     |
| ----------------- | ----------------- | ---------------------------- |
| `balanced`        | 震荡/方向不明     | 质量、估值、动量、流动性均衡 |
| `quality_value`   | 价值修复/防守行情 | 高 ROE、低估值、现金流质量   |
| `growth_momentum` | 进攻行情/题材主线 | 增速、趋势、成交活跃度       |
| `defensive`       | 缩量弱市/避险     | 低估值、低负债、稳定质量     |
| `turning_point`   | 超跌修复/拐点     | 估值安全垫 + 技术转强        |

### Step 2: 解释评分

脚本输出四个因子桶和三个技术信号：

- 质量：ROE、净利增速、营收增速、毛利率、负债率、经营现金流/EPS。
- 估值：PE、PB、PEG、PE/ROE。
- 动量：20 日收益、均线结构、MACD 金叉/死叉（↑/↓/→）、RSI、量能比、换手率、量价配合。
- 流动性：成交额、市值、换手适中程度。
- 量价信号：放量上涨=资金介入、缩量下跌=抛压减轻、放量下跌=主力出货、缩量上涨=量价背离。

硬过滤（自动，按板块差异化；阈值为当前值，修改需同步 `stock-init/SKILL.md` 和 `scripts/strategies/thresholds.py`）：

- ST 名称前缀匹配
- 成交额不足（主板 <5000 万，创业板/科创板 <3500 万，北交所 <7500 万）
- 市值过小（主板 <40 亿，创业板/科创板 <24 亿，北交所 <16 亿）
- 涨跌停限制（依板块涨跌停制度自动判断）
- EPS<=0（需 --exclude-loss 启用）

### Step 3: 输出格式

```text
## 选股结论
- 当前市场判断:
- 推荐策略:
- 首选候选:
- 观察候选:
- 剔除/回避:

## 分数表
| 代码 | 名称 | 总分 | 质量 | 估值 | 动量 | 流动性 | PE | ROE | RSI | 20日% | 趋势 | 量价 |

## 跟踪条件
- 买入触发:
- 失效条件:
- 止损/降仓:
- 仓位上限:
```

### Step 4: A 股约束

- 主板（10%涨跌停）、科创板/创业板（20%）、北交所（30%）制度不同；结果中提示板块属性。
- A 股普通股票交易以 T+1 为主，短线策略必须考虑次日无法卖出的隔夜风险。
- 涨跌停附近标的已自动过滤，不纳入候选。
- 选股只是候选池，不是买入指令；买点必须由市场环境、板块强弱和个股触发条件确认。

## Guardrails

- 不要把多因子分数解释为确定收益。
- 不要只输出排名，必须说明策略适配的市场环境（Step 0 中判断）。
- 对高波动标的给仓位上限和失效条件；没有这些就不是完整建议。
- RSI >70 超买区标的需提示追高风险。
- 量价背离标的需特别警示。

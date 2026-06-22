---
name: screener
description: 选股策略。触发词：推荐几只股票、帮我选股、有什么好股票、筛股票、找便宜的好公司、哪些股票值得买、初始化股票池、刷新股票池。支持5种策略（均衡/质量价值/成长动量/防守低波/拐点修复）多因子筛选，含股票池初始化。
version: 1.13.1
model: sonnet
allowed-tools: Bash(python3 scripts/*) Bash(python3 scripts/init_pool.py *) Bash(python3 scripts/refresh_pool.py *) Read(./scripts/data/sector_stocks.json) Read(./skills/_shared/references/*.md)
---

# Screener

A 股选股策略系统：先排雷，再打分，最后给可执行跟踪清单。

## Usage

```text
/screener [--sector 板块] [--strategy balanced|quality_value|growth_momentum|defensive|turning_point] [--top N]
/screener init              # 初始化/刷新股票池（原 /stock-init）
/screener init force        # 强制重新初始化
/screener init default      # 使用预置默认数据（离线可用）
/screener init full-market  # 初始化全市场股票池（约 5000 只）
```

## 高级选项（Sprint 2-5）

```text
--no-regime      禁用市场状态 overlay（保留 V1 固定权重）
--no-normalize   禁用因子 z-score 标准化（保留 V1 原始分数）
--snapshot       保存本次筛选快照到 data/snapshots/<strategy>/<date>/<hash>.json
--full-market    全市场模式（约 5000 只股票）
--exclude-board  排除指定板块（默认排除北交所）
--no-constraints 禁用组合约束（板块集中度 + 趋势降权）
```

也可直接用自然语言触发，例如"按成长动量筛资源板块前 5 名"。

## Instructions

使用中文。先输出入选名单和策略结论，再解释因子分、剔除原因和交易计划。涉及最新行情时必须运行脚本，不要凭记忆选股。

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

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

### Step -1: 检查股票池（init 子命令）

运行前检查股票池是否已初始化。未初始化时自动触发：

```bash
ls scripts/data/sector_stocks.json 2>/dev/null || python3 scripts/init_pool.py
```

用户显式调用 `init` 子命令时：

```bash
python3 scripts/init_pool.py                # 检测并初始化（已有数据则跳过）
python3 scripts/init_pool.py --force        # 强制重新初始化
python3 scripts/init_pool.py --default      # 使用预置默认数据（离线可用）
python3 scripts/init_pool.py --full-market  # 初始化全市场 A 股池（约 5000 只）
python3 scripts/init_pool.py --top 30       # 每板块取 Top 30
```

初始化成功后展示摘要：每板块股票数量和总计。无需配置即可使用（内置预置数据），API 失败自动 fallback。

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

策略含义详见 [`../_shared/references/strategies.md`](../_shared/references/strategies.md)。

### Step 2: 解释评分

脚本输出四个因子桶和三个技术信号：

- 质量：ROE、净利增速、营收增速、毛利率、负债率、经营现金流/EPS。
- 估值：PE、PB、PEG、PE/ROE。
- 动量：20 日收益、均线结构、MACD 金叉/死叉（↑/↓/→）、RSI、量能比、换手率、量价配合。
- 流动性：成交额、市值、换手适中程度。
- 量价信号：放量上涨=资金介入、缩量下跌=抛压减轻、放量下跌=主力出货、缩量上涨=量价背离。

硬过滤（自动，按板块差异化；阈值为当前值，修改需同步 `scripts/strategies/thresholds.py`）：

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

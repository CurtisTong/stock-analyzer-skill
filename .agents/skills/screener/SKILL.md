---
name: screener
description: A 股选股策略系统 skill。用于从内置板块库或用户给定股票池中按多因子策略筛选候选股，支持均衡精选、质量价值、成长动量、防守低波、拐点修复；优先运行 scripts/screener.py，并结合 A 股交易制度、流动性、板块轮动和风险约束解释结果。
---

# Screener

A 股选股策略系统：先排雷，再打分，最后给可执行跟踪清单。

## Usage

```text
/screener [--sector 板块] [--strategy balanced|quality_value|growth_momentum|defensive|turning_point] [--top N]
```

也可直接用自然语言触发，例如“按成长动量筛资源板块前 5 名”。

## Instructions

使用中文。先输出入选名单和策略结论，再解释因子分、剔除原因和交易计划。涉及最新行情时必须运行脚本，不要凭记忆选股。

### Step 1: 运行选股脚本

当前 skill 目录到包根目录为 `../../..`：

```bash
cd ../../..
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

策略含义：

| 策略 | 适用市场 | 核心偏好 |
|------|----------|----------|
| `balanced` | 震荡/方向不明 | 质量、估值、动量、流动性均衡 |
| `quality_value` | 价值修复/防守行情 | 高 ROE、低估值、现金流质量 |
| `growth_momentum` | 进攻行情/题材主线 | 增速、趋势、成交活跃度 |
| `defensive` | 缩量弱市/避险 | 低估值、低负债、稳定质量 |
| `turning_point` | 超跌修复/拐点 | 估值安全垫 + 技术转强 |

### Step 2: 解释评分

脚本输出四个因子桶：

- 质量：ROE、净利增速、营收增速、毛利率、负债率、经营现金流/EPS。
- 估值：PE、PB、PEG、PE/ROE。
- 动量：20 日收益、均线结构、量能比、换手率、涨跌停风险。
- 流动性：成交额、市值、换手适中程度。

硬过滤优先于分数：ST、成交额过低、市值过小、亏损等标的即使分数高也不能直接推荐。

### Step 3: 输出格式

```text
## 选股结论
- 策略:
- 市场适配:
- 首选候选:
- 观察候选:
- 剔除/回避:

## 分数表
| 代码 | 名称 | 总分 | 质量 | 估值 | 动量 | 流动性 | 交易计划 |

## 跟踪条件
- 买入触发:
- 失效条件:
- 止损/降仓:
- 仓位上限:
```

### Step 4: A 股约束

- 主板与 ST、科创板、创业板、北交所涨跌幅制度不同；结果中要提示板块属性和波动约束。
- A 股普通股票交易以 T+1 为主，短线策略必须考虑次日无法卖出的隔夜风险。
- 新股、次新股、涨跌停附近、成交额不足的标的不适合机械追入。
- 选股只是候选池，不是买入指令；买点必须由市场环境、板块强弱和个股触发条件确认。

## Guardrails

- 不要把多因子分数解释为确定收益。
- 不要只输出排名，必须说明策略适配的市场环境。
- 对高波动标的给仓位上限和失效条件；没有这些就不是完整建议。

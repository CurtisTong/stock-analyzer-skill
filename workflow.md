# Skill 工作流编排

本文件定义 8 个 skill 的协作关系。原则：先判断环境，再筛候选，再深挖标的，再落到组合和跟踪。

## 入口选择

| 用户意图 | 首选 skill | 必要联动 |
|----------|------------|----------|
| 今天市场怎么看 | `market` | 强弱板块明确后转 `sector` 或 `screener` |
| 想找股票/候选池 | `screener` | 先用 `market` 判断策略，再用 `technical` 确认买点 |
| 看某个板块 | `sector` | 需要挑标的时转 `screener`，需要个股深挖时转 `stock` |
| 看某只股票 | `stock` | 技术买卖点转 `technical`，财务建模转 `financial-analyst` |
| 只看图形和买卖点 | `technical` | 不判断估值；如需基本面回到 `stock` 或 `financial-analyst` |
| 看持仓风险 | `portfolio` | 先用 `market` 判风格，再用 `technical` 查破位，用 `screener` 找替换 |
| 做财务模型 | `financial-analyst` | 输出假设和敏感性后回到 `stock` 做投资结论 |
| 做尽调/研究报告 | `investment-researcher` | 汇总 `market`/`sector`/`stock`/`financial-analyst`/`technical` 证据 |

## 标准流水线

### 1. 自上而下选股

`market` → `sector` → `screener` → `stock` → `technical` → `portfolio`

- `market` 给出市场状态：进攻、均衡、防守。
- `sector` 找强弱板块和主题位置。
- `screener` 生成候选池和剔除原因。
- `stock` 对候选股做五层分析。
- `technical` 给买入触发、失效位、支撑阻力。
- `portfolio` 决定是否纳入持仓、替换谁、仓位多少。

### 2. 自下而上验证

`stock` → `financial-analyst` → `sector` → `technical` → `portfolio`

- 适合用户已经给定个股。
- 先判断公司质量和估值，再看板块是否配合，最后确认技术触发。

### 3. 持仓再平衡

`portfolio` → `market` → `technical` → `screener` → `stock`

- 先找组合风险，再确认市场风格。
- 对弱势持仓跑 `technical` 判破位。
- 用 `screener` 找替代候选，再用 `stock` 精筛。

### 4. 深度研究报告

`investment-researcher` 作为总控，按需调用：

- `market`：宏观市场和风格。
- `sector`：行业景气和竞争格局。
- `financial-analyst`：财务质量、预测、场景。
- `stock`：投资结论和风险收益比。
- `technical`：交易窗口和失效条件。

## 交接字段

每个 skill 输出给下游时，尽量保留这些字段：

| 字段 | 含义 |
|------|------|
| `market_regime` | 进攻/均衡/防守/冰点/亢奋 |
| `sector_view` | 强势/弱势/轮动启动/主升/退潮 |
| `strategy` | balanced/quality_value/growth_momentum/defensive/turning_point |
| `candidates` | 候选代码、名称、入选理由、剔除原因 |
| `fundamental_rating` | 基本面质量和估值评级 |
| `technical_trigger` | 买入触发、支撑、阻力、止损、失效条件 |
| `position_plan` | 试探仓/标准仓/重仓/回避，以及仓位上限 |
| `confidence` | 高/中/低，说明数据缺口 |

## 决策门槛

- 市场不配合：候选股降级为观察，不直接给买入。
- 板块退潮：个股再好也降低仓位上限。
- 基本面差：技术强势只能短线观察，不进入中长期池。
- 技术未触发：高分候选只进跟踪清单。
- 组合已拥挤：新增标的必须说明替换对象或现金来源。


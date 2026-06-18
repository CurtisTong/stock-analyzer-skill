# Skill 工作流编排

本文件定义 9 个核心 skill 的协作关系。原则：先判断环境，再筛候选，再深挖标的，再落到组合和跟踪。

## 入口选择

| 用户意图         | 首选 skill           | 必要联动                                                                   |
| ---------------- | -------------------- | -------------------------------------------------------------------------- |
| 今天市场怎么看   | `market`             | 强弱板块明确后转 `sector` 或 `screener`                                    |
| 想找股票/候选池  | `screener`           | 先用 `market` 判断策略，再用 `technical` 确认买点                          |
| 看某个板块       | `sector`             | 需要挑标的时转 `screener`，需要个股深挖时转 `stock`                        |
| 看某只股票       | `stock`              | 技术买卖点转 `stock technical`，财务建模转 `research financial`            |
| 只看图形和买卖点 | `stock technical`    | 不判断估值；如需基本面回到 `stock` 或 `research financial`                 |
| 看持仓风险       | `portfolio`          | 先用 `market` 判风格，再用 `stock technical` 查破位，用 `screener` 找替换  |
| 做财务模型       | `research financial` | 输出假设和敏感性后回到 `stock` 做投资结论                                  |
| 做尽调/研究报告  | `research report`    | 汇总 `market`/`sector`/`stock`/`research financial`/`stock technical` 证据 |
| 实时监控持仓     | `monitor`            | 设置告警条件后可自动推送                                                   |
| 初始化股票池     | `screener init`      | 首次使用需要初始化候选池，零配置可用                                       |
| 历史回测验证     | `backtest`           | 验证选股策略的有效性                                                       |
| 查看帮助         | `help`               | 显示所有可用 skills 和使用说明                                             |

## 标准流水线

支持 4 种链路长度，按场景选择：

| 模式 | 链路                        | 适用场景           | 耗时       |
| ---- | --------------------------- | ------------------ | ---------- |
| 快速 | `stock` → `stock technical` | 已有标的，快速判断 | 1-2 分钟   |
| 标准 | 完整 6 环节                 | 常规选股分析       | 5-10 分钟  |
| 深度 | `research report` 总控      | 重大决策、研究报告 | 15-30 分钟 |
| 监控 | `monitor` 自动推送          | 持仓实时监控       | 持续       |

### 1. 自上而下选股

`market` → `sector` → `screener` → `stock` → `stock technical` → `portfolio`

- `market` 给出市场状态：进攻、均衡、防守。
- `sector` 找强弱板块和主题位置。
- `screener` 生成候选池和剔除原因。
- `stock` 对候选股做五层分析。
- `stock technical` 给买入触发、失效位、支撑阻力。
- `portfolio` 决定是否纳入持仓、替换谁、仓位多少。

### 2. 自下而上验证

`stock` → `research financial` → `sector` → `stock technical` → `portfolio`

- 适合用户已经给定个股。
- 先判断公司质量和估值，再看板块是否配合，最后确认技术触发。

### 3. 持仓再平衡

`portfolio` → `market` → `stock technical` → `screener` → `stock`

- 先找组合风险，再确认市场风格。
- 对弱势持仓跑 `stock technical` 判破位。
- 用 `screener` 找替代候选，再用 `stock` 精筛。

### 4. 深度研究报告

`research report` 作为总控，按需调用：

- `market`：宏观市场和风格。
- `sector`：行业景气和竞争格局。
- `research financial`：财务质量、预测、场景。
- `stock`：投资结论和风险收益比。
- `stock technical`：交易窗口和失效条件。

### 5. 持仓实时监控

`monitor` 作为常驻进程，按需调用：

- `monitor` 定时检查持仓和关注标的价格/异动
- 达到告警条件时通过 Bark/其他渠道推送
- 可设置涨跌幅提醒、成交额异动、技术信号触发等

## 交接字段

每个 skill 输出给下游时，尽量保留这些字段：

| 字段                 | 含义                                                           |
| -------------------- | -------------------------------------------------------------- |
| `market_regime`      | 进攻/均衡/防守/冰点/亢奋                                       |
| `sector_view`        | 强势/弱势/轮动启动/主升/退潮                                   |
| `strategy`           | balanced/quality_value/growth_momentum/defensive/turning_point |
| `candidates`         | 候选代码、名称、入选理由、剔除原因                             |
| `fundamental_rating` | 基本面质量和估值评级                                           |
| `technical_trigger`  | 买入触发、支撑、阻力、止损、失效条件                           |
| `position_plan`      | 试探仓/标准仓/重仓/回避，以及仓位上限                          |
| `confidence`         | 高/中/低，说明数据缺口                                         |
| `investment_horizon` | 短期（<1月）/中期（1-6月）/长期（>6月），决定专家权重          |
| `catalyst`           | 预期催化剂（财报/政策/事件），决定论点时效性                   |
| `thesis_breaker`     | 论点破灭条件，决定何时退出                                     |

## 决策门槛

| 门槛         | 量化标准                                   | 动作                             | 触发 skill                 |
| ------------ | ------------------------------------------ | -------------------------------- | -------------------------- |
| 市场不配合   | 沪深300 < MA20 且成交额 < 8000 亿          | 候选股降级为观察，不开新仓       | `screener` / `stock`       |
| 板块退潮     | 板块 ETF 跌破 MA10 且资金连续 3 日净流出   | 该板块仓位上限降为 5%            | `sector` / `portfolio`     |
| 基本面差     | ROE < 10% 或 EPS < 0                       | 仅允许短线观察，不进入中长期池   | `stock` / `screener`       |
| 技术未触发   | 未达到买入触发条件                         | 高分候选只进跟踪清单             | `technical`                |
| 组合已拥挤   | 持仓数 ≥ 10 或单行业占比 > 30%             | 新增标的必须说明替换对象         | `portfolio`                |
| 监控告警     | 持仓涨跌幅超阈值或成交额异动               | 通过 Bark 推送告警               | `monitor`                  |
| 回测验证     | `backtest` 输出夏普 < 0.5 或回撤 > 30%     | 不建议实盘使用                   | `backtest`（决策前先验证） |
| 专家分歧大   | debate 输出信心指数 < 40 或双组 2:2 分歧   | 仅观望，不开仓                   | `stock debate`             |
| 校准偏差     | 校准因子绝对值 > 0.3（专家历史准确率偏低） | 信心指数自动降权 ±10 分          | `calibration report`       |
| 美股剧烈波动 | VIX > 25 或标普 -2% 以上                   | A 股开盘前先 `/market full` 判断 | `market`                   |

> 表中"触发 skill"列指**应当主动核对或先行调用哪个 skill**：例如 `stock` 出投资结论前必须确认"市场不配合 / 基本面差 / 技术未触发"三条；`portfolio` 调仓时必须确认"组合已拥挤"和"板块退潮"；`stock debate` 决策前先看"专家分歧大"和"校准偏差"两栏判断是否值得信。

---

## 9 Skills 速查表

| Skill     | 命令                                               | 功能                                  |
| --------- | -------------------------------------------------- | ------------------------------------- |
| stock     | /stock <代码> [quick\|full\|debate\|technical]     | 单股分析，五层框架 + 8人专家圆桌      |
| market    | /market [full\|quick\|intraday]                    | 大盘复盘，指数+板块+风格+资金         |
| sector    | /sector <板块> [overview\|compare\|stock]          | 板块分析，标的对比+多空博弈           |
| portfolio | /portfolio [health\|rebalance\|compare]            | 持仓健康检查，涨跌+支撑+风险预警      |
| screener  | /screener [--sector 板块] [--strategy 策略] [init] | 多因子选股系统 + 股票池初始化         |
| research  | /research [financial\|report]                      | 深度研究：财务建模 / 市场研究 / 尽调  |
| monitor   | /monitor [start\|stop\|status]                     | 实时监控持仓和告警 + 策略关键点位扫描 |
| help      | /help                                              | 显示所有可用 skills 和使用说明        |
| backtest  | /backtest --strategy 策略 --days 天数              | 策略回测验证                          |

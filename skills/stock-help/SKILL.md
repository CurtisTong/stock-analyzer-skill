---
name: stock-help
description: Stock Analyzer 帮助索引 `/stock-help`：哪些功能、怎么用、技能列表、新手怎么开始。显示所有skills和使用说明。
version: 1.15.0
model: haiku
disable-model-invocation: false
---

# /stock-help · Stock Analyzer 帮助

> **你不需要全看——告诉我你想做什么就行**。本指南是"我大概看一下"就够了，命令清单在底部。
>
> ⚠️ **风险提示**：所有分析仅供参考，不构成投资建议。

<!-- 识别指令（给 Claude Agent 看）：
- 如果用户说"我是新手 / 第一次用 / 怎么开始 / 怎么用 / 能干嘛 / 有哪些功能 / 使用说明 / 命令清单 / 技能列表"，先 Read ../_shared/references/welcome.md 输出欢迎卡，再根据目标给出下方"按目标选入口"段
- 如果用户没说要"开始"但也没指定 skill，直接给"按目标选入口"表
-->

## 🎯 按目标选入口

### 核心（日常必用）

| 你的目标                        | 命令                   | 会得到什么                                        |
| ------------------------------- | ---------------------- | ------------------------------------------------- |
| 📊 看今天大盘涨跌               | `/market quick`        | 三大指数 + 板块 Top3 + 一句话策略                 |
| 🔍 找几只值得买的股票           | `/screener`            | 5 策略 × 5 因子筛选 → 候选池 + 跟踪清单           |
| 🎤 听 8 位 active 专家圆桌（16 份人设中 8 active = 5 长线 + 3 短线）辩论一只股票 | `/stock <代码> debate` | 8 active（5 长 + 3 短）投票 + 最终方向 + 仓位 |

### 进阶（组合管理）

| 你的目标                  | 命令               | 会得到什么                              |
| ------------------------- | ------------------ | --------------------------------------- |
| 💼 看看我的持仓           | `/portfolio`       | 涨跌 + 板块集中度 + 风险预警 + 调仓建议 |
| 🌐 某个板块怎么样         | `/sector <板块>`   | 板块全景 + 核心标的对比 + 板块内筛选    |
| 🔬 深度研究一只股票       | `/research <任务>` | 财务建模 + 排雷 + DCF + 投资建议        |
| 🧪 验证选股策略的历史表现 | `/backtest`        | 胜率 + 收益 + 夏普 + 回撤 + 基准对比    |

### 辅助（按需使用）

| 你的目标                      | 命令       | 会得到什么                           |
| ----------------------------- | ---------- | ------------------------------------ |
| 📡 盘中盯盘（异动/预警/推送） | `/monitor` | 持仓异动 + 价格预警 + Bark/企微/钉钉 |
| 📚 学投资基础（PE/ROE/MACD）  | `/learn`   | 系统化学习路径，从概念到策略         |

## 🚀 第一次使用

3 步走：

1. `/stock sh600519 quick` — 分析一只股票（3 分钟跑通，自动初始化股票池）
2. `/market quick` — 看今天市场
3. `/screener` — 找几只值得买的股票

> 跳步不会出错——系统会在需要时自动初始化股票池，无需手动操作。

### 🆕 新手推荐路径

如果你是第一次使用，建议按以下顺序：

1. **先看一只股票**：`/stock 贵州茅台 quick` → 了解五层分析框架
2. **听专家辩论**：`→ 贵州茅台 debate` → 了解 8 人（5 长线 + 3 短线）圆桌投票
3. **看今天市场**：`/market quick` → 了解大盘状态
4. **选几只股票**：`/screener` → 了解多因子选股
5. **学投资知识**：`/learn` → 系统化学习路径

## 13 个 Skill 一句话速查

### 核心 9 个

| Skill        | 命令                                             | 用途                                  |
| ------------ | ------------------------------------------------ | ------------------------------------- |
| `/stock`     | `<代码或名称> [quick\|full\|debate\|technical]`  | 单股 5 层分析 / 8 人圆桌辩论（16 份人设中 8 active = 5 长线 + 3 短线） |
| `/market`    | `[full\|quick\|intraday]`                        | 大盘复盘（指数/板块/风格/资金）       |
| `/sector`    | `<板块> [overview\|compare\|stock]`              | 板块全景 / 标的对比 / 板块内筛选      |
| `/portfolio` | `[health\|rebalance\|compare\|web]`              | 持仓健康 / 调仓 / 模拟盘 / Web 录入   |
| `/screener`  | `[--sector 板块] [--strategy 策略]`              | 5 策略 × 5 因子批量选股 + 股票池 init |
| `/research`  | `[financial\|report] <任务>`                     | 财务建模 / 全维度研究报告             |
| `/backtest`  | `[--strategy 策略] [--all]`                      | 策略历史胜率 + 收益 + 夏普 + 回撤     |
| `/monitor`   | `[scan\|levels\|check\|--cache]`                 | 盘中异动 + 价格预警 + 推送            |
| `/learn`     | `[basics\|valuation\|technical\|strategy\|risk]` | 系统化投资学习路径                    |

### 变体 4 个

| Skill                | 命令                        | 用途                              |
| -------------------- | --------------------------- | --------------------------------- |
| `/stock-technical`   | `<代码> [指标\|战法\|缠论]` | 纯技术面分析（从 stock 拆出）     |
| `/portfolio-web`     | `--port 8765`               | Web 录入服务（从 portfolio 拆出） |
| `/portfolio-natural` | `<自然语言>`                | 自然语言 → 命令映射               |
| `/stock-help`        |                             | 本帮助页（meta 索引）             |

> 📌 股票代码格式：`sh600519`（沪）/ `sz000858`（深）/ `600519`（自动推断）/ `贵州茅台`（名称模糊匹配）

## 4 个组合使用流程

### A. 自上而下选股（最常用）

```
/market quick
  → /sector 资源
    → /screener --sector 资源 --strategy quality_value
      → /stock 候选股 quick
        → /stock 候选股 technical
          → /portfolio
```

### B. 诊断现有持仓

```
/portfolio
  → /stock 持仓股 debate
    → /stock 持仓股 technical
```

### C. 深度研究单股

```
→ 贵州茅台 debate
  → /research financial 茅台
    → /research report 茅台投资价值
```

### D. 持仓再平衡

```
/portfolio rebalance
  → /market
    → /screener --strategy balanced
      → /stock 候选 quick
        → /portfolio rebalance
```

## 共享约定

- 13 个 skill = 9 核心 + 4 变体（`/technical` → `/stock technical`，`/stock-init` → `/screener init`，`/financial-analyst` + `/investment-researcher` → `/research`，旧命令仍可用）
- 所有分析仅供参考，不构成投资建议
- 数据源：腾讯 / 东财 / 新浪 / 雪球 / 同花顺 / 通达信 / AkShare / efinance（28 个，熔断器自动故障转移）

## 📚 高级子模式速查（附录）

| Skill              | 子模式                                                                    | 用途                                                                   |
| ------------------ | ------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `/stock`           | `quick` / `full` / `debate` / `debate 长线` / `debate 短线` / `technical` | quick=3 分钟；full=五层；debate=8 人圆桌（5 长 + 3 短）；technical=纯技术分析 |
| `/market`          | `full`（默认）/ `quick` / `intraday`                                      | intraday=盘中分时（5 分钟 K 线）                                       |
| `/sector`          | `overview`（默认）/ `compare` / `stock`                                   | compare=标的横向对比；stock=板块内个股深挖                             |
| `/portfolio`       | `health`（默认）/ `rebalance` / `compare` / `web`                         | rebalance=按 workflow 联动；web=本地录入服务                           |
| `/screener`        | `--strategy` 6 选 1 / `init` 子命令                                       | balanced / quality_value / growth_momentum / defensive / turning_point / ma_volume_momentum |
| `/monitor`         | `start` / `stop` / `status` / `scan` / `levels` / `check`                 | scan/levels/check=关键点位；check 支持 `--dry-run`                     |
| `/backtest`        | `--strategy` / `--all` / `--days N` / `--codes` / `--benchmark`           | --all=6 策略横评；--benchmark=对比基准指数                             |
| `/research`        | `financial <任务>` / `report <任务>`                                      | financial=财务建模；report=全维度研究报告                              |
| `/learn`           | `basics` / `valuation` / `technical` / `strategy` / `risk`                | 5 个 Level 主题                                                        |
| `/stock-technical` | `均线` / `MACD` / `KDJ` / `BOLL` / `RSI` / `缠论` / `战法`                | 纯技术面分析（从 stock 拆出的变体）                                    |

## 🆘 获取更多帮助

- 完整工作流：[`workflow.md`](../../workflow.md)
- 投资方法论：[`methodology.md`](../../methodology.md)
- 8 位 active 专家档案（16 份人设中 8 active = 5 长线 + 3 短线）：[`experts/`](../../experts/)
- 完整文档：[`README.md`](../../README.md) · [`docs/user-guide.md`](../../docs/user-guide.md) · [`docs/quick-start.md`](../../docs/quick-start.md)

## 当用户触发此 skill 时

`/stock-help` 是 meta 索引 skill（已被恢复为可被 Claude 主动调用），本身不执行分析。
触发后流程：

1. 识别用户意图：是想开始 / 想看命令清单 / 想知道怎么学。
2. 新手 → 引用 `../_shared/references/welcome.md` 输出欢迎卡 + 给出"按目标选入口"表。
3. 老手 → 直接给下方 9 个 skill 命令清单表。
4. 路径不明的提问 → 给出"按目标选入口"段。

不修改任何持仓/数据；不调用任何 `scripts/*.py`；不向外部 API 发送请求。

## 注意事项

- `/stock-help` 是只读索引 skill，**不**修改任何文件、**不**执行投资决策。
- 风险提示：所有分析仅供参考，**不构成投资建议**。
- 用户问"哪个 skill 适合我"时，根据意图（看持仓/选股/回测/研究/学习）给出 1-2 个最相关的入口。
- 13 个 skill 之间的依赖关系（market → sector → screener → stock → portfolio）详见 `workflow.md`。
- 历史合并的 4 个 skill（`/technical` `/stock-init` `/financial-analyst` `/investment-researcher`）已删除，请使用新命令：`/stock technical` `/screener init` `/research financial` `/research report`。

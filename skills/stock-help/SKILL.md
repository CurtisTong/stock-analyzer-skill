---
name: stock-help
description: Stock Analyzer 帮助。命令 `/stock-help`，触发词：/help、有哪些功能、怎么用、你会什么、帮我看看有什么命令、技能列表、使用说明、新手怎么开始、我想学习投资。显示所有可用skills和使用说明。
version: 1.13.0
model: haiku
disable-model-invocation: true
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

| 你的目标 | 命令 | 会得到什么 |
| --- | --- | --- |
| 🔍 找几只值得买的股票 | `/screener` | 5 策略 × 5 因子筛选 → 候选池 + 跟踪清单 |
| 📊 看今天大盘涨跌 | `/market quick` | 三大指数 + 板块 Top3 + 一句话策略 |
| 💼 看看我的持仓 | `/portfolio` | 涨跌 + 板块集中度 + 风险预警 + 调仓建议 |
| 🎤 听 8 位专家辩论一只股票 | `/stock <代码> debate` | 4 长线 + 4 短线投票 + 最终方向 + 仓位 |
| 🌐 某个板块怎么样 | `/sector <板块>` | 板块全景 + 核心标的对比 + 板块内筛选 |
| 🔬 深度研究一只股票 | `/research <任务>` | 财务建模 + 排雷 + DCF + 投资建议 |
| 📡 盘中盯盘（异动/预警/推送） | `/monitor` | 持仓异动 + 价格预警 + Bark/企微/钉钉 |
| 🧪 验证选股策略的历史表现 | `/backtest` | 胜率 + 收益 + 夏普 + 回撤 + 基准对比 |
| 📚 学投资基础（PE/ROE/MACD） | `/learn` | 系统化学习路径，从概念到策略 |

## 🚀 第一次使用

3 步走：

1. `/screener init` — 初始化股票池（首次需要，30 秒，零配置）
2. `/stock sh600519 quick` — 分析一只股票（3 分钟跑通）
3. `/market quick` — 看今天市场

> 跳步不会出错——系统会在需要时提示你。完整 3 步说明见 `_shared/references/welcome.md`。

## 9 个 Skill 一句话速查

| Skill | 命令 | 用途 |
| --- | --- | --- |
| `/stock` | `<代码或名称> [quick\|full\|debate\|technical]` | 单股 5 层分析 / 8 人圆桌 |
| `/market` | `[full\|quick\|intraday]` | 大盘复盘（指数/板块/风格/资金） |
| `/sector` | `<板块> [overview\|compare\|stock]` | 板块全景 / 标的对比 / 板块内筛选 |
| `/portfolio` | `[health\|rebalance\|compare\|web]` | 持仓健康 / 调仓 / 模拟盘 / Web 录入 |
| `/screener` | `[--sector 板块] [--strategy 策略]` | 5 策略 × 5 因子批量选股 + 股票池 init |
| `/research` | `[financial\|report] <任务>` | 财务建模 / 全维度研究报告 |
| `/backtest` | `[--strategy 策略] [--all]` | 策略历史胜率 + 收益 + 夏普 + 回撤 |
| `/monitor` | `[scan\|levels\|check\|--cache]` | 盘中异动 + 价格预警 + 推送 |
| `/learn` | `[basics\|valuation\|technical\|strategy\|risk]` | 系统化投资学习路径 |

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
/stock 贵州茅台 debate
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

- 9 个核心 skill（`technical` / `stock-init` / `financial-analyst` / `investment-researcher` 已合并至其他 skill，旧命令仍可用）
- 所有分析仅供参考，不构成投资建议
- 数据源：腾讯 / 东财 / 新浪 / 雪球 / 同花顺 / 通达信 / AkShare / efinance（28 个，熔断器自动故障转移）

## 📚 高级子模式速查（附录）

| Skill | 子模式 | 用途 |
| --- | --- | --- |
| `/stock` | `quick` / `full` / `debate` / `debate 长线` / `debate 短线` / `technical` | quick=3 分钟；full=五层；debate=8 人圆桌；technical=纯技术分析 |
| `/market` | `full`（默认）/ `quick` / `intraday` | intraday=盘中分时（5 分钟 K 线） |
| `/sector` | `overview`（默认）/ `compare` / `stock` | compare=标的横向对比；stock=板块内个股深挖 |
| `/portfolio` | `health`（默认）/ `rebalance` / `compare` / `web` | rebalance=按 workflow 联动；web=本地录入服务 |
| `/screener` | `--strategy` 5 选 1 / `init` 子命令 | balanced / quality_value / growth_momentum / defensive / turning_point |
| `/monitor` | `start` / `stop` / `status` / `scan` / `levels` / `check` | scan/levels/check=关键点位；check 支持 `--dry-run` |
| `/backtest` | `--strategy` / `--all` / `--days N` / `--codes` / `--benchmark` | --all=5 策略横评；--benchmark=对比基准指数 |
| `/research` | `financial <任务>` / `report <任务>` | financial=财务建模；report=全维度研究报告 |
| `/learn` | `basics` / `valuation` / `technical` / `strategy` / `risk` | 5 个 Level 主题 |

## 🆘 获取更多帮助

- 完整工作流：[`workflow.md`](../../workflow.md)
- 投资方法论：[`methodology.md`](../../methodology.md)
- 8 人专家档案：[`experts/`](../../experts/)
- 完整文档：[`README.md`](../../README.md) · [`docs/user-guide.md`](../../docs/user-guide.md) · [`docs/quick-start.md`](../../docs/quick-start.md)

## 当用户触发此 skill 时

`/stock-help` 是 meta 索引 skill（`disable-model-invocation: true`），本身不执行分析。
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
- 9 个 skill 之间的依赖关系（market → sector → screener → stock → portfolio）详见 `workflow.md`。
- 历史合并的 4 个 skill（`/technical` `/stock-init` `/financial-analyst` `/investment-researcher`）已删除，请使用新命令：`/stock technical` `/screener init` `/research financial` `/research report`。

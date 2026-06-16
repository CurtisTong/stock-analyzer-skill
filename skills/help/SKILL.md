---
name: help
description: 帮助。触发词：有哪些功能、怎么用、你会什么、帮我看看有什么命令、技能列表、使用说明、新手怎么开始、我想学习投资。显示所有可用skills和使用说明。
version: 1.11.0
model: haiku
disable-model-invocation: true
---

# Stock Analyzer Skills 帮助

显示所有可用的 A 股分析 skills 和使用说明。

## Usage

```text
/help
/stocks
/skills
```

## 你现在最关心什么？

根据你的目标，选择最合适的入口：

### 🔍 我想找机会（选股）

> 不知道买什么，想从市场里捞候选

1. `/market quick` — 3 分钟看今天市场强弱
2. `/screener` — 按策略筛出候选（默认均衡精选）
3. `/stock <候选股> quick` — 快速分析一只
4. `/stock <候选股> technical` — 确认买点和止损

### 📊 我想看大盘（复盘）

> 今天市场怎么样？该进攻还是防守？

- `/market quick` — 3 分钟快评（涨跌 + 最强最弱板块）
- `/market` — 完整复盘（指数 + 板块 + 风格 + 资金）
- `/market intraday` — 盘中分时复盘

### 💼 我想看持仓（管理）

> 我有持仓，想看看现在怎么样

1. `/portfolio health` — 持仓健康检查（涨跌 + 支撑 + 风险）
2. `/portfolio rebalance` — 调仓建议（联动市场风格）
3. `/portfolio compare` — 持仓互相对比

### 🎤 我想深度研究（单股）

> 有一只股票，想全面了解

1. `/stock <代码> full` — 五层完整分析
2. `/stock <代码> debate` — 8 人专家圆桌辩论
3. `/stock <代码> technical` — 技术面深度分析
4. `/research financial <代码>` — 财务建模与预测

### 📈 我想看板块（行业）

> 某个行业怎么样？谁是龙头？

1. `/market` — 先看今日板块强弱
2. `/sector <板块>` — 板块全景 + 核心标的
3. `/sector <板块> compare` — 板块内标的横向对比

## 新手引导

如果你是第一次使用，请告诉我你想做什么，我会一步步引导你：

### 场景 A：我想分析一只股票

请告诉我股票名称或代码（如"茅台"或"600519"），我会帮你：

1. 查看实时行情和估值
2. 分析技术面信号
3. 查看 8 位专家的投票结果

示例：`茅台` 或 `600519`

### 场景 B：我想了解今日大盘

请告诉我"大盘"，我会帮你：

1. 查看三大指数涨跌
2. 分析板块强弱
3. 判断市场情绪

示例：`大盘`

### 场景 C：我想学习投资知识

请告诉我"学习"，我会带你了解：

1. 基础概念（PE、ROE、MACD 等）
2. 估值方法
3. 技术分析入门
4. 投资策略

示例：`学习`

### 场景 D：我想选股

请告诉我"选股"，我会帮你：

1. 了解当前市场风格
2. 按策略筛选候选股
3. 分析候选股详情

示例：`选股`

---

## 第一次使用

首次使用请按以下步骤：

1. `/screener init` — 初始化股票池（零配置可用，无需 token）
2. 如需全量选股，运行 `/screener init full-market` 初始化全市场 A 股池（约 5000 只）
3. 如需持仓分析，编辑 `scripts/data/portfolio.json` 添加持仓（可选）
4. `/market quick` — 快速了解今日市场状态

完成后即可使用各分析功能。

### 股票池模式

| 模式         | 数据量   | 初始化命令                   | 适用场景             |
| ------------ | -------- | ---------------------------- | -------------------- |
| 主题板块池   | ~140 只  | `/screener init`（默认）     | 板块分析、快速选股   |
| 全市场股票池 | ~5000 只 | `/screener init full-market` | 全量选股、多因子筛选 |

## 共享约定

- 9 个核心 skill（`technical`/`stock-init`/`financial-analyst`/`investment-researcher` 已合并）

## 工作流建议

### 快速选股流程

1. `/market quick` - 了解市场状态
2. `/screener` - 筛选候选股
3. `/stock <候选股> quick` - 快速分析
4. `/stock <候选股> technical` - 确认买点

### 完整分析流程

1. `/market` - 大盘复盘
2. `/sector <强势板块>` - 板块分析
3. `/screener --sector <板块>` - 板块内选股
4. `/stock <候选股> full` - 五层分析
5. `/stock <候选股> technical` - 技术确认
6. `/portfolio` - 持仓调整

### 持仓检查流程

1. `/portfolio health` - 检查持仓健康
2. `/market` - 确认市场风格
3. `/stock <弱势持仓> technical` - 检查是否破位
4. `/screener` - 找替代候选
5. `/portfolio rebalance` - 调仓建议

### 高级子模式速查

| Skill        | 子模式                                                           | 用途                                                                                      |
| ------------ | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `/stock`     | `quick`/`full`/`debate`/`debate 长线`/`debate 短线`/`technical`  | quick=3 分钟；full=五层；debate=8 人圆桌；technical=纯技术分析（含缠论+战法）             |
| `/market`    | `full`（默认）/ `quick` / `intraday`                             | intraday=盘中分时复盘（5 分钟 K 线）                                                      |
| `/sector`    | `overview`（默认）/ `compare` / `stock`                          | compare=标的横向对比；stock=板块内个股深挖                                                |
| `/portfolio` | `health`（默认）/ `rebalance` / `compare` / `web`                | rebalance=按 workflow 联动；web=本地录入服务                                              |
| `/screener`  | `--strategy` 5 选 1 / `init` 子命令                              | balanced / quality_value / growth_momentum / defensive / turning_point；init=初始化股票池 |
| `/monitor`   | `start` / `stop` / `status` / `scan` / `levels <code>` / `check` | scan/levels/check=关键点位扫描；check 支持 `--dry-run`                                    |
| `/backtest`  | `--strategy` / `--all` / `--days N` / `--codes` / `--benchmark`  | --all=5 策略横评；--benchmark=对比基准指数                                                |
| `/research`  | `financial <任务>` / `report <任务>`                             | financial=财务建模（排雷/杜邦/DCF）；report=全维度研究报告                                |

## 数据来源

- **实时行情**：腾讯财经 `qt.gtimg.cn`
- **财务数据**：东方财富 `emweb.securities.eastmoney.com`
- **K 线数据**：新浪财经 `money.finance.sina.com.cn`
- **公告/研报**：东方财富 `np-anotice-stock.eastmoney.com`

所有数据 API 在国内直连，无须代理。

## Guardrails

- 所有分析仅供参考，不构成投资建议
- 涉及实时行情时，脚本会自动获取最新数据
- 如果脚本不可用，会参考 `methodology.md` 中的方法论
- 数据失败时会说明失败的数据源和影响

## 获取更多帮助

- 9 个核心 skill 命令清单（`technical`/`stock-init`/`financial-analyst`/`investment-researcher` 已合并至其他 skill）
- 查看本仓库根目录的 `workflow.md` 了解 skill 协作流程（入口选择 / 标准流水线 / 交接字段 / 决策门槛）
- 查看本仓库根目录的 `methodology.md` 了解完整投资方法论（五层框架、专家圆桌、字段含义）
- 查看 `README.md` 了解项目结构和安装说明

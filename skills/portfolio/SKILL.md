---
name: portfolio
description: 持仓管理。触发词：我的持仓怎么样、帮我看看持仓、我买了XX、加仓XX、减仓XX、清仓XX、持仓健康检查、帮我调仓、自选股、持仓对比、仓位分析。支持买入/加仓/减仓/清仓CRUD、自选股管理、组合涨跌/集中度/风险预警/调仓再平衡。⚠️ AI 辅助生成，仅供参考，不构成投资建议。
version: 1.22.1
model: glm-5.2
allowed-tools: Bash(python3 scripts/quote.py *) Bash(python3 scripts/finance.py *) Bash(python3 scripts/kline.py *) Bash(python3 scripts/portfolio_web.py *) Bash(curl -X POST http://127.0.0.1:8765/api/positions *) Bash(lsof -i:8765 *) Read(./scripts/data/portfolio.json) Read(./scripts/data/portfolio_example.json) Read(./skills/_shared/references/*.md)
---

# Portfolio Management

持仓组合管理与健康检查——增删改查 + 实时盈亏 + 板块分布 + 风险监控 + 调仓建议。

> 本 skill 是 **持仓 CRUD 主流程**；两个子模块共享同一 `portfolio_web.py` 入口（非独立进程）：
> - Web 服务操作（`web` / `--port` / `--open` / `--stop`）见 [`/portfolio-web`](./../portfolio-web/SKILL.md)
> - 自然语言触发词典（"我买了 XX" / "减仓" / "清仓" 等）见 [`/portfolio-natural`](./../portfolio-natural/SKILL.md)

## API 契约（关键不变量）

CRUD 操作在 `scripts/portfolio/crud.py`，`PortfolioManager` 仅作 facade。SKILL 命令与 Web `/api/positions` 共用同一层契约，**避免上层假设返回类型漂移**。

| 操作 | 函数 | 入参关键约束 | 返回类型 |
| --- | --- | --- | --- |
| 买入/加仓 | `add_position(manager, code, name, cost, quantity, buy_date="", tags=None, auto_save=True, cost_source="user_input")` | `cost > 0`、`quantity > 0`、code 自动 normalize | `dict`（已存在则加权平均成本；截图自动置 `cost_source="screenshot"`，加权平均后自动置 `"calculated"`） |
| 减仓 | `reduce_position(manager, code, quantity, auto_save=True)` | `quantity > 0` 且 ≤ 当前持仓 | `dict`（清空则 `None`） |
| 清仓 | `remove_position(manager, code, auto_save=True)` | — | `bool` |
| 更新字段 | `update_position(manager, code, auto_save=True, **fields)` | fields 允许 `cost/name/quantity/buy_date/tags` | `dict` |
| 加自选 | `add_watch(manager, code, name="", note="", auto_save=True)` | code 自动 normalize | `dict` |

**读取侧契约**：`get_positions() -> list[dict]`；`get_watchlist() -> list[dict]`；`get_position(code) -> dict | None`（未找到返回 `None`，**不是空 dict**）；`is_virtual() -> bool`。

> **错配历史（避免回归）**：`add_position` 返回 `dict` 而 `get_positions` 返回 `list` 是符合各操作语义的（CRUD 返回变更后的实体，读取返回集合），**不要统一成同一种类型**。`cost_source` 显式列为入参，加仓产生加权平均成本时自动置 `"calculated"`。详见 `scripts/portfolio/crud.py` 顶部 docstring。

## Usage

```text
/portfolio [操作] [参数...]
```

### 持仓操作

| 操作 | 说明 | 示例 |
| --- | --- | --- |
| `add <code> <qty> <cost>` | 买入建仓/加仓 | `/portfolio add sh600989 1000 18.50` |
| `reduce <code> <qty>` | 减仓 | `/portfolio reduce sh600989 500` |
| `remove <code>` | 清仓 | `/portfolio remove sh600989` |
| `update <code> [字段=值]` | 更新持仓信息 | `/portfolio update sh600989 cost=19.00` |
| `tag <code> <标签...>` | 添加标签 | `/portfolio tag sh600989 长线 能源` |
| `untag <code> <标签...>` | 移除标签 | `/portfolio untag sh600989 短线` |
| `undo` / `history` | 撤销最近操作 / 查看操作历史 | `/portfolio undo` |

### 自选操作

| 操作 | 说明 | 示例 |
| --- | --- | --- |
| `watch <code>` | 加自选 | `/portfolio watch sz000807 --buy 12.00` |
| `unwatch <code>` | 删自选 | `/portfolio unwatch sz000807` |

### 查询模式

| 模式 | 说明 |
| --- | --- |
| `health`（默认） | 持仓健康检查，涨跌+支撑位+风险预警 |
| `rebalance` | 调仓建议（**按 `workflow.md` §3 联动 `market` → `technical` → `screener` → `stock`**，不是单点输出） |
| `compare` | 未实现——标的对比由 `/stock` 多股对比或 `/sector` 覆盖 |

### 虚拟持仓（模拟盘）

`--virtual` 参数启动虚拟持仓模式，数据存 `scripts/data/portfolio_virtual.json`（与实盘隔离），支持所有 CRUD，适合练习与策略验证：

```bash
python3 scripts/portfolio_web.py --virtual
/portfolio health --virtual
```

## Instructions

使用中文，输出用表格+红绿标记。先给组合状态和最需要处理的风险，再给逐项数据。不要假设用户的真实持仓，除非 `scripts/data/portfolio.json` 或用户消息提供了持仓。

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

Web 服务相关命令见 [`/portfolio-web`](../portfolio-web/SKILL.md)，**不要阻塞当前会话等 `serve_forever()` 结束**。

### 持仓数据读取

Claude Code 运行时工作目录即为项目根目录。先读取 `scripts/data/portfolio.json`；不存在时使用 `scripts/data/portfolio_example.json`，并在输出中标注"示例持仓"。

v2 数据模型包含 `positions`（持仓）和 `watchlist`（自选）两个列表，自动兼容 v1 格式（仅 `codes` 列表）。

### 持仓操作执行

使用 Python 调用 `crud.py`（或走 `/portfolio-web` HTTP API）：

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from portfolio import PortfolioManager
pm = PortfolioManager()
pm.add_position('sh600989', '宝丰能源', 18.50, 1000, tags=['能源', '长线'])   # 买入/加仓
pm.reduce_position('sh600989', 500)                                          # 减仓
pm.add_watch('sz000858', '五粮液', target_buy=120.0)                         # 加自选
"
```

加仓时自动计算加权平均成本：原 1000 股 @ 18.50 + 加仓 500 股 @ 19.00 → 新成本 = (18.50×1000 + 19.00×500) / 1500 = 18.67。

撤销与风险报告（高级功能）：

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from portfolio import PortfolioManager
pm = PortfolioManager()
print(pm.undo())                                            # 撤销最近一次操作（最多保留 50 条）
print(pm.risk_summary(quotes={'sh600519': 1900}))           # 1 日 VaR/CVaR + 风险贡献 Top5
print(pm.attribution_report(quotes={'sh600519': 1900}))     # Brinson 归因（配置/选择/交互效应）
"
```

### 数据获取

按 `../_shared/references/script-catalog.md` 调用 `quote.py` / `finance.py` / `kline.py`，组合维度用 `-j` JSON 计算权重、行业暴露和排序。

- 大盘：`sh000001,sz399001,sz399006,sh000016`
- 板块 ETF：`sh512010,sh512480,sh512690,sh512800,sh513120,sh518880`

## Workflow Coordination

完整链路见包根目录 `workflow.md`。本 skill 是最终落地和再平衡环节：

- 上游来自 `market`：接收市场状态，决定组合进攻/均衡/防守。
- 上游来自 `technical`：接收破位、止损、支撑阻力，决定减仓或观察。
- 上游来自 `screener`/`stock`：接收替代候选和投资结论，决定换仓。
- 下游到 `screener`：组合需要补行业、降集中度或替换弱势股时，生成候选池。
- 下游到 `stock`：对拟买入或拟替换标的做最终五层确认。

输出必须包含 `position_plan`、行业集中度、需要处理的持仓、替代候选需求。

## Output Format

### 双时间戳约定（health_report 返回 as_of + data_mtime）

| 字段 | 含义 | 来源 | 用途 |
| --- | --- | --- | --- |
| `as_of` | 行情快照/调用时间 | `quotes_map["__as_of__"]` → `datetime.now()` 兜底 | 标题时间戳"📊 我的持仓 (YYYY-MM-DD HH:MM)" |
| `data_mtime` | portfolio.json 最后写入时间 | `Path.stat().st_mtime` | 数据新鲜度判断；与行情时间错位时提示"持仓快照 16:15 / 行情 10:30" |

### 实际总仓位（可选）

`portfolio.json` 顶层可配置 `total_assets`（账户总资产），health_report 输出 `position_ratio`（持仓成本 ÷ 总资产 %）。未配置时不报错，仅提示无法计算实际总仓位；选股报告给新标的仓位建议时，须结合 `position_ratio` 校验实际组合仓位不超限。

### 持仓一览（默认输出）

```
📊 我的持仓 (2025-06-08 14:30)
┌──────────┬───────┬────────┬─────────┬──────────┐
│ 股票      │ 现价   │ 涨跌    │ 盈亏      │ 状态      │
├──────────┼───────┼────────┼─────────┼──────────┤
│ 宝丰能源  │ 19.20 │ +3.2%  │ +700 📈  │ 🟢 健康   │
│ 云铝股份  │ 13.80 │ -1.5%  │ -1,200📉 │ 🟡 弱势   │
└──────────┴───────┴────────┴─────────┴──────────┘
总成本: 47,500 | 总市值: 50,400 | 总盈亏: +2,900 (+6.1%)

📋 自选股 (2)
┌──────────┬────────┬────────┬────────┬──────────┐
│ 股票      │ 现价    │ 目标买  │ 止损/卖  │ 状态      │
├──────────┼────────┼────────┼────────┼──────────┤
│ 云铝股份  │ 13.80  │ 12.00  │ 16.00  │ 🟢 观望   │
│ 北方华创  │ 320.00 │ 280.00 │ 260.00 │ 🟡 接近买 │
└──────────┴────────┴────────┴────────┴──────────┘
```

自选股状态分级：🔴 已破止损（现价 ≤ target_sell）| 🟡 接近止损（距止损 ≤3%）| 🟡 接近买点（距买点 ≤5%）| 🟢 到达买点（现价 ≤ target_buy）| 🟢 观望。

### 健康检查（health 模式）

```
持仓健康检查 | 时间: YYYY-MM-DD HH:MM
┌─────────┬──────┬──────┬──────┬──────┬──────┐
│ 标的     │ 现价  │ 今日  │ 盈亏  │ 状态  │ 风险  │
├─────────┼──────┼──────┼──────┼──────┼──────┤
│ 宝丰能源 │ 24.59│ +0.2%│ +6090│ ✅   │ 24.0 │
└─────────┴──────┴──────┴──────┴──────┴──────┘
板块分布: 资源40% 医药0% 科技5% 避险8% 金融3.5% 现金30%
风险评级: ⚠️ 资源仓位偏重，科技偏轻
```

### 风险预警规则

> 权威阈值表：`../_shared/references/alert-thresholds.md`（与 `portfolio-web` 后台监控共享）。

| 预警 | 条件 | 操作建议 |
| --- | --- | --- |
| 🔴 破位 | 跌破关键支撑位 | 减仓/止损 |
| 🟡 弱势 | 连续2日跑输板块 | 观察/减仓 |
| 🟢 健康 | 在支撑位上方运行 | 持有 |
| ⭐ 强势 | 板块领涨+放量 | 持有/加仓 |

### 持仓技术分析交叉校验（批量诊断必跑）

> 当对持仓批量做技术分析（如逐只跑 `technical.py`）时，必须对每只股票的止损位与现价交叉校验，防止"止损价高于现价"被误读为正常止损。详见 `../_shared/references/guardrails.md` §四止损位置约束。

1. `止损价 < 现价`（`breakdown=false`）：正常，按止损位执行风控。
2. `止损价 ≥ 现价`（`breakdown=true`）：标记"已破位"，该只**不得输出"持有/观察"**，必须输出"破位减仓/离场"，并在汇总表用 ⚠️ 标记。
3. 汇总段必须单独列出"已破位标的"清单。

> 校验方式：`technical.py -j` 输出的 `features.breakdown` 布尔字段为权威信号，`features.stop_loss_pct` 为负值即破位。

## Guardrails

- 自动兼容 v1 格式，首次使用时引导用户补充成本价和数量。
- 加仓时自动计算加权平均成本，减仓时保持成本价不变。
- 清仓时确认后移除，不保留历史记录（简化设计）。
- 未知成本价时，不计算真实盈亏，只做当日涨跌、估值和风险状态。
- 调仓建议必须包含"减/加多少、触发条件、替代标的或现金比例"，避免泛泛而谈。
- 不要建议超过用户风险承受能力的集中仓位；单一行业或主题过重时优先提示组合风险。
- web server 与 CLI / 外部脚本同时写 `scripts/data/portfolio.json` 时，后写覆盖前写；建议 web 作为唯一录入入口。

## 辅助专家引用

仓位上限与集中度约束的权威来源 = [experts/risk_manager.md](../../experts/risk_manager.md) §四 仓位与止损（前 3 大 ≤ 50%、前 5 大 ≤ 70%、单一行业 ≤ 30%；总仓位牛 80-90% / 震 70% / 熊 ≤ 50% / 极度恐慌 ≤ 30-40%）；portfolio 任何"加仓到 X%"建议必须在此上限之内。
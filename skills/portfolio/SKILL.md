---
name: portfolio
description: 持仓管理。触发词：我的持仓怎么样、帮我看看持仓、我买了XX、加仓XX、减仓XX、清仓XX、持仓健康检查、帮我调仓、自选股、持仓对比、仓位分析。支持买入/加仓/减仓/清仓CRUD、自选股管理、组合涨跌/集中度/风险预警/调仓再平衡。
version: 1.11.0
model: sonnet
allowed-tools: Bash(python3 scripts/quote.py *) Bash(python3 scripts/finance.py *) Bash(python3 scripts/kline.py *) Bash(python3 scripts/portfolio_web.py *) Bash(curl -X POST http://127.0.0.1:8765/api/positions *) Bash(lsof -i:8765 *) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/scripts/data/portfolio.json) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/scripts/data/portfolio_example.json) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/skills/**)
---

# Portfolio Management

持仓组合管理与健康检查——增删改查 + 实时盈亏 + 板块分布 + 风险监控 + 调仓建议。

## Usage

```text
/portfolio [操作] [参数...]
```

### 持仓操作

| 操作                      | 说明          | 示例                                    |
| ------------------------- | ------------- | --------------------------------------- |
| `add <code> <qty> <cost>` | 买入建仓/加仓 | `/portfolio add sh600989 1000 18.50`    |
| `reduce <code> <qty>`     | 减仓          | `/portfolio reduce sh600989 500`        |
| `remove <code>`           | 清仓          | `/portfolio remove sh600989`            |
| `update <code> [字段=值]` | 更新持仓信息  | `/portfolio update sh600989 cost=19.00` |
| `tag <code> <标签...>`    | 添加标签      | `/portfolio tag sh600989 长线 能源`     |
| `untag <code> <标签...>`  | 移除标签      | `/portfolio untag sh600989 短线`        |

### 自选操作

| 操作             | 说明   | 示例                                    |
| ---------------- | ------ | --------------------------------------- |
| `watch <code>`   | 加自选 | `/portfolio watch sz000807 --buy 12.00` |
| `unwatch <code>` | 删自选 | `/portfolio unwatch sz000807`           |

### 查询模式

| 模式             | 别名     | 说明                                                                                                                                   |
| ---------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `health`（默认） |          | 持仓健康检查，涨跌+支撑位+风险预警                                                                                                     |
| `rebalance`      | 调仓建议 | 结合大盘风格给出调仓建议（**会按 `workflow.md` §3 "持仓再平衡"链路联动 `market` → `technical` → `screener` → `stock`**，不是单点输出） |
| `compare`        |          | 持仓标的互相对比+替换建议                                                                                                              |

### Web 录入

| 操作                          | 说明                                                            | 示例                                   |
| ----------------------------- | --------------------------------------------------------------- | -------------------------------------- |
| `web`                         | 启动本地 Web 录入服务（127.0.0.1:8765），默认启用后台策略监控   | `/portfolio web`                       |
| `web --port <端口>`           | 指定端口启动                                                    | `/portfolio web --port 9000`           |
| `web --open`                  | 启动后自动打开浏览器                                            | `/portfolio web --open`                |
| `web --no-notify`             | 启动时不推送通知（默认自动接入已配置的推送通道）                | `/portfolio web --no-notify`           |
| `web --no-monitor`            | 禁用后台策略监控                                                | `/portfolio web --no-monitor`          |
| `web --monitor-interval <秒>` | 监控检查间隔（默认 300 秒）                                     | `/portfolio web --monitor-interval 60` |
| `web --stop`                  | 停止后台运行的 Web 服务                                         | `/portfolio web --stop`                |
| `web --status`                | 查看 Web 服务运行状态                                           | `/portfolio web --status`              |
| `web --virtual`               | 启动虚拟持仓模式（模拟盘），数据存储在 `portfolio_virtual.json` | `/portfolio web --virtual`             |

### 虚拟持仓（模拟盘）

使用 `--virtual` 参数启动虚拟持仓模式，适合练习和策略验证：

```bash
# 启动虚拟持仓 Web 服务
python3 scripts/portfolio_web.py --virtual

# 或通过 skill 触发
/portfolio web --virtual
```

虚拟持仓特点：

- 数据存储在 `scripts/data/portfolio_virtual.json`（与实盘隔离）
- 支持所有 CRUD 操作（买入/减仓/清仓/加自选）
- 不影响真实持仓数据
- 适合验证投资策略、练习操作

对比实盘和虚拟盘：

```bash
# 查看实盘
/portfolio health

# 查看虚拟盘（需先启动 --virtual Web 服务）
/portfolio health --virtual
```

### 自然语言

支持自然语言触发，例如：

- "买入了 1000 股宝丰能源，成本 18.5"
- "宝丰能源卖了 500 股"
- "关注云铝股份，目标买入价 12"
- "看看我的持仓"

## Instructions

使用中文，输出用表格+红绿标记。先给组合状态和最需要处理的风险，再给逐项数据。不要假设用户的真实持仓，除非 `scripts/data/portfolio.json` 或用户消息提供了持仓。

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

### Web 录入命令处理

当用户输入 `/portfolio web` 系列命令时，按以下方式处理：

| 命令                           | 处理方式                                                         |
| ------------------------------ | ---------------------------------------------------------------- |
| `/portfolio web`               | `python3 scripts/portfolio_web.py`（后台启动 + 自动打开浏览器）  |
| `/portfolio web --port <端口>` | `python3 scripts/portfolio_web.py --port <端口>`                 |
| `/portfolio web --no-open`     | `python3 scripts/portfolio_web.py --no-open`（不自动打开浏览器） |
| `/portfolio web --stop`        | `pkill -f "portfolio_web.py" && echo "已停止"`                   |
| `/portfolio web --status`      | `lsof -i:8765 2>/dev/null && echo "运行中" \|\| echo "未运行"`   |

**注意**：

- `web` 命令默认自动打开浏览器，使用 `--no-open` 可禁用。
- 如果端口已被占用（上一次未正常退出），提示用户先运行 `web --stop`。
- 启动后在输出中附加一行：`浏览器访问：http://127.0.0.1:8765/`
- 不要阻塞当前会话等 `serve_forever()` 结束。

## 共享约定

- 代码前缀：`../_shared/references/code-prefix.md`
- 脚本目录：`../_shared/references/script-catalog.md`

### 持仓数据读取

Claude Code 运行时工作目录即为项目根目录。先读取 `scripts/data/portfolio.json`；不存在时使用 `scripts/data/portfolio_example.json`，并在输出中标注"示例持仓"。

v2 数据模型包含 `positions`（持仓）和 `watchlist`（自选）两个列表。自动兼容 v1 格式（仅 `codes` 列表），首次使用时提示用户补充持仓信息。

使用 Python 读取数据：

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from portfolio import PortfolioManager
pm = PortfolioManager()
positions = pm.get_positions()
watchlist = pm.get_watchlist()
codes = pm.get_all_codes()
print('持仓:', positions)
print('自选:', watchlist)
"
```

### 持仓操作执行

使用 CLI 命令操作：

```bash
# 买入建仓 / 加仓
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from portfolio import PortfolioManager
pm = PortfolioManager()
pm.add_position('sh600989', '宝丰能源', 18.50, 1000, tags=['能源', '长线'])
print('✅ 已添加持仓')
"

# 减仓
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from portfolio import PortfolioManager
pm = PortfolioManager()
pm.reduce_position('sh600989', 500)
print('✅ 已减仓')
"

# 加自选
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from portfolio import PortfolioManager
pm = PortfolioManager()
pm.add_watch('sz000807', '云铝股份', target_buy=12.00)
print('✅ 已加自选')
"
```

加仓时自动计算加权平均成本：

- 原持仓 1000 股 @ 18.50，加仓 500 股 @ 19.00
- 新成本 = (18.50×1000 + 19.00×500) / 1500 = 18.67

## Web 录入（可选）

不想每次打 CLI？启一个本地 web server，浏览器或手机都能录：

```bash
python3 scripts/portfolio_web.py           # 监听 127.0.0.1:8765
# 浏览器打开 http://127.0.0.1:8765/
```

支持 8 个 action 的 JSON Webhook，方便外部脚本/IFTTT 推送：

```bash
curl -X POST http://127.0.0.1:8765/api/positions \
  -H 'Content-Type: application/json' \
  -d '{"action":"add_position","code":"sh600989","cost":18.5,"quantity":1000,"tags":["长线"]}'
```

action 列表：`add_position` / `reduce_position` / `remove_position` /
`update_position` / `tag_position` / `untag_position` / `add_watch` / `update_watch` / `remove_watch`

**注意事项**：

- 默认仅监听 `127.0.0.1`，不对外暴露。
- **谨防竞态条件**：CLI 工具与本 Web 服务**同时**写 `scripts/data/portfolio.json` 时，后写会覆盖前写（无文件锁）。建议：
  - 把 Web 服务作为唯一录入入口。
  - 如果 CLI 命令后的操作确认结果与预期不符，可能是被 Web 服务覆盖。
  - 如需同时使用，建议间隔至少 1 秒，或待 Web 服务空闲时操作（[portfolio.json](scripts/data/portfolio.json) 修改时间可作为参考）。
- `update_position` 的 `tags` 字段是**整列表覆盖**，不是合并；要追加/删除请用 `tag_position` / `untag_position`。
- `add_watch` 的 `target_buy=0` / `target_sell=0` 会被忽略（表示"未设"）；如要显式清零，请用 web 表单/curl 时改用 `update_watch` 路径或编辑文件。
- 股票代码必须传 `sh600989` / `sz000807` 完整形式，不归一化。
- 详细协议与错误码见 `tests/test_portfolio_web.py`。

### 数据获取

按 `../_shared/references/script-catalog.md` 调用 `quote.py` / `finance.py` / `kline.py`，组合维度用 `-j` JSON 计算权重、行业暴露和排序。

### 大盘+板块

- 大盘：`sh000001,sz399001,sz399006,sh000016`
- 板块 ETF：`sh512010,sh512480,sh512690,sh512800,sh513120,sh518880`

## Workflow Coordination

完整链路见包根目录 `workflow.md`。本 skill 是最终落地和再平衡环节：

- 上游来自 `market`：接收市场状态，决定组合进攻/均衡/防守。
- 上游来自 `technical`：接收破位、止损、支撑阻力，决定减仓或观察。
- 上游来自 `screener`/`stock`：接收替代候选和投资结论，决定换仓。
- 下游到 `screener`：当组合需要补行业、降低集中度或替换弱势股时，生成候选池。
- 下游到 `stock`：对拟买入或拟替换标的做最终五层确认。

输出必须包含 `position_plan`、行业集中度、需要处理的持仓、替代候选需求。

## Output Format

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
┌──────────┬────────┬────────┬──────────┐
│ 股票      │ 现价    │ 目标买   │ 备注      │
├──────────┼────────┼────────┼──────────┤
│ 云铝股份  │ 13.80  │ 12.00  │ 等回调     │
│ 北方华创  │ 320.00 │ 280.00 │ 等支撑确认 │
└──────────┴────────┴────────┴──────────┘
```

### 操作确认

```
✅ 已添加持仓：宝丰能源 sh600989
   数量: 1,000 股 | 成本: 18.50 | 投入: ¥18,500
   标签: 能源, 长线

⚠️ 减仓确认：宝丰能源 sh600989
   原持仓: 1,000 股 → 剩余: 500 股
   成本价: 18.50（不变）
```

### 健康检查（health 模式）

```
持仓健康检查 | 时间: YYYY-MM-DD HH:MM

┌─────────┬──────┬──────┬──────┬──────┬──────┐
│ 标的     │ 现价  │ 今日  │ 盈亏  │ 状态  │ 风险  │
├─────────┼──────┼──────┼──────┼──────┼──────┤
│ 宝丰能源 │ 24.59│ +0.2%│ +6090│ ✅   │ 24.0 │
│ 云铝股份 │ 28.52│ -0.9%│+28640│ ✅   │ 27.5 │
│ ...      │      │      │      │      │      │
└─────────┴──────┴──────┴──────┴──────┴──────┘

板块分布: 资源40% 医药0% 科技5% 避险8% 金融3.5% 现金30%
风险评级: ⚠️ 资源仓位偏重，科技偏轻
```

### 风险预警规则

> 权威阈值表：`../_shared/references/alert-thresholds.md`（与 `monitor` 共享）。

| 预警    | 条件             | 操作建议  |
| ------- | ---------------- | --------- |
| 🔴 破位 | 跌破关键支撑位   | 减仓/止损 |
| 🟡 弱势 | 连续2日跑输板块  | 观察/减仓 |
| 🟢 健康 | 在支撑位上方运行 | 持有      |
| ⭐ 强势 | 板块领涨+放量    | 持有/加仓 |

## Guardrails

- 自动兼容 v1 格式，首次使用时引导用户补充成本价和数量。
- 加仓时自动计算加权平均成本，减仓时保持成本价不变。
- 清仓时确认后移除，不保留历史记录（简化设计）。
- 未知成本价时，不计算真实盈亏，只做当日涨跌、估值和风险状态。
- 调仓建议必须包含"减/加多少、触发条件、替代标的或现金比例"，避免泛泛而谈。
- 不要建议超过用户风险承受能力的集中仓位；单一行业或主题过重时优先提示组合风险。
- 本 web server 与 CLI / 外部脚本同时写 `scripts/data/portfolio.json` 时，后写覆盖前写；建议 web 作为唯一录入入口。

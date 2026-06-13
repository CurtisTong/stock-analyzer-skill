---
name: market
description: A 股大盘复盘 skill。用于市场快评、完整复盘、盘中分时复盘、指数/板块 ETF/风格轮动/资金偏好判断；优先使用 stock-analyzer-skill 包内 scripts/quote.py 和 scripts/kline.py 获取实时指数与板块 ETF 数据；支持拉取美股收盘数据作为参考。
version: 1.7.0
model: sonnet
allowed-tools: Bash(python3 scripts/quote.py *) Bash(python3 scripts/kline.py *) Bash(python3 scripts/technical.py *) Bash(python3 scripts/screener.py *) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/data/sector_*) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/methodology.md) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/skills/**)
---

# Market Review

每日大盘复盘——指数+板块+风格+资金+预判。

## Usage

```text
/market [范围: full|quick|intraday]
```

- `full`（默认）：完整复盘，指数+板块+风格+持仓影响+明日预判
- `quick`：3分钟快评，涨跌+最强最弱板块+一句话结论
- `intraday`：分时复盘，大盘+关键标的5分钟走势分析

## 共享约定

- 代码前缀：`../_shared/references/code-prefix.md`
- 脚本目录：`../_shared/references/script-catalog.md`

## Instructions

使用中文，输出简洁有结构。先给市场状态和操作倾向，再展开指数、板块、风格证据。涉及“今天、盘中、最新”时必须取实时数据。

## Workflow Coordination

完整链路见包根目录 `workflow.md`。本 skill 是大多数分析的上游入口：

- 下游到 `sector`：当输出强/弱板块、轮动方向或行业主题时，继续做板块全景。
- 下游到 `screener`：当用户要“找机会/选股/候选池”时，把市场状态映射为策略：进攻=`growth_momentum`，均衡=`balanced`，防守=`defensive`，价值修复=`quality_value`，急跌企稳=`turning_point`。
- 下游到 `portfolio`：当用户关心持仓影响或调仓时，交接 `market_regime`、强弱板块、风险级别。

输出必须包含 `market_regime`（进攻/均衡/防守/冰点/亢奋）和适合的下一步 skill。

### Step 1: 获取大盘数据 + 板块 ETF + 美股参考

按 `../_shared/references/script-catalog.md` 调用 `quote.py` 与 `kline.py`。常用标的：

- 指数：`sh000001,sz399001,sz399006,sh000300,sh000016,sh000905`
- 板块 ETF：`sh510050,sh510300,sh510500,sh512010,sh512480,sh512690,sh512800,sh513120,sh512660,sh515790,sh515030,sh516160`
- 美股参考（full 模式）：`quote.py -j us:^gspc,us:^ixic,us:^dji,us:^vix,us:spy,us:qqq` 获取美股主要指数收盘数据
- `intraday` 模式额外取 5 分钟 K 线（48 根）

**美股代码约定**：使用 `us:` 前缀 + yfinance 符号（如 `us:^gspc` = 标普500, `us:spy` = 标普500 ETF）。

**启用美股功能**：美股数据依赖可选第三方包 yfinance，**未安装时自动跳过且不影响 A 股功能**。安装命令：

```bash
pip install yfinance>=0.2
```

未安装时调用 `us:` 前缀代码会返回空，不报错也不影响主链路。

**通达信局域网数据源（v1.7.1 可选启用）**：如有本地通达信客户端并开启了 7709 端口，可启用局域网直连数据源：

```bash
pip install pytdx
```

启用后行情和 K 线会自动优先走 pytdx（优先级 9，仅次于 tencent=10）。优势：速度快（局域网）、无限频限制、K 线历史回溯深度大（800 根）。未安装时不影响任何功能。

### Step 2: 分析输出

**full模式输出结构：**

```
## 大盘全景
| 指数 | 收盘 | 涨跌 | 信号 |

## 板块涨跌排行
🔥 强势板块 | 💀 弱势板块

## 风格判断
- 大小盘分化: 上证50 vs 中证500
- 市场风格: 成长/价值/防御
- 资金流向: 流入/流出板块

## 美股参考
| 指数 | 收盘 | 涨跌% | 对 A 股影响 |
- VIX 恐慌指数解读（>20 避险情绪升温）
- 美股板块强弱对 A 股映射（如科技→半导体、银行→金融）
- 美联储政策/美债收益率对北向资金的潜在影响

## 持仓影响
| 持仓 | 今日 | 板块 | 匹配度 |

## 明日预判
- 方向判断
- 关注板块
- 操作建议
- 数据日期/时间
```

**quick模式：** 只输出指数+最强最弱板块+一句话

**intraday模式：** 额外获取关键标的5分钟K线做分时分析

### Step 4: 风格信号库

| 信号               | 含义                    | 历史胜率           |
| ------------------ | ----------------------- | ------------------ |
| 上证50涨+中证500跌 | 大小盘分化，防御为主    | 高                 |
| 半导体/光伏暴跌    | 成长板块杀跌            | 短期超跌反弹概率大 |
| 医药/白酒/银行齐涨 | 防御行情确立            | 持续2-3天          |
| 券商+黄金同涨      | 市场方向不明，博弈+避险 | 震荡延续           |
| 创业板单日+3%以上  | 超跌暴力反弹            | 需观察次日是否延续 |

## Guardrails

- 不要虚构北向资金、成交额、融资余额等脚本无法直接提供的数据；如用户需要，说明当前工具未覆盖或另行查询。
- 若市场休市，明确说明行情数据可能是上一交易日。
- 输出建议按”进攻/均衡/防守”分层，不给无条件满仓或清仓指令。
- 美股参考依赖 `yfinance` 包；未安装时 `quote.py` 返回 `NOT_HANDLED`，`market full` 应**自动跳过美股段落**而不是失败——遇到该情况需在输出中说明”美股参考未启用（yfinance 未安装）”，不要硬塞假数据。

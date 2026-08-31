---
name: stock
description: 单股分析。触发词：帮我看看XX、分析一下XX、XX怎么样、XX能买吗、看看XX的技术面、技术分析XX、XX估值如何、XX基本面、专家讨论XX。用于个股快速/完整五层分析、技术分析（均线/MACD/KDJ/BOLL/RSI/缠论/战法）、估值判断、8人专家圆桌多空辩论（16份人设中 8 active = 5长线+3短线）。⚠️ AI 辅助生成，仅供参考，不构成投资建议。
version: 1.22.0
model: glm-5.2
allowed-tools: Bash(python3 scripts/quote.py *) Bash(python3 scripts/kline.py *) Bash(python3 scripts/finance.py *) Bash(python3 scripts/technical.py *) Bash(python3 scripts/stock.py *) Bash(python3 scripts/events.py *) Bash(python3 scripts/market_anchor.py *) Bash(python3 scripts/calibration.py *) Bash(python3 scripts/calibration_backfill.py *) Read(./methodology.md) Read(./experts/*.md) Read(./skills/_shared/references/*.md)
---

# Stock Analysis

快速个股分析——五层框架 + 专家讨论。

## Usage

```text
/stock <股票名称或代码> [quick|full|debate|technical] [长线|短线]
```

- `quick`（默认）：基本面+估值+技术面，3分钟出结论
- `full`：五层完整分析+风险收益比+仓位建议
- `debate`：五层分析 + 8人专家圆桌（5长线+3短线）
- `debate 长线`：仅5位长线（lynch/soros/value_institution/sector_specialist/risk_manager）
- `debate 短线`：仅3位短线（topic_leader/emotion_tech/momentum_trader）
- `technical`：纯技术分析，不做基本面
- `--brief`：精简模式，一句话结论 + 关键数据 + 操作建议（<500字），可与上述模式组合

> `/stock` 不带参数时走 `quick`；需要专家圆桌必须显式写 `debate`。

### 龙虎榜（短线可选）

```bash
python3 scripts/data/lhb.py sh600519 [--days 10]   # 最近 7 / 10 日龙虎榜
```

输出：上榜次数、累计净买入、买入/卖出前 5 营业部（机构/游资识别）、关联游资标签。

## 共享约定

- 代码前缀：`../_shared/references/code-prefix.md`
- 脚本目录与批量调用约定：`../_shared/references/script-catalog.md`
- 五层分析框架与评级阈值：`../_shared/references/five-layer.md`

按需加载，无须默读。

## Instructions

使用中文，输出用表格+要点格式。先给结论，再给证据和风险。涉及实时行情、最新公告、研报或盘中走势时必须获取数据，不要只凭记忆判断。

输出遵循统一规范 v2（三段式：30 秒研判 / 风险与决策路径 / 详细论证 / 数据护栏与免责统一承载）。详见 `../_shared/references/output-template.md`。
**生成器护栏权威源**：`../_shared/references/guardrails.md`（不在最终报告中向用户展示）。

## Workflow Coordination

完整链路见包根目录 `workflow.md`。本 skill 负责把候选股变成投资判断：

- 上游来自 `screener`：接收候选分数、策略和剔除/入选理由，做五层验证。
- 上游来自 `sector`：接收板块景气和同业比较，避免孤立看个股。
- 下游到 `technical`：当结论是买入/持有/观察时，确认技术触发、支撑阻力和失效位。
- 下游到 `/research financial`：财务数据异常、估值分歧大或需要预测时进入建模。
- 下游到 `portfolio`：涉及实际操作时，输出仓位计划、止损、替代方案。

输出必须包含 `fundamental_rating`、`valuation_view`、`sector_context`、`technical_next_step`、`position_plan`。

### Step 0：市场环境锚定（full / debate / technical 必跑）

> **重要**：个股的"破位/突破/强势/弱势"必须放在市场环境中判断——一只票在牛市跌破 20 日均线是"洗盘"，在熊市是"破位"。剥离大盘谈个股，技术信号会反向。

调用 `market_anchor.py` 一次性拉取大盘状态 + 板块强度 + 个股相对位置（16 维度：regime / 指数 / 宽度 / 板块强度 / 个股 RPS / 多时间框架 / 宏观-估值桥 / 杠杆 / 情绪周期 / 行业 beta / 组合相关性 / 题材轮动 / 北向 / 数据降级）：

```bash
python3 scripts/market_anchor.py <股票代码> -j                  # full / debate：全量
python3 scripts/market_anchor.py <股票代码> --no-sector -j   # technical：仅大盘 + 宽度
```

**优雅降级**：任一字段失败均不阻塞主流程——大盘失败→regime 默认 `defensive`；板块失败→`sector_strength=null`；个股板块反查失败→"板块归属未知"；yfinance 宏观失败→fixture 降级；个股 amount 缺失→`volume×close` 估算。

**复用（不重写）**：`experts.market_detector.detect_market_state()`、`market_breadth.get_market_breadth()/get_market_state()`、`quote.py`（≤15/批）、`data.get_kline()`（scale=240 datalen=250）、`technical.moving_average.ma_system()`、`technical.volatility.compute_atr()`、`industry_beta.compute_beta()`、`portfolio.manager.PortfolioManager.get_positions()` 直接 import。

### Step 1: 获取数据

> **⚠️ 工作目录**：Claude Code 调用脚本时 `cwd` 已是项目根目录，SKILL.md 里的 `scripts/xxx.py` 是相对路径，直接运行即可。

按 `../_shared/references/script-catalog.md` 调用 `quote.py` / `finance.py` / `kline.py` / `announcements.py`。**批量调用语法差异（quote 逗号位置参数 / finance 必须 `-c` / kline·technical·market_anchor 逐个）见 script-catalog.md §多代码批量调用约定**。多股分析推荐用 helper 批量取数：

```bash
python3 scripts/dev/multi_fetch.py finance sh600519 sh600036 sh000858
python3 scripts/dev/multi_fetch.py technical sh600519 sh600036
```

`--with-backtest` 模式附加近 60 日回测胜率（`win_rate` / `total_return` / `sharpe` / `max_drawdown`）：

```bash
python3 scripts/stock.py sh600989 --with-backtest
```

### 事件日历

分析时查询近期事件（财报披露、解禁、分红），在输出顶部显示提醒：

```bash
python3 scripts/events.py sh600989 [--days 60] [-j]
```

### Step 2: 五层分析

五层定义与评级阈值详见 `../_shared/references/five-layer.md`（唯一权威源，去重）。仅在需要展开方法论时读取包根目录 `methodology.md`。

### Step 3: 输出结论

> **统一前置**：所有模式报告**开头**先输出 Step 0 的"市场环境锚定"小节（📊 emoji），再进入各自模式核心内容。不破坏第一行一句话结论的硬约束（来自 `output-template.md`）。

- **quick**：顶部锚定简版（一行表格）→ 一句话结论 → 关键数据表 → 操作建议 → 数据时间戳
- **full**：顶部完整锚定（含个股 RPS）→ 五层详细表格 → 支撑/阻力 → 情景分析（牛/基准/悲观）→ 仓位建议+止损位
- **debate（全模式/默认）**：顶部完整锚定 → 五层 → 8人专家圆桌（regime 权重已由 Step 0 给出，**不再二次判定**）→ 多空投票+跨组加权（长线 ≥4/5 多数 + 短线均分区间驱动）→ 最终折中
- **debate 长线**：五层 + 仅5位长线，组内投票 ≥4/5 看多/看空算组内多数
- **debate 短线**：五层 + 仅3位短线，组内投票 ≥2/3 阈值（双组冲突时短线方向用均分区间驱动）

### Step 3.1: 输出格式模板（v2）

深度分析报告（`full` / `debate`）使用 `reports/full-template.md` 的 v2 骨架（**渐进披露三层 + 30 秒研判卡片 + 数据护栏与免责**）。`quick` 模式仅输出 30 秒研判卡片 + 数据护栏与免责。

- **30 秒研判**（必呈现）：一句话研判 + 核心矛盾 + 当前动作 + 风险提示
- **风险与决策路径**（必呈现）：核心矛盾与监测优先级 + 5 情景概率 + 论点破灭触发器
- **详细论证**：财务/估值/技术/板块/圆桌/跟踪条件等
- **数据护栏与免责**（统一承载）：🛡️ 数据护栏条 + 时间戳 + 数据源 + 免责声明

### Step 3.2: 生成器护栏（约束 agent 写作，不在最终报告中向用户展示）

> 本节约束生成器行为，不在用户报告中渲染。报告渲染时仅展示护栏结论（🛡️ 数据护栏条，见 `reports/full-template.md` §数据护栏与免责）。

护栏权威源：`../_shared/references/guardrails.md`。骨架约束摘要：

- **去重**：同一数据点 ≤2 次（数据表 1 次 + 分析论证 1 次）
- **评分统一**：`A+/A/B+/B/C` 五档字母制，禁用 ⭐ 符号
- **排名限定**：仅本行业（申万二级），禁止跨行业排名
- **数据来源**：核心数据表每行须标来源，禁止推算值不标来源
- **增速分列**：利润增速 vs 营收增速，模板强制两行
- **杜邦对账**：重建 ROE vs 原始 ROE 偏差 >2pp 须标注 ⚠️
- **PE 多口径**：Q1 年化 / H1 修正 / 机构预测三口径并列
- **合规措辞**："建议/买入/目标价/止损"等持牌投顾措辞替换为"研判/观察/观察上沿/观察下沿"

评级标准和五个维度定义详见 `../_shared/references/five-layer.md`（唯一权威源）。

### Step 4: 专家讨论（debate 模式）

**三种子模式**：

| 模式           | 参数          | 参与专家            | 决策机制               |
| -------------- | ------------- | ------------------- | ---------------------- |
| 全模式（默认） | `debate`      | 8人（长线5+短线3）  | 跨组加权，市场环境调权 |
| 长线模式       | `debate 长线` | 长线5人             | 组内投票 ≥4/5 阈值    |
| 短线模式       | `debate 短线` | 短线3人             | 组内投票 ≥2/3 阈值（双组冲突时短线用均分区间驱动）|

> 长线5：林奇（成长）/ 索罗斯（趋势）/ 价值机构锚（merged 价值双锚+机构派）/ 行业专家 / 风控官；短线3：题材龙头（merged 徐翔+赵老哥）/ 情绪技术（merged 养家+新一）/ 动量派。8 份 legacy 档案（巴菲特/段永平/徐翔/赵老哥/养家/作手新一/value_anchor/institution）保留为研究档案，不参与新框架投票。完整决策引擎见 `experts/decide.md`。

**全模式标准流程**：

1. **获取大盘数据**判断市场环境（牛市/熊市/震荡/冰点/亢奋）：`python3 scripts/quote.py sh000001,sh510300 -j`
2. **每位专家独立打分**：对照 `experts/<name>.md` §九 评分矩阵，用步骤1/3的数据在各维度打分（0-100）。**量化基线（推荐）**：一键 `python3 scripts/dev/experts_cli.py <code> [--long|--short] [-j]` 自动收集数据+跑专家；量化分与 LLM 推理分差异 >15 分需在报告中说明原因。多股对比用 `python3 scripts/dev/multi_fetch.py technical <codes>` 保留完整技术字段（勿用 `--quick`，无数值字段）。
3. **投票汇总**：按 `experts/decide.md` 规则——分组计票、市场环境调整权重、冲突解决（巴菲特否决警示：不改方向仅降信心、养家情绪降权）。
4. **输出**：按 `decide.md` §四 格式——评分表 + 方向 + 风险 + 仓位，计算信心指数。
5. **记录校准数据**：debate 完成后 `run_debate` 编排器（自动回灌校准因子 + 落库预测）或手动 `calibration.py record`；定期 `calibration.py verify/factor` + `calibration_backfill.py status` 验证到期预测。

**发言规则**（强制约束每位专家 `reason` 字段）：

- **数据基础性**：`reason` 必须引用触发评分矩阵分支的具体数据值（如"PE 35倍处行业85%分位→估值分25"），禁止纯定性结论。
- **禁用表述**：不得使用"反向加分""反向指标"等表述。低分仅代表"不符合本专家体系"，不构成对价格走势的反向预测。
- **三元组展示**：展示维度拆分（breakdown）时，必须输出 `原始分 × 权重 = 贡献值` 三元组。
- **模型边界**：承认对强周期资产盈利能力评估的结构性局限；周期股因框架限制得低分时应说明"不符合本体系投资标准"，而非推断价格将下跌。

> 渲染层兜底：`experts/formatter.py` 检测 reason 缺数据引用或含禁用表述时追加 `⚠理由缺数据引用` / `⚠含禁用表述` 标记。

**长线/短线单组流程**：获取数据（同全模式）→ 仅调用对应组专家打分 → 组内投票（长线 ≥4/5 看多=看多、2:3=中性；短线 ≥2/3）→ 输出评分表 + 组内方向 + 风险 + 仓位，信心指数基于组内标准差。

### Step 5: 技术分析（technical 模式）

详见 [`/stock-technical`](../stock-technical/SKILL.md) 子模块。本步骤仅做调用入口说明：

```bash
python3 scripts/market_anchor.py <代码> --no-sector -j   # 大盘锚定（轻量版，无板块强弱）
python3 scripts/technical.py sh600989 [--classify] [--quick]
```

**为什么 technical 也需要大盘锚定**：技术信号在不同 regime 下含义不同——`bull` 中放量突破是真信号、缩量回踩是洗盘；`bear / panic` 中放量长上影是出货信号；`defensive` 中低估值高股息抗跌，成长股破位需警惕。

## Guardrails

- 明确声明这不是投资保证，给出风险触发条件而不是绝对化预测。
- 数据失败时说明失败的数据源和影响，仍可用已有数据给低置信度结论。
- 不要虚构实时价格、最新公告、研报评级或成交数据。
- **专家 `reason` 字段约束**：核心理由必须基于实际数据值，不得编造"反向加分""反向指标"等无数据支撑的论述。`experts/formatter.py` 渲染层检测并标记违规。

### 日内T策略过滤器

用户询问日内T、T+0、做T等短线操作时，先读取 `../_shared/references/day-trading.md`，按"禁止/谨慎/推荐做T条件"过滤后再给操作建议（下跌趋势不做T，超卖信号需二次确认）。
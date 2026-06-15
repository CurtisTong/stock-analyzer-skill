---
name: stock
description: 单股分析。触发词：帮我看看XX、分析一下XX、XX怎么样、XX能买吗、看看XX的技术面、技术分析XX、XX估值如何、XX基本面、专家讨论XX。用于个股快速/完整五层分析、技术分析（均线/MACD/KDJ/BOLL/RSI/缠论/战法）、估值判断、8人专家圆桌多空辩论。
version: 1.10.0
model: opus
allowed-tools: Bash(python3 scripts/*) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/methodology.md) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/experts/*) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/skills/**)
---

# Stock Analysis

快速个股分析——五层框架 + 专家讨论。

## Usage

```text
/stock <股票名称或代码> [quick|full|debate|technical] [长线|短线]
```

- `quick`（默认）：基本面+估值+技术面，3分钟出结论
- `full`：五层完整分析+风险收益比+仓位建议
- `debate`：五层分析 + 8人专家圆桌多空辩论（8 人全模式）
- `debate 长线`：仅长线4人（巴菲特/林奇/索罗斯/段永平），适合价值投资者
- `debate 短线`：仅短线4人（徐翔/赵老哥/炒股养家/作手新一），适合交易型选手
- `technical`：纯技术分析（均线/MACD/KDJ/BOLL/RSI/缠论/本土战法），不做基本面

> `/stock` 不带参数时走 `quick`；需要专家圆桌必须显式写 `debate`。

## 共享约定

- 代码前缀（`sh`/`sz`/`SH`/`SZ` 大小写规则）：`../_shared/references/code-prefix.md`
- 脚本目录与参数：`../_shared/references/script-catalog.md`
- 五层分析框架与评级阈值：`../_shared/references/five-layer.md`

按需加载，无须默读。

## Instructions

使用中文，输出用表格+要点格式。先给结论，再给证据和风险。涉及实时行情、最新公告、研报或盘中走势时必须获取数据，不要只凭记忆判断。

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

## Workflow Coordination

完整链路见包根目录 `workflow.md`。本 skill 负责把候选股变成投资判断：

- 上游来自 `screener`：接收候选分数、策略和剔除/入选理由，做五层验证。
- 上游来自 `sector`：接收板块景气和同业比较，避免孤立看个股。
- 下游到 `technical`：当结论是买入/持有/观察时，必须确认技术触发、支撑阻力和失效位。
- 下游到 `financial-analyst`：当财务数据异常、估值分歧大或需要预测时，进入建模。
- 下游到 `portfolio`：当涉及实际操作时，输出仓位计划、止损、替代方案。

输出必须包含 `fundamental_rating`、`valuation_view`、`sector_context`、`technical_next_step`、`position_plan`。

### Step 1: 获取数据

按 `../_shared/references/script-catalog.md` 调用 `quote.py` / `finance.py` / `kline.py` / `announcements.py`。`debate` 模式额外取 5 分钟 K 线（48 根）。

`--with-backtest` 模式附加近 60 日回测胜率：

```bash
python3 scripts/stock.py sh600989 --with-backtest
```

输出 `backtest` 字段包含 `win_rate`（胜率%）、`total_return`（累计收益%）、`sharpe`（夏普比率）、`max_drawdown`（最大回撤%）。

### 事件日历

分析时查询近期事件（财报披露、解禁、分红），在输出顶部显示提醒：

```bash
python3 scripts/events.py sh600989              # 查询近 30 日事件
python3 scripts/events.py sh600989 --days 60    # 查询近 60 日事件
python3 scripts/events.py sh600989 -j           # JSON 输出
```

输出示例：

```
📅 近 30 日事件日历 (sh600989)

📊 财报披露:
  2026-06-20 - 宝丰能源 (600989)

💰 分红:
  2026-06-25 - 宝丰能源 每股 0.5000 元

🎯 📊 财报披露: 2026-06-20 | 💰 分红: 2026-06-25
```

### Step 2: 五层分析

| 层级       | 分析内容                  | 输出                 |
| ---------- | ------------------------- | -------------------- |
| 基本面     | ROE/增速/毛利/负债/现金流 | 评级(A/B/C)          |
| 估值       | PE/PEG/PE-ROE             | 评级(低估/合理/偏贵) |
| 技术面     | K线趋势/支撑阻力/量价     | 评级(强/中/弱)       |
| 板块       | 所属板块今日表现          | 板块排名             |
| 风险收益比 | 情景分析+概率加权         | 期望收益%            |

详细阈值和字段解释见包根目录 `methodology.md`。只在需要展开方法论或字段含义时读取该文件，避免无关上下文膨胀。

### Step 3: 输出结论

**quick模式：**

- 一句话结论
- 关键数据表
- 操作建议（买入/持有/回避）
- 明确数据时间戳或交易日

**full模式：**

- 五层分析详细表格
- 支撑/阻力位图示
- 情景分析表（牛市/基准/悲观）
- 仓位建议+止损位

**debate模式（全模式/默认）：**

- 五层分析
- 8人专家圆桌（4长线+4短线）
- 多空投票 + 跨组加权
- 最终折中方案

**debate 长线模式：**

- 五层分析
- 仅4位长线专家（巴菲特/林奇/索罗斯/段永平）
- 组内投票，无跨组加权
- 适合中长期价值判断

**debate 短线模式：**

- 五层分析
- 仅4位短线专家（徐翔/赵老哥/炒股养家/作手新一）
- 组内投票，无跨组加权
- 适合短线交易时机判断

### Step 3.1: 输出格式模板

深度分析报告（`full` / `debate` 模式）使用 `reports/full-template.md` 中的完整模板。`quick` 模式不展开。

评级标准和五个维度定义详见 `../_shared/references/five-layer.md`（唯一权威源）。

### Step 4: 专家讨论（debate模式）

**三种子模式**：

| 模式           | 参数          | 参与专家           | 决策机制               |
| -------------- | ------------- | ------------------ | ---------------------- |
| 全模式（默认） | `debate`      | 8人（长线4+短线4） | 跨组加权，市场环境调权 |
| 长线模式       | `debate 长线` | 长线4人            | 组内投票，无跨组权重   |
| 短线模式       | `debate 短线` | 短线4人            | 组内投票，无跨组权重   |

> 专家全名：徐翔、赵老哥、**炒股养家**（养家）、作手新一。

长线团：巴菲特（价值）、彼得林奇（成长）、索罗斯（趋势）、段永平（逆向）
短线团：徐翔（涨停板）、赵老哥（趋势龙头）、炒股养家（养家，情绪流）、作手新一（低吸）

**全模式标准流程**（参考 experts/decide.md 决策引擎）：

1. **获取大盘数据**，判断市场环境（牛市/熊市/震荡/冰点/亢奋）：

   ```bash
   python3 scripts/quote.py sh000001,sh510300 -j
   ```

2. **每位专家独立打分**：对照 `experts/<name>.md` 中 §九 评分矩阵，用步骤1和步骤3获取的数据在各维度打分，输出 0-100 总分。关键：
   - 巴菲特：重 ROE/PE/负债率/安全边际
   - 林奇：重 PEG/增速/内部人交易
   - 索罗斯：重趋势/反身性/市场情绪一致性
   - 段永平：重商业模式/护城河/FCF/管理层
   - 徐翔：重涨停基因/板块效应/封单强度（仅排雷基本面）
   - 赵老哥：重均线排列/题材生命周期/龙头地位
   - 养家：重情绪周期阶段/涨停跌停家数（几乎不看基本面）
   - 作手新一：重 K线反转形态/缩量程度/止损成本

   **量化基线参考**（可选但推荐）：在 LLM 推理打分前，先运行量化评分获取基线：

   ```bash
   python3 scripts/quote.py <股票代码> -j
   python3 scripts/finance.py <股票代码> -j
   python3 scripts/kline.py <股票代码> -j
   ```

   然后在 Python 中调用 `experts.scoring.score_expert_precise()` 获取每位专家的量化评分，
   作为 LLM 推理的参考基线。如果量化分与 LLM 推理分差异 >15 分，需在报告中说明原因。

3. **投票汇总**：按 experts/decide.md 规则——分组计票、市场环境调整权重、冲突解决（巴菲特否决权、养家情绪降权）。

4. **输出**：按 decide.md §四 格式——评分表 + 方向 + 风险 + 仓位。记得计算信心指数。

5. **记录校准数据**：debate 完成后，记录本次预测供后续验证（**需要 1.6.0+**，`scripts/calibration.py` 由 1.6.0 引入；旧版本可跳过此步，不影响主流程）：

   ```bash
   python3 scripts/calibration.py record --stock <代码> --direction <方向> \
     --scores '{"buffett":72,"lynch":65,...}'
   ```

   输出中附带当前校准因子（如有历史数据）：

   ```
   校准因子: +0.15 (8位专家平均校准率 62%)
   ```

**长线/短线单组模式流程**（参考 experts/decide.md §七）：

1. **获取数据**：同全模式步骤1（行情+财务+K线），无需获取大盘数据。
2. **仅调用对应组专家打分**：长线模式只跑巴菲特/林奇/索罗斯/段永平，短线模式只跑徐翔/赵老哥/养家/作手新一。
3. **组内投票**：按 decide.md §七 规则——组内 ≥3/4 看多=看多，≥3/4 看空=看空，2:2=中性。
4. **输出**：评分表（仅该组4人）+ 组内方向 + 风险 + 仓位。信心指数基于4人标准差计算。

### Step 5: 技术分析（technical 模式）

纯技术视角，不涉及基本面。运行 `scripts/technical.py` 获取完整技术报告：

```bash
python3 scripts/technical.py sh600989                     # 完整报告（日K 250根）
python3 scripts/technical.py sh600989 --quick              # 快速摘要
python3 scripts/technical.py sh600989 --classify           # 启用分类+缠论+战法+市场自适应
python3 scripts/technical.py sh600989 --classify --no-chan # 跳过缠论（仅分类+战法）
python3 scripts/technical.py sh600989 --scale 60           # 60分钟K线
```

输出包含：综合评分、均线系统、MACD（含背离）、KDJ、BOLL、RSI、成交量、K线形态、缠论（笔-线段-中枢-买卖点）、A股本土战法（三阴一阳/老鸭头/美人肩/双针探底/涨停双响炮/底部首板）、支撑/阻力位。

**指标解读要点**：

- **均线系统**：中长期趋势方向。多头排列=强势，空头=弱势，粘合=即将变盘
- **MACD**：趋势动量。金叉+红柱放大=加速上涨，死叉+绿柱放大=加速下跌。背离是强烈反转信号
- **KDJ**：短线超买超卖。J>100=极度超买，J<0=极度超卖。单边趋势中 KDJ 会钝化
- **BOLL**：波动率。带宽收窄=变盘前兆，价格触轨=极端位置
- **成交量**：量价配合=健康，量价背离=预警
- **涨跌停分析**：封涨停时技术指标暂停参考，需等次日开盘验证

**个股类型 × 指标权重**：

| 类型     | 加权指标                            | 降权指标          |
| -------- | ----------------------------------- | ----------------- |
| 题材股   | K线形态×1.5, 涨停分析×1.5, 量比×1.3 | MACD×0.5, KDJ×0.5 |
| 强成长股 | MACD×1.3, BOLL×1.2, 量比×1.2        | KDJ×0.4           |
| 周期股   | MACD×1.3, KDJ×1.2, 缠论×1.3         | 均线×0.6          |
| 蓝筹股   | 均线×1.3, BOLL×1.2, 箱体×1.1        | KDJ×0.4           |

## Guardrails

- 明确声明这不是投资保证，给出风险触发条件而不是绝对化预测。
- 数据失败时说明失败的数据源和影响，仍可用已有数据给低置信度结论。
- 不要虚构实时价格、最新公告、研报评级或成交数据。

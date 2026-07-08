---
name: stock
description: 单股分析。触发词：帮我看看XX、分析一下XX、XX怎么样、XX能买吗、看看XX的技术面、技术分析XX、XX估值如何、XX基本面、专家讨论XX。用于个股快速/完整五层分析、技术分析（均线/MACD/KDJ/BOLL/RSI/缠论/战法）、估值判断、9人专家圆桌多空辩论（15份人设中 9 active = 6长线+3短线）。⚠️ AI 辅助生成，仅供参考，不构成投资建议。
version: 1.15.0
model: opus
allowed-tools: Bash(python3 scripts/*) Read(./methodology.md) Read(./experts/*.md) Read(./skills/_shared/references/*.md)
---

# Stock Analysis

快速个股分析——五层框架 + 专家讨论。

## Usage

```text
/stock <股票名称或代码> [quick|full|debate|technical] [长线|短线]
```

- `quick`（默认）：基本面+估值+技术面，3分钟出结论
- `full`：五层完整分析+风险收益比+仓位建议
- `debate`：五层分析 + 9人专家圆桌（6长线+3短线：林奇/索罗斯/价值双锚/行业专家/机构派/风控 + 题材龙头/情绪技术/动量派）
- `debate 长线`：仅6位长线（lynch/soros/value_anchor/sector_specialist/institution/risk_manager）
- `debate 短线`：仅3位短线（topic_leader/emotion_tech/momentum_trader）
- `technical`：纯技术分析（均线/MACD/KDJ/BOLL/RSI/缠论/本土战法），不做基本面
- `--brief`：精简模式，一句话结论 + 关键数据 + 操作建议（<500字），可与上述模式组合

> `/stock` 不带参数时走 `quick`；需要专家圆桌必须显式写 `debate`。

### 龙虎榜（v2.4.0 新增）

短线交易者可调用龙虎榜查看机构/游资席位净买入：

```bash
python3 scripts/data/lhb.py sh600519              # 最近 30 日龙虎榜
python3 scripts/data/lhb.py sh600519 --days 10    # 最近 10 日
```

输出包含：
- 上榜次数、累计净买入额
- 买入/卖出前 5 营业部（机构/游资识别）
- 关联游资标签（"赵老哥"、"孙哥"、"章盟主"等）

数据源：`scripts/fetchers/lhb/` 多源适配器（东财/同花顺）。

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
- 下游到 `/research financial`：当财务数据异常、估值分歧大或需要预测时，进入建模。
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
- 9人专家圆桌（6长线+3短线；另有6份legacy档案保留研究）
- 多空投票 + 跨组加权（≥4/6 长线 + ≥2/3 短线多数阈值）
- 最终折中方案

**debate 长线模式：**

- 五层分析
- 仅6位长线专家（lynch/soros/value_anchor/sector_specialist/institution/risk_manager）
- 组内投票，≥4/6 看多/看空算组内多数
- 适合中长期价值判断

**debate 短线模式：**

- 五层分析
- 仅3位短线专家（topic_leader/emotion_tech/momentum_trader）
- 组内投票，≥2/3 多数阈值
- 适合短线交易时机判断

### Step 3.1: 输出格式模板

深度分析报告（`full` / `debate` 模式）使用 `reports/full-template.md` 中的完整模板。`quick` 模式不展开。

评级标准和五个维度定义详见 `../_shared/references/five-layer.md`（唯一权威源）。

### Step 4: 专家讨论（debate模式）

**三种子模式**：

| 模式           | 参数          | 参与专家                       | 决策机制               |
| -------------- | ------------- | ------------------------------ | ---------------------- |
| 全模式（默认） | `debate`      | 9人（长线6 + 短线3）           | 跨组加权，市场环境调权 |
| 长线模式       | `debate 长线` | 长线6人                        | 组内投票，≥4/6 阈值    |
| 短线模式       | `debate 短线` | 短线3人                        | 组内投票，≥2/3 阈值    |

> 短线 3 人：题材龙头（topic_leader）、情绪技术复合（emotion_tech）、动量交易（momentum_trader）。
> 另有 6 份 legacy 档案（巴菲特/段永平/徐翔/赵老哥/养家/作手新一）保留为研究档案，不参与新框架投票。

长线团（6）：彼得林奇（成长）、索罗斯（趋势）、价值双锚（merged 巴菲特+段永平）、行业专家、机构派、风控官
短线团（3）：题材龙头（merged 徐翔+赵老哥）、情绪技术复合（merged 养家+新一）、动量交易（v2.2.0）

**全模式标准流程**（参考 experts/decide.md 决策引擎）：

1. **获取大盘数据**，判断市场环境（牛市/熊市/震荡/冰点/亢奋）：

   ```bash
   python3 scripts/quote.py sh000001,sh510300 -j
   ```

2. **每位专家独立打分**：对照 `experts/<name>.md` 中 §九 评分矩阵，用步骤1和步骤3获取的数据在各维度打分，输出 0-100 总分。9 位 active 专家关键维度：
   - 林奇（lynch）：重 PEG/增速/内部人交易
   - 索罗斯（soros）：重趋势/反身性/市场情绪一致性
   - 价值双锚（value_anchor）：重 ROE/PE/负债率/安全边际（merged 巴菲特+段永平）
   - 题材龙头（topic_leader）：重涨停基因/板块效应/封单强度+均线排列（merged 徐翔+赵老哥）
   - 情绪技术（emotion_tech）：重情绪周期/涨停跌停家数/K线反转（merged 养家+作手新一）
   - 行业专家（sector_specialist）：按5大行业类差异化阈值
   - 机构派（institution）：高瓴/红杉框架 + 5-10 年产业投资
   - 风控官（risk_manager）：Howard Marks 二阶思维 + 风险预算
   - 动量派（momentum_trader）：利弗莫尔关键转折 + 海龟交易法则（v2.2.0）

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
   校准因子: +0.15 (9位 active 专家平均校准率 62%；6份 legacy 档案不参与校准)
   ```

**长线/短线单组模式流程**（参考 experts/decide.md §七）：

1. **获取数据**：同全模式步骤1（行情+财务+K线），无需获取大盘数据。
2. **仅调用对应组专家打分**：长线模式只跑 lynch/soros/value_anchor/sector_specialist/institution/risk_manager（6人），短线模式只跑 topic_leader/emotion_tech/momentum_trader（3人）。
3. **组内投票**：按 decide.md §七 规则——长线组 ≥4/6 看多=看多，≥4/6 看空=看空，3:3=中性；短线组 ≥2/3 看多=看多，≥2/3 看空=看空。
4. **输出**：评分表（仅该组专家）+ 组内方向 + 风险 + 仓位。信心指数基于组内标准差计算。

### Step 5: 技术分析（technical 模式）

详见 [`/stock-technical`](../stock-technical/SKILL.md) 子模块。本步骤仅做调用入口说明。

```bash
python3 scripts/technical.py sh600989              # 完整报告
python3 scripts/technical.py sh600989 --classify   # 含分类+缠论+战法
python3 scripts/technical.py sh600989 --quick      # 快速摘要
```

输出包含：综合评分、均线系统、MACD、KDJ、BOLL、RSI、成交量、K线形态、缠论、A 股本土战法、支撑/阻力位。详见子模块文档。

## Guardrails

- 明确声明这不是投资保证，给出风险触发条件而不是绝对化预测。
- 数据失败时说明失败的数据源和影响，仍可用已有数据给低置信度结论。
- 不要虚构实时价格、最新公告、研报评级或成交数据。

### 日内T策略过滤器

**核心原则：下跌趋势不做T，超卖信号需二次确认**

当用户询问日内T、T+0、做T等短线操作时，必须先检查以下过滤条件：

#### 禁止做T条件（任一满足则不推荐T）

| 条件     | 判断方法                               | 原因                      |
| -------- | -------------------------------------- | ------------------------- |
| 放量下跌 | `volume_price_signal == -1` 且含"出货" | 主力出货，超卖是假信号    |
| 下跌浪   | `wave` 含"下跌"                        | 趋势向下，反弹空间有限    |
| 空头排列 | `ma.alignment == "空头排列"`           | 均线压制，做T容易被套     |
| KDJ钝化  | `kdj.钝化 == True`                     | 趋势延续，超卖更超卖      |
| 市场退潮 | `market_breadth.limit_up_count < 20`   | 涨停家数<20家，赚钱效应弱 |
| 市场冰点 | `market_breadth.limit_down_count > 50` | 跌停>50家，市场极度恐慌   |

#### 谨慎做T条件（需额外确认）

| 条件          | 确认方式           | 说明                     |
| ------------- | ------------------ | ------------------------ |
| 超卖+放量下跌 | 等待放量阳线止跌   | 超卖信号在下跌趋势中失效 |
| 箱体底部      | 确认支撑有效再入场 | 可能破位下跌             |
| MACD底背离    | 需要二次背离确认   | 单次背离可能失败         |
| 接力生态恶化  | 连板高度<2板       | 短线情绪低迷             |

#### 推荐做T条件（需全部满足）

1. **趋势中性或偏多**：`wave` 为"盘整"或"上升浪"
2. **量价配合**：`volume_price_signal >= 0`（非放量下跌）
3. **支撑明确**：有清晰的支撑位（均线/前低/整数关口）
4. **振幅充足**：近20日平均振幅 > 3%
5. **非钝化状态**：KDJ未钝化
6. **缩量确认**：`shrink_signal == 1`（连续缩量4-5日，抛压减轻）
7. **市场情绪健康**：涨停家数>20家，连板高度>2板

#### 输出模板（当推荐做T时）

```
## 日内T操作建议

**T策略评级**: ⭐⭐⭐⭐ (1-5星)

**前提条件**:
- ✅ 趋势中性/偏多
- ✅ 量价配合
- ✅ 支撑明确

**操作区间**:
- 买入区间: XX.XX - XX.XX
- 止盈目标: XX.XX - XX.XX
- 止损位: XX.XX (跌破即止损)

**风险提示**:
- 当前市场环境: [牛市/震荡/熊市]
- 最大回撤风险: X%
- 建议仓位: X成

⚠️ 以上为技术面参考，不构成投资建议。
```

#### 输出模板（当禁止做T时）

```
## ⚠️ 当前不建议做日内T

**禁止原因**:
- [ ] 放量下跌(主力出货)
- [ ] 下跌趋势
- [ ] 空头排列
- [ ] KDJ钝化
- [ ] 市场退潮(涨停<20家)
- [ ] 市场冰点(跌停>50家)

**建议**:
1. 等待止跌信号（放量阳线）
2. 等待趋势反转（均线金叉）
3. 观望为主，不参与下跌趋势

**替代方案**:
- 如果已持仓：等待反弹减仓
- 如果空仓：等待右侧机会
```

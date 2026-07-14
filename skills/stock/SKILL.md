---
name: stock
description: 单股分析。触发词：帮我看看XX、分析一下XX、XX怎么样、XX能买吗、看看XX的技术面、技术分析XX、XX估值如何、XX基本面、专家讨论XX。用于个股快速/完整五层分析、技术分析（均线/MACD/KDJ/BOLL/RSI/缠论/战法）、估值判断、8人专家圆桌多空辩论（16份人设中 8 active = 5长线+3短线）。⚠️ AI 辅助生成，仅供参考，不构成投资建议。
version: 1.5.0
model: glm-5.2
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
- `debate`：五层分析 + 8人专家圆桌（5长线+3短线：林奇/索罗斯/价值机构锚/行业专家/风控 + 题材龙头/情绪技术/动量派）
- `debate 长线`：仅5位长线（lynch/soros/value_institution/sector_specialist/risk_manager）
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

输出遵循统一规范 v2（三段式：第一屏研判 / 第二屏风险与决策路径 / 第三屏详细论证 /
页脚数据护栏统一承载）。详见 `../_shared/references/output-template.md`。
**生成器护栏权威源**：`../_shared/references/guardrails.md`（不在最终报告中向用户展示）。

## Workflow Coordination

完整链路见包根目录 `workflow.md`。本 skill 负责把候选股变成投资判断：

- 上游来自 `screener`：接收候选分数、策略和剔除/入选理由，做五层验证。
- 上游来自 `sector`：接收板块景气和同业比较，避免孤立看个股。
- 下游到 `technical`：当结论是买入/持有/观察时，必须确认技术触发、支撑阻力和失效位。
- 下游到 `/research financial`：当财务数据异常、估值分歧大或需要预测时，进入建模。
- 下游到 `portfolio`：当涉及实际操作时，输出仓位计划、止损、替代方案。

输出必须包含 `fundamental_rating`、`valuation_view`、`sector_context`、`technical_next_step`、`position_plan`。

### Step 0：市场环境锚定（full / debate / technical 必跑）

> **重要**：个股的"破位 / 突破 / 强势 / 弱势"必须放在市场环境中判断。
> 一只票在牛市跌破20日均线是"洗盘"，在熊市是"破位"——剥离大盘谈个股，技术信号会反向。

调用 `market_anchor.py` 一次性拉取大盘状态 + 板块强度 + 个股相对位置：

```bash
python3 scripts/market_anchor.py <股票代码> -j      # full / debate：全量
python3 scripts/market_anchor.py <股票代码> --no-sector -j   # technical：仅大盘 + 宽度
```

**输出包含**（v2.5.x 升级后共 19 个字段）：

| 维度 | 字段 | 说明 |
|------|------|------|
| 大盘状态 | `regime` / `regime_label_zh` / `regime_confidence` | bull/bear/sideways/panic/euphoria/defensive（来自 `experts/market_detector.py`，与 `decide.md §二` 权重表一致）|
| 大盘指数 | `index_change_pct` | 沪深 300 当日涨跌幅 |
| 市场宽度 | `breadth` | 上涨家数 / 下跌家数 / 涨停家数 / 跌停家数 |
| 板块强度 | `sector_strength.top/bottom` | top3 强势 + bottom3 弱势板块 ETF（来自 `data/sector_etf.csv` 的 13 个 ETF）|
| 个股 RPS | `stock_sector_compare.rps_vs_sector/_index` | 个股 vs 所在板块 ETF vs 大盘三段式对比 |
| **多时间框架**（v2.5.x 新增）| `multi_timeframe.{ma20,ma60,ma250,ma_alignment,ret_5d_pct,ret_20d_pct,atr_14,vs_ma250_pct}` | 大盘 MA20/60/250 + 5/20 日动量 + ATR14 + 年线偏离度 |
| **宏观-估值桥**（v2.5.x 新增）| `macro.{treasury_10y_pct,usd_index,usd_cny,vix,gold_usd_oz,brent_oil_usd,wti_oil_usd,lithium_carbonate_cny_t}` | 10Y 国债 / 美元 / 汇率 / VIX / 大宗商品；yfinance 失败 → fixture |
| **杠杆-反身性**（v2.5.x 新增）| `leverage.{margin_balance_total_yi,margin_change_5d_pct,if/ic/ih_main_basis_pts}` | 两融余额 + IF/IC/IH 期货基差 |
| **估值桥**（v2.5.x 新增）| `valuation_bridge.erp_sh300_pct` | 沪深 300 ERP = 1/PE - 10Y 国债 |
| **流动性+波动率**（v2.5.x 新增）| `liquidity_volatility.{sh300_atr_14,sh300_annualized_vol_pct,stock_avg_amount_20d_yi,stock_liquidity_ratio_pct}` | 大盘 ATR/年化波 + 个股日均成交额/流动性比率 |
| **情绪周期**（v2.5.x 新增）| `emotion_phase` | 主升/退潮/震荡/冰点（来自 `market_breadth.get_market_state`）|
| **行业 beta**（v2.6.0 新增）| `industry_beta.{beta,alpha,alpha_annual,r_squared,volatility_pct,interpretation}` | 动态选基准指数（沪深300/中证500/中证1000）+ 60 日窗口手写 OLS，与 `dcf.py` 折现率字典呼应 |
| **组合相关性**（v2.6.0 新增）| `portfolio_correlation.{matrix,avg_pairwise_corr,high_corr_pairs,vs_portfolio}` | 与 /portfolio skill 联动；持仓矩阵 + 个股 vs 持仓组合（分散化收益判定）|
| **题材轮动**（v2.7.0 新增）| `sector_rotation.{rotation_strength,biggest_risers,biggest_fallers,interpretation}` | 5 日板块排名位次变化（即时计算，无持久化；>3=剧烈轮动）|
| **北向资金**（v2.7.0 新增）| `northbound_pricer.{total_net_yi,direction,recent_5d_slope,interpretation}` | 20 日累计净流入 + 近 5 日斜率（边际定价者；沪/深股通分项）|
| 数据降级 | `data_quality.degraded_fields` | 失败字段名（数组，空数组表示全成功）|

**优雅降级**：

- 大盘拉取失败 → regime 默认 `defensive`（v2.4.3 fail-safe）
- 板块拉取失败 → `sector_strength = null`
- 个股板块反查失败 → `verdict = "板块归属未知/覆盖盲区"`
- yfinance 拉取宏观失败 → fixture 降级（数据为前次缓存或手工维护值）
- 个股 amount 字段缺失 → `stock_avg_amount` 用 `volume × close` 估算（标注 `volume*close(估算)`）
- **任一字段失败均不阻塞主流程**

**复用（不重写）**：

- `experts.market_detector.detect_market_state()` 直接 import
- `market_breadth.get_market_breadth()` + `get_market_state()` 直接 import
- `scripts/quote.py` 批量调用（≤15/批）
- `scripts/data.get_kline()` scale=240 datalen=250（足够 MA250）
- `technical.moving_average.ma_system()` 直接 import（MA5/10/20/60/120/250）
- `technical.volatility.compute_atr()` 直接 import（ATR）
- `strategies/macro/gate.py` 的 yfinance try/except 模式（范本）
- `industry_beta.compute_beta()` v2.6.0 手写 OLS（不引入 numpy/pandas）
- `portfolio.manager.PortfolioManager.get_positions()` v2.6.0 持仓 API

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

五层定义与评级阈值详见 `../_shared/references/five-layer.md`（唯一权威源，P1-24 去重）。仅在需要展开方法论或字段含义时读取包根目录 `methodology.md`，避免无关上下文膨胀。

### Step 3: 输出结论

> **统一前置**：所有模式（quick / full / debate / technical）的报告**开头**先输出 Step 0 的"市场环境锚定"小节，再进入各自模式的核心内容。
> 市场环境是小节标题用 📊 emoji，与个股分析章节视觉分隔，但不破坏 existing 第一行一句话结论的硬约束（来自 `output-template.md`）。

```
## 📊 市场环境锚定
🟢 市场状态: 牛市 (high) — 指数在均线上方，量能放大，市场宽度良好
📈 大盘指数: sh000300 当日 +1.20%
🌐 市场宽度: 上涨 3200 家 / 下跌 1500 家 | 涨停 45 家 / 跌停 8 家
🔥 强势板块: 半导体ETF +2.34% | 新能源车ETF +1.85% | 黄金ETF +1.20%
💀 弱势板块: 银行ETF -0.50% | 白酒ETF -0.30%

### 🎯 个股 vs 板块 vs 大盘 (sh600519)
- 所属板块: 消费 → ETF sh512690 白酒ETF
- 个股涨跌: +0.50%
- 板块涨跌: +0.30%
- 大盘涨跌: +1.20%
- RPS vs 板块: +0.20pp（板块内偏强）
- RPS vs 大盘: -0.70pp
- 结论: 在弱势板块中相对抗跌 / 跑输大盘

📊 数据时间戳: 2026-07-10 09:30:00 | 数据源: quote.py / market_breadth.py / sector_etf_strength.py
```

**quick模式：**

- 顶部"市场环境锚定"小节（一行表格简版，不展开个股 RPS）
- 一句话结论
- 关键数据表
- 操作建议（买入/持有/回避）
- 明确数据时间戳或交易日

**full模式：**

- 顶部完整"市场环境锚定"小节（含个股 RPS）
- 五层分析详细表格
- 支撑/阻力位图示
- 情景分析表（牛市/基准/悲观）
- 仓位建议+止损位

**debate模式（全模式/默认）：**

- 顶部完整"市场环境锚定"小节
- 五层分析
- 8人专家圆桌（regime 权重已由 Step 0 给出，**不再二次判定**）
- 多空投票 + 跨组加权（长线 ≥4/5 投票多数 + 短线均分区间驱动）
- 最终折中方案

**debate 长线模式：**

- 五层分析
- 仅5位长线专家（lynch/soros/value_institution/sector_specialist/risk_manager）
- 组内投票，≥4/5 看多/看空算组内多数
- 适合中长期价值判断

**debate 短线模式：**

- 五层分析
- 仅3位短线专家（topic_leader/emotion_tech/momentum_trader）
- 组内投票，≥2/3 多数阈值
- 适合短线交易时机判断

### Step 3.1: 输出格式模板（v2）

深度分析报告（`full` / `debate` 模式）使用 `reports/full-template.md` 中的 v2
骨架（**渐进披露三层 + 决策卡片首屏 + 数据护栏页脚**）。`quick` 模式仅输出第一
屏研判卡片 + 页脚，不展开第二、三屏。

- 第一屏（必呈现）：一句话研判 + 核心矛盾 + 当前动作 + 风险提示
- 第二屏（必须呈现）：核心矛盾与监测优先级 + 5 情景概率 + 论点破灭触发器
- 第三屏（详细论证）：财务/估值/技术/板块/圆桌/跟踪条件等
- 页脚（统一承载）：🛡️ 数据护栏条 + 时间戳 + 数据源 + 免责声明

### Step 3.2: 生成器护栏（约束 agent 写作，不在最终报告中向用户展示）

> **本节约束生成器行为，不在用户报告中渲染**。报告渲染时仅展示护栏结论
> （🛡️ 数据护栏条，详见 `reports/full-template.md` §页脚）。

护栏权威源：`../_shared/references/guardrails.md`。本节仅指引，不重复列出
全部规则。骨架约束摘要：

- **去重**：同一数据点 ≤2 次（数据表 1 次 + 分析论证 1 次）
- **评分统一**：`A+/A/B+/B/C` 五档字母制，禁用 ⭐ 任何符号
- **排名限定**：仅本行业（申万二级），禁止跨行业排名
- **数据来源**：核心数据表每行须标来源，禁止推算值不标来源
- **增速分列**：利润增速 vs 营收增速，模板强制两行
- **杜邦对账**：重建 ROE vs 原始 ROE 偏差 >2pp 须标注 ⚠️
- **PE 多口径**：Q1 年化 / H1 修正 / 机构预测三口径并列
- **合规措辞**："建议/买入/目标价/止损"等持牌投顾措辞需替换为"研判/观察/
  观察上沿/观察下沿"（详见 `output-template.md` §三）

评级标准和五个维度定义详见 `../_shared/references/five-layer.md`（唯一权威源）。

### Step 4: 专家讨论（debate模式）

**三种子模式**：

| 模式           | 参数          | 参与专家                       | 决策机制               |
| -------------- | ------------- | ------------------------------ | ---------------------- |
| 全模式（默认） | `debate`      | 8人（长线5 + 短线3）           | 跨组加权，市场环境调权 |
| 长线模式       | `debate 长线` | 长线5人                        | 组内投票，≥4/5 阈值    |
| 短线模式       | `debate 短线` | 短线3人                        | 组内投票，≥2/3 阈值    |

> 短线 3 人：题材龙头（topic_leader）、情绪技术复合（emotion_tech）、动量交易（momentum_trader）。
> 另有 8 份 legacy 档案（巴菲特/段永平/徐翔/赵老哥/养家/作手新一/value_anchor/institution）保留为研究档案，不参与新框架投票。

长线团（5）：彼得林奇（成长）、索罗斯（趋势）、价值机构锚（merged 价值双锚+机构派）、行业专家、风控官
短线团（3）：题材龙头（merged 徐翔+赵老哥）、情绪技术复合（merged 养家+新一）、动量交易（v2.2.0）

**全模式标准流程**（参考 experts/decide.md 决策引擎）：

1. **获取大盘数据**，判断市场环境（牛市/熊市/震荡/冰点/亢奋）：

   ```bash
   python3 scripts/quote.py sh000001,sh510300 -j
   ```

2. **每位专家独立打分**：对照 `experts/<name>.md` 中 §九 评分矩阵，用步骤1和步骤3获取的数据在各维度打分，输出 0-100 总分。8 位 active 专家关键维度：
   - 林奇（lynch）：重 PEG/增速/内部人交易
   - 索罗斯（soros）：重趋势/反身性/市场情绪一致性
   - 价值机构锚（value_institution）：重 ROE/PE/负债率/安全边际/行业空间（merged 价值双锚+机构派；价值双锚=巴菲特+段永平）
   - 题材龙头（topic_leader）：重涨停基因/板块效应/封单强度+均线排列（merged 徐翔+赵老哥）
   - 情绪技术（emotion_tech）：重情绪周期/涨停跌停家数/K线反转（merged 养家+作手新一）
   - 行业专家（sector_specialist）：按5大行业类差异化阈值
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

   **发言规则**（强制约束每位专家的 `reason` 核心理由字段）：

   - **数据基础性**：`reason` 必须引用触发评分矩阵分支的具体数据值（如"PE 35倍处行业85%分位->估值分25"、"ROE 18%->基本面90"）。禁止纯定性结论（如仅写"基本面优秀"而不附数值）。
   - **禁用表述**：不得使用"反向加分""反向指标""该分数可作为反向参考"等表述。低分仅代表"不符合本专家体系"，不构成对未来价格走势的反向预测。周期/情绪类结论必须附带指标数值（如"PE分位82%->周期顶部警示"而非仅"处于周期顶部"）。
   - **三元组展示**：当展示维度拆分（breakdown）时，必须同时输出 `原始分 × 权重 = 贡献值` 三元组格式。例如"估值：33 × 22.5% = 7.42"，而非仅展示贡献值 7.42 或仅展示原始分 33。
   - **模型边界**：承认本体系对强周期资产盈利能力评估的结构性局限。如某周期股因框架限制得低分，应说明"不符合本体系投资标准"，而非推断其价格将下跌。

   > 渲染层兜底：`experts/formatter.py` 会在输出时检测 `reason` 是否含数据引用、是否出现禁用表述，缺失时追加 `⚠理由缺数据引用` 或 `⚠含禁用表述` 警告标记。

3. **投票汇总**：按 experts/decide.md 规则——分组计票、市场环境调整权重、冲突解决（巴菲特否决权、养家情绪降权）。

4. **输出**：按 decide.md §四 格式——评分表 + 方向 + 风险 + 仓位。记得计算信心指数。

5. **记录校准数据**：debate 完成后，记录本次预测供后续验证（**需要 1.6.0+**，`scripts/calibration.py` 由 1.6.0 引入；旧版本可跳过此步，不影响主流程）。

   v2.4.3 起推荐使用 `run_debate` 编排器（自动回灌校准因子 + 落库预测）：

   ```python
   from experts.decide import run_debate
   result = run_debate(stock_code, expert_results, market_state, horizon)
   # result["_pred_id"] 为预测记录 ID，result["_calibration_factor"] 为使用的校准因子
   ```

   或手动记录（使用 active 专家名，legacy 名会自动归一化）：

   ```bash
   python3 scripts/calibration.py record --stock <代码> --direction <方向> \
     --composite <综合分> \
     --scores '{"value_institution":72,"lynch":65,"soros":55,"sector_specialist":68,"risk_manager":60,"topic_leader":45,"emotion_tech":40,"momentum_trader":55}'
   ```

   输出中附带当前校准因子（如有历史数据）：

   ```
   校准因子: +0.15 (8位 active 专家平均校准率 62%；8份 legacy 档案不参与校准)
   ```

   定期验证到期预测以累积真实准确率（v2.4.3 起默认使用真实价格回调）：

   ```bash
   python3 scripts/calibration.py verify --days 30      # 验证并获取实际收益率
   python3 scripts/calibration.py factor                # 查看全局+分组校准因子
   python3 scripts/calibration_backfill.py status       # 查看预测状态与专家准确率
   ```

**长线/短线单组模式流程**（参考 experts/decide.md §七）：

1. **获取数据**：同全模式步骤1（行情+财务+K线），无需获取大盘数据。
2. **仅调用对应组专家打分**：长线模式只跑 lynch/soros/value_institution/sector_specialist/risk_manager（5人），短线模式只跑 topic_leader/emotion_tech/momentum_trader（3人）。
3. **组内投票**：按 decide.md §七 规则——长线组 ≥4/5 看多=看多，≥4/5 看空=看空，2:3=中性；短线组 ≥2/3 看多=看多，≥2/3 看空=看空。
4. **输出**：评分表（仅该组专家）+ 组内方向 + 风险 + 仓位。信心指数基于组内标准差计算。

### Step 5: 技术分析（technical 模式）

详见 [`/stock-technical`](../stock-technical/SKILL.md) 子模块。本步骤仅做调用入口说明。

```bash
# 市场环境锚定（technical 模式不需要板块横向，但保留大盘状态用于"市场风格判断"）
python3 scripts/market_anchor.py <股票代码> --no-sector -j

# 技术分析
python3 scripts/technical.py sh600989              # 完整报告
python3 scripts/technical.py sh600989 --classify   # 含分类+缠论+战法
python3 scripts/technical.py sh600989 --quick      # 快速摘要
```

输出包含：顶部"市场环境锚定"小节（轻量版，无板块强弱）+ 综合评分、均线系统、MACD、KDJ、BOLL、RSI、成交量、K线形态、缠论、A 股本土战法、支撑/阻力位。详见子模块文档。

**为什么 technical 也需要大盘锚定**：技术信号在不同 regime 下含义不同——

- `bull` 中：放量突破是真信号，缩量回踩是洗盘
- `bear / panic` 中：放量长上影是出货信号（不是启动）
- `defensive` 中：低估值高股息抗跌，成长股破位需警惕

## Guardrails

- 明确声明这不是投资保证，给出风险触发条件而不是绝对化预测。
- 数据失败时说明失败的数据源和影响，仍可用已有数据给低置信度结论。
- 不要虚构实时价格、最新公告、研报评级或成交数据。
- **专家 `reason` 字段约束**：核心理由必须基于步骤1/3获取的实际数据值，不得编造"反向加分""反向指标"等无数据支撑的论述。模型低分仅代表"不符合本体系投资标准"，不代表对未来价格走势的预测。`experts/formatter.py` 会在渲染层检测并标记违规 reason。

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

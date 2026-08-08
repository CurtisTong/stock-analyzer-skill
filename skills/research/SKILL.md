---
name: research
description: 深度研究。触发词：深度研究一下XX、财务分析XX、排雷XX、DCF估值、写一份研究报告、XX的投资价值分析、对比XX和XX、XX能不能长期持有、XX的盈利质量怎么样。财务建模（DCF/杜邦/排雷）和全维度投资研究报告。
version: 1.20.0
model: glm-5.2
allowed-tools: Bash(python3 scripts/quote.py *) Bash(python3 scripts/kline.py *) Bash(python3 scripts/finance.py *) Bash(python3 scripts/technical.py *) Bash(python3 scripts/announcements.py *) Bash(python3 scripts/events.py *) Bash(python3 scripts/market_anchor.py *) Bash(python3 scripts/sector.py *) Bash(python3 scripts/concept.py *) Bash(python3 scripts/industry_beta.py *) Bash(python3 scripts/portfolio_correlation.py *) Bash(python3 scripts/stock.py *) Read(./methodology.md) Read(./experts/*.md) Read(./skills/_shared/references/*.md)
---

# 深度研究

> ⚠️ **NOTE**：本 skill 无独立 Python 入口（`scripts/research.py` 不存在），
> 由 Claude 通过 `allowed-tools` 委派到 `finance.py` / `quote.py` / `kline.py` /
> `technical.py` / `market_anchor.py` / `events.py` / `sector.py` / `announcements.py`
> 等脚本组合调用。
> 直接运行 `python3 scripts/research.py <args>` 会 ModuleNotFoundError。
>
> **P2 流程修复（2026-08-08）**：增加 `events.py` / `sector.py` 到 allowed-tools，
> Step 2 强制 8 项基础数据，Guardrails 增加"业绩预增必上跳评级"等业务规则，
> 详见 Guardrails 章节的强制流程规则。
>
> **P3 信号冲突检测（2026-08-08 二轮复盘后）**：v2 报告发现 stock.py 综合评分
> 与业绩催化机械上跳存在冲突。v1.20.0 引入规则 3.5 信号冲突检测，Step 2 升级为
> 9 项必调（含 `stock.py`），Step 4 强制输出 `signal_conflict` 章节。
> 当业绩预增 vs 技术超买 / vs 综合评分<50 冲突时，评级**不上跳至 BUY**。

财务建模 + 全维度投资研究报告。两个子命令覆盖不同深度。

## Usage

```text
/research financial <任务描述>       # 财务建模：排雷/杜邦/DCF/敏感性
/research report <任务描述>          # 全维度研究报告：整合多模块证据
/research report <代码> --brief      # 简版报告（仅核心结论+风险）
```

典型任务：

- "排雷 sh600989"、"DCF 估值 sz300750"
- "研究宁德时代，给一份完整投资报告"
- "对比比亚迪和宁德时代的投资价值"

## Instructions

使用简洁中文。先给核心结论和置信度，再给关键数据、模型假设和行动项。

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

## 共享约定

- 代码前缀：`../_shared/references/code-prefix.md`
- 脚本目录：`../_shared/references/script-catalog.md`
- 五层框架：`../_shared/references/five-layer.md`

## Workflow Coordination

本 skill 是深度研究的**总控编排**，整合其他 skill 的产出：

```
用户需求 → research (编排器)
  ├─ market: 市场状态、风格、风险偏好 → market_regime
  ├─ sector: 行业景气、竞争格局、轮动位置 → sector_view
  ├─ stock: 五层分析 → fundamental_rating
  ├─ technical: 交易窗口、支撑阻力、失效条件 → technical_trigger
  └─ portfolio: 组合适配、仓位上限 → position_plan
```

---

## 子命令 1: /research financial — 财务建模

财务深挖——排雷→指标→建模→验证，不做交易买点。

### Step 1: 确定分析范围

- 排雷模式：检查财务造假信号（营收/利润/现金流匹配度、非经常性损益占比、关联交易）
- 质量评估模式：杜邦分解、ROE 驱动力拆解、毛利率趋势
- 估值分歧模式：DCF 建模、情景分析、同业对比
- 增长预测模式：历史增速拆分、驱动因子、天花板判断

### Step 2: 收集财务数据

```bash
python3 scripts/finance.py SH600989 -j       # 最近 4 季财务数据
python3 scripts/quote.py sh600989 -j          # 实时行情（PE/PB/市值）
python3 scripts/announcements.py 600989       # 最新公告
python3 scripts/announcements.py 600989 reports  # 券商研报
```

### Step 3: 分析框架

#### 财务排雷

| 信号                       | 危险阈值 | 含义                             |
| -------------------------- | -------- | -------------------------------- |
| 经营现金流/净利润 < 0.5    | ⚠️       | 利润无现金支撑                   |
| 非经常性损益占比 > 30%     | 🔴       | 主业利润被夸大                   |
| 应收/营收增速 > 2×营收增速 | 🔴       | 收入质量下降                     |
| 毛利率突变 > ±10pct/年     | ⚠️       | 需确认原因（产品结构/价格/成本） |
| 商誉/净资产 > 30%          | ⚠️       | 减值风险                         |
| 大股东质押 > 60%           | 🔴       | 流动性风险                       |

#### 杜邦分解（ROE 驱动力）

```
ROE = 净利率 × 资产周转率 × 权益乘数
```

- 高净利率 → 护城河/品牌溢价
- 高周转率 → 运营效率型
- 高杠杆 → 风险驱动型（需警惕去杠杆）

#### DCF 简化估值

假设条件（需明确列出）：

| 假设       | 基准                      | 乐观 | 悲观 |
| ---------- | ------------------------- | ---- | ---- |
| 营收增速   | 近3年均值                 | +5%  | -5%  |
| 利润率     | 近3年均值                 | +2%  | -2%  |
| WACC       | 8-10%（行业风险因子调整） | -1%  | +1%  |
| 终值增长率 | 3%                        | 4%   | 2%   |

---

## 子命令 2: /research report — 全维度研究报告

综合 multi-agent 证据，输出存档级研究报告。

### Step 1: 明确研究范围

- 个股/行业/市场？时间维度？投资风格（价值/成长/趋势/逆向）？
- 确定分析深度（快速扫描 / 标准报告 / 深度尽调）

### Step 2: 获取基础数据（强制 9 项）

> ⚠️ **强制调用**：以下脚本**缺一不可**，遗漏任一项将导致结论可靠性不达标。

```bash
# 1. 行情
python3 scripts/quote.py <代码> -j

# 2. 财务
python3 scripts/finance.py <SH/SZ代码> -j

# 3. K线
python3 scripts/kline.py <代码> 240 60

# 4. 技术分析（指标维度）
python3 scripts/technical.py <代码> --classify

# 5. 公告/研报
python3 scripts/announcements.py <代码> [reports]

# 6. ★ 事件日历（业绩预告/分红/解禁/股东变动）—— 必调！
python3 scripts/events.py <代码> --days 60 -j

# 7. ★ 市场环境锚定（大盘+板块+宽度）—— 必调！
python3 scripts/market_anchor.py --no-portfolio -j

# 8. ★ 板块强度（确定行业景气与轮动位置）—— 多股时必调！
python3 scripts/sector.py <板块名> -j

# 9. ★ 综合评分（系统评级+买卖信号+5维度融合）—— 必调！—— v1.20.0 新增
python3 scripts/stock.py <代码> -j
```

**事件日历检查规则**：
- 若 `forecast_type=increase` 且 `change_midpoint > 50%` → 触发评级上跳候选（**需经信号冲突检测后生效**，见 Guardrails 规则3.5）
- 若 `forecast_type=decrease` 且 `change_midpoint < -30%` → 评级下调候选（同样需经冲突检测）
- 若预增/预减公告日期 < 7天 → 视为**强催化**，需在"核心观点"中显著标注

**市场环境使用规则**：
- `regime = sideways` 时，**禁止给出"大盘强势"等乐观定性**
- 必须使用 `market_anchor.py` 的 `regime` + `breadth.advance_ratio` 联合判断，不可用简单 `quote.py` 涨跌替代
- 若需查个股 RPS，使用 `market_anchor.py <stock_code> --no-portfolio -j`

**综合评分使用规则**（v1.20.0 新增）：
- `stock.py` 输出的"综合评分 + 评级"是**多维度融合的最终结论**，与单维数据可能冲突
- 当单维信号（业绩/事件/技术）结论与 `stock.py` 综合评分**矛盾**时，**必须触发信号冲突检测**（见 Guardrails 规则 3.5）
- 综合评分 < 50 → **禁止评级上跳到 BUY**（除非有 3 个以上独立维度的强支撑）

### Step 3: 分模块分析（复用 `/stock full`，不重复实现）

直接调用 [`/stock <代码> full`](../stock/SKILL.md) 取其五层分析输出（符合 `skills/_shared/contracts/stock.schema.json`）。

本步骤不再重复实现基本面/估值/技术面/风险收益模块，仅在 Step 4 融合以下增量证据：

| 增量模块   | 数据来源                                       | 备注                                       |
| ---------- | ---------------------------------------------- | ------------------------------------------ |
| 市场环境   | `scripts/market_anchor.py --no-portfolio -j`   | 必须用此脚本获取 `regime`/`breadth`/`sector_strength` |
| 板块景气   | `scripts/sector.py <板块> -j`                  | 叠加 `sector_view` 上下文                  |
| 事件催化   | `scripts/events.py <代码> --days 60 -j`        | 业绩预告必须显式纳入评级考量               |
| 持仓约束   | `/portfolio health`（如适用）                  | 叠加 `position_plan` 上下文                |
| 同业基准   | `scripts/quote.py <可比公司代码> -j`           | 多股对比时必须引用行业龙头 PE/PB 锚        |
| 组合相关性 | `scripts/portfolio_correlation.py -j`          | 多股配置时权重需基于相关性矩阵             |

### Step 4: 输出格式

```
═══════════════════════════════════════
  研究报告: 名称(代码)
  投资建议: buy/hold/sell/observe
  置信度: 高/中/低 | 数据日期: YYYY-MM-DD
═══════════════════════════════════════

## 核心观点（3-5 行）
## 事件催化 (event_catalysts)
## 信号冲突声明 (signal_conflict)        ★ v1.20.0 强制新增
## 模块证据（市场/板块/基本面/估值/技术面/风险收益）
## 风险映射 (risk_map)
## 跟踪计划 (tracking_plan)
```

**event_catalysts 章节模板**：
```
## 事件催化 (event_catalysts)
- [YYYY-MM-DD] [业绩预增] [影响: 强正面] [内容: H1净利预增XXX%-XXX%，Q2单季X-X亿]
- [YYYY-MM-DD] [股东增持] [影响: 中性正面] [内容: 实控人增持计划，金额X亿]
- [YYYY-MM-DD] [限售解禁] [影响: 弱负面] [内容: X月X日解禁X万股，占比X%]
```

**signal_conflict 章节模板**（v1.20.0 新增）：
```
## 信号冲突声明 (signal_conflict)
- 冲突类型: [类型A/B/C/无]
- 冲突程度: [高/中/低/无]
- 冲突维度明细:
  - [正向]: 业绩预增 H1+XXX% / 净利同比 +XXX%
  - [负向]: stock.py 综合评分 XX.X (中性) / KDJ J=XX 超买 / BOLL 上轨
- 评级裁决: [BUY→HOLD / HOLD→HOLD / 等待确认]
- 触发条件: [等待中报兑现 + KDJ回落至80以下 + BOLL回到中轨]
```

## Guardrails

- DCF 模型必须列出所有关键假设，不给出"黑箱"估值。
- 不要把脚本未返回的数据包装成事实；缺失项标注为"未覆盖"。
- 非经常性损益占比 > 30% 时必须有排雷标注。
- 财务分析不给出交易买点，只出具财务健康判断。
- 每个模块证据必须标注数据来源和时间戳。
- 综合建议需要体现分歧（看多 vs 看空），不做单一叙事。
- 所有投资建议需附带"不构成投资建议"声明。

### 强制流程规则（P2-2026-08-08 复盘后新增，v1.20.0 信号冲突检测强化）

- **9 项基础数据必调**：quote / finance / kline / technical / announcements / **events / market_anchor / sector / stock**。任一缺失则报告置信度自动下调至"低"。
- **业绩预告必看（带冲突检测）**：`forecast_type=increase` 且 `change_midpoint > 50%` 时**触发评级上跳候选**，但**必须经规则 3.5 信号冲突检测后**才生效。预减规则对称。
- **市场环境必查**：禁止用 `quote.py sh000001` 涨跌判断大盘强弱，必须用 `market_anchor.py` 的 `regime` 字段。`regime=sideways` 时定性必须为"震荡"而非"强势"。
- **板块强度必查**：多股对比必须用 `sector.py` 查询板块强度，不能凭印象给"产业链联动"结论。
- **同业基准必引**：估值对比至少引用 1 个行业龙头（如锂电→宁德时代 PE 21）作为锚，否则 PE/PB 数字无解读意义。
- **事件催化章节必出**：报告必须包含 `event_catalysts` 章节，列出 30/60 天内的业绩预告、解禁、股东变动等关键事件。
- **配置权重必量化**：组合配置权重需基于 `portfolio_correlation.py` 相关性矩阵或显式给出量化依据，禁止"3:2:5"等直觉数字。
- **综合评分必用**：必须调用 `stock.py` 获取"综合评分 + 系统评级 + 买卖信号"。综合评分是系统多维融合结果，**不可绕过**。

### 规则 3.5 — 信号冲突检测（v1.20.0 新增，防止机械上跳评级）

> 🎯 **目的**：防止业绩催化（事件）信号与系统综合信号（技术面+多维度）冲突时，机械执行"上跳评级"导致结论与系统矛盾。

**触发条件**：当以下任一组合出现时，必须**强制触发冲突检测**：

| 冲突类型 | 正向信号 | 负向信号 |
|---------|---------|---------|
| **类型A：业绩 vs 技术** | events 预增 +50% 以上 | technical KDJ J >= 90 超买 / BOLL 触及上轨 / stock.py 卖出信号 |
| **类型B：基本面 vs 综合** | finance 营收/净利 YoY > 50% | stock.py 综合评分 < 50 / 系统评级"中性" |
| **类型C：市场 vs 个股** | market_anchor regime=bull 或强势板块 | stock.py 综合评分 < 40 |

**冲突处理规则**（必须按顺序判定）：

1. **冲突程度 = 高**（2 个以上独立维度同时冲突）：
 - 评级**禁止上调**至 BUY，可上调至 HOLD
 - 投资建议改为 **"等待确认"**：要求"中报兑现 + 技术面修复"双确认
 - 报告核心观点必须**显著标注**"业绩 vs 信号冲突"
2. **冲突程度 = 中**（1 个维度冲突）：
 - 评级**可上调一档**，但**不上跳到 BUY**
 - 报告必须给出"冲突说明"章节，列出冲突维度
3. **冲突程度 = 低**（仅单一指标轻微冲突）：
 - 评级按常规上跳
 - 报告附"风险提示"标注冲突指标

**判断矩阵示例**：

```
                  综合评分 ≥ 50    综合评分 40-50    综合评分 < 40
                  (系统非中性)      (中性)            (弱)
预增 +50%以上     ✅ 上跳生效       ⚠️ 类型B中等      🔴 类型B高 → 等待
+ KDJ 超买          类型A中等
+ BOLL 上轨
预增 +50%但       ⚠️ 类型A中等      🔴 类型A高       🔴 双重高
+ KDJ J≥100        → HOLD上限      → 等待           → observe
```

**强制声明**：报告必须包含 `## 信号冲突声明` 章节，按上述规则判定后给出"无冲突 / 中等冲突 / 高冲突"结论。

### 信号冲突声明模板（Step 4 强制章节）

```
## 信号冲突声明 (signal_conflict)
- 冲突类型: [类型A/B/C/无]
- 冲突程度: [高/中/低/无]
- 冲突维度明细:
  - [业绩预增 +1074%] vs [stock.py 综合评分 42.4 (中性)]
  - [H1预增催化] vs [KDJ J=96 超买 + BOLL上轨]
- 评级裁决: [BUY→HOLD / HOLD→HOLD / 按规则生效]
- 触发条件: [等待中报兑现 + KDJ回落至80以下]
```

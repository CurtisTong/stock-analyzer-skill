---
name: research
description: 深度研究。触发词：深度研究一下XX、财务分析XX、排雷XX、DCF估值、写一份研究报告、XX的投资价值分析、对比XX和XX、XX能不能长期持有、XX的盈利质量怎么样。财务建模（DCF/杜邦/排雷）和全维度投资研究报告。
version: 1.14.1
model: opus
allowed-tools: Bash(python3 scripts/*) Read(./methodology.md) Read(./experts/*.md) Read(./skills/_shared/references/*.md)
---

# 深度研究

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

### Step 2: 获取基础数据

```bash
# 行情
python3 scripts/quote.py <代码> -j

# 财务
python3 scripts/finance.py <SH/SZ代码> -j

# K线
python3 scripts/kline.py <代码> 240 60

# 公告/研报
python3 scripts/announcements.py <代码> [reports]

# 技术分析
python3 scripts/technical.py <代码> --classify

# 大盘判断
python3 scripts/quote.py sh000001,sh510300,sh510500 -j
```

### Step 3: 分模块分析（复用 `/stock full`，不重复实现）

直接调用 [`/stock <代码> full`](../stock/SKILL.md) 取其五层分析输出（符合 `skills/_shared/contracts/stock.schema.json`）。

本步骤不再重复实现基本面/估值/技术面/风险收益模块，仅在 Step 4 融合以下增量证据：

| 增量模块   | 数据来源                          | 备注                              |
| ---------- | --------------------------------- | --------------------------------- |
| 市场环境   | `/market full` 或 `scripts/quote.py sh000001` | 叠加 `market_regime` 上下文       |
| 板块景气   | `/sector <板块> overview`         | 叠加 `sector_view` 上下文         |
| 持仓约束   | `/portfolio health`（如适用）     | 叠加 `position_plan` 上下文       |

### Step 4: 输出格式

```
═══════════════════════════════════════
  研究报告: 名称(代码)
  投资建议: buy/hold/sell/observe
  置信度: 高/中/低 | 数据日期: YYYY-MM-DD
═══════════════════════════════════════

## 核心观点（3-5 行）
## 模块证据（市场/板块/基本面/估值/技术面/风险收益）
## 风险映射 (risk_map)
## 跟踪计划 (tracking_plan)
```

## Guardrails

- DCF 模型必须列出所有关键假设，不给出"黑箱"估值。
- 不要把脚本未返回的数据包装成事实；缺失项标注为"未覆盖"。
- 非经常性损益占比 > 30% 时必须有排雷标注。
- 财务分析不给出交易买点，只出具财务健康判断。
- 每个模块证据必须标注数据来源和时间戳。
- 综合建议需要体现分歧（看多 vs 看空），不做单一叙事。
- 所有投资建议需附带"不构成投资建议"声明。

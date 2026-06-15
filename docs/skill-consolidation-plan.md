# Skill 整合设计方案

> 状态：设计文档（未实施）| 日期：2026-06-15

## 背景

当前 13 个 skill 对新手用户选择困难。通过合并功能重叠的 skill，精简至 9 个，降低认知负担。

## 合并方案

### 合并 1: technical → stock

**理由**：`/stock full` 已包含完整技术分析（MA/MACD/KDJ/BOLL/RSI/缠论），`/technical` 是冗余入口。

| 项目     | 详情                                           |
| -------- | ---------------------------------------------- |
| 来源     | `skills/technical/SKILL.md` (178 行)           |
| 目标     | `skills/stock/SKILL.md` (216 行)               |
| 模型差异 | technical 用 sonnet，stock 用 opus → 保留 opus |

**合并策略**：

1. 在 `skills/stock/SKILL.md` 的 Usage 区域添加 `/stock <code> technical` 子命令
2. 子命令等价于运行 `python3 scripts/technical.py <code>` + 原 technical SKILL.md 的输出格式指引
3. 保留 `/technical` 作为别名（SKILL.md 内容精简为 3 行 redirect）

**stock SKILL.md 新增**：

```text
/stock sh600989 technical             # 纯技术分析（MA/MACD/KDJ/BOLL/RSI/缠论）
/stock sh600989 technical --no-chan    # 技术分析不含缠论
```

**technical SKILL.md 精简为**：

```markdown
---
name: technical
description: 纯技术分析（已合并至 /stock technical 子命令）
version: 1.9.0
model: sonnet
---

# 已合并

本 skill 已合并至 `/stock`。请使用：

/stock <code> technical
```

---

### 合并 2: stock-init → screener

**理由**：股票池初始化是选股的前置步骤，合并后 `/screener` 自动检查池状态。

| 项目     | 详情                                                  |
| -------- | ----------------------------------------------------- |
| 来源     | `skills/stock-init/SKILL.md` (121 行)                 |
| 目标     | `skills/screener/SKILL.md` (142 行)                   |
| 模型差异 | stock-init 用 haiku，screener 用 sonnet → 保留 sonnet |

**合并策略**：

1. 在 `skills/screener/SKILL.md` 的前置步骤中添加"检查股票池状态，未初始化则自动触发"
2. 保留 `/stock-init` 作为别名（精简为 redirect）
3. screener 的 allowed-tools 扩展添加 `Bash(python3 scripts/init_pool.py *)`

**screener SKILL.md 新增前置步骤**：

````markdown
## 前置步骤

运行前检查股票池是否已初始化：

```bash
ls scripts/data/sector_stocks.json 2>/dev/null || python3 scripts/init_pool.py
```
````

如未初始化，自动运行 `/stock-init`（零配置，内置预置数据）。

````

---

### 合并 3: financial-analyst + investment-researcher → research

**理由**：两者都是深度研究功能，合并为统一的研究入口。

| 项目 | 详情 |
|------|------|
| 来源 1 | `skills/financial-analyst/SKILL.md` (138 行) |
| 来源 2 | `skills/investment-researcher/SKILL.md` (156 行) |
| 目标 | 新建 `skills/research/SKILL.md` |
| 模型 | 均为 opus → 保留 opus |

**合并策略**：

1. 新建 `skills/research/SKILL.md`，包含两个子命令：
   - `/research financial <code>` — 财务建模（DCF/杜邦/排雷）
   - `/research report <code>` — 全维度研究报告
2. 原两个 SKILL.md 精简为 redirect
3. research 的 allowed-tools 合并两者

**research SKILL.md 核心内容**：

```markdown
---
name: research
description: 深度研究 skill。财务建模（DCF/杜邦分解/排雷）和全维度投资研究报告。
version: 1.9.0
model: opus
allowed-tools: Bash(python3 scripts/*) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/methodology.md) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/experts/*) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/skills/**)
---

# 深度研究

## 子命令

/research financial sh600989        # 财务建模：DCF/杜邦分解/盈利质量排雷/敏感性分析
/research report sh600989           # 全维度研究报告：整合 market/sector/stock/technical/portfolio
/research report sh600989 --brief   # 简版报告（仅核心结论+风险）
````

---

## 合并前后对比

| 维度       | 合并前    | 合并后                   |
| ---------- | --------- | ------------------------ |
| Skill 数量 | 13        | 9 + 4 redirect           |
| 新手选择   | 13 个命令 | 9 个核心命令             |
| 向后兼容   | —         | 旧命令仍可用（redirect） |

## 合并后 Skill 清单

| #   | Skill         | 触发命令                                                            | 模型   |
| --- | ------------- | ------------------------------------------------------------------- | ------ |
| 1   | **stock**     | `/stock <code> [quick\|full\|debate\|technical]`                    | opus   |
| 2   | **market**    | `/market [full\|quick\|intraday]`                                   | sonnet |
| 3   | **sector**    | `/sector <name> [overview\|compare\|stock]`                         | sonnet |
| 4   | **screener**  | `/screener [--sector X] [--strategy Y] [--top N]`                   | sonnet |
| 5   | **portfolio** | `/portfolio [add\|reduce\|remove\|health\|rebalance\|compare\|web]` | sonnet |
| 6   | **monitor**   | `/monitor [scan\|levels\|check\|--cache\|--sources\|--cleanup]`     | sonnet |
| 7   | **backtest**  | `/backtest [--strategy X] [--all] [--days N]`                       | haiku  |
| 8   | **research**  | `/research [financial\|report] <code>`                              | opus   |
| 9   | **help**      | `/help`                                                             | haiku  |

**保留但不合并**：`learn`（教学功能独立）

**Redirect（旧命令仍可用）**：`technical`、`stock-init`、`financial-analyst`、`investment-researcher`

---

## 实施步骤

### Phase 1: 合并 technical → stock

1. 编辑 `skills/stock/SKILL.md`：添加 `technical` 子命令文档
2. 精简 `skills/technical/SKILL.md`：保留 frontmatter + redirect
3. 更新 `skills/_shared/references/` 中的引用
4. 测试：`/stock sh600989 technical` 输出与原 `/technical sh600989` 一致

### Phase 2: 合并 stock-init → screener

1. 编辑 `skills/screener/SKILL.md`：添加前置步骤 + allowed-tools 扩展
2. 精简 `skills/stock-init/SKILL.md`：保留 frontmatter + redirect
3. 测试：首次运行 `/screener` 时自动触发初始化

### Phase 3: 合并 research

1. 新建 `skills/research/SKILL.md`
2. 精简 `skills/financial-analyst/SKILL.md` 和 `skills/investment-researcher/SKILL.md`
3. 更新 symlinks（`install.sh` 和 `install-plugin.js`）
4. 测试：`/research financial sh600989` 和 `/research report sh600989`

### Phase 4: 更新文档

1. 更新 README.md 的 Skill 列表
2. 更新 `help/SKILL.md` 的命令列表
3. 更新 CLAUDE.md 的 Skill 表格
4. 更新 `install.sh` 和 `install-plugin.js` 的 symlink 数量

---

## 风险评估

| 风险                  | 影响 | 缓解                                                    |
| --------------------- | ---- | ------------------------------------------------------- |
| 用户习惯旧命令        | 低   | redirect 保留旧命令                                     |
| SKILL.md 引用路径断裂 | 中   | 全局搜索 `skills/technical` 和 `skills/stock-init` 引用 |
| 合并后 SKILL.md 过长  | 低   | stock 从 216→~240 行，可接受                            |

## 工时估算

| 阶段                           | 工时     |
| ------------------------------ | -------- |
| Phase 1: technical → stock     | 0.5h     |
| Phase 2: stock-init → screener | 0.5h     |
| Phase 3: research 合并         | 1h       |
| Phase 4: 文档更新              | 0.5h     |
| **总计**                       | **2.5h** |

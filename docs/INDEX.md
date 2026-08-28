# 文档索引（docs/）

> 🟢 **一句话**：docs/ 目录下分两层 —— **核心指南**（活跃维护）+ **archive/**（历史归档），按"你是谁 / 你想干啥"两条线分类。
> 🟡 **只想看一份**？
> 🆕 新用户 → [quick-start.md](quick-start.md) · 📈 投资者 → [product-architecture.md](product-architecture.md) · 🛠️ 开发者 → [developer-guide.md](developer-guide.md) · 🤝 贡献者 → [CONTRIBUTING.md](../CONTRIBUTING.md)
> ⚫ **文档数**：9 份核心指南 + 1 份合规 + 26 份历史归档（designs/reviews/reports/releases） = 36 份
> 📦 投资方法论新版见 [../methodology.md](../methodology.md)（已从 docs/ 移到仓库根目录）

> 适用文档：stock-analyzer-skill v1.20.2
> 索引目的：解决 docs/ 目录下"找不到入口"问题
> 上次重构：2026-08-20（docs/methodology.md 重复清理 + 历史归档分层）

---

## 📑 目录

1. [按角色索引](#1-按角色索引)
2. [按阶段索引](#2-按阶段索引)
3. [角色 × 阶段交叉矩阵](#3-角色--阶段交叉矩阵)
4. [文档分类清单（按文件类型）](#4-文档分类清单按文件类型)
5. [入口跳转（按意图）](#5-入口跳转按意图)
6. [文档维护责任](#6-文档维护责任)
7. [历史归档（archive/）](#7-历史归档archive)

> 语义说明：🟢 健康 / 🟡 中性 / ⚫ 数据事实。角色 emoji：🆕 新用户 / 📈 投资者 / 🛠️ 开发者 / 🤝 贡献者 / 📐 审查者。

---

## 1. 按角色索引

### 🆕 新用户（首次接触）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 上手 | [quick-start.md](quick-start.md) | 5 分钟安装 + 第一个 `/stock` 命令 |
| 上手 | [user-guide.md](user-guide.md) | 使用者指南：12 个 skill 完整流程 |
| 上手 | [tutorials/walkthrough-600519.md](tutorials/walkthrough-600519.md) | 贵州茅台完整演练（12 skill 串联） |
| 入门 | [../methodology.md](../methodology.md) | 投资方法论（PE/ROE/PEG 等术语翻译） |
| 入门 | [../skills/learn/SKILL.md](../skills/learn/SKILL.md) | `/learn <概念>` 学习助手 |

### 📈 投资者（已上手）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 决策 | [product-architecture.md](product-architecture.md) | 产品架构：五层分析 / 16 份专家人设 / 数据源 |
| 决策 | [../methodology.md](../methodology.md) | 投资方法论 + 评分公式 |
| 决策 | [../experts/README.md](../experts/README.md) | 16 份专家档案库（8 active + 8 legacy） |
| 决策 | [persona.md](persona.md) | 3 类用户画像 + 设计启示 |
| 风控 | [user_expert.md](user_expert.md) · [visual_expert.md](visual_expert.md) | 用户面 / 视觉审查视角 |

### 🛠️ 二次开发者（要写代码）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 入门 | [developer-guide.md](developer-guide.md) | 项目结构 + BaseFetcher / CircuitBreaker |
| 入门 | [api-reference.md](api-reference.md) | fetcher 接口 + 数据类型 + 返回格式 |
| 入门 | [product-architecture.md](product-architecture.md) | 三层架构 + 数据源矩阵 + 行业阈值 |
| 进阶 | [archive/reviews/](archive/reviews/) | 历史架构审查（2026-07 系列，含 90+ 技术债修复） |

### 🤝 贡献者（要发 PR）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 入门 | [CONTRIBUTING.md](../CONTRIBUTING.md) | 提交规范 + Commit 格式 |
| 入门 | [CHANGELOG.md](../CHANGELOG.md) | 变更日志（Keep a Changelog 格式） |
| 流程 | [archive/designs/skill-consolidation-plan.md](archive/designs/skill-consolidation-plan.md) | skill 整合决策记录（历史） |
| 流程 | [archive/reviews/review-issues.md](archive/reviews/review-issues.md) · [archive/reviews/review-verification.md](archive/reviews/review-verification.md) | 审查问题清单 + 验证记录（Round 11 收官归档） |
| 流程 | [archive/designs/implementation-plan-2026-q3-q4.md](archive/designs/implementation-plan-2026-q3-q4.md) | Q3/Q4 实施计划（历史，2026-06-15 ~ 11-01 窗口） |

### 📐 审查视角（要做评审）

| 角色 | 文档 | 说明 |
| :--- | :--- | :--- |
| 用户专家 | [user_expert.md](user_expert.md) | 12 项硬指标 + 三明治错误信息 |
| 视觉专家 | [visual_expert.md](visual_expert.md) | 14 项硬指标 + 视觉三级层 |
| 产品专家 | [persona.md](persona.md) | 3 类画像 + 设计启示 |
| 投资专家 | [../methodology.md](../methodology.md) · [../experts/README.md](../experts/README.md) | 投资逻辑 + 16 份专家人设 |

---

## 2. 按阶段索引

### 🚀 阶段 1：上手（30 秒 → 5 分钟）

- [quick-start.md](quick-start.md) — 5 分钟快速入门
- [README.md §30 秒上手](../README.md#-30-秒上手) — 3 条命令跑通
- [tutorials/walkthrough-600519.md](tutorials/walkthrough-600519.md) — 完整演练教程

### 📖 阶段 2：精通（1 天 → 1 周）

- [user-guide.md](user-guide.md) — 12 skill 完整流程
- [../methodology.md](../methodology.md) — 投资方法论
- [product-architecture.md](product-architecture.md) — 产品架构
- [../experts/README.md](../experts/README.md) — 16 份专家人设

### 🔧 阶段 3：扩展（1 周 → 1 月）

- [developer-guide.md](developer-guide.md) — 开发者指南
- [api-reference.md](api-reference.md) — API 参考
- [archive/reviews/architecture-review-2026-07-07.md](archive/reviews/architecture-review-2026-07-07.md) — 最近期架构审查

### 🏛 阶段 4：维护（持续）

- [CHANGELOG.md](../CHANGELOG.md) — 变更日志
- [archive/reviews/review-issues.md](archive/reviews/review-issues.md) — 审查问题清单（Round 11 收官归档）
- [archive/designs/implementation-plan-2026-q3-q4.md](archive/designs/implementation-plan-2026-q3-q4.md) — 历史实施计划（33/33 项已完成）

---

## 3. 角色 × 阶段交叉矩阵

| | 上手（5 min） | 精通（1 天） | 扩展（1 周） | 维护（持续） |
| :--- | :---: | :---: | :---: | :---: |
| 🆕 **新用户**     | [quick-start](quick-start.md) | [user-guide](user-guide.md) | — | — |
| 📈 **投资者**     | [quick-start](quick-start.md) | [../methodology](../methodology.md) · [product-architecture](product-architecture.md) | — | [CHANGELOG](../CHANGELOG.md) |
| 🛠️ **二次开发者** | [quick-start](quick-start.md) | [developer-guide](developer-guide.md) | [api-reference](api-reference.md) · [archive/reviews/](archive/reviews/) | [CHANGELOG](../CHANGELOG.md) |
| 🤝 **贡献者**     | [CONTRIBUTING](../CONTRIBUTING.md) | [review-issues](archive/reviews/review-issues.md) | [implementation-plan-2026-q3-q4](archive/designs/implementation-plan-2026-q3-q4.md) | [CHANGELOG](../CHANGELOG.md) |
| 📐 **审查者**     | [persona](persona.md) | [user_expert](user_expert.md) · [visual_expert](visual_expert.md) | [archive/reviews/](archive/reviews/) | [review-verification](archive/reviews/review-verification.md) |

---

## 4. 文档分类清单（按文件类型）

### 📘 核心指南（长期维护）

| 文档 | 角色定位 | 更新频率 |
| :--- | :--- | :--- |
| [quick-start.md](quick-start.md) | 上手 | 季度 |
| [user-guide.md](user-guide.md) | 精通 | 月度 |
| [developer-guide.md](developer-guide.md) | 扩展 | 月度 |
| [api-reference.md](api-reference.md) | 扩展 | 月度 |
| [product-architecture.md](product-architecture.md) | 决策 | 月度 |
| [../methodology.md](../methodology.md) | 决策 | 季度 |
| [persona.md](persona.md) | 审查 | 季度 |
| [user_expert.md](user_expert.md) | 审查 | 季度 |
| [visual_expert.md](visual_expert.md) | 审查 | 季度 |

### 🛡 合规

| 文档 | 说明 |
| :--- | :--- |
| [data-source-license.md](data-source-license.md) | 数据源许可证声明 |

### 📦 历史归档

详见 [§7 历史归档](#7-历史归档archive)。

---

## 5. 入口跳转（按意图）

| 我现在想…… | 直接看 |
| :--- | :--- |
| 装上试试 | [quick-start.md](quick-start.md) |
| 知道有哪些命令 | [README.md §12 个 Skill 速查](../README.md#-12-个-skill-速查) |
| 跑个单股分析 | `/stock sh600519 quick` → [user-guide.md](user-guide.md) |
| 看懂专家怎么打分 | [../experts/README.md](../experts/README.md) |
| 改个 fetcher | [developer-guide.md](developer-guide.md) + [api-reference.md](api-reference.md) |
| 加个新数据源 | [developer-guide.md §扩展数据源](developer-guide.md) |
| 写新策略 | [../scripts/strategies/registry.py](../scripts/strategies/registry.py) 注释 + [../methodology.md](../methodology.md) |
| 改专家人设 | [../experts/registry.py](../experts/registry.py) + 对应 expert yaml |
| 看最近改了什么 | [CHANGELOG.md](../CHANGELOG.md) |
| 找术语解释 | [../methodology.md §术语表](../methodology.md) |
| 检查文档质量 | [user_expert.md](user_expert.md) + [visual_expert.md](visual_expert.md) |
| 翻历史审查报告 | [archive/reviews/](archive/reviews/) |
| 翻历史设计稿 | [archive/designs/](archive/designs/) |

---

## 6. 文档维护责任

| 文档类型 | 主审 | 协审 | 频率 |
| :--- | :--- | :--- | :--- |
| 上手指南 | 用户专家 | 产品专家 | 季度 |
| 投资方法论 | 投资专家 | 产品专家 | 季度 |
| 开发者文档 | 二次开发者 | 视觉专家 | 月度 |
| API 参考 | 二次开发者 | — | 月度 |
| 审查报告（活跃） | 审查者 | 产品专家 | 每轮 |
| 历史归档（archive/） | — | — | 只读，git mv 不重写 |
| 规划文档 | 产品专家 | 投资专家 | 季度 |
| CHANGELOG | 贡献者 | — | 每次发版 |

> **本文档版本**：v1.20.2 / 2026-08-20 / 与 [README.md](../README.md) §"文档导航"段配合使用

---

## 7. 历史归档（archive/）

> 🟡 **原则**：归档文件**只读**，不重写、不翻译、不删 inbound 链接（CHANGELOG 等历史快照中的旧路径保持原状）。
> 历史归档本身在 git 历史中保留完整上下文；如需追溯历史责任，参考具体文件。

### 📐 designs/ — 历史设计稿（11 份）

| 文档 | 时期 | 说明 |
| :--- | :--- | :--- |
| [01_Screener_V2_Master_Plan.md](archive/designs/01_Screener_V2_Master_Plan.md) | 2026-06 | Screener V2 规划 |
| [02_Strategy_Engine_Design.md](archive/designs/02_Strategy_Engine_Design.md) | 2026-06 | 策略引擎设计 |
| [03_Market_Regime_Design.md](archive/designs/03_Market_Regime_Design.md) | 2026-06 | 市场状态机设计 |
| [SPRINT_SUMMARY.md](archive/designs/SPRINT_SUMMARY.md) | 2026-06 | Sprint 20-23 收尾总结 |
| [skill-consolidation-plan.md](archive/designs/skill-consolidation-plan.md) | 2026-06 | skill 13→9 整合决策 |
| [implementation-plan.md](archive/designs/implementation-plan.md) | 2026 | 旧实施计划（已被 Q3/Q4 取代） |
| [implementation-plan-2026-q3-q4.md](archive/designs/implementation-plan-2026-q3-q4.md) | 2026-Q3/Q4 | 三方审查整合实施计划（33/33 项已完成归档） |
| [next-tasks.md](archive/designs/next-tasks.md) | 2026-08 | 后续任务清单 |
| [methodology.md](archive/designs/methodology.md) | 2026-06 | **旧版投资方法论**（已被仓库根 [../methodology.md](../methodology.md) 取代） |
| [2026-06-05-improvement-roadmap.md](archive/designs/2026-06-05-improvement-roadmap.md) | 2026-06 | 早期改进路线图（多数项已完成） |
| [2026-06-16-skill-workflow-optimization.md](archive/designs/2026-06-16-skill-workflow-optimization.md) | 2026-06 | Skill 工作流优化施工方案（Phase 1-6 已实施） |

### 📊 reviews/ — 审查与回归报告（10 份）

| 文档 | 时期 | 说明 |
| :--- | :--- | :--- |
| [architecture-review-2026-07-07.md](archive/reviews/architecture-review-2026-07-07.md) | 2026-07 | 架构审查（最近期 90+ 技术债修复） |
| [full-module-review-2026-07-02.md](archive/reviews/full-module-review-2026-07-02.md) | 2026-07 | 全模块深度审查 |
| [deep-review-2026-07-15.md](archive/reviews/deep-review-2026-07-15.md) | 2026-07 | 深度审查 |
| [audit-2026-07-28.md](archive/reviews/audit-2026-07-28.md) | 2026-07-28 | 审计报告（19 项 + 11 维度附录） |
| [regression-2026-07-28.md](archive/reviews/regression-2026-07-28.md) | 2026-07-28 | 回归报告（1005/1005 测试） |
| [skill-smoke-2026-07-28.md](archive/reviews/skill-smoke-2026-07-28.md) | 2026-07-28 | skill 冒烟报告 |
| [screener-review.md](archive/reviews/screener-review.md) | 2026 | 选股模块审查 |
| [2026-08-12-replay-meta-review.md](archive/reviews/2026-08-12-replay-meta-review.md) | 2026-08-12 | 运行期元复盘（11 项 P0-P2） |
| [review-issues.md](archive/reviews/review-issues.md) | 2026-Q3 | **75 项深度审阅问题清单（P0×15 + P1×30 + P2×30，Round 11 收官归档）** |
| [review-verification.md](archive/reviews/review-verification.md) | 2026-Q3 | **逐条源码验证报告（116 项中 100 真实 + 12 部分真实 + 4 不真实/已修复）** |

### 📈 reports/ — 阶段性报告（2 份）

| 文档 | 时期 | 说明 |
| :--- | :--- | :--- |
| [optimization-report.md](archive/reports/optimization-report.md) | 2026 | v1.3.1 性能优化实施报告 |
| [improvement-roadmap.md](archive/reports/improvement-roadmap.md) | 2026 | 改进路线图 |

### 🚀 releases/ — 发版归档（3 份）

| 文档 | 时期 | 说明 |
| :--- | :--- | :--- |
| [README.md](archive/releases/README.md) | — | 发版归档目录说明 |
| [v1.3.2.md](archive/releases/v1.3.2.md) | 2026 | v1.3.2 发版说明 |
| [v1.15.0.md](archive/releases/v1.15.0.md) | 2026 | v1.15.0 发版说明 |

> 其他版本已合并到 [CHANGELOG.md](../CHANGELOG.md)。
# 文档索引（docs/）

> 🟢 **一句话**：docs/ 目录下 30+ 份文档，按"你是谁 / 你想干啥"两条线分类。  
> 🟡 **只想看一份**？  
> 🆕 新用户 → [quick-start.md](quick-start.md) · 📈 投资者 → [product-architecture.md](product-architecture.md) · 🛠️ 开发者 → [developer-guide.md](developer-guide.md) · 🤝 贡献者 → [CONTRIBUTING.md](../CONTRIBUTING.md)  
> ⚫ **文档数**：26 份核心指南 + 5 份审查报告 + 9 份规划与历史 + 1 份发版归档 = 41 份

> 适用文档：stock-analyzer-skill v1.15.0
> 索引目的：解决 docs/ 目录下"找不到入口"问题

---

## 📑 目录

1. [按角色索引](#1-按角色索引)
2. [按阶段索引](#2-按阶段索引)
3. [角色 × 阶段交叉矩阵](#3-角色--阶段交叉矩阵)
4. [文档分类清单（按文件类型）](#4-文档分类清单按文件类型)
5. [入口跳转（按意图）](#5-入口跳转按意图)
6. [文档维护责任](#6-文档维护责任)

> 语义说明：🟢 健康 / 🟡 中性 / ⚫ 数据事实。角色 emoji：🆕 新用户 / 📈 投资者 / 🛠️ 开发者 / 🤝 贡献者 / 📐 审查者。

---

## 1. 按角色索引

### 🆕 新用户（首次接触）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 上手 | [quick-start.md](quick-start.md) | 5 分钟安装 + 第一个 `/stock` 命令 |
| 上手 | [user-guide.md](user-guide.md) | 使用者指南：13 个 skill 完整流程 |
| 上手 | [tutorials/walkthrough-600519.md](tutorials/walkthrough-600519.md) | 贵州茅台完整演练（12 skill 串联） |
| 入门 | [methodology.md](../methodology.md) | 投资方法论（PE/ROE/PEG 等术语翻译） |
| 入门 | [learn SKILL.md](../skills/learn/SKILL.md) | `/learn <概念>` 学习助手 |

### 📈 投资者（已上手）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 决策 | [product-architecture.md](product-architecture.md) | 产品架构：五层分析 / 16 份专家人设 / 数据源 |
| 决策 | [methodology.md](../methodology.md) | 投资方法论 + 评分公式 |
| 决策 | [experts/README.md](../experts/README.md) | 16 份专家档案库（8 active + 8 legacy） |
| 决策 | [persona.md](persona.md) | 3 类用户画像 + 设计启示 |
| 风控 | [user_expert.md](user_expert.md) · [visual_expert.md](visual_expert.md) | 用户面 / 视觉审查视角 |

### 🛠️ 二次开发者（要写代码）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 入门 | [developer-guide.md](developer-guide.md) | 项目结构 + BaseFetcher / CircuitBreaker |
| 入门 | [api-reference.md](api-reference.md) | fetcher 接口 + 数据类型 + 返回格式 |
| 入门 | [product-architecture.md](product-architecture.md) | 三层架构 + 数据源矩阵 + 行业阈值 |
| 进阶 | [optimization-report.md](optimization-report.md) | 性能优化实施报告 |
| 进阶 | [architecture-review-2026-07-07.md](architecture-review-2026-07-07.md) | 架构审查（最近期 90+ 技术债修复） |
| 进阶 | [full-module-review-2026-07-02.md](full-module-review-2026-07-02.md) | 全模块深度审查报告 |

### 🤝 贡献者（要发 PR）

| 阶段 | 文档 | 说明 |
| :--- | :--- | :--- |
| 入门 | [CONTRIBUTING.md](../CONTRIBUTING.md) | 提交规范 + Commit 格式 |
| 入门 | [CHANGELOG.md](../CHANGELOG.md) | 变更日志（Keep a Changelog 格式） |
| 流程 | [skill-consolidation-plan.md](skill-consolidation-plan.md) | skill 整合决策记录 |
| 流程 | [review-issues.md](review-issues.md) · [review-verification.md](review-verification.md) | 审查问题清单 + 验证记录 |
| 流程 | [implementation-plan.md](implementation-plan.md) · [implementation-plan-2026-q3-q4.md](implementation-plan-2026-q3-q4.md) | 实施计划 + Q3/Q4 路线图 |

### 📐 审查视角（要做评审）

| 角色 | 文档 | 说明 |
| :--- | :--- | :--- |
| 用户专家 | [user_expert.md](user_expert.md) | 12 项硬指标 + 三明治错误信息 |
| 视觉专家 | [visual_expert.md](visual_expert.md) | 14 项硬指标 + 视觉三级层 |
| 产品专家 | [persona.md](persona.md) | 3 类画像 + 设计启示 |
| 投资专家 | [methodology.md](../methodology.md) · [experts/README.md](../experts/README.md) | 投资逻辑 + 16 份专家人设 |

---

## 2. 按阶段索引

### 🚀 阶段 1：上手（30 秒 → 5 分钟）

- [quick-start.md](quick-start.md) — 5 分钟快速入门
- [README.md §30 秒上手](../README.md#-30-秒上手) — 3 条命令跑通
- [tutorials/walkthrough-600519.md](tutorials/walkthrough-600519.md) — 完整演练教程

### 📖 阶段 2：精通（1 天 → 1 周）

- [user-guide.md](user-guide.md) — 13 skill 完整流程
- [methodology.md](../methodology.md) — 投资方法论
- [product-architecture.md](product-architecture.md) — 产品架构
- [experts/README.md](../experts/README.md) — 16 份专家人设

### 🔧 阶段 3：扩展（1 周 → 1 月）

- [developer-guide.md](developer-guide.md) — 开发者指南
- [api-reference.md](api-reference.md) — API 参考
- [optimization-report.md](optimization-report.md) — 性能优化报告
- [architecture-review-2026-07-07.md](architecture-review-2026-07-07.md) — 最近期架构审查

### 🏛 阶段 4：维护（持续）

- [CHANGELOG.md](../CHANGELOG.md) — 变更日志
- [review-issues.md](review-issues.md) — 审查问题清单
- [implementation-plan-2026-q3-q4.md](implementation-plan-2026-q3-q4.md) — 实施计划
- [improvement-roadmap.md](improvement-roadmap.md) — 改进路线图

---

## 3. 角色 × 阶段交叉矩阵

| | 上手（5 min） | 精通（1 天） | 扩展（1 周） | 维护（持续） |
| :--- | :---: | :---: | :---: | :---: |
| 🆕 **新用户**     | [quick-start](quick-start.md) | [user-guide](user-guide.md) | — | — |
| 📈 **投资者**     | [quick-start](quick-start.md) | [methodology](../methodology.md) · [product-architecture](product-architecture.md) | — | [CHANGELOG](../CHANGELOG.md) |
| 🛠️ **二次开发者** | [quick-start](quick-start.md) | [developer-guide](developer-guide.md) | [api-reference](api-reference.md) · [architecture-review](architecture-review-2026-07-07.md) | [CHANGELOG](../CHANGELOG.md) |
| 🤝 **贡献者**     | [CONTRIBUTING](../CONTRIBUTING.md) | [review-issues](review-issues.md) | [implementation-plan](implementation-plan.md) | [CHANGELOG](../CHANGELOG.md) · [improvement-roadmap](improvement-roadmap.md) |
| 📐 **审查者**     | [persona](persona.md) | [user_expert](user_expert.md) · [visual_expert](visual_expert.md) | [full-module-review](full-module-review-2026-07-02.md) | [review-verification](review-verification.md) |

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
| [methodology.md](../methodology.md) | 决策 | 季度 |
| [persona.md](persona.md) | 审查 | 季度 |
| [user_expert.md](user_expert.md) | 审查 | 季度 |
| [visual_expert.md](visual_expert.md) | 审查 | 季度 |

### 📊 审查报告（阶段性归档）

| 文档 | 时期 | 性质 |
| :--- | :--- | :--- |
| [architecture-review-2026-07-07.md](architecture-review-2026-07-07.md) | 2026-07 | 架构审查（最近期） |
| [full-module-review-2026-07-02.md](full-module-review-2026-07-02.md) | 2026-07 | 全模块深度审查 |
| [review-issues.md](review-issues.md) | 持续 | 审查问题清单 |
| [review-verification.md](review-verification.md) | 持续 | 审查验证记录 |
| [screener-review.md](screener-review.md) | 历史 | 选股模块审查 |

### 📋 规划与历史

| 文档 | 角色定位 | 备注 |
| :--- | :--- | :--- |
| [implementation-plan.md](implementation-plan.md) | 实施计划 | 历史归档 |
| [implementation-plan-2026-q3-q4.md](implementation-plan-2026-q3-q4.md) | 实施计划 | 当前 |
| [improvement-roadmap.md](improvement-roadmap.md) | 改进路线图 | 持续 |
| [skill-consolidation-plan.md](skill-consolidation-plan.md) | skill 整合 | 历史 |
| [SPRINT_SUMMARY.md](SPRINT_SUMMARY.md) | Sprint 总结 | 历史 |
| [optimization-report.md](optimization-report.md) | 性能优化 | 阶段 |
| [01_Screener_V2_Master_Plan.md](01_Screener_V2_Master_Plan.md) | V2 规划 | 历史 |
| [02_Strategy_Engine_Design.md](02_Strategy_Engine_Design.md) | 引擎设计 | 历史 |
| [03_Market_Regime_Design.md](03_Market_Regime_Design.md) | 状态机设计 | 历史 |

### 📦 发版归档

- [releases/v1.3.2.md](releases/v1.3.2.md) — v1.3.2 发版说明（其他版本已合并到 [CHANGELOG.md](../CHANGELOG.md)）

### 🖼 资源

- [assets/](assets/) — README 引用的 GIF 演示素材
- [tutorials/walkthrough-600519.md](tutorials/walkthrough-600519.md) — 贵州茅台完整演练
- [src/](src/) — mdBook 文档站源码（自动部署到 GitHub Pages）
- [book.toml](book.toml) — mdBook 配置
- [superpowers/](superpowers/) — 内部工具集合

---

## 5. 入口跳转（按意图）

| 我现在想…… | 直接看 |
| :--- | :--- |
| 装上试试 | [quick-start.md](quick-start.md) |
| 知道有哪些命令 | [README.md §13 个 Skill 速查](../README.md#-13-个-skill-速查) |
| 跑个单股分析 | `/stock sh600519 quick` → [user-guide.md](user-guide.md) |
| 看懂专家怎么打分 | [experts/README.md](../experts/README.md) |
| 改个 fetcher | [developer-guide.md](developer-guide.md) + [api-reference.md](api-reference.md) |
| 加个新数据源 | [developer-guide.md §扩展数据源](developer-guide.md) |
| 写新策略 | [scripts/strategies/registry.py](../scripts/strategies/registry.py) 注释 + [methodology.md](../methodology.md) |
| 改专家人设 | [experts/registry.py](../experts/registry.py) + 对应 expert yaml |
| 看最近改了什么 | [CHANGELOG.md](../CHANGELOG.md) |
| 找术语解释 | [methodology.md §术语表](../methodology.md) |
| 检查文档质量 | [user_expert.md](user_expert.md) + [visual_expert.md](visual_expert.md) |

---

## 6. 文档维护责任

| 文档类型 | 主审 | 协审 | 频率 |
| :--- | :--- | :--- | :--- |
| 上手指南 | 用户专家 | 产品专家 | 季度 |
| 投资方法论 | 投资专家 | 产品专家 | 季度 |
| 开发者文档 | 二次开发者 | 视觉专家 | 月度 |
| API 参考 | 二次开发者 | — | 月度 |
| 审查报告 | 审查者 | 产品专家 | 每轮 |
| 规划文档 | 产品专家 | 投资专家 | 季度 |
| CHANGELOG | 贡献者 | — | 每次发版 |

> **本文档版本**：v1.15.0 / 2026-07-09 / 与 [README.md](../README.md) §"文档导航"段配合使用
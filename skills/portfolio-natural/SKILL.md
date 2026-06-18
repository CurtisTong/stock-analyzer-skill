---
name: portfolio-natural
description: 持仓自然语言触发词典。触发词：我的持仓怎么样、帮我看看持仓、我买了XX、加仓XX、减仓XX、清仓XX、持仓健康检查、帮我调仓、卖了一半、止盈了、破位止损、再加一手。从 portfolio 拆分：仅覆盖自然语言 → 命令的映射规则。短描述适合 haiku。
version: 1.13.0
model: sonnet
allowed-tools: Bash(python3 scripts/quote.py *) Bash(python3 scripts/portfolio_web.py *) Read(./scripts/data/portfolio.json) Read(./skills/_shared/references/*.md)
---

# Portfolio Natural Language

持仓操作的自然语言触发词典。本文档从 `/portfolio` 拆分，专注于 NL → 命令映射。

## 口语化触发 → 操作映射

| 自然语言 | 等价命令 |
|---|---|
| "我的持仓怎么样" / "看看持仓" | `/portfolio health` |
| "持仓健康检查" | `/portfolio health` |
| "帮我看看持仓" | `/portfolio health` |
| "我买了 XX" | `/portfolio add <code> <qty> <cost>` |
| "加仓 XX" | `/portfolio add <code> <qty> <cost>` |
| "再加一手 XX" | `/portfolio add <code> 100 <cost>` |
| "减仓 XX" / "卖了一半" | `/portfolio reduce <code> <qty>` |
| "止盈了 XX" | `/portfolio reduce <code> <qty>` |
| "清仓 XX" | `/portfolio remove <code>` |
| "破位止损 XX" | `/portfolio remove <code>` |
| "帮我调仓" / "再平衡" | `/portfolio rebalance` |
| "持仓对比" | `/portfolio compare` |

完整 CRUD 命令见 [`/portfolio`](../portfolio/SKILL.md)。

## Instructions

使用中文输出。当用户用自然语言描述持仓操作时，本 skill 负责把口语化表达解析为标准命令，
然后调用 [`/portfolio`](../portfolio/SKILL.md) 执行。

歧义消解规则：

- "我买了 XX" 需追问：数量、成本价（除非用户提供）
- "减仓 XX" 默认减 50%（除非指定数量）
- "清仓 XX" 必须二次确认（避免误操作）

## Guardrails

- 自然语言解析必须保留 2 步确认：先展示映射结果，等用户确认再执行
- 模糊表达（如"调一下仓"）必须追问，禁止直接执行
- 触发"破位止损""清仓"等高风险关键词时，先用 `/portfolio health` 给出当前状态

---
name: financial-analyst
description: 财务分析 agent 已合并至 /research financial 子命令。原功能：专注财务建模（DCF/杜邦分解）、盈利质量排雷与异常检测、增长可持续性判断和多情景敏感性分析。当 /stock 五层框架中的基本面分歧需要更深入的纵深财务证据链条来进行支撑时使用。
version: 1.10.0
model: opus
---

# 已合并

本 skill 已合并至 `/research`。请使用：

```text
/research financial <任务描述>       # 财务建模：排雷/杜邦/DCF/敏感性
```

典型任务："排雷 sh600989"、"DCF 估值 sz300750"、"分析恒瑞医药的盈利质量"。

## Instructions

当用户输入 `/financial-analyst` 时，重定向至 `/research financial` 子命令执行。

## Guardrails

本 skill 已合并，所有分析逻辑和防护规则已迁移至 `/research` SKILL.md。

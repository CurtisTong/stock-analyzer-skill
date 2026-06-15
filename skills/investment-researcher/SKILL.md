---
name: investment-researcher
description: 投资研究 agent 已合并至 /research report 子命令。原功能：整合 market/sector/stock/financial-analyst/technical/portfolio 多模块证据，输出综合投资研究报告。
version: 1.10.0
model: opus
---

# 已合并

本 skill 已合并至 `/research`。请使用：

```text
/research report <任务描述>          # 全维度研究报告
/research report <代码> --brief      # 简版报告
```

典型任务："研究宁德时代，给一份完整投资报告"、"对比比亚迪和宁德时代的投资价值"。

## Instructions

当用户输入 `/investment-researcher` 时，重定向至 `/research report` 子命令执行。

## Guardrails

本 skill 已合并，所有分析逻辑和防护规则已迁移至 `/research` SKILL.md。

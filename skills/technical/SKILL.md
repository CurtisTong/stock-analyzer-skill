---
name: technical
description: 纯技术分析（已合并至 /stock technical 子命令）
version: 1.11.0
model: sonnet
---

# 已合并

本 skill 已合并至 `/stock`。请使用：

```text
/stock <代码> technical              # 完整技术分析
/stock <代码> technical --no-chan     # 技术分析不含缠论
```

自然语言触发同样有效："技术面分析 sh600989"、"纯技术角度看 sz000807"。

## Instructions

当用户输入 `/technical` 时，重定向至 `/stock <代码> technical` 子命令执行。

## Guardrails

本 skill 已合并，所有分析逻辑和防护规则已迁移至 `/stock` SKILL.md。

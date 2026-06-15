---
name: stock-init
description: 初始化股票池（已合并至 /screener init 子命令）
version: 1.10.0
model: haiku
disable-model-invocation: true
---

# 已合并

本 skill 已合并至 `/screener`。请使用：

```text
/screener init              # 初始化/刷新股票池
/screener init force        # 强制重新初始化
/screener init default      # 使用预置默认数据（离线可用）
/screener init full-market  # 初始化全市场股票池（约 5000 只）
```

## Instructions

当用户输入 `/stock-init` 时，重定向至 `/screener init` 子命令执行。

## Guardrails

本 skill 已合并，所有初始化逻辑和防护规则已迁移至 `/screener` SKILL.md。

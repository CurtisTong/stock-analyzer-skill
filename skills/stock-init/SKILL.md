---
name: stock-init
description: 初始化或刷新股票池。为每个板块拉取前 N 只活跃股票（默认 20），供 screener/sector/stock 后续分析使用。零配置可用（内置预置数据），API 失败自动 fallback。
version: 1.8.0
model: haiku
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/init_pool.py *) Bash(python3 scripts/refresh_pool.py *)
---

# 初始化股票池

为 A 股各板块初始化前 20 只活跃股票，供选股、板块分析等 skill 使用。

> **旧别名**：`/init-pool` 已并入本 skill。详见 [`~/.claude/skills/init-pool/SKILL.md`](file:///Users/curtis/.claude/skills/init-pool/SKILL.md)。

## Usage

```text
/stock-init              # 检测并初始化（已有数据则跳过）
/stock-init force        # 强制重新初始化
/stock-init top 30       # 每板块取 Top 30
/stock-init default      # 使用预置默认数据（离线可用，不访问 API）
/stock-init full-market  # 初始化全市场股票池（约 5000 只）
```

## Instructions

当用户触发此 skill 时，执行以下步骤：

输出遵循统一模板：首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `../_shared/references/output-template.md`。

1. **运行初始化脚本**：

   ```bash
   python3 scripts/init_pool.py
   ```

2. **如果用户指定 `force`**，加 `--force` 参数：

   ```bash
   python3 scripts/init_pool.py --force
   ```

3. **如果用户指定 `top N`**，加 `--top N` 参数：

   ```bash
   python3 scripts/init_pool.py --top 30
   ```

4. **如果用户指定 `default`**，加 `--default` 参数（离线模式，不访问 API）：

   ```bash
   python3 scripts/init_pool.py --default
   ```

5. **如果用户指定 `full-market`**，加 `--full-market` 参数（初始化全市场 A 股池）：

   ```bash
   python3 scripts/init_pool.py --full-market
   ```

6. **输出结果**：展示初始化摘要，包括每板块股票数量和总计。

## 前置条件

- **无需配置即可使用**：脚本内置预置默认股票池数据，首次运行自动初始化
- 可选设置 `EASTMONEY_API_TOKEN` 环境变量（东财 push2 API 的 ut 参数）以获取最新数据
- 如未设置 token，脚本会尝试免费访问 API，失败时自动使用预置数据

## 输出格式

初始化成功后，展示类似：

```
✅ 初始化完成: 14 个板块，共 280 只股票

各板块分布:
  金融: 20 只
  消费: 20 只
  医药: 20 只
  ...
```

## Notes

- 已有数据时默认跳过，避免重复拉取
- 使用 `force` 参数可强制刷新
- 数据来源: 东方财富 push2 API（优先） → 预置默认数据（fallback）
- 使用 `--default` 参数可跳过 API 直接使用预置数据（离线可用）
- 过滤规则: 排除 ST 股、低成交额、低市值标的

### 全市场股票池初始化

运行以下命令初始化全市场 A 股池：

```bash
python3 scripts/init_pool.py --full-market
```

这会创建 `scripts/data/all_stocks.json`，包含全部 A 股（约 5000 只），按上市板块分组（主板沪/主板深/创业板/科创板/北交所）。与主题板块池（`sector_stocks.json`，约 140 只）互补使用：主题池用于板块分析，全市场池用于全量选股。

### 过滤阈值

过滤规则与 `/screener` 硬过滤一致（见 `screener/SKILL.md` Step 1 的硬过滤描述），按上市板块差异化执行：

| 板块   | 最低成交额（万元） | 最低市值（亿元） |
| ------ | ------------------ | ---------------- |
| 主板   | 5,000              | 40               |
| 创业板 | 3,500              | 24               |
| 科创板 | 3,500              | 24               |
| 北交所 | 7,500              | 16               |

> ⚠️ 此表与 screener 共享。修改阈值时需同步更新 `screener/SKILL.md` 和 `scripts/strategies/thresholds.py`。

## Guardrails

- 已有数据时默认跳过；用 `force` 参数才会覆盖
- API 失败自动回退到预置数据；不静默丢失，写入 `data/stock_pool.json`
- `default` 参数走完全离线分支，跳过所有网络请求
- 不修改持仓数据（`portfolio.json`），不推送任何通知
- 过滤阈值与 `/screener` 硬过滤保持一致（上表为当前值）

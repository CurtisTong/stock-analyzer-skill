---
name: init
description: 初始化或刷新股票池，为每个板块拉取前 20 只股票。当用户输入 /init、/setup、"初始化股票池"、"刷新股票池"时触发。
---

# 初始化股票池

为 A 股各板块初始化前 20 只活跃股票，供选股、板块分析等 skill 使用。

## Usage

```text
/init              # 检测并初始化（已有数据则跳过）
/init force        # 强制重新初始化
/init top 30       # 每板块取 Top 30
```

## Instructions

当用户触发此 skill 时，执行以下步骤：

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

4. **输出结果**：展示初始化摘要，包括每板块股票数量和总计。

## 前置条件

- 需要设置 `EASTMONEY_API_TOKEN` 环境变量（东财 push2 API 的 ut 参数）
- 如未设置，脚本会提示获取方式

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
- 数据来源: 东方财富 push2 API
- 过滤规则: 排除 ST 股、低成交额、低市值标的

---
name: help
description: 显示所有可用的股票分析 skills 和使用说明。当用户问"有哪些功能"、"怎么用"、列出 skill 列表或查询工作流建议时触发。
version: 1.4.1
model: haiku
disable-model-invocation: true
---

# Stock Analyzer Skills 帮助

显示所有可用的 A 股分析 skills 和使用说明。

## Usage

```text
/help
/stocks
/skills
```

## 第一次使用

首次使用请按以下步骤：

1. `/stock-init` — 初始化股票池（零配置可用，无需 token）
2. 如需全量选股，运行 `/stock-init full-market` 初始化全市场 A 股池（约 5000 只）
3. 如需持仓分析，编辑 `scripts/data/portfolio.json` 添加持仓（可选）
4. `/market quick` — 快速了解今日市场状态

完成后即可使用各分析功能。

### 股票池模式

| 模式         | 数据量   | 初始化命令                | 适用场景             |
| ------------ | -------- | ------------------------- | -------------------- |
| 主题板块池   | ~140 只  | `/stock-init`（默认）     | 板块分析、快速选股   |
| 全市场股票池 | ~5000 只 | `/stock-init full-market` | 全量选股、多因子筛选 |

## 共享约定

- 12 个 skill 完整命令清单：`./references/skill-catalog.md`（按需加载）

## 工作流建议

### 快速选股流程

1. `/market quick` - 了解市场状态
2. `/screener` - 筛选候选股
3. `/stock <候选股> quick` - 快速分析
4. `/technical <候选股>` - 确认买点

### 完整分析流程

1. `/market` - 大盘复盘
2. `/sector <强势板块>` - 板块分析
3. `/screener --sector <板块>` - 板块内选股
4. `/stock <候选股> full` - 五层分析
5. `/technical <候选股>` - 技术确认
6. `/portfolio` - 持仓调整

### 持仓检查流程

1. `/portfolio health` - 检查持仓健康
2. `/market` - 确认市场风格
3. `/technical <弱势持仓>` - 检查是否破位
4. `/screener` - 找替代候选
5. `/portfolio rebalance` - 调仓建议

## 数据来源

- **实时行情**：腾讯财经 `qt.gtimg.cn`
- **财务数据**：东方财富 `emweb.securities.eastmoney.com`
- **K 线数据**：新浪财经 `money.finance.sina.com.cn`
- **公告/研报**：东方财富 `np-anotice-stock.eastmoney.com`

所有数据 API 在国内直连，无须代理。

## Guardrails

- 所有分析仅供参考，不构成投资建议
- 涉及实时行情时，脚本会自动获取最新数据
- 如果脚本不可用，会参考 `methodology.md` 中的方法论
- 数据失败时会说明失败的数据源和影响

## 获取更多帮助

- 12 个 skill 命令清单：`./references/skill-catalog.md`
- 查看 `workflow.md` 了解 9 个 skill 的协作流程
- 查看 `methodology.md` 了解完整投资方法论
- 查看 `README.md` 了解项目结构和安装说明

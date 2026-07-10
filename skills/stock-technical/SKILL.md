---
name: stock-technical
description: 纯技术分析子模块（从 /stock 拆分）。触发词：技术面分析 XX、纯技术角度看 XX、K 线分析 XX、缠论分析 XX、战法识别 XX。支持均线/MACD/KDJ/BOLL/RSI/缠论/本土战法。
version: 2.8.0
model: glm-5.2
allowed-tools: Bash(python3 scripts/technical.py *) Bash(python3 scripts/kline.py *) Read(./skills/_shared/references/*.md)
---

# Stock Technical Analysis

纯技术分析子模块。本文档从 `/stock` 拆分（Step 5），仅覆盖技术面。

## Usage

```text
/stock-technical <代码>                  # 完整技术分析（含缠论）
/stock-technical <代码> --no-chan         # 不含缠论
/stock-technical <代码> --classify        # 含类型分类（成长/周期/防御/题材）
/stock-technical <代码> --quick           # 快速模式（仅核心指标）
```

## 输出维度

- **均线系统**：MA5/MA10/MA20/MA60 多头/空头排列
- **MACD**：金叉/死叉/柱状图方向
- **KDJ**：超买/超卖/钝化
- **BOLL**：上中下轨 + 开口/收口
- **RSI**：6/12/24 三周期
- **量能**：量比、换手率、量价配合
- **缠论**：分型/笔/段/中枢（需 `--chan` 启用）。⚠️ 非标准简化实现，买卖点信号可能与标准缠论软件有差异，仅供学习参考
- **本土战法**：6 种 A 股经典形态（v2 优化：三阴一阳增加量化评分）
  - 三阴一阳/三阳一阴：量比、跌幅、反弹比例三维评分
  - 老鸭头、美人肩、双针探底、涨停双响炮、底部首板
- **组合策略**：MA10/MA21 金叉 + 放量 2.5x 突破（71.4% 胜率，+6.39% 平均收益）

## 共享约定

- 代码前缀：`../_shared/references/code-prefix.md`
- 脚本目录：`../_shared/references/script-catalog.md`

详细调用见 [`/stock`](../stock/SKILL.md) 主文档。

## Instructions

使用中文输出。技术分析必须基于最新 K 线数据（`scripts/kline.py`），不要凭历史记忆判断。

输出遵循统一模板：首行技术面定调（看多/看空/震荡），尾行数据时间戳 + 数据源。
详见 `../_shared/references/output-template.md`。

子模块细分：

- `--quick` 模式只输出均线+MACD+RSI 三个核心指标
- `--classify` 模式额外输出股票类型（成长/周期/防御/题材）
- 默认含缠论（`--no-chan` 关闭）

## Guardrails

- 技术分析不输出买入/卖出信号（信号层在 `/stock` 主流程）
- 不替代 `/stock full` 的基本面判断
- 仅基于技术面给出的操作建议须标注"仅供参考"
- 数据 stale 时（>3 个交易日）必须警告用户

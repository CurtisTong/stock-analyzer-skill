"""因子分析模块（v3.0: IC 动态权重）。

与 `factors/`（复数）的区别：
- `factors/` 包含 14 个**评分实现**（quality/valuation/momentum/...），
  对应单只股票的维度打分。
- `factor/`（本目录）仅含 IC（Information Coefficient）动态权重分析工具，
  用于跨时间/跨 regime 统计因子预测能力，反向调整 overlay multiplier。

不要把新的评分维度放进本目录；新维度一律放 `factors/`。
"""

# 日内T策略过滤器

> 供 `/stock` 按需加载：当用户询问日内T、T+0、做T等短线操作时启用。
> 数据来源分两步（A 股 T+1，做T = 底仓做T）：
> 1. **个股技术面**：`python3 scripts/technical.py <code> --json`，读 `features.*` 与 `score.structured_signals.*`
> 2. **市场情绪**：`python3 scripts/market_breadth.py --json`，读 `limit_up_count` / `limit_down_count` / `continuous_limit_height`（technical.py **不含**这些字段，必须单独调用）
>
> 最短判断捷径：`score.structured_signals.is_downtrend == true` 已把下方"放量下跌 / 下跌浪 / 空头排列"三条件合并计算（下跌趋势不做T），无需自行拼三条。

**核心原则：下跌趋势不做T，超卖信号需二次确认**

## 禁止做T条件（任一满足则不推荐T）

| 条件     | 判断方法                                                     | 原因                          |
| -------- | ------------------------------------------------------------ | ----------------------------- |
| 放量下跌 | `score.structured_signals.volume_outflow == true`（等价：`features.volume.volume_price_signal == -1` 且 `features.volume.volume_price` 含"放量下跌(主力出货)"） | 主力出货，超卖是假信号  |
| 下跌浪   | `features.wave` 含"下跌"（如 `下跌浪(高点降低+低点降低)`）    | 趋势向下，反弹空间有限        |
| 空头排列 | `features.ma_system.alignment == "空头排列"`                  | 均线压制，做T容易被套         |
| KDJ钝化  | `features.kdj.钝化 == true`                                   | 趋势延续，超卖更超卖           |
| 市场退潮 | `limit_up_count < 20`                                         | 涨停家数<20家，赚钱效应弱      |
| 市场冰点 | `limit_down_count > 50`                                       | 跌停>50家，市场极度恐慌        |

> 前三行任一命中 ⇒ `score.structured_signals.is_downtrend == true`。结构化布尔字段为权威来源，字符串子串判断仅作核对。

## 谨慎做T条件（需额外确认）

| 条件          | 确认方式                                                    | 说明                     |
| ------------- | ----------------------------------------------------------- | ------------------------ |
| 超卖+放量下跌 | 等待放量阳线止跌                                            | 超卖信号在下跌趋势中失效 |
| 箱体底部      | 确认支撑有效再入场                                          | 可能破位下跌             |
| MACD底背离    | `features.macd.divergence` 含"底背离(看涨)"，且需二次背离确认 | 单次背离可能失败         |
| 接力生态恶化  | `continuous_limit_height < 2`                               | 短线情绪低迷             |

## 推荐做T条件（需全部满足）

1. **趋势中性或偏多**：`features.wave` 为"盘整"、"上升浪"**或"可能有底部结构(低点抬高)"**（低吸形态）
2. **量价配合**：`score.structured_signals.volume_outflow == false`（非放量下跌）
3. **支撑明确**：有清晰的支撑位（`features.support_resistance.nearest_support` / `features.ma_system.ma_supports` / 整数关口）
4. **波动空间充足**：`features.bollinger.bandwidth >= 0.05`（≈5%；`< 0.05` 为"极度收窄"，日内空间不足。注：technical 输出无"近20日均振幅"直接字段，以 BOLL 带宽近似）
5. **非钝化状态**：`features.kdj.钝化 == false`
6. **缩量确认**：`features.volume.shrink_signal == 1`（连续缩量 **≥3 日**即触发，抛压减轻）
7. **市场情绪健康**：`limit_up_count > 20` 且 `continuous_limit_height > 2`

## 日内确认（推荐做T时）

日线只定方向，分时定时机：再跑 `python3 scripts/technical.py <code> --scale 60 --json`，在 60min 级别找超卖（`features.kdj.钝化 == false` 且含"超卖"）或贴近日线支撑位时分批低吸；日内买点不依赖日线单一价位。

## 输出模板（推荐做T时）

```
## 日内T操作建议

**T策略评级**: ⭐⭐⭐⭐ (1-5星)

**前提条件**:
- ✅ 趋势中性/偏多
- ✅ 量价配合
- ✅ 支撑明确

**操作区间**（日线方向 + 60min 确认位）:
- 买入区间: XX.XX - XX.XX
- 止盈目标: XX.XX - XX.XX
- 止损位: XX.XX (跌破即止损)

**风险提示**:
- 当前市场环境: [牛市/震荡/熊市]
- 最大回撤风险: X%
- 建议仓位: X成（底仓做T不加仓）

⚠️ 以上为技术面参考，不构成投资建议。
```

## 输出模板（禁止做T时）

```
## ⚠️ 当前不建议做日内T

**禁止原因**:
- [ ] 放量下跌(主力流出)
- [ ] 下跌趋势
- [ ] 空头排列
- [ ] KDJ钝化
- [ ] 市场退潮(涨停<20家)
- [ ] 市场冰点(跌停>50家)

**建议**:
1. 等待止跌信号（放量阳线）
2. 等待趋势反转（均线金叉）
3. 观望为主，不参与下跌趋势

**替代方案**:
- 如果已持仓：等待反弹减仓
- 如果空仓：等待右侧机会
```
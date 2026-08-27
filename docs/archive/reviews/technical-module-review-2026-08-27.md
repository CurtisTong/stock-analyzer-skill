# 技术分析模块审查报告（2026-08-27）

> **审查时间**：2026-08-27
> **审查对象**：`skills/stock-technical/SKILL.md` + `scripts/technical.py` + `scripts/technical/`（19 文件）+ `scripts/strategies/patterns/`（本土战法 7 检测器）+ 4 个测试文件（195 例）
> **方法**：全文件通读 + 合成数据实测验证（突破检测全周期、RSI 输出字段、评分基线、信号冲突、市场环境标签）+ 测试覆盖审计
> **流程**：grill-me 三阶段（Discovery → Attack → Synthesis），立场默认怀疑
> **相关文档**：[strategy-validation.md](../../strategy-validation.md)、[stock/SKILL.md](../../../skills/stock/SKILL.md)

---

## 一、一句话结论

> 🚨 **技术指标计算层扎实（公式、边界、历史修复经得起推敲），但文档契约层与集成层存在 3 处 P0 硬冲突和 3 处信号失效**：SKILL.md 声称"默认含缠论"但代码只在 `--classify` 时运行；声称"RSI 6/12/24 三周期"但实现只有 RSI(14)；突破检测在真实调用链下是死代码（"突破确认"状态永远无法输出）；KDJ 钝化降权三处声明一处未落地。195 例单测全绿但主要锁的是函数行为、没锁集成调用链——**测试通过 ≠ 声明成立**。

---

## 二、保留项（经 Attack 仍成立）

- **指标核心公式正确**：MACD（EMA12/26/DEA9 + ε 防浮点噪声）、KDJ（含 20cm/30cm 板块差异化阈值）、BOLL（总体标准差，通达信口径）、RSI（Wilder 平滑）、ATR（TR 三要素）均实现正确，`scripts/technical/core.py:16` 的 ε 机制经得起推敲。
- **H2/M1/M2/M4/M5 历史修复有效**：全中性股票评分 42.6 → "中性"（修复前 35.9 偏空）；缩量窗口 off-by-one 已修（`volume.py:159`）；空行情不再误判冰点；下跌趋势中 KDJ 超卖金叉正确降级为"待确认"（实测验证）。
- **组合策略披露诚实**：MA10/MA21 + 2.5x 突破的 71.4% 胜率标注为"5 只股票样本内拟合、oos_validated: false"，`scripts/strategies/patterns/ma_volume_strategy.py:226` disclosure 完整。
- **缠论免责声明到位**：SKILL.md:30 明示"非标准简化实现，仅供学习参考"。

---

## 三、风险项

### P0（声明与现实硬冲突）

**P0-1 缠论默认启用声明与代码硬冲突**
- 声明：`skills/stock-technical/SKILL.md:16`（"/stock-technical <代码> 完整技术分析（含缠论）"）、`:55`（"默认含缠论（--no-chan 关闭）"）、`:30`（"需 `--chan` 启用"）
- 证据：`scripts/technical.py:168` `do_chan = do_classify and not no_chan` —— 缠论**只在 `--classify` 时运行**，默认调用输出 `{"valid": false, "error": "未启用"}`；argparse 无 `--chan` 标志（`--classify/--no-chan` 才有）。父文档 `skills/stock/SKILL.md:411` 正确使用 `--classify`，子文档自相矛盾。
- 建议：修订 SKILL.md 为"`--classify` 时含缠论"，删除 `--chan` 引用。

**P0-2 RSI 三周期声明与实现冲突**
- 声明：SKILL.md:28 "RSI：6/12/24 三周期"
- 证据：`scripts/technical/rsi.py:7` 只有单一 `rsi_features(closes, period=14)`（实测输出 keys 无 `period`）；`scripts/technical/report.py:102` 渲染固定 "RSI-14"（`rsi_data.get('period', 14)` 恒取默认值）；docstring 称"与通达信/同花顺一致"，而通达信默认恰是 6/12/24。
- 建议：二选一——实现三周期 RSI，或改 SKILL.md 为"RSI(14) Wilder 平滑"。

**P0-3 突破检测是集成死代码**
- 声明：SKILL.md 输出维度含"突破"（趋势结构段）
- 证据：`scripts/technical/trend.py:125` `broke = last > resistance and prev <= resistance`；`scripts/technical.py:102-104` 只在 `nearest_r` 存在时调用，而 `support_resistance` 构造的 `nearest_resistance` **恒在现价上方**（`trend.py:26` 摆动高点过滤 `> last`、`:38` 均线阻力 `>= last`）→ `last > resistance` 恒 False；突破后该阻力跌出列表、检查直接跳过。实测：突破前"未突破"，突破后"无阻力位"。单测（`tests/unit/test_technical_indicators.py:146-163`）传硬编码阻力 11.5 只锁函数行为、没锁调用链。
- 建议：让 `breakout_check` 消费"最近 60 日摆动高点"而非"现价上方最近阻力"，或删除该功能并如实标注；补一条集成测试锁调用链。

**P0-4 本土战法数量与清单漂移**
- 声明：SKILL.md:31 "6 种 A 股经典形态"
- 证据：`scripts/strategies/patterns/__init__.py:83-104` 实际 7 个检测器，缺"断板反包"（`scoring.py:452` 有 +7 加分）；且 `detect_all_local_patterns:119` 只保留最近 5 个形态，第 6 个起静默丢弃。
- 建议：SKILL.md 补断板反包；`detect_all_local_patterns` 的截断行为写入文档或改为可配置。

### P1（功能失效/声明含糊）

**P1-1 KDJ 钝化降权未落地且信号矛盾**
- 声明：`report.py:91` "⚠ KDJ钝化中，超买超卖信号暂停参考"
- 证据：实测钝化+超买时 `sell_signals` 仍输出"KDJ超买区(J=95) [KDJ高位钝化-趋势延续]"（`signals.py:183-184`）；`scoring.py:230` 钝化权重 5 与超买档位同乘 5，钝化前后评分仅差 0.9 分。
- 建议：钝化时 `signals.py` 抑制超买超卖信号；`scoring.py` 钝化档位降权。

**P1-2 市场环境单日涨跌幅直接映射"牛市/熊市"**
- 声明：`detect_market_environment` 输出市场状态驱动权重调整
- 证据：`scoring.py:707-710` 单日 +1.6% → "牛市"、-1.6% → "熊市"（置信度低）；±1.6% 是 A 股日常波动，却驱动权重矩阵（牛市 `trend_following` 1.4、`bullish_bias` 1.3）改变全部子评分；`technical.py` 从不传 `recent_quotes`，多日平滑路径实际不可用。
- 建议：单日标签降级为"温和上涨/下跌"或加多日确认门。

**P1-3 Guardrail "不输出买卖信号"与报告输出矛盾**
- 声明：SKILL.md:59 "技术分析不输出买入/卖出信号（信号层在 /stock 主流程）"
- 证据：`report.py:28-31` 渲染"买入信号/卖出信号"，`report.py:424-427` render_quick 渲染"买入/卖出"，`composite_score` 返回 `buy_signals/sell_signals`。模块本身就是信号层。
- 建议：guardrail 措辞改为"不输出买卖建议（仅信号）"，对齐实现。

### P2（一致性/文档）

- **版本号漂移**：SKILL.md frontmatter `version: 1.21.0` vs CHANGELOG 当前 v1.21.1
- **`--quick` 声明**：SKILL.md:53 "只输出均线+MACD+RSI 三个核心指标"，实际 `render_quick` 输出评分/趋势/量能/支撑阻力/连板/买卖信号 8 项
- **`_score_rsi` docstring 过时**：`scoring.py:269` 声称"无独立上限"，实际 `clamp(0, 15)`
- **过滤口径不一致**：`pipeline.py:28` 只过滤 close+volume，`core.py:132-148` `filter_records` 过滤五字段——两条消费路径 K 线条数可能不同
- **数据 stale 守卫未实现**：SKILL.md:62 "数据 stale 时（>3 个交易日）必须警告用户"，代码无任何 stale 检查

---

## 四、待澄清项

- **RSI 三周期是产品需求还是文档笔误？** 若真需要 6/12/24，为何 report.py 渲染 RSI(14) 且无任何 multi-period 残留？
- **突破检测的预期语义**：是"突破最近摆动高点"（需改数据源），还是仅"突破均线阻力"（现实现语义）？决定修死代码还是删功能。
- **钝化降权**：钝化时超买超卖信号应完全抑制，还是仅降权？`scoring.yaml` 是否要加钝化权重档？
- **市场环境标签**："牛市/熊市"是否应改为"强势/弱势"避免误导？多日窗口 `recent_quotes` 谁负责传？

---

## 五、下一步行动

1. 修订 `stock-technical/SKILL.md`：缠论默认声明改为 `--classify` 启用、删除 `--chan`、RSI 改单周期口径、补断板反包、版本号 1.21.0 → 1.21.1（4 处文档修正，一轮对话可完成）。
2. 突破检测二选一：改 `breakout_check` 数据源（前高列表）或标注"仅回踩检测"——并补一条集成测试锁调用链。
3. KDJ 钝化：`signals.py` 钝化时抑制超买超卖信号 + `scoring.py` 钝化降权落地。
4. `detect_market_environment`：单日标签降级为"温和上涨/下跌"或加多日确认门。
5. guardrail 措辞改为"不输出买卖建议（仅信号）"，对齐实现。

---

## 六、立场结论

**技术模块值得继续，但当前"文档说的 ≠ 代码做的"会让下游用户拿到误导性信号**——指标计算层是资产，契约层是负债。建议先修 P0 三项（缠论声明、RSI 口径、突破死代码）再谈新增功能；若两周内不修，至少把 SKILL.md 改到与代码一致，避免用户按文档操作拿到错误结论。

---

## 七、实施记录（2026-08-27）

审查后同日完成修复，全部经用户确认方案后落地：

| 风险项 | 修复内容 | 落地文件 | 验证 |
|---|---|---|---|
| P0-1 缠论声明 | SKILL.md 改为 `--classify` 启用缠论、删除不存在的 `--chan`、版本 1.21.0→1.21.1 | `skills/stock-technical/SKILL.md` | 文档 |
| P0-2 RSI 三周期 | `rsi_features` 增加 rsi6/12/24 键（主键 rsi14 兼容），report 渲染多周期 | `scripts/technical/rsi.py`、`report.py` | `TestRsiMultiPeriod`（4 例） |
| P0-3 突破死代码 | `support_resistance` 新增 `recent_swing_highs`/`breakout_target`（现价下方摆动高点），`technical.py` 改传 target，"突破确认(放量)"真实可达 | `scripts/technical/trend.py`、`technical.py` | `TestBreakoutCheck` 集成用例（2 例），实测"突破确认(放量)"输出 |
| P0-4 战法数量 | SKILL.md 补"断板反包"（7 种） | `skills/stock-technical/SKILL.md` | 文档 |
| P1-1 钝化降权 | 钝化时超买/超卖信号不入 buy/sell 列表；`_score_kdj` 超买/超卖档位 ×0.5 | `scripts/technical/signals.py`、`scoring.py` | `TestKdjDunhuaDowngrade`（3 例） |
| P1-2 市场标签 | 单日涨跌定性"牛市/熊市"→"强势/弱势"，新增默认权重矩阵 | `scripts/technical/scoring.py` | 断言更新 + 全分支回归 |
| P1-3 guardrail | SKILL.md 改为"不输出买卖建议（仅信号）" | `skills/stock-technical/SKILL.md` | 文档 |
| P2 杂项 | `_score_rsi` docstring 修正；`pipeline.compute_indicators` 过滤口径对齐五字段 | `scoring.py`、`pipeline.py` | 集成回归 133 通过 |

**验证结果**：技术模块 4 个单测文件 204 例全绿；`test_screening_service` + `test_screener_pipeline` 133 例通过；全量 unit `-m "not network"` 1707 通过（2 例 `test_portfolio_health` 失败为既有问题，与本次改动无关——stash 验证确认）。CHANGELOG v1.21.1 段已记录。

**未实施项**（超范围，保持已知缺口）：数据 stale 警告（需 kline 数据源配合）；`detect_all_local_patterns` 最近 5 个形态截断（行为可接受，已在报告中标注）。
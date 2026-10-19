# 技术指标深度定位与复测审查报告（2026-10-19）

> **审查时间**：2026-10-19
> **修复状态**：2026-10-19 当日已按本报告逐项落地（v1.23.1），详见对应 commit；遗留项为补测（战法 6 检测器/缠论专项测试）
> **审查对象**：`skills/stock-technical/SKILL.md` + `scripts/technical.py`（CLI 兼容入口）+ `scripts/technical/`（22 文件）+ `scripts/strategies/patterns/`（本土战法 9 检测器）+ `scripts/chan/`（缠论）+ `scripts/technical/pipeline.py`（统一管道）
> **方法**：全文件通读定位 + 全量测试套件复跑 + 合成数据数学锚点实测（37 项）+ 离线 E2E（`_compute_all` → `render_report`/`render_quick`/JSON）+ SKILL.md 声明逐条对照代码
> **基线**：上一轮 `technical-module-review-2026-08-27`（3 P0 + 3 P1 已修复，v1.21.1 落地）；本报告验证其修复项是否仍成立，并定位新增漂移
> **相关文档**：[technical-module-review-2026-08-27.md](./technical-module-review-2026-08-27.md)、[grill-me-positioning-2026-08-20.md](./grill-me-positioning-2026-08-20.md)

---

## 一、一句话结论

> ✅ **技术指标计算层经外部锚点复测全部正确，08-27 三类 P0 修复（缠论开关/RSI 三周期/突破检测集成）与 P1 修复（KDJ 钝化降权/市场标签）在两个月后依然成立**；全量测试 1909 passed / 0 failed。**但 Guardrails 层有一条声明至今无代码支撑（stale 数据警告），且新增 4 处 P1/P2 级显示与披露精度问题**：同名战法信号重复渲染、本土战法静默截断至 5 个、SKILL"换手率"与"BOLL 开口"维度无对应输出、组合策略头行数字为单股最优而非均值。

---

## 二、深度定位：技术指标全貌地图

### 2.1 入口与调用链

```
skills/stock-technical/SKILL.md          # 声明层（version 1.23.0，与 package.json/stock SKILL 一致 ✓）
  └─ scripts/technical.py                # CLI 兼容入口（--quick/--classify/--no-chan/--chip/-j/--scale）
       └─ technical.analyzer._compute_all  # 统一指标计算器（TechnicalInput 封装）
            ├─ technical/                # 指标包（22 文件，__init__.py 导出 22 个公共 API）
            ├─ strategies/patterns/      # 本土战法 7 检测器（9 个 def，含 detect_all_local_patterns）
            ├─ chan/                     # 缠论（--classify 且非 --no-chan 时）
            ├─ classifier + finance      # 个股分类（--classify 时）
            └─ data.chip_dist            # 成本分布（--chip 时，新增 v1.23.0）
```

### 2.2 指标实现清单（scripts/technical/）

| 模块 | 公开 API | 声明维度 | 复测结论 |
|---|---|---|---|
| core.py | sma/ema/stddev/_ema_series/_find_swing_points/filter_records | 数学工具+数据对齐 | ✅ 手算锚点全过 |
| moving_average.py | ma_system/incremental_ma | MA5/10/20/60/120/250+排列+粘合 | ✅ |
| macd.py | macd_full | DIF/DEA/柱/金叉死叉/顶底背离 | ✅ |
| kdj.py | kdj_full | K/D/J+超买超卖+钝化（20cm/30cm 差异化阈值） | ✅ 强上涨超买与高位钝化实测触发 |
| boll.py | bollinger | 上中下轨+带宽+位置（总体标准差口径） | ✅ 与手算一致 |
| rsi.py | rsi_features | RSI-14 主周期 + rsi6/12/24 | ✅ Wilder 平滑，StockCharts 锚点 70.46 精确命中 |
| volume.py | volume_analysis | 量比/量价/OBV/连续缩量（VP_* 枚举） | ✅ |
| candlestick.py | detect_candle_patterns | K 线形态 | ✅ 测试覆盖 |
| trend.py | support_resistance/box_detection/breakout_check/wave_state | 支撑阻力/箱体/突破/波浪 | ✅ 突破集成链实测可达 |
| astock.py | limit_analysis | 涨跌停/连板/制度 | ✅ |
| bamboo.py / ma_stop.py | bamboo_node / ma_stop_buy | 竹节法/均线止跌 | ✅ 测试覆盖 |
| scoring.py | composite_score/detect_market_environment | 自适应评分/市场环境 | ✅ KDJ 钝化降权实测生效 |
| signals.py | _generate_signals | 买卖信号汇总+结构化字段 | ✅ 钝化抑制实测生效 |
| report.py | render_report/render_quick | 报告渲染 | ✅ E2E 段落齐全 |
| chip_distribution.py | chip_distribution/classify_tier | 筹码（v1.23.0 新增） | ✅ 获利+套牢≈100、tier 档位合法 |
| sentiment.py | MarketDataFetcher | 涨跌停数据（market_breadth 消费） | ✅ 不在指标计算链 |

### 2.3 消费方（统一管道之外的 15 处）

`business/stock_analysis.py`、`business/screening_service.py`、`business/risk_warning.py`、`screener.py`、`backtest/engine.py`、`market_anchor.py`、`market_breadth.py`、`chan/beichi.py`、`chan/maidian.py`、`data/chip_dist.py`、`data/zt_pool.py`、`strategies/factors/capacity.py`、`strategies/factors/dealer.py`、`strategies/regime/breadth.py`、`portfolio/health_report.py`（importlib 加载 technical.py）。

---

## 三、复测结果

### 3.1 测试套件

| 套件 | 结果 |
|---|---|
| 技术单测（test_technical_indicators/macd_kdj_boll/supplement/bamboo/ma_stop） | **160 passed** |
| 全量（tests/，非网络） | **1909 passed / 13 skipped（需 --run-network 或可选依赖）/ 0 failed** |

### 3.2 合成数据数学锚点（37 项全过，详见 ## 四）

- RSI(14) 初始值 70.46 精确命中 StockCharts 公开示例；全涨=100 / 全跌=0 / 平坦=50 / 数据不足=None
- SMA/EMA/stddev 手算锚点一致；BOLL 中轨/上下轨与"总体标准差×2"手算一致
- KDJ 强上涨触发超买区（主板 80 阈值档），高位持续 K 触发钝化
- 突破检测集成链：摆动高点位于现价下方 → 放量突破输出"突破确认(放量)"、缩量输出"突破待确认(缩量)"、未突破输出"未突破"——08-27 P0-3 死代码问题未回归
- KDJ 钝化时 signals 不输出 KDJ 卖出信号、结构化字段全 False；非钝化超买正常输出——08-27 P1-1 未回归
- 市场环境 state 枚举 ⊆ {强势, 弱势, 震荡, 冰点, 亢奋}——08-27 P1-2 未回归
- composite_score 钝化场景总分 < 非钝化场景（降权生效）
- 筹码分布：获利+套牢≈100、平均成本在价格区间内、tier ∈ {筹码在脚下, 深度套牢, 上方有墙}、数据不足返回 None

### 3.3 离线 E2E（合成 250 根 K 线喂 _compute_all）

- 20 个 features 键齐全（--classify 不含 --chip）；readout 全指标有值；`breakout` 输出"突破维持(回踩未破)"（非空）
- render_report 输出全部 12 个标准段落（综合评分/均线/MACD/KDJ/BOLL/成交量/RSI/形态/支撑阻力/趋势结构/特化/仓位参考）
- render_quick 正常；破位场景输出"⚠️ 破位警示"

---

## 四、发现清单

### P0：无

### P1：声明与实现冲突（影响使用）

**P1-1 数据 stale 警告无实现支撑（08-27 已知缺口，仍未落地）**
- 声明：`SKILL.md:64` "数据 stale 时（>3 个交易日）必须警告用户"
- 证据：`scripts/technical.py` / `technical/report.py` / `kline.py` 全无新鲜度比对。K 线的 `day` 字段可拿到（`kline.py` 返回记录含 day），但 technical.py 从未取末根 `day` 输出，报告头部时间戳是 `datetime.now()`（分析时刻）而非数据时刻。模型无数据日期可依，guardrail 不可执行。
- 建议：technical.py 在 meta 中加 `data_date = records[-1]["day"]` 并渲染"数据时间戳"；用 stdlib 实现"距最新交易日 >3 天则输出 stale 警告"（A 股节假日表已在 data/a_share_holidays.json，无需网络）。

### P2：显示与披露精度

**P2-1 同名战法信号重复渲染（实测"三阳一阴"×4）**
- 证据：`signals.py:147-152` 对 `local_patterns["patterns"]` 逐条 `append(lp["name"])`，不做按名去重；合成数据实测 buy/sell 列表出现 "三阳一阴" 4 次（不同日期各触发一次），quick 与评分段噪音明显。
- 建议：按 name 去重（保留最近日期）或渲染为 "三阳一阴(N 次)"。

**P2-2 本土战法静默截断至最近 5 个**
- 证据：`strategies/patterns/__init__.py:117` `recent = deduped[-5:]`，`count` 字段为截断后数量；08-27 报告 P0-4 附带的建议（写入文档或改为可配置）未落地，SKILL 宣传 7 种战法但输出上限 5 个。
- 建议：输出 `detected_count`（未截断总数）+ 截断说明，或 SKILL 注明"展示最近 5 个"。

**P2-3 SKILL"量能：量比、换手率、量价配合"中"换手率"无对应输出**
- 证据：`volume.py` 输出 7 字段（量比/量价/OBV/缩量…），`report.py` 量能段渲染量比/量价/OBV，全链路无换手率。
- 建议：SKILL 删"换手率"或由 volume 段补换手率（quote 有数据源可接）。

**P2-4 SKILL"BOLL：开口/收口"中"开口"档缺失**
- 证据：`boll.py` bandwidth_desc 仅 3 档：极度收窄(变盘信号)/收窄中/正常带宽，无"开口"状态。
- 建议：补 "开口" 档（如 bandwidth ≥ 0.15 → 开口）或 SKILL 改为"收口/带宽状态"。

**P2-5 组合策略头行数字为单股最优而非均值**
- 证据：SKILL.md:36 "71.4% 胜率，+6.39% 平均收益"；`config.json` 标注 71.4% 为宝丰能源单股最优、5 只平均 59.7%。SKILL 已标"样本内拟合"但未点明"最优个股"口径；且 `detect_ma_volume_signal` 实际触发是 3 条件（金叉/放量 2.5x/突破前高）任意 2 条，并非严格"金叉+放量"。
- 建议：SKILL 头行改为"（单股最优 71.4%；5 只平均 59.7%，样本内）"，或引用均值。

### 保留项（复测仍成立）

- RSI Wilder 平滑与通达信/同花顺口径一致（外部锚点命中），rsi6/12/24 键与报告渲染正常
- 突破检测消费 `breakout_target`（现价下方摆动高点）而非 `nearest_resistance`，集成链真实可达
- KDJ 钝化降权三处一致（signals 抑制 + scoring 权重 5 + dunhua_penalty 0.5 + 报告提示语）
- 市场状态枚举 强势/弱势/震荡/冰点/亢奋（不再产出牛市/熊市）
- 缠论仅 --classify 启用、--no-chan 关闭；SKILL 措辞与代码一致
- 本土战法 7 检测器与 SKILL 7 种清单一致（断板反包已补）
- 版本一致性：SKILL 1.23.0 = package.json + stock/SKILL.md（v1.23.0，CHANGELOG 对齐）
- --chip 筹码功能声明与实现一致（report 渲染 成本分布段 + 模型推算免责）

---

## 五、结论与建议

- **计算层可信**：指标公式、边界处理、历史修复均经外部锚点与合成数据验证，可长期复用。
- **建议修复顺序**：P1-1（stale 警告）> P2-1（信号去重）> P2-3/P2-4（SKILL 声明对齐）> P2-2（截断披露）> P2-5（数字口径）。
- 本轮为纯审查，未改代码；如需修复请按上列顺序逐项指示。
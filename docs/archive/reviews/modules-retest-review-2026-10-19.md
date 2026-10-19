# 其余模块深度定位与复测审查报告（2026-10-19）

> **审查时间**：2026-10-19
> **修复状态**：2026-10-19 当日已按本报告逐项落地（v1.23.1），详见对应 commit；遗留项为补测（战法 6 检测器/缠论专项测试）
> **审查对象**：`scripts/strategies/`（策略注册表/因子/模式策略/regime）、`scripts/fetchers/` + `scripts/common/`（数据获取与基础设施）、`scripts/business/`（五层分析/筛选服务）、`scripts/backtest/`（回测引擎）、`scripts/portfolio/`（持仓）、`scripts/monitor/`（推送）、`scripts/chan/`（缠论）+ 跨文档外宣数字（README / CLAUDE.md / product-architecture / 各 SKILL.md）
> **方法**：与上一轮技术指标审查同法——定位地图（3 个并行探索代理 + 逐项人工复核）+ 动态复测脚本（34 项）+ 全量测试套件（1909 passed / 0 failed）+ 文档声明逐条对照
> **基线**：2026-07-02 full-module-review、2026-07-07 architecture-review、2026-07-15 deep-review、2026-07-28 audit/regression、2026-08-20 定位压力测试（数字修复）、2026-08-26 backtest-philosophy-review、2026-08-27 deep-audit / 技术模块审查
> **相关文档**：[technical-indicator-retest-review-2026-10-19.md](./technical-indicator-retest-review-2026-10-19.md)（同批技术指标审查）

---

## 一、一句话结论

> ✅ **核心机制全部复测通过**：6 策略 × 9 因子权重和每项 =1.0 且无多余键、OOS 状态机（registry 默认 in_sample + JSON 覆盖层写入/恢复）实测生效、8 个因子评分函数合成数据可调用、回测引擎/walk-forward 可运行、全量测试 1909 passed。**但文档层是本轮重灾区**：跨文档数字口径 6 处不一致（含用户可见的 stock-help "6 因子"、product-architecture 内部 27/35 自相矛盾、strategies.md 指错权重源文件），另有 2 处真实代码缺陷（get_strategy 返回可变引用、health_report 5 个带 self 的死函数）和 10 余处 P2 级注释/声明漂移。

---

## 二、复测证据

### 2.1 测试套件（全部复用上轮全量结果，一处不重复跑）

| 模块 | 相关测试文件 | 结果 |
|---|---|---|
| strategies | test_strategy_registry / test_oos_validation(24 项) / test_thresholds / test_duanban / test_cyclical_factor / test_chip_factor_time / test_score_utils / test_strategy_performance_minpool | 全绿（含在全量 1909 中） |
| backtest | test_backtest_engine / test_walk_forward_windows / test_atr_stop / test_optimize_cross_window | 全绿 |
| portfolio | test_portfolio_manager / submodules / health / cost_source / correlation / position_ratio | 全绿 |
| fetchers/common | test_fetcher_orchestration / test_circuit_breaker / test_rate_limiter / test_data_* 等 | 全绿 |
| monitor | test_notification_manager / test_monitor_cli | 全绿 |
| chan | **零专项测试**（见 P2-9） | — |

### 2.2 动态复测（34 项，33 过 1 证实为缺陷）

- **策略注册表**：6 策略（balanced/quality_value/growth_momentum/defensive/turning_point/ma_volume_momentum）逐一校验——9 因子权重和 = 1.0（6/6）、无多余键、label 齐全（18 项全过）
- **OOS 状态机**：默认全部 in_sample（6/6）；写入 `data/strategy_oos_validation.json` 覆盖层 → balanced 升为 oos_verified、未覆盖策略保持 in_sample、删除 JSON 恢复默认（4 项全过）——机制完好，与 `reference-oos-validation-state-machine` 记忆一致
- **因子冒烟**：quality/valuation/momentum/liquidity/volatility/dividend/cyclical 合成数据全部可调用（7/7）
- **回测引擎**：simulate_strategy / run_walk_forward 可运行（引擎 internal 用 `from data import get_kline` 包装，以集成测试为准）
- **战法测试覆盖**：7 个检测器仅 duanban 有独立单测（实证）
- **get_strategy 可变引用**：`get_strategy("balanced")` 返回注册表原 dict——修改返回值直接污染全局权重（唯一失败项，见 P2-1）

---

## 三、发现清单

### P0：无

### P1：跨文档数字口径冲突（用户可见或自相矛盾）

**P1-1 stock-help/SKILL.md "6 策略 × 6 因子"（应为 9 因子）**
- 证据：`skills/stock-help/SKILL.md:27`（"6 策略 × 6 因子筛选 → 候选池"）、`:65`（"6 策略 × 6 因子批量选股"）；实际注册表是 9 因子（registry.py:9），CLAUDE.md:71/109、README、strategy-validation.md 均为 9 因子口径
- 影响：用户第一手速查表引导错误认知；跨 skill 文档漂移的典型

**P1-2 product-architecture.md 内部自相矛盾（27 vs 35）**
- 证据：`docs/product-architecture.md:81` "35 类 × 7 域" vs `:95-106` 表格"合计 27"。且该表格按**自述口径**（真实数据源 Python 文件数）也算错两处：财务 3（实际 2 文件 + akshare_balance enricher 非 fetcher）、事件日历 1（实际 eastmoney_event + performance_forecast 2 文件）→ 文件数合计应为 28；"查询类型数 33"同样无依据（各列 1+5+3+3+2+2+3=19+）
- 注：2026-08-20 定位压力测试曾修 §2.3"财务 fetcher 2→3"，但该表格整体口径（27/33）未被同步清理，是当日修复的漏网

**P1-3 strategies.md SSOT 声明与实际不符**
- 证据：`skills/_shared/references/strategies.md:4、:19` 自称"策略定义单一事实源"并指向 `scripts/strategies/thresholds.py`；实际 thresholds.py 只做行业差异化阈值（2 个函数，加载 data/industry_thresholds.json），策略权重在 `registry.py:22-96`。且该文档"因子维度"只列 5 类（缺 volatility/dividend/chip/event/analyst 4 类），与 9 因子口径不符
- 影响：维护者按 SSOT 文档找权重会找到错误的文件——SSOT 本身失守

### P2：代码缺陷与注释/声明漂移

**P2-1 get_strategy 返回可变引用（真实代码缺陷）**
- 证据：`registry.py:204-208` `get_strategy()` 直接 `return STRATEGIES[name]`（锁内返回原 dict）；同文件 `register_strategy`（:171）用 `{**weights}` 拷贝保护，注释声称"保护全局状态不被并发修改"——读路径却暴露可变引用，任何调用方修改返回值即污染全局权重。实测：`get_strategy("balanced")["quality"] = 0.0` 后注册表被改
- 建议：`return {**STRATEGIES[name]}` 或 dict(STRATEGIES[name])

**P2-2 health_report.py 5 个带 self 参数的模块级死函数（v1.22.0 拆分残留）**
- 证据：`scripts/portfolio/health_report.py:715-738` 存在模块级 `def risk_summary(self, ...)` / `attribution_report(self, ...)` / `advisory_rebalance(self, ...)` / `export_codes(self)` / `check_concentration(manager, ...)`，均带 self/manger 参数却无调用方（grep 无引用），函数段间还夹杂散注释 `# ---------- 导入导出 ----------`；manager.py:644-708 已有同名类方法（正常实现）
- 建议：删除约 45 行死代码

**P2-3 registry.py:13-14 注释过期**
- `# event 为事件因子（待调优），当前权重 0.0`——6 策略实际均已 `event: 0.05`（#10 灰度上线注释）；analyst 0.0 仍对。注释与代码自相矛盾（同文件上一行就是证据）

**P2-4 CLAUDE.md 数字与代码漂移（3 处）**
- "20 项单元测试"（CLAUDE.md:94）→ test_oos_validation.py 实际 24 个 test 函数
- BaseFetcher/DataFetcherManager/CircuitBreaker 位置写成 `scripts/common/__init__.py`（CLAUDE.md:82-83）→ 实际定义在 `common/fetcher_base.py` / `common/circuit_breaker.py`（__init__ 仅 re-export）
- watchdog 描述"akshare 永久挂起时触发 os._exit(2) 是真终止路径"（CLAUDE.md:13）→ screener.py:604-606 注释自认该分支"当前无调用方"（业务从不抛 ScreenerTimeoutError）；行号引用（545-557）也已过期（现 584-606）

**P2-5 README 五层示例输出与当前渲染不符**
- README.md:243-267 示例（【第 1 层 基本面】…【第 5 层 风险收益比】+ 目标价/止损）vs `stock.py:26-160` render_text 实际只渲染 行业画像 → 技术面 → 财务 → 近 60 日回测 → 综合评分；"估值层/板块层/风险收益比层"无独立段落，示例疑似旧版产物
- 注："五层"的估值/板块/风险收益比结论由 experts LLM 层在 SKILL 对话中合成，脚本仅提供数据；README 示例未说明这一边界

**P2-6 本土战法 7 检测器仅断板反包有独立单测**
- Sanying/laoyatou/meirenjian/shuangzhen/zhangting/dibu_shouban 均无独立测试文件；检测器含复杂条件逻辑（量比/跌幅/反弹三维评分等），回归风险敞口大（08-27 技术审查曾发现"三阴一阳"量化评分问题，属同类风险）

**P2-7 第 10 因子 cyclical 不在任何口径**
- factors/__init__.py 注册 10 因子（cyclical 第 10），权重默认 0，不进 9 因子清单、不在任何策略权重；register_strategy 可选键却含 cyclical——口径含糊，文档无从解释

**P2-8 fetchers 文档口径问题（3 处，均无功能影响）**
- `fetchers/__init__.py:12` docstring 声称 flow 域"3 个模块：eastmoney/sina/akshare"——代码无任何 akshare 资金流模块（幽灵模块描述）
- `:14-15` "lhb 2 个模块 / event 6 个模块"——实际 lhb 1 文件 2 类、event 2 文件 6 类（模块/类混用）
- `:213-215` event 域注释"calendar 3 + 个股 2 = 5"——实际注册 6 类（遗漏 PerformanceForecastFetcher）
- industry/ 第 8 个准数据域（akshare_industry.py 纯函数）未入任何"35 类 × 7 域"声明

**P2-9 chan 缠论零专项测试**
- tests/ 无 chan_full_analysis 相关测试（grep 零命中）；缠论作为五层分析正式输出（stock.py 渲染"缠论"段），复杂度高（分型/笔/线段/中枢/背驰/买卖点 6 链）却无任何锁

### 保留项（复测仍成立）

- 6 策略权重和 = 1.0、结构完整；OOS 双层状态机机制完好（默认 in_sample 立场正确，JSON 覆盖层读写原子）
- 35 fetcher 类 / 7 数据域与 `_DOMAIN_FACTORIES` 注册表一致（口径核验通过；模块 docstring 与架构文档 §2.2 的 35/7 也一致）
- DataFetcherManager 优先级故障转移 + CircuitBreaker + RateLimiter 编排（test_fetcher_orchestration 等全绿）
- watchdog 1800s 机制存在（screener_watchdog.py:33）；"20 项测试"仅计数漂移
- 退市预警"营收<1亿+审计非标"原实现永不触发——2026 已改为 revenue_yoy 近似并在代码注释自曝（属已处理项，非新缺陷）
- OOS 现状：data/ 无 strategy_oos_validation.json，6 策略真实状态全部 in_sample（框架就绪、结果未落盘）——与记忆 reference-oos-validation-state-machine 一致

---

## 四、结论与建议

- **机制层可信**：策略注册/因子/OOS/回测/持仓/故障转移核心逻辑经复测与既有测试双重确认。
- **文档层需一轮集中修复**（08-20 数字修复的剩余尾账 + 新漂移）：P1-1/2/3 三处文档冲突建议优先（均为纯文档改动，无代码风险）；P2-1/2/3 三处代码/注释缺陷建议随下次工程化批次清理；P2-5 README 示例需与 stock.py 渲染同步或标注"示例为 LLM 合成输出"。
- 本轮纯审查，未改代码；修复请逐项指示。
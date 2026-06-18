<!-- markdownlint-disable MD024 -->

# Changelog

本文件记录 stock-analyzer-skill 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased] - 2026-06-18

### Added
- **experts**: 新增动量派 v2.2.0——利弗莫尔+丹尼斯趋势跟踪
- **technical**: 新增市场宽度分析 + T策略过滤器
- **scripts**: 新增 hot_rank 热度榜 + backtest 自动基准对比
- **cli**: Sprint 25-26 --version flag + 性能基准 JSON 持久化
- **experts**: Sprint 14+15 覆盖测试 + D6 yaml 机器可读版
- **strategy_performance**: Sprint 10 跨策略对比子命令
- **snapshots**: Sprint 5 选股快照系统（review#16）
- **regime**: 实施 Sprint 2 市场状态机 + 板块集中度修复
- **screener**: 实施 Sprint 1 五项 P0 任务
- **screener**: 全市场模式支持 --exclude-board 排除指定板块
- **sector**: 新增板块查询脚本，支持并行获取与去重
- 添加合并型专家评分模式，更新 apply_veto 函数返回逻辑，调整最终信心指数计算
- add technical/pipeline.py shared indicator computation (B6)
- add dividend_yield thresholds to industry_thresholds.json (C20)
- add pe_percentile + ScoringContext in factors/common.py (A1, B5)

### Fixed
- **experts**: 修复 _resolve_conflict 两极分化分支不可达
- **scripts**: 修复 announcements 接受 sh/sz 前缀与 backtest 单标的报错
- **scripts**: 移除 parallel_map 已废弃的 max_workers 参数
- apply_veto return empty list when veto_results is None (C11)
- calibration.py dynamic expert names from registry (A2)
- private symbols cleanup, token externalization, YAML fallback (C9, C10, C12)
- remove sys.path hack from long_term/sentiment, fix typo (B6, B8)
- externalize stop_loss/take_profit thresholds to config (A3)
- NotificationManager thread safety for shared mutable state (A2)
- BOLL scoring dead branch — pos < 0.3 without 收窄 (B7)
- board_limit_pct remove cross-layer ConfigLoader dependency (C21)
- to_dict use dataclasses.asdict, add FinanceRecord fields (B8, C15-16)
- _detect_quant_activity only use market_amount (C18)
- explicit cleanup_tmp_files in 12 CLI entry scripts (A5)
- ConfigLoader mtime-based cache invalidation (B10)
- parallel_map type annotation object -> Callable (C14)
- MetricsCollector latencies bounded by deque maxlen=1000 (C13)
- connection pool thread safety + Retry-After propagation (A1, A4)
- cache.put rename, SHA256 keys, single-stat cleanup (A3, B9, C15)

### Changed
- **skills**: 重命名 /help 为 stock-help + smoke test 全清
- **backtest**: 修复 silent bug + 死代码清理 + 导入优化
- **classifier,refresh_pool**: 一致性与健壮性改进
- **business**: 深度优化业务层——4 项一致性与健壮性改进
- **strategies**: 深度优化筛选策略模块——6 项一致性改进
- **chan**: 深度优化缠论模块——修复索引错位 + 逻辑改进
- **monitor**: 深度优化监控模块——修复推送内容缺失 + 5 项改进
- **portfolio**: 深度优化持仓管理模块——修复死锁 + 3 项架构改进 + 代码安全
- **technical**: 深度优化技术分析模块——修复致命导入错误 + 6 项逻辑改进
- **data**: 深度优化数据获取模块——修复 4 个运行时 bug + 7 项架构改进 + 代码整洁
- **v2.1**: main() 重构 + 统一版本号 + v2.1.0 tag
- **screener**: Sprint 9 两阶段管线（review 末节架构建议）
- **screener**: Sprint 4 性能优化 + 行业分类 fallback
- **factors**: Sprint 3 因子级精修 + backtest 接入 regime
- **scoring**: 抽取 _consistency_from_scores 消除信心指数公式重写 (C2)
- **scoring**: _score_valuation 复用 pe_percentile 统一 PE 估值 (B3)
- **factors**: 清理 valuation_score 未用变量与误导注释 (B2)
- **factors**: 移除 momentum _detect_quant_activity 死分支 (B1)
- **screener**: 抽取共享分析核心消除 analyze_code/_analyze_stock 重复 (A1)
- unify thread pool management and improve error handling
- 并行数据获取、代码去重、backtest 模块拆分
- scoring dedup score/score_with_reasoning, cleanup aliases (B5, C9, C12)
- split decide.py into market_detector/vote_engine/formatter (B4, B7, C13)
- extract ExpertProfile to types.py, break circular import (A3)
- merge type_map into ALERT_LEVELS (B5, C14)
- _compute_all extract valuation + incremental MA (A1, C13)
- split composite_score into 10 dimension functions (B4)
- stock_analysis use pipeline, KlineBar directly, narrow exceptions (B6, C12, C19)
- dividend.py use industry_thresholds, remove ROE heuristic (B10, C17)
- screening_service dedup filters, eps, board thresholds (A2, A4, B7, C14)
- momentum.py use pe_percentile, remove inline PE logic (A1)
- filters.py use ConfigLoader, registry copy weights, remove volatility_score (A3, B9, B11)
- extract _compute_vol_score, deduplicate volatility functions (C13)
- split formatters.py into glossary + exporters (B8)
- fetcher managers thread-safe + remove sys.path hack (B6, B7)
- common/__init__.py lazy loading + last_error + NOT_HANDLED pickle (A2, A5, B11, C16, C17)

### Documentation
- **changelog**: 记录 v1.12.1 10 模块深度审查修复
- **experts,skills**: 深度优化投资专家档案与 SKILL 文档产品化
- 用户体验优化 - 散户视角重构文档与引导
- 嵌入 9 个 skill 终端 demo GIF 演示
- **README**: Sprint 12 / C7 30s demo 段 + 可重放脚本
- **plan**: 增加 Screener V2 规划与复盘文档
- **screener**: 标注包装函数为测试桩点，消除 vol_price 映射重复 (A2)
- add expert system optimization design spec — 14 issues
- add technical+monitor layer optimization design spec — 14 issues
- add business layer optimization design spec — 21 issues across business/strategies/data
- add infra layer optimization design spec — 18 issues across common/fetchers/config
- 缩短 portfolio/stock SKILL.md——引用子模块
- 文档瘦身——portfolio/stock 拆分 + research 去重

### Testing
- **coverage**: Sprint 13 核心模块分支测试（62% / 24 新增测试）
- Sprint 8 修复 3 个 pre-existing 测试失败

### CI/CD
- smoke_test 入 CI + 跨 skill JSON Schema 契约
- P0 地基修复——绝对路径/hypothesis/clock 注入

### Maintenance
- **deps**: 统一版本号 1.12.0 → 1.11.0
- **scripts**: 全量版本升级至 1.12 并扩展 sync 覆盖
- 忽略测试产物 .coverage 与 strategy_performance.json
- 统一版本 v2.1.0 → v1.12.0
- **v2.0**: Sprint 20-23 收官 + 完整总结
- **v2.0.0**: Sprint 16-19 收官 + 33/33 plan 项全部完成
- **coverage**: Sprint 11 覆盖率提升到 61%（D5 落地）
- **ci**: Sprint 7 工程化债清理（SKILL.md/flake8/pre-commit）
- **v2**: Sprint 6 月度校准 + 性能压测 + black 收尾
- **data**: 格式化 data/__init__.py（black）
- remove dead YAML configs from experts/yaml/ (A1)

### Other
- merge: chore/skill-workflow-optimization → main
- **strategy**: 回测优化 growth_momentum 策略权重
- 新增防御型市场状态——回测反馈驱动专家权重调整
- 修复 monitor 时间 mock——patch dev.clock 而非 datetime
- 补合并型专家回退测试——3 用例覆盖降权触发与中性不触发
- 合并型专家名兼容——_find_expert 回退 + 注册表断言强化
- 补 portfolio/daily_report.py 0 覆盖——21 测试 + 绕过 HttpClient import bug
- 补 calibration_sync.py 0 覆盖——19 测试 mock gh CLI
- 补 scripts/events.py 0 覆盖——14 测试覆盖 format_events_text
- 补 portfolio/performance.py 0 覆盖——19 测试 + property 恒等式
- v2.1.2 补盲区 scoring 完整实现——26 测试覆盖
- v2.1.1 合并型 scoring——继承 legacy 逻辑而非骨架
- v2.1.0 切换 API——list_active/legacy_experts
- 补 scripts/stock.py 0 覆盖——11 个测试覆盖 CLI/渲染/E2E
- init_pool/refresh_pool/calibration 加 --json 输出
- 8 → 8 真实合并——原 6 人 active=False，新框架用 5+3
- 补 0 覆盖——clock property + contracts schema 测试
- 8 → 14 双轨——3 合并 + 3 补盲区 + horizon 优先
- 4 个核心脚本迁 argparse + 策略单一事实源

## [Unreleased]

### Changed · 用户体验优化（v1.12.1）

- 🎯 新增 `_shared/references/welcome.md` 统一欢迎卡（4 段：心智建立 + 3 步上手 + 4 目标入口 + 退出方式），可被 `/help` 和 `/learn` 复用
- 🆘 重写 `/help` SKILL.md：合并"5 场景入口"和"4 新手引导场景"为一张"按目标选入口"表；顶部加识别指令自动加载 welcome.md；"高级子模式速查"挪到末尾附录
- 📚 `/learn` description 补充概念类触发词（什么是 PE/ROE/MACD/KDJ/K线、均线怎么用、估值方法、技术分析入门、什么是缠论）
- 📖 README.md：副标题改写为"把专业 A 股分析变成 9 条对话命令"；新增"4 个常见问题 → 4 条命令"段；插入 5 行心智建立段
- 📖 user-guide.md：顶部加 TL;DR 9 skill 一句话表 + 4 个组合使用场景提前；原"组合使用场景"段改名为"完整使用流程（自下而上 / 再平衡 / 研究报告）"
- 🚀 `install.sh` / `install-plugin.js` 末尾新增"新手起步"提示（直接输入 `/help` 或 `/stock 贵州茅台 quick`）
- 🧭 `docs/quick-start.md` 顶部加 README 导航行

### Fixed · 10 模块深度审查（v1.12.1）

本次对 10 个核心模块进行深度代码审查，共提交 10 个 commit，修复 46+ 项问题。
所有改动均通过 1733 项单元测试（100% 通过率）。

#### 数据获取模块（commit `3e4d06f`）

- 🔴 **同花顺 fetcher 语义修复**：thquote 接口实际返回最近 K 线收盘价而非实时行情，优先级从 7 下调至 3 并加注释说明
- 🔴 **雪球行情字段映射对齐**：`pre_close` → `prev_close`，`turnover_rate` → `turnover`，`market_cap` → `total_cap`（统一单位亿元）
- 🟠 **Baostock 模块级一次性 login**：`atexit.register(bs.logout)` + 模块级 `_bs_logged_in` 锁，消除每次 fetch 的握手开销
- 🟠 **熔断器配置接入**：`BaseFetcher` 从 `data_source.yaml` 动态读取 `failure_threshold/recovery_timeout/half_open_max`
- 🟠 **连接池列表化**：`{key: conn}` → `{key: [conn, ...]}`，同 host 可保持多个 keep-alive 连接
- 🟠 **HTTP 客户端去重**：`http_get` / `http_get_with_headers` 合并为 `_http_get_internal`
- 🟡 清理 21 个 fetcher 文件的 `sys.path.insert` 样板代码

#### 技术分析模块（commit `4469233`）

- 🔴 **`scripts/technical/sentiment.py` 双致命错误修复**：`HttpClient` 不存在 + `_EASTMONEY_UT` 自引用 `NameError`，改用 `http_get` + `urlencode`
- 🔴 **`scripts/technical/pipeline.py` 数组错位修复**：`closes/volumes` 独立过滤导致数组长度不一致，改为统一过滤 `valid_bars`
- 🟠 **量价评分方向性修复**：极低量加分仅在 `vp_signal >= 0` 时生效（放量下跌时不再加分）
- 🟠 **背离检测峰值匹配容差优化**：从区间匹配 `abs(i - target) <= 5` 改为最近邻匹配
- 🟠 **量价分析窗口优化**：从等分窗口改为非对称窗口（近期 5 日 vs 前 20 日）
- 🟠 **亏损公司 OCF 信号修复**：亏损但有现金流时给出"造血能力尚存"正面评价
- 🟡 光头光脚阳线/阴线检测改用 0.1% 浮点容差
- 🟡 `report.py` `meta['price_num']` 改用 `meta.get('price_num', 0)` 安全访问

#### 持仓管理模块（commit `38fecd0`）

- 🔴 **`atomic_update()` 文件锁死锁修复**：抽取 `_raw_write()` 不加锁写入，`atomic_update` 在已持锁状态下直接调用，消除 10 秒超时死锁
- 🔴 **`daily_report.py` 导入错误修复**：`HttpClient` 不存在，改用 `http_get` + `parse_tencent_line`，批量请求行情
- 🟠 **日报数据模型对齐 v2 格式**：兼容 `quantity/cost` 和旧 `shares/cost_price`
- 🟠 **`max_drawdown` 日期对齐修复**：`NAV[date] = Σ(close_i × qty_i)`，不再按股票顺序错位追加
- 🟠 **通知状态管理修复**：直接修改 `utils._notify_enabled` 而非模块级变量遮蔽
- 🟡 `get_position`/`get_watch` 返回 `copy.deepcopy` 副本；内部操作使用 `_find_position`/`_find_watch` 获取可变引用

#### 实时监控模块（commit `af99534`）

- 🔴 **`compute_key_levels` 返回值修复**：增加 `position`/`watch` 键，修复推送内容缺失
- 🟠 **`support_touch_weak` 触发修复**：按支撑位强度分级（强→`support_touch`，弱→`support_touch_weak`）
- 🟠 **`NotificationManager`/`PortfolioManager` 单例缓存**：模块级惰性初始化
- 🟠 **批量行情预取**：`scan_all` 预调用 `get_quotes` 预热缓存，减少逐股串行 HTTP
- 🟡 log 轮转检查从每次写入改为每 10 次写入检查一次
- 🟡 `dingtalk.py` 的 `__import__("base64")` 改为顶层 `import base64`

#### 缠论模块（commit `b07501f`）

- 🟠 **`closes` 索引对齐修复**：不再过滤零值，保持与 records 索引对齐
- 🟠 **三买回踩检测逻辑修复**：从"站在 ZG 上方 0-3%"（实为"突破站稳"）改为"距 ZG 2% 以内"（真正的回踩）
- 🟡 `merge` 合并后保留 `open`/`close` 字段

#### 筛选策略模块（commit `cce78a8`）

- 🟠 **`_stdev` 与 `technical/core.py` 一致化**：改为总体标准差（除以 n）
- 🟠 **`_count_dividend_years` 回退逻辑修复**：无记录时返回 0，移除误导性固定 2 回退
- 🟠 **`momentum.py` `int()` 截断改为 `round(2)`**：避免 RSI 加权系数精度丢失
- 🟠 **`overlay.py` 归一化后精确总和为 1.0**：先除后 round
- 🟠 **`PRE_SCREEN_FILTER` 与 `config/limits.yaml` 同步更新**
- 🟠 **`thresholds.py` 配置文件缺失时增加 warning 日志**

#### 业务层模块（commit `7493af1`）

- 🟠 **删除不存在的 `backtest_service` 文档引用**
- 🟠 **删除两个文件中未使用的 `InsufficientDataError` 导入**
- 🟠 **`_calculate_composite_score` 复用 `strategies.pe_percentile`**，删除 15 行重复 PE 分位逻辑
- 🟠 **`_hard_filter` 涨跌停判断修复**：从 `abs() >= limit` 改为双向 `>= limit OR <= -limit`
- 🟠 **`compute_features` 统一过滤 `close > 0 and volume > 0`**，消除数组错位

#### classifier + refresh_pool 模块（commit `4cd9100`）

- 🟠 **`_classify_board` 与 `common.board_type` 对齐**：输出从"主板沪/主板深"统一为"主板"
- 🟠 **`_fetch_xuangu_page` 增加 `max_retries=2` 重试逻辑**
- 🟠 **`build_dividend_pool` 参数名重命名 + 注释对齐**
- 🟠 **`refresh_pool` 增加 diff guard**：新池与当前池相同时跳过写入
- 🟡 `classifier.py` 顶部统一导入 `board_type`

#### 回测引擎模块（commit `7716611`）

- 🔴 **`stock.py --with-backtest` silent bug 修复**：字段名映射 `win_rate_pct → win_rate` 等 4 个字段，子进程传参从位置参数改为 `--codes`
- 🟠 **`_build_hist_quote` 死分支删除**：`total_cap` 已是 0 又再赋 0
- 🟠 **`simulate_strategy` 循环内 3 处 `from import` 提到文件顶部**
- 🟡 场景标签从误导性年份改为时间窗口（近1月/近3月/近6月）

#### 投资专家模块（commit `fd86cf4`）

- 🟠 **`_resolve_conflict` 4:4 两极分化分支可达性修复**：增加 `long_votes["bull"] != 2` 守卫，避免 2:2:2:2 全面分歧分支抢先匹配

### 测试结果

```text
1733 passed, 45 skipped, 0 failed in ~35s
```

### 累计统计

| 维度 | 数值 |
| --- | --- |
| 审查模块数 | 10 |
| 提交 commit 数 | 10 |
| 修复问题数 | 46+ |
| 代码变更 | 1277 insertions, 420 deletions（净 +857 行） |
| 测试通过率 | 100% |

## [1.12.0] - 2026-06-17（统一版本：V2 量化策略平台 + V2.1 维护）

> 本版本将所有 Sprint 1-26 的 V2 改造合并发布为统一版本 v1.12.0
> 历史 tag（v1.1.0 - v1.11.0、v2.0.0、v2.1.0）已合并到此版本。

### Added

- **Screener V2 量化策略平台**（Sprint 1-26 综合）：
  - 6 因子 z-score 标准化（review#14）消除跨因子尺度差异
  - 4 状态市场状态机（bull/bear/range/panic）自动调节策略权重（doc#03）
  - 两阶段管线（Phase 1 无 K 线初筛 → Phase 2 仅对 Top N×3 拉 K 线精排）
  - 5 策略 V2 权重升级（balanced/quality_value/growth_momentum/defensive/turning_point）
  - 选股快照系统（review#16）：保存/对比/列出 JSON 快照
  - 跨策略对比子命令（strategy_performance compare）
  - 月度校准（strategy_performance record）记录到 JSON
  - 性能压测工具（perf_bench.py + save 子命令 JSON 持久化）
  - 板块集中度算法修复（review#15，候选池 < 10 不强制）
  - 因子级精修：波动率窗口 20→60 / ROE 趋势下降占比 60% / 动量阈值 p75 / PEG 用 3y CAGR / 动量趋势基础分收敛
  - K 线批量预拉（review#12）减少 5000 次独立 IO
  - 行情+财务并行拉取（review#11）耗时从 sum 降到 max
  - 行业分类 fetcher_industry 优先（review#13）
  - turning_point 两阶段模型（review#2）超跌+量能+基本面三重过滤
  - ESG/分红 fetcher 字段映射（review#9+10）dividend_records/consecutive_dividend_years 等
- **experts/yaml 机器可读版**（D6 落地）：13 个 expert yaml 配置 + 加载器
  - `experts/yaml_loader.py` 支持 load/load_all/export/round_trip
  - `experts/registry.py` 优先从 yaml 加载，向后兼容硬编码
- **screener.py main() 重构**（V2.1）：提取 `_build_parser()` 和 `_run_main(args)` 助手
  - `_build_parser()` 返回 argparse parser（便于构造 Namespace）
  - `_run_main(args)` 接收参数后直接执行（不解析 argv）
  - `main()` 仅 5 行（parse + delegate）
- **统一版本号**：`scripts/common/version.py` 暴露 `__version__ = "1.12.0"`
  - `screener --version` / `backtest --version` 输出带前缀
- **C7 README 30s demo**：`scripts/demo.sh` 可重放脚本 + README demo 段

### Changed

- `compute_weighted_score` 支持 market regime overlay（strategy 参数 → 实时调节权重）
- 策略权重从 V1 经验值（balanced.quality=0.23）升级到 V2（0.30）
- `_dict_to_finance` 支持 5 个新字段（dividend_yield/consecutive_dividend_years 等）

### Engineering

- 覆盖率 55% → 62.1%（fail-under 60% 达标）
- 168 测试 → 1780 测试（+1612 测试，0 失败）
- pre-commit 钩子 + flake8 + black 格式化
- 21 个独立 commit
- 5 个新模块（regime / filters / snapshots / strategy_performance / perf_bench）
- 13 个 expert yaml（V2 + V2.1.0 完整覆盖）

## [1.11.0] - 2026-06-16

### Changed

- **screener.py main() 重构**：提取 `_build_parser()` 和 `_run_main(args)` 助手，便于单测覆盖
  - `_build_parser()` 返回 argparse parser（便于构造 Namespace）
  - `_run_main(args)` 接收参数后直接执行（不解析 argv）
  - `main()` 仅 5 行（parse + delegate）
- **统一版本号**：`scripts/common/version.py` 暴露 `__version__ = "2.1.0"`
  - `screener --version` / `backtest --version` 输出带前缀（screener 2.1.0）
- **性能基准持久化**：`perf_bench.py save` 子命令保存到 `data/perf_benchmarks.json`（含 version + timestamp）
- **v2.1.0 扩展视角 yaml 完整迁移**（Sprint 21）：5 个 expert yaml

### Engineering

- 覆盖率 61.8% → 62.1%（+0.3%，新增 7 个 _run_main 测试）
- 测试 1773 → 1780（+7）
- 20 → 21 个独立 commit

## [1.8.0] - 2026-06-17（v2 量化策略平台首版）

### Added

- **Screener V2 量化策略平台**（15 Sprint 综合）：
  - 6 因子 z-score 标准化（review#14）消除跨因子尺度差异
  - 4 状态市场状态机（bull/bear/range/panic）自动调节策略权重（doc#03）
  - 两阶段管线（Phase 1 无 K 线初筛 → Phase 2 仅对 Top N×3 拉 K 线精排）
  - 5 策略 V2 权重升级（balanced/quality_value/growth_momentum/defensive/turning_point）
  - 选股快照系统（review#16）：保存/对比/列出 JSON 快照
  - 跨策略对比子命令（strategy_performance compare）
  - 月度校准（strategy_performance record）记录到 JSON
  - 性能压测工具（perf_bench.py）
  - 板块集中度算法修复（review#15，候选池 < 10 不强制）
  - 因子级精修：波动率窗口 20→60 / ROE 趋势下降占比 60% / 动量阈值 p75 / PEG 用 3y CAGR / 动量趋势基础分收敛
  - K 线批量预拉（review#12）减少 5000 次独立 IO
  - 行情+财务并行拉取（review#11）耗时从 sum 降到 max
  - 行业分类 fetcher_industry 优先（review#13）
  - turning_point 两阶段模型（review#2）超跌+量能+基本面三重过滤
  - ESG/分红 fetcher 字段映射（review#9+10）dividend_records/consecutive_dividend_years 等
- **experts/yaml 机器可读版**（D6 落地）：8 个专家 yaml 配置 + 加载器
  - `experts/yaml_loader.py` 支持 load/load_all/export/round_trip
  - `experts/registry.py` 优先从 yaml 加载，向后兼容硬编码

### Changed

- `compute_weighted_score` 支持 market regime overlay（strategy 参数 → 实时调节权重）
- 策略权重从 V1 经验值（balanced.quality=0.23）升级到 V2（0.30），覆盖更全面
- `_dict_to_finance` 支持 5 个新字段（dividend_yield/consecutive_dividend_years 等）

### Engineering

- 覆盖率从 55% 提升到 61.8%（fail-under 60% 达标）
- 168 测试 → 1773 测试（+1605 测试，0 失败）
- pre-commit 钩子 + flake8 + black 格式化
- Sprint 1-15 共 15 个独立 commit

## [1.11.0] - 2026-06-16

### Added

- **反追涨杀跌机制**：4 层估值约束嵌入决策引擎
  - `signals.py` 新增估值买卖信号（PE 行业分位底/顶、PEG 偏高）
  - `momentum.py` 新增估值衰减（PE>80%分位 → 动量×0.45，PE>65% → ×0.70）
  - `decide.py` 新增估值硬约束（长线组估值分<20 → 仓位×0.5，<30 → ×0.7）
- **短线专家估值权重提升**：徐翔/赵老哥/养家/作手新一估值权重从 5-8% 统一提升至 12%
- **估值数据注入**：`technical.py` 和 `stock_analysis.py` 自动计算 PE 行业分位并注入 features

### Changed

- 短线组专家情绪/技术面权重相应下调（总权重保持 100%）
- 专家 md 文件权重表同步更新

### Documentation

- 全量更新文档同步至 v1.10.0 / 9 skill 结构

## [1.10.0] - 2026-06-15

### Added

- **Skill 整合 13→9**：`/technical` 合并至 `/stock technical`、`/stock-init` 合并至 `/screener init`、`/financial-analyst` + `/investment-researcher` 合并至 `/research`（旧命令保留为 redirect stub，自动跳转）
- **估值增强**：估值因子评分逻辑优化，PE/PB 缺失时对称处理
- **置信度调整**：`compute_confidence_index()` 公式优化，校准贡献上限 ±10 分
- **dev**: 版本自动同步机制

### Changed

- 全量文档同步至 9 skill 结构（README / workflow / user-guide / developer-guide / product-architecture / skill-catalog / SUMMARY.md）
- CHANGELOG 清理重复 [Unreleased] 段，合并为正式 release

### CI/CD

- 优化所有 GitHub Actions 工作流
- 添加 CHANGELOG 自动更新工作流

### Maintenance

- 更新测试版本号和 skill 列表到 1.10.0
- 同步所有版本号到 1.10.0

## [1.9.0] - 2026-06-15

### Added

- **新手引导流程**：帮助用户快速上手
- **专家意见卡片化**：简洁展示投票结果
- **持仓日报推送**：自动生成日报并通知（`scripts/portfolio/daily_report.py`）
- **监控分级推送**：支持 urgent/important/normal 三级（`scripts/monitor/alert_engine.py`）
- **术语解释**：自动检测并解释专业术语
- **风险提示增强**：在输出末尾添加风险提示
- **数据导出 CSV**：支持导出分析结果
- **学习路径**：系统化投资学习教程（`skills/learn/SKILL.md`）
- **情绪温度计**：计算市场情绪指数（`scripts/technical/sentiment.py`）
- **专家逻辑透明**：展示评分推理链
- **长期持有评估**：评估股票是否适合长期持有（`scripts/technical/long_term.py`）
- **portfolio_web.py 拆分**：1289 行拆分为 5 个模块（`scripts/portfolio/web/`）
- **GitHub Release 自动化**：优化 release workflow，新增一键发布脚本

### Fixed

- **新浪 volume 归一化**：修正成交量计算并优化涨跌停检测
- **refresh_pool 全市场获取**：修复从 260 只恢复到 5296 只股票

## [1.8.0] - 2026-06-15

### Added

- **模拟盘（虚拟持仓）**：
  - `PortfolioManager(path, virtual=True)`：虚拟持仓模式，数据存储在 `portfolio_virtual.json`（与实盘隔离）
  - `portfolio_web.py --virtual`：Web 服务支持虚拟/实盘切换
  - `PortfolioManager.is_virtual` / `portfolio_type` / `data_path` 属性
  - `skills/portfolio/SKILL.md`：虚拟持仓文档和使用说明

- **事件日历模块**：
  - `scripts/events.py`：个股事件查询（财报披露、限售解禁、分红）
  - `fetchers/eastmoney_event.py`：东方财富事件日历数据源（已有，新增 CLI 入口）
  - `skills/stock/SKILL.md`：事件日历文档

- **统一输出模板**：
  - `scripts/common/formatters.py`：统一格式化工具（首行结论 + 尾行数据源 + 时间戳）
  - `skills/_shared/references/output-template.md`：12 skill 共用模板规范
  - 12 个 SKILL.md 全部更新：Instructions 段加入模板引用

- **专家合规隔离**：
  - `experts/registry.py`：`LEGACY_ALIAS` 表 + `get_display_name()` 函数
  - 支持未来"虚构化"专家名称，不影响评分函数和 decide.py

- **校准数据同步**：
  - `scripts/calibration_sync.py`：GitHub Gist 双向同步（`--pull` / `--push` / `--auto` / `--status`）
  - 依赖 gh CLI，零 Python 三方依赖

- **专家圆桌胜率卡片**：
  - `experts/decide.py`：`format_debate_output()` 尾部自动附加校准胜率表
  - 样本不足时显示"样本不足，参考价值有限"

- **数据源证据链**：
  - `scripts/common/formatters.py`：`collect_source_evidence()` 工具函数
  - 自动从 fetcher 结果中收集成功/失败源列表

- **回测胜率附加**：
  - `scripts/stock.py --with-backtest`：附加近 60 日回测胜率（win_rate / total_return / sharpe / max_drawdown）
  - `skills/stock/SKILL.md`：--with-backtest 文档

- **结构化 JSON 日志**：
  - `scripts/monitor.py --log-json`：输出完整 JSON（timestamp / cache / sources / summary）
  - `scripts/monitor.py --sources`：升级为表格化健康度矩阵（名称/优先级/状态/失败次数/熔断状态）

- **自审计脚本**：
  - `scripts/dev/check_allowed_tools.py`：SKILL.md vs settings.json 一致性检查
  - `.github/workflows/ci.yml`：接 CI 自动阻断 PR

- **场景化帮助**：
  - `skills/help/SKILL.md`：5 个场景入口（找机会/看大盘/看持仓/深度研究/看板块）

- **property-based 测试**：
  - `tests/test_scoring_properties.py`：13 个 hypothesis 测试（direction_from_score / compute_confidence_index / score_from_dimensions / detect_market_state）

- **mdBook 文档站**：
  - `docs/book.toml` + `docs/src/`：mdBook 配置和页面
  - `.github/workflows/docs.yml`：GitHub Pages 自动部署
  - `docs/tutorials/walkthrough-600519.md`：12 skill 完整演练教程

- **用户画像**：
  - `docs/persona.md`：3 类核心用户画像（散户/学习者/量化爱好者）

- **CHANGELOG 生成器**：
  - `scripts/dev/gen_changelog.py`：Conventional Commits → CHANGELOG 自动生成

- **mypy strict 增量**：
  - `mypy.ini`：common/ 子包 strict 模式
  - `scripts/common/` 全模块类型注解修复（cache / http / utils / parsers / metrics / exceptions / `__init__.py`）

### Changed

- `skills/screener/SKILL.md`：5 个策略名加小白注释（"啥都来点"/"找便宜的好公司"等）
- `skills/portfolio/SKILL.md`：`rebalance` 加别名"调仓建议"
- `scripts/portfolio_web.py`：`--open` 改为默认行为（`--no-open` 可禁用）
- `.github/workflows/ci.yml`：覆盖率门槛 60% → 70%、增加 ruff 静态检查、增加自审计步骤
- `scripts/monitor.py`：重构为结构化输出（check_cache_status / check_sources 返回 dict）

### Fixed

- `skills/screener/SKILL.md`：路径 `data/sector_stocks.json` → `scripts/data/sector_stocks.json`
- `.claude/settings.json`：补齐 `init_pool.py` / `refresh_pool.py` / `patterns_local.py` / `classifier.py` / `events.py` / `calibration_sync.py` 权限
- `tests/test_skill_consistency.py`：`portfolio_virtual.json` 加入 RUNTIME_DATA_FILES 白名单
- `docs/implementation-plan-2026-q3-q4.md`：fenced code block 加 language 标识

## [1.7.0] - 2026-06-12

### Added

- 专家圆桌决策引擎 `experts/decide.py`（decide.md 代码化）：
  - `detect_market_state()`：市场环境检测（牛市/熊市/震荡/冰点/亢奋），基于价格均线偏移、量能比、市场宽度指标综合判定
  - `aggregate_votes()`：8 位专家加权投票聚合，整合市场状态权重 × 投资期限权重，输出净多/净空/方向/强度/共识度/仓位建议/信心指数
  - `aggregate_group_votes()`：长线-only / 短线-only 单组模式投票聚合（decide.md §七）
  - `format_debate_output()`：结构化辩论报告格式化，含方向分布、共识评估、仓位上沿/下沿
  - `_MARKET_WEIGHTS` / `_HORIZON_WEIGHTS`：双权重矩阵（市场状态 × 投资期限），支持短线/中线/长线三种周期
  - `_market_state_reason()`：把市场状态判定结果翻译成一句话自然语言（"指数在均线上方，量能放大…"），便于 debate 输出回显给用户
  - 冲突解决（decide.md §三）：双一致看多/空、长线主导、短线主导、巴菲特否决权（中长期模式）、养家情绪周期降权/冰点特殊处理
- 单元测试 `tests/test_decide.py`（486 行）：market_state / aggregate_votes / format_output 全链路覆盖，含判势多场景、冰点孤例、共识判断置信边界、全零输入防护
- 数据层动态线程数与分类型缓存：
  - `scripts/data/config.py::DataConfig.max_workers`：动态计算（`cpu_count * 2`，下界 8，上界 32），替代旧硬编码 8 线程
  - 分类型缓存 TTL：`quote_cache_ttl`（盘后 900s）/ `intraday_quote_cache_ttl`（盘中 90s）/ `kline_cache_ttl`（6h）/ `finance_cache_ttl`（6h）/ `margin_cache_ttl`（1h）/ `ann_cache_ttl`（30min）等均按数据类型差异化
  - `scripts/common/utils.py::FetcherConfig` dataclass：统一 Fetcher 配置契约（`max_workers` / `timeout` / `retries`）
  - 错误透传机制：Fetcher 级异常统一包装为 `DataError`，携带原始异常链（`__cause__`），便于定位上游数据源问题
- 文档一致性与用户专家审查修复（P0-P3 全部）：
  - `skills/_shared/references/alert-thresholds.md`：新增预警与告警阈值共享表，`portfolio` 和 `monitor` 共用同一份权威源
  - 12 个 SKILL.md 全量深度审查修复（P0-P2 问题）
  - `skills/help/SKILL.md`："高级子模式速查"表 + "9 个 skill" → "12 个 skill" 修正
  - `skills/stock/SKILL.md`：`/stock` 参数默认行为明确、短线团专家首次出现补全全名、calibration 步骤加版本说明
  - `skills/portfolio/SKILL.md`：数据路径修正（4 处）、allowed-tools 增补、rebalance 模式联动作业说明
  - `workflow.md`：决策门槛表加"触发 skill"列
  - 新增 `docs/user-guide.md` 用户指南文档

### Changed

- `scripts/screener.py`：同步 `data/__init__.py` 动态线程 API，分类型缓存适配
- `tests/test_business.py` / `tests/test_screener.py`：同步新配置接口与缓存策略

### Fixed

- 文档一致性与用户跑不下去的坑（用户专家审查报告 P0 必修）
  - `skills/stock/SKILL.md`：移除 `debate (默认全模式)` 的双重"默认"声明，附提示"需要专家圆桌必须显式写 `debate`"
  - `skills/portfolio/SKILL.md`（4 处）+ `skills/monitor/SKILL.md`（2 处）：数据路径 `data/portfolio.json` → `scripts/data/portfolio.json`（与实际文件位置一致）
  - `skills/portfolio/SKILL.md`：`allowed-tools` 增补 `Bash(lsof -i:8765 *)` 与 `web --status` 内部命令对齐
  - `skills/stock/SKILL.md`：短线团专家首次出现补全为"**炒股养家**（养家）"，跨文档统一
  - `skills/stock/SKILL.md`：第 5 步 `calibration` 记录加"需要 1.6.0+" 版本说明
  - `workflow.md`：决策门槛表加"触发 skill"列，绑定每条门槛的主动核对 / 先行调用方

## [1.6.0] - 2026-06-12

### Added

- 专家评分硬编码体系（替代 LLM 推理 markdown）：
  - `experts/scoring.py::score_expert_precise()`：8 位专家专属评分函数（`_score_buffett` / `_score_lynch` / `_score_soros` / `_score_duan_yongping` / `_score_xu_xiang` / `_score_zhao_laoge` / `_score_chaogu_yangjia` / `_score_zuoshou_xinyi`），精确复现 `experts/*.md §九` 评分矩阵阈值规则，输出量化基线参考；缺失函数自动回退到 `score_expert` 并标记 `method="fallback"`
  - `experts/scoring.py::compute_confidence_index()`：信心指数计算含校准因子（公式 `consistency*0.35 + composite*0.55 + cal*0.1`，校准贡献上限 ±10 分）
- 校准数据自动回写机制：
  - `experts/calibration.py`：`record_prediction` / `verify_predictions` / `get_calibration` / `get_pending_predictions` / `compute_calibration_factor` / `get_calibration_report` 6 个 API，落地 `data/expert_calibration.json`，`tempfile.mkstemp + os.replace` 原子写入并发安全；同日同股按 `pred_YYYYMMDD_<code>` ID 去重覆盖
  - `scripts/calibration.py` CLI 入口：`record` / `verify` / `report` / `pending` 4 个子命令
  - 校准因子归一化到 `[-1, 1]`，公式 `mean × (1 − min(CV, 0.5))`
- 全市场股票池支持（~5000 只 A 股全覆盖）：
  - `scripts/refresh_pool.py::fetch_all_market_stocks()`：按板块归档到 `data/all_stocks.json`（主板沪 / 主板深 / 创业板 / 科创板 / 北交所），分页 `page_size=5000`，排除 ST 与未分类板块
  - `--full-market` 参数在 `refresh_pool.py` / `screener.py` / `init_pool.py` 三处贯通：refresh 拉取并保存全量、screener 加载全市场 universe 后预筛、init 智能跳过已存在数据（除非 `--force`）
  - `scripts/screener.py::load_full_market_universe(boards=None)` + `_BOARD_KEY_MAP`：按 `board_type()` 映射到 all_stocks.json 键名，支持子集筛选
  - `scripts/screener.py::pre_screen_quotes()`：大池高效预筛，复用 `refresh_pool.FILTER` 统一阈值（成交额 主板 5000 万 / 创业科创 3500 万 / 北交所 7500 万；总市值 主板 40 亿 / 创业科创 24 亿 / 北交所 16 亿），支持 `--board-limit` 按板块分桶截取
- 美股收盘数据接入（大盘分析新增美股参考板块）：
  - `scripts/fetchers/yfinance_quote.py::YfinanceQuoteFetcher`（priority=6）：基于 `yfinance` 包，识别 `us:` 前缀，未安装包时返回 `NOT_HANDLED`；字段对齐 `Quote` 数据类型（price/prev_close/change_pct/pe/pb/total_cap 等）
  - `scripts/fetchers/yfinance_kline.py` 同步支持 `us:` 前缀
  - `scripts/common/__init__.py::NOT_HANDLED` 哨兵值：与 `None` 失败语义区分，`DataFetcherManager.fetch` 遇到 `NOT_HANDLED` 跳过且不计熔断失败，A 股 / 美股跨域数据源安全共存
  - 典型用法：`python3 scripts/quote.py -j us:^gspc,us:^ixic,us:^dji,us:^vix,us:spy,us:qqq`（标普500 / 纳指 / 道指 / VIX / SPY / QQQ）
- npm 自动发布 workflow：
  - 新增 `.github/workflows/release.yml`：`v*` tag push 触发，Python 3.11/3.12 矩阵测试 → `npm publish` → `softprops/action-gh-release@v2` 创建 GitHub Release（`body_path: CHANGELOG.md` + `generate_release_notes`）
  - 需要配置 `NPM_TOKEN` secret；流程：`git tag v1.6.0 → git push --tags → 自动测试 → npm publish → GitHub Release`
- 单元测试新增 ~126 个：
  - `tests/test_calibration.py`（267 行）：record/verify/compute_factor/report 全链路覆盖
  - `tests/test_scoring.py`（338 行）：8 位专家专属评分函数边界测试
  - `tests/test_yfinance_us.py`（242 行）：US 前缀识别、NOT_HANDLED 短路、字段映射、熔断隔离 19 个用例
  - `tests/test_screener.py` 新增 `TestPreScreenQuotes` 和全市场 universe 用例

### Changed

- `skills/stock/SKILL.md` debate 流程新增 2 个步骤：
  - 「量化基线参考」：调用 `experts.scoring.score_expert_precise()` 获取量化分，与 LLM 推理分差 >15 时需说明分歧
  - 「记录校准数据」：debate 完成后调用 `python3 scripts/calibration.py record --stock <代码> --direction <方向> --scores '{...}'` 写入校准库；输出附带当前校准因子（示例 `校准因子: +0.15`）
- `skills/market/SKILL.md`：
  - 数据获取段加入美股收盘命令与 `us:` 前缀约定（`us:^gspc` = 标普500、`us:spy` = SPY ETF）
  - 新增「美股参考」段：包含 VIX 避险阈值、美股板块映射 A 股（科技→半导体、银行→金融）、美联储/美债收益率对北向资金影响
- `skills/stock-init/SKILL.md` / `skills/screener/SKILL.md` / `skills/help/SKILL.md`：同步 `--full-market` 命令与流程说明
- `package.json`：移除不存在的 `"main": "index.js"` 字段（避免 npm 安装时入口报错）
- `scripts/refresh_pool.py`：去重 `_infer_exchange` 推断逻辑，统一前缀生成路径

## [1.5.0] - 2026-06-11

### Added

- 回测模块新增 3 个核心指标：
  - `calmar_ratio`：卡玛比率（年化收益/最大回撤），衡量风险调整收益
  - `profit_loss_ratio`：盈亏比（平均盈利/平均亏损），衡量盈亏不对称性
  - `total_trades`：总交易次数，方便统计样本量
- 回测输出 JSON 格式已包含全部 11 个指标（策略/轮次/总收益/平均收益/最大收益/最小收益/胜率/夏普比率/最大回撤/卡玛比率/盈亏比/交易次数）

### Changed

- `scripts/backtest.py`：`run_backtest()` 函数新增指标计算逻辑

## [1.4.1] - 2026-06-11

### Added

- `portfolio_web.py` 启动时自动启用后台监控：每 300 秒扫描持仓+自选股关键点位，交易时段触发预警自动推送
- 新增 `/api/monitor` 端点：查询监控状态和最近预警结果
- Web 页面新增「📡 策略监控」面板：实时显示预警列表和推送状态
- 新增 `--no-monitor` / `--monitor-interval` 参数控制监控开关和频率
- 新增 `scripts/monitor/alert_engine.py`：策略信号引擎，计算持仓+自选股的关键点位（支撑/压力/MACD/均线/目标价），盘中触及即推送
- 新增 `/monitor scan` 命令：扫描全部持仓+自选股，输出关键点位集合
- 新增 `/monitor levels <code>` 命令：查看单股关键点位详情
- 新增 `/monitor check` 命令：盘中检查+推送（支持 `--dry-run` 预览模式）
- `scripts/config/notification.yaml` 新增 `strategy_alert` 配置块：支撑/压力位、目标买入/卖出价、MACD 金叉死叉、均线突破、涨跌停附近、止损止盈线

### Changed

- `skills/monitor/SKILL.md`：version 1.3.1 → 1.4.0，新增 scan/levels/check 命令说明和策略关键点位监控段落
- description 新增"策略关键点位扫描"能力描述

## [1.4.0] - 2026-06-11

### Added

- 新增 `scripts/portfolio_web.py`：零依赖 stdlib HTTP server（`ThreadingHTTPServer`），监听 `127.0.0.1:8765`，提供持仓/自选的 HTML 表单录入 + JSON Webhook API
- 新增 6 个路由：`GET /`、`GET /api/health`、`GET /api/positions`、`GET /api/positions/{code}`、`POST /api/positions`（`action` 分发）、`GET /favicon.ico`
- 新增 8 个 webhook action：`add_position` / `reduce_position` / `remove_position` / `update_position` / `tag_position` / `untag_position` / `add_watch` / `remove_watch`
- 业务坑点显式防护：`add_watch` 的 0 值陷阱 → 400；`update_position` tags 整列表覆盖 → 警告；`reduce_position(quantity<=0)` → 400
- HTML 表单内置本地股票名补全（扫 `data/portfolio.json` / `portfolio_example.json` / `sector_stocks.json`），不联网
- 新增 `tests/test_portfolio_web.py`：49 用例覆盖路由、action 校验、并发安全、端到端
- `tests/smoke_test.sh` 末尾追加段 7 冒烟用例（5 个断言：health / HTML 表单 / POST 落库 / GET 读出 / 405 校验）

### Changed

- `skills/portfolio/SKILL.md`：version 1.3.1 → 1.4.0，allowed-tools 新增 web 启动命令，正文加「Web 录入（可选）」段，Guardrails 增补并发写警告
- `README.md`：5 分钟上手段补充"本地 Web 录入"小节
- `.claude/settings.json`：`permissions.allow` 追加 `Bash(python3 scripts/portfolio_web.py *)`

## [1.3.3] - 2026-06-11

### Changed

- README 全面重构：PM / 用户专家 / 产品专家三维优化，体积从 20638 bytes 降至 ~8700 bytes（−58%）
- README 新增 Hero 段 + 4 个 status badge + 5 分钟上手最短路径 + 4 个典型场景（自上而下选股 / 诊断持仓 / 板块挖掘 / 深度研究）
- README 新增"12 个 skill 速查表"，按"决策/专家/环境/选股/组合/技术/验证/数据/研究/辅助"七大类分组，`stock-debate` 独立成行 + 🌟 视觉强调
- 4 个典型场景后追加特色功能 callout，点名 8 位投资专家为独特卖点
- GitHub 仓库地址统一为 `https://github.com/CurtisTong/stock-analyzer-skill`（README / CHANGELOG / package.json / plugin.json 全部对齐）

## [1.3.2] - 2026-06-10

### Added

- 新增 `skills/_shared/references/`：集中管理代码前缀、脚本目录、五层分析框架三份共享文档
- 新增 `skills/stock/reports/full-template.md`：stock 深度报告完整模板外移
- 新增 `tests/test_skill_metadata.py`：100 个 SKILL.md 元数据校验测试（frontmatter、description、章节、过期路径等）
- 新增 `scripts/stock.py` 五层分析 CLI（薄 CLI，路由到 `business.StockAnalysisService`）
- 新增 `experts/__init__.py` + `experts/registry.py`：8 位专家人设沉淀为 Python `ExpertProfile` 数据类 + `EXPERT_REGISTRY` 字典 + `direction_from_score()` / `apply_veto()` 等可调用 API
- 新增 `experts/scoring.py`：`score_from_dimensions()` 按权重加总 + `score_expert()` 启发式端到端打分
- 新增 `tests/test_business.py` (25)、`tests/test_monitor.py` (21)、`tests/test_portfolio.py` (34)、`tests/test_channels.py` (24)、`tests/test_experts.py` (40) 五份缺失层测试
- fetchers 新增 `get_fetchers_by_domain()` + `list_data_domains()` 查询 API（按 quote/kline/finance/flow/lhb/event/chip 数据域组织）

### Changed

- 12 个 SKILL.md 全面升级 frontmatter：新增 `version: 1.3.1` / `model` (haiku/sonnet/opus 按场景分配) / `allowed-tools` / 3 个命令式 skill 加 `disable-model-invocation: true`
- description 全面改写：从"硬编码 `/X` 触发句"升级为"能力 + 触发场景"（平均长度 110 → 116 字符）
- 删除 5 处过期路径表述 "当前 skill 目录到包根目录为 `../../..`"，统一为"Claude Code 工作目录即为项目根目录"
- 抽取 stock/market/sector/portfolio/financial-analyst/investment-researcher 的"数据获取"段为共享引用，消除 ~50 行重复
- `install.sh` 全局同步从 `cp -r` 改为 `ln -s`，单源真相
- `backtest` description 从 42 字符扩到 94，加入策略对比/胜率验证场景说明
- `screener.py::hard_filter` 改为 7 行适配器，业务逻辑全部下沉到 `business.ScreeningService._hard_filter`（包含完整 ST/退市/EPS/商誉/质押/涨跌停/板块差异化规则集）
- `screener.py::daily_features` 和 `business._compute_features` 中的量价信号统一复用 `technical.volume.volume_analysis`（消除三处重复实现）
- `technical/scoring.py` 改为从 `config/scoring.yaml` 读取 `_STOCK_TYPE_WEIGHTS` / `_MARKET_WEIGHT_ADJUSTMENTS` / `alignment_scores`（YAML 缺失时回退到代码内硬编码默认）
- `data/cache.py` 迁移到 `common/cache.py`，消除 common ↔ data 循环依赖（删除 30+ 行 `__getattr__` 魔术和延迟加载）
- `chan/macd.py` 重命名为 `chan/area.py`（消除与 `technical/macd.py` 的命名空间冲突）
- fetchers/`__init__.py` 按 7 个数据域分块注释 + `_DOMAIN_FACTORIES` 注册表

### Removed

- 删除 `scripts/api/`（quote_cli.py + screener_cli.py）：0 调用方，与顶层 `scripts/quote.py` / `scripts/screener.py` 重复
- 删除 6 个空目录遗存：`scripts/infrastructure/{data,http}/`、`tests/{fixtures,integration,mocks}/`、`tests/unit/{test_strategies,test_technical}/`
- 删除 `config/industry_thresholds.yaml`（4 行业 sample 死代码）+ `config.get_industry_threshold()`（0 调用方），单一数据源回退到 `data/industry_thresholds.json`
- 删除 `common/__init__.py` 中 30+ 行循环依赖处理代码（`__getattr__`、`_get_cache_module`、`_get_cache_items`）
- 删除 `screener.py` 中重复的 `_get_min_survival_cap` / `_get_goodwill_warning_threshold` / `_get_pledge_warning_threshold` / `_get_board_limit` 4 个辅助函数

### Fixed

- README/CLAUDE.md/plugin.json/marketplace.json 中 skill 数量从 8/11 混用统一为 12
- `plugin.json` / `marketplace.json` version 从 1.0.0/1.1.0 升到 1.3.1，与 package.json 对齐
- 旧 `init-pool` skill 不再在源目录存在（install.sh 重跑后自动清理残留）
- `business.StockAnalysisService._analyze_technical` 中 `kdj_full(closes)` 缺参数 bug（实际签名要求 `(closes, highs, lows)`）— 此前因 0 调用方未被暴露
- `chan/beichi.py` 中 `_ema_series(dif_series, 9)` 比 `dif_series` 短 8 元素导致 `list index out of range` — 此前因 0 调用方未被暴露
- `ScreeningService.screen()` 中 `quote_map` key 与 normalized_codes 不匹配的潜在 bug（用纯数字 code 作 key，但查找用 `sh/sz` 前缀，永远查不到）— 此前因 0 调用方未被暴露
- `experts/scoring.py` 评分模块 4 项修复：
  - `_score_fundamentals` 注释与��际权重不符（"加权"改为"均分"）
  - `_score_valuation` 在 pe/pb 都缺失时返回 0 而非 50（修复不对称边界）
  - `dimension_breakdown` 增加 0-100 clamp，与 `score_from_dimensions` 一致
  - "风险"维度评分逻辑反直觉，改为正面评分（基本面 40% + 估值安全 30% + 低负债 30%）

## [1.3.1] - 2026-06-10

### Added

- 新增雪球（`xueqiu_quote.py`）和同花顺（`ths_quote.py`）两个行情 Fetcher，行情源从 7 个扩展到 9 个
- 新增企业微信（`wechat.py`）和钉钉（`dingtalk.py`）webhook 告警通道，支持 markdown 与加签安全设置
- 新增资金面（筹码）数据模块：`scripts/data/chip.py` + `scripts/chip.py` CLI，集成融资融券/股东户数/十大流通股东三个数据源
- 评分引擎新增资金面因子（上限 +10 分，下限 -5 分），支持利空信号正确扣分

### Changed

- `chan.py`（591 行）重构为 `chan/` 包下的 9 个独立模块（merge/fenxing/bi/xianduan/zhongshu/macd/beichi/maidian/**init**），保持原有 API 向后兼容
- `backtest.py` 数据获取改为 8 线程并发，批量回测性能显著提升
- `monitor/health.py` 新增缓存清理（`--cleanup`）、最大文件数告警（默认 2000）和大小阈值告警（默认 500MB，可通过 `STOCK_CACHE_MAX_SIZE_MB` 环境变量调整）
- `FinanceRecord` 数据类型新增 `goodwill`（商誉，亿元）和 `pledge_ratio`（质押比例，%）字段

### Documentation

- 更新 `docs/optimization-report.md`：v1.3.1 技术架构优化实施报告
- 同步 `docs/product-architecture.md`、`docs/developer-guide.md` 数据源矩阵与技能清单

## [1.3.0] - 2026-06-10

### Added

- 新增预置默认股票池数据（`sector_stocks.default.json`），内置 14 个板块核心标的
- `init_pool.py` 新增 `--default` 参数，支持离线模式直接使用预置数据
- `refresh_pool.py` 新增 `--default` 参数，支持离线模式初始化
- API 失败时自动 fallback 到预置默认数据，确保零配置即可使用

### Changed

- `init_pool.py` 移除 token 硬性检查，无 token 时自动尝试免费访问或使用预置数据
- `refresh_pool.py` 移除 token 硬性检查，无 token 时也能正常工作
- 更新 `stock-init` skill 文档，说明免费数据源特性

### Documentation

- 更新 SKILL.md：新增 `--default` 参数说明和离线使用方式
- 更新 README.md：突出"零配置即可使用"特性
- 更新 CHANGELOG.md：记录本次变更

## [1.2.3] - 2026-06-09

### Changed

- 更新 `methodology.md`：策略权重更新为五因子模型，新增波动率因子权重配置
- 更新 `docs/product-architecture.md`：添加五因子详解表格，更新策略权重与代码一致

### Documentation

- 明确五因子模型：质量、估值、动量、流动性、波动率
- 添加各因子评分逻辑说明

## [1.2.2] - 2026-06-09

### Changed

- 更新 `workflow.md`：新增 monitor、stock-init、backtest、help 等 4 个 skill，扩展工作流至 12 个技能
- 更新技能速查表：添加决策门槛量化标准（监控告警、回测验证）

### Documentation

- 更新投资专家工作流：持仓实时监控链路、策略回测验证
- 完善交接字段与决策门槛

## [1.2.1] - 2026-06-09

### Changed

- 更新 `docs/product-architecture.md`：新增技术架构章节，添加三层架构设计、核心技术组件、数据源矩阵、行业差异化阈值表格
- 更新 `docs/developer-guide.md`：更新项目结构，添加 BaseFetcher/CircuitBreaker/DataFetcherManager 核心技术说明，扩展数据源架构文档

### Documentation

- 完善开发者指南中的扩展开发说明
- 添加健康检查和回测验证命令说明

## [1.1.0] - 2026-06-08

### Added

- 新增 `/help` skill，显示所有可用 skills 和使用说明
- 支持 `/stocks` 和 `/skills` 作为 `/help` 的别名
- 在 help 中包含工作流建议和使用示例

### Changed

- 将项目重构为 Claude Code plugin 格式
- 创建 `.claude-plugin/plugin.json` 和 `marketplace.json`
- 将 `.claude/skills/` 移动到 `skills/` 目录
- 更新 README.md 安装说明，支持 plugin 方式安装

### Fixed

- 优化 skill description 提高触发准确率

## [1.0.0] - 2026-06-05

### Added

- 初始版本发布
- 8 个股票分析 skills：
  - `/stock` - 单股分析（quick/full/debate 模式）
  - `/market` - 大盘复盘（full/quick/intraday 模式）
  - `/sector` - 板块分析（overview/compare/stock 模式）
  - `/portfolio` - 持仓健康检查（health/rebalance/compare 模式）
  - `/screener` - 多因子选股策略系统
  - `/technical` - 纯技术分析（quick/full 模式）
  - `/financial-analyst` - 财务分析 agent
  - `/investment-researcher` - 投资研究 agent
- 完整投资方法论（methodology.md）
- 8 人专家圆桌系统（巴菲特/林奇/索罗斯/段永平 + 徐翔/赵老哥/炒股养家/作手新一）
- 5 种选股策略（均衡精选/质量价值/成长动量/防守低波/拐点修复）
- 行业差异化阈值（金融/消费/科技/周期/医药/制造/能源/地产）
- 工具脚本（Python stdlib only）：
  - quote.py - 腾讯实时行情
  - finance.py - 东财财务数据
  - kline.py - 新浪 K 线
  - announcements.py - 东财公告/研报
  - screener.py - A 股多因子选股器
  - technical.py - 纯技术分析
  - classifier.py - 个股类型分类
  - chan.py - 缠论结构
  - patterns_local.py - A 股本土战法形态
- 静态参考数据：
  - sector_etf.csv - 板块 ETF 清单
  - sector_stocks.json - 板块核心标的库
  - portfolio_example.json - 持仓配置示例
- 端到端冒烟测试（tests/smoke_test.sh）
- 贡献指南（CONTRIBUTING.md）
- 工作流编排（workflow.md）

### Technical Details

- 零项目依赖：不引用任何业务项目内文件
- 零外部 Python 库：只用 stdlib（urllib + json + pathlib）
- 支持 Codex（.agents/skills/）和 Claude Code（.claude/skills/）两套入口
- 所有数据 API 在国内直连，无须代理

## [Unreleased]

### Planned

- 回测权重网格搜索优化
- 回测模拟实盘模式
- 港股深度支持
- 多语言（英文）输出
- 更多本土战法形态

---

## 版本说明

- **主版本号**：不兼容的 API 变更
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

## 链接

- [GitHub 仓库](https://github.com/CurtisTong/stock-analyzer-skill)
- [问题反馈](https://github.com/CurtisTong/stock-analyzer-skill/issues)
- [发布页面](https://github.com/CurtisTong/stock-analyzer-skill/releases)

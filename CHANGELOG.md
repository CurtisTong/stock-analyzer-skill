<!-- markdownlint-disable MD024 MD033 MD022 MD032 MD050 -->

# Changelog

> 🟢 **一句话**：想知道每次发版改了什么？看这里。
>
> 🟢 **当前状态**：v1.20.2（2026-08-13）mypy 白名单扩至 203 文件 + experts/config/dev 类型清零 + 修复 screener 主线偏离警告静默失效 bug + dcf/cyclical 双命名回归；v1.20.1（2026-08-12）screener 整体任务超时 watchdog + 新增 sector_summary CLI（akshare 同花顺 + 东财 push2 + sector_etf 拼接三级降级）。
>
> 🔴 **风险提示**：本文件描述技术变更；任何"投资策略/选股结果/仓位建议"均不构成投资建议。

## 📑 目录

- 当前版本速览（见下方表格）
- 完整变更（按版本向下滚动）
- 版本说明与链接（见文末）

---

## 当前版本速览

| 版本 | 日期 | 一句话变更 |
| --- | --- | --- |
| 1.20.2 | 2026-08-13 | mypy 白名单扩至 203 文件（10 目录 + 5 顶层脚本）+ experts/config/dev 类型清零 + 修复 screener 主线偏离警告静默失效 bug + dcf/cyclical 双命名冲突回归修复 |
| 1.20.1 | 2026-08-12 | screener 整体任务超时 watchdog + sector_summary CLI + CI 黑块修复（black 19 文件 / ruff F601+F821 / sector 授权 sector_summary）+ 数据快照 |
| 1.20.0 | 2026-08-08 | screener 三段式漏斗 + 板块模式放宽容差 + regime 新增 RANGE_CHOPPY + 高波震荡动量提权 + akshare 行业补全 fetcher + market 数据时效三档 + 涨跌停软校验 + research 信号冲突检测强化 + stock 宝丰 v2 报告 |
| 1.19.0 | 2026-08-05 | 数据源降级可观测性 + P1 健康度：monitor 新增 akshare 探活 + baostock IP 风险 + 跨源校验；五层分析 data_sources 透传真实数据源名；缓存命中双重归一化修复 + 18 项数据源/导入/API/格式 Bug |
| 1.18.0 | 2026-08-05 | 市场分析降级可观测性 + 来源追踪：涨跌停降级改用涨跌比定性、`_degraded` 标记透传、宏观字段 `*_source` 与 `[fixture]` 渲染标注、`/market` SKILL.md 4 段硬约束 |
| 1.17.0 | 2026-08-05 | 移除 `/monitor` CLI skill + 新增题材概念数据层 + FinanceRecord 存货字段 + 多种战法因子 + VWAP 监控 + 周期股期货修复 |
| 1.16.1 | 2026-08-03 | fetchers 深度审查 P0–P2 修复 27+3+4 项 + technical H/M/L 回归 + skill schema 清洗 + 测试/文档对齐 |
| 1.16.0 | 2026-07-28 | finance 域 WP1-WP6 重构 + tests 框架重构 + 止损破位检测 + 38 个 [Unreleased] 折叠 |
| 1.15.0 | 2026-07-09 | 多轮审查修复 + 文档同步 + 数据域补齐 |
| 1.14.2 | 2026-06-29 | 异常分类 + 输出模板统一 + backtest 解耦 + 文档对齐 |
| 1.14.0 | 2026-06-24 | 回测增强 + 估值模型 + 事件驱动 + 架构重构 |
| 1.13.0 | 2026-06-18 | 动量派专家 + 用户体验优化 + 10 模块深度审查 |
| 1.12.0 | 2026-06-17 | V2 量化策略平台 + V2.1 维护（合并历史 tag） |

> 💡 完整变更向下滚动。语义说明：🟢 已发版 / 🟡 待发版 / 🔴 风险提示 / ⚫ 数据事实。

## [1.20.2] - 2026-08-13（mypy 白名单扩至 203 文件 + experts/config/dev 类型清零 + screener 主线偏离警告静默失效 bug 修复 + dcf/cyclical 双命名回归）









### Added
- **docs**: 复盘元复盘问题清单 — [issues/2026-08-12-replay-meta-review.md](docs/issues/2026-08-12-replay-meta-review.md)（11 项 P0-P2，含 P0-01 screener 全市场超时、P0-02 sh/sz 前缀误判、P0-03 macro fixture 标注不全）
- **screener**: `--exclude-sector-momentum` 自动剔除退潮板块标的 + `sector_momentum_warning` ⚠️ 标记（P1-02，`scripts/sector_momentum.py`）
- **sector**: 行业 ETF 覆盖扩展 10→17（智能汽车/通信/人工智能/机器人/电力/家电/游戏）+ 盲区映射清零（P1-01a）
- **sector**: 新增 `scripts/data/stock_sector_map.json` 股票→细分行业映射（219 只 + 30 条行业→ETF 代理），板块归属来源链 stock_sector_map → sector_stocks → 代码段推断（P1-01b）
- **market**: industry_beta 新增 `interpretation_confidence`（R² 分级，低 R² 报独立行情）（P1-01c）
- **market**: 组合相关性窗口声明 + 双半窗口稳定性 + 负相关显著性/R² 感知 + `corr_confidence`（P1-04）
- **market**: 剧烈轮动期（rotation_strength>3）附加保守操作建议（P2-02）
- **portfolio**: 候选股与持仓行业重叠率 `compute_industry_overlap` + 30% 集中度预警（P2-04）
- **skills**: 报告长度硬约束——`guardrails.md` 新增表格上限（单报告 ≤3 张，quick ≤1 张）+ `output-template.md` 新增折叠披露机制（默认只渲染结论层，详细论证按需展开）（P2-03）
- **screener**: 数据预取阶段进度输出（`data_prefetch` 事件：行情/预筛/财务/完成）；JSON 模式进度走 stderr 不污染 stdout（P0-01 后续）
- **portfolio**: 实际组合总仓位 `compute_total_position_ratio`——`portfolio.json` 顶层可选 `total_assets`，成本/市值口径占比 + >90% 仓位过重警告，接入 `health_report`（P2-04 第 1 条）
- **strategies**: `valuation_score` 语义修复（P2-H6）——revenue/net_profit 仅用标准化字段（移除 TOTALOPERATEREVETZ 等原始键死回退）+ PEG 3 年 CAGR 优先（孤儿 TODO）+ PS 优先真实值（市值/营收）近似兜底
- **experts**: `_calibration_factor_from_rates` 新公式——(mean_rate-0.5)×2×(1-min(cv,0.5))，mean_rate=0.5（无信息）恒归零（P0-08）
- **portfolio**: `portfolio/crud.py` 新模块——全部 10 个 CRUD 写操作方法（add/reduce/remove/update/tag/untag + add/remove_watch）及 `_record_trade_log`/`_position_cost` 从 manager 整体搬移，manager 变一行委托 thin wrapper（-297 行），P2-P1 god-class 拆分 4/4 完成
- **test(circuit-breaker)**: 新增 `tests/unit/test_circuit_breaker.py` 14 项确定性测试——状态机全路径 + strict 恢复守卫 + 半开窗口期节流（配额耗尽拒绝/过期自动续期/`recovery_timeout=0` 拒绝续期）+ 并发下窗口内放行数严格 == half_open_max（v2.7 #2 窗口期逻辑固化）
- **common**: mypy 21 错误清零（v2.7 #1）——`_connection_pool` 实际存 `tuple[HTTPConnection, float]` 但标注 `list[HTTPConnection]`、`_parse_url` 返回顺序标错、`BaseFetcher.fetch` 返回类型补 `_NotHandled` 哨兵 + 4 处 identity check 改 `isinstance` 窄化、requests 响应 None 守卫、`key: str=None` 补 union、`value: Any`、unused `type: ignore` 与 atexit None 防御清理；**common/ 已纳入 CI + pre-commit mypy 白名单**（26 文件校验通过）
- **all**: mypy 白名单扩至 78 文件（v2.7 #1 扩展）——fetchers/ 43 + business/ 34 文件 50 错误清零：`from common import` 异常改从 `common.exceptions` 正确源导入、混合 dict 字面量显式 `dict[str, Any]`（stock_analysis/flow/_base_bulk 等）、`_NotHandled` 返回类型补全、`risk_warning` mapping 同名遮蔽拆 `mapping_int/mapping_str`、`is_st` 遮蔽改 `is_st_flag`、`kline_bars: list=None` 补 union、`benchmark_weights: dict|None` + assert 窄化；mypy.ini 为 strategies/refresh_pool 门面模块开 `implicit_reexport`，删除失效 experts section
- **portfolio/skills/tests**: Review 全量推进——review-issues 主表 44 项全部收敛（P0-01~15 权限/配置/CI/校准公式 + P1-01~30 fetcher 精确匹配与 is_minimal/净吞错/定时自动校准验证/龙虎榜与龙头横截面接入/缠论与 swing points/结构化 signals/市场环境指数行情/时间超时分层/hard filter 分离/historical VaR/ST 单轨/脚本-catalog 等；P2-P1 portfolio 4 模块拆分已 3/4）
- **all**: mypy 白名单扩至 212 文件（v2.7 #1 收尾 2026-08-13）——`chan/` 包清零纳入白名单（beichi.py result dict 显式 `dict[str, Any]` 标注，原 `list[Never]` + `zs.get` 类型污染 5 错误）；白名单 11 目录 + 5 顶层脚本

### Fixed
- **screener**: 修复主线偏离警告静默失效 bug——`_print_mainline_deviation_warning` 引用的 `SECTOR_ETFS`（sector_etf_strength **从未导出**，早已改名 SECTOR_ETF_CSV）被 `except Exception: return` 吞掉导致警告永久不生效，改用 `_load_sector_etfs()`
- **experts/config/dev**: 类型清零——`scoring/_utils` score float 标注、`vote_engine` 查找字典键 str 窄化、`momentum_trader` `module_from_spec` None 守卫、`calibration` `data.get_kline` 依赖路径、config `loader` value Any、dev `cross_validate_sources` `_NotHandled`/set 类型、`experts_cli` float 防御
- **screener**: watchdog 默认超时 600→1800s（P0-01a）
- **screener**: full_market 强制走两阶段管线（Phase1 无 K 线粗筛 + Phase2 TopN 精排），解决全市场超时（P0-01b）
- **data**: K 线本地磁盘缓存验证（P0-01c）——`get_kline`/`prefetch_kline_all` 已接 common.cache（key 含 code+scale+datalen，日 K 1h TTL），新增 `test_kline_cache_p001c` 3 项验证缓存命中与参数隔离
- **data**: `infer_exchange` 002/003 段强制判 sz，修复 sh002920 等误冠前缀导致整链路静默空输出（P0-02）
- **market**: macro 字段全部追加 `_source` + 渲染 `[fixture]` 标注 + fixture 时结论置信度降级（P0-03 a/b/c）
- **portfolio**: 成本来源 `cost_source`（screenshot/user_input/calculated）+ oplog 记录 `cost_before/cost_after`（P1-03）
- **skills**: screener SKILL 增加"用 screener 前先跑 /market、/sector 确认板块状态"提示（P1-02b）
- **skills**: sector SKILL 回避名单分类——"业绩反转陷阱"标记观察而非回避 + 反转触发条件（P2-01）
- **market**: 修复 black 26.5.1 在 py3.14 下将 `except (ValueError, TypeError)` 破坏为 py2 语法的回归（`market_anchor.py`）

### Maintenance
- **release**: v1.20.1 版本号同步 + CI 黑块修复 + 板块授权 + changelog 整理

### Added
- **portfolio**: 实际组合总仓位 compute_total_position_ratio + health_report 接入（P2-04 第 1 条）
- **screener**: 数据预取阶段进度输出——JSON 模式走 stderr 不污染 stdout，K 线精排慢/卡可见（P0-01 后续）

### Fixed
- **types**: chan/ 模块 mypy 清零（beichi result dict 显式标注）并纳入白名单，白名单扩至 212 文件（v2.7 #1）
- **types**: mypy 白名单扩至 203 文件（10 目录 + 5 顶层）+ experts/config/dev 清零 + 修复 screener SECTOR_ETFS 静默失效与 dcf 双命名回归（v2.7 #1 收尾）
- **types**: fetchers/business mypy 50 错误清零 + strategies/refresh_pool reexport 配置 + 纳入 CI 白名单（v2.7 #1 扩展）
- **common**: mypy 21 错误清零（连接池/parse_url 标注、哨兵 isinstance、响应 None 守卫、atexit 防御）+ 纳入 CI/pre-commit 白名单（v2.7 #1）
- **technical**: P1-14 swing points 加 past-only confirm 模式 + P1-13/16 状态补记
- **experts**: P1-08 4:1 边界矩阵 + P1-10 verify --quiet + P1-11 zhao_laoge 龙虎榜/龙头排名接入 + 状态补记(P1-06/07/09)
- **fetchers**: P1-02 ths quote 加 is_minimal 标记 + P1-01/03/04/05 状态补记
- P0 组推进——校准公式无信息归零(P0-08)、CI 测试单一来源(P0-13)、sync boundary(P0-15)、权限收紧(P0-01)+状态补记(P0-02/12/14)
- **strategies**: valuation_score——PEG 3 年 CAGR 优先 + PS 真实市值/营收优先，保持双格式兼容（P2-H6）
- **data**: K 线本地缓存验证——get_kline/prefetch_kline_all 已接 common.cache，新增缓存命中测试（P0-01c）
- **portfolio**: cost_source 追溯 + 相关性窗口/显著性 + 行业重叠率（P1-03/P1-04/P2-04）
- **market**: 代码前缀 002/003→sz + macro 来源标注 + beta 置信度 + ETF 覆盖扩展 + 板块归属映射 + 轮动保守建议（P0-02/P0-03/P1-01/P2-02）
- **screener**: watchdog 超时 1800s + full_market 强制两阶段 + 退潮板块过滤（P0-01/P1-02）

### Changed
- **portfolio**: PortfolioManager CRUD 方法拆至 portfolio/crud 模块，manager 变 thin wrapper（P2-P1）

### Documentation
- **changelog**: 记录 chan/ 包纳入 mypy 白名单（212 文件）
- **changelog**: v2.7 #1 收尾记录——mypy 白名单扩至 203 文件 + screener 主线警告静默失效 bug 修复 + dcf/cyclical 双命名回归
- **review-issues**: v2.7 #4 coverage 评估记录——低 ROI 维持现状
- **review-issues**: v2.7 #1 白名单扩展至 78 文件记录 + CHANGELOG 补录
- **review-issues**: v2.7 #1 标记完成（common/ mypy 21 错误清零 + CI 白名单）+ CHANGELOG 补录
- **review-issues**: P2-P1 标记完成（crud 拆分 4/4）+ CHANGELOG 补 v2.7 #2 与 crud 条目
- **review-issues**: 主表全量状态收敛——批量补记 12 项修复标记（6 列行修复脚本 bug）+ CHANGELOG 汇总
- **review-issues**: P1-24/25/28/29 skills/CI 组状态补记
- **review-issues**: P1-17/18/19/20/21/22 business 组状态补记（均已验证已修）
- **review-issues**: 补记 P0-05/06/03/04/07/09 已修复状态（基于代码+gittest 验证）
- **review**: 补齐修复 commit hash + full_market 端到端验证观察记录
- **skills**: 报告长度硬约束——表格上限 + 折叠披露（P2-03）
- **review**: 元复盘问题清单 + CHANGELOG 汇总 + screener/sector SKILL 指引（P1-02b/P2-01）

### Testing
- **circuit-breaker**: 新增 14 项确定性测试固化半开窗口期节流语义（v2.7 #2）
- **portfolio**: 健康检查测试注入临时持仓，隔离真实用户 portfolio.json 数据耦合

### Fixed
- **types**: chan.py 兼容层加 mypy attr-defined 禁用注释，实现 standalone 零错误（白名单命令保持 chan/ 目录覆盖其逻辑）
- **types**: chan/ 模块 mypy 清零（beichi result dict 显式标注）并纳入白名单，白名单扩至 212 文件（v2.7 #1）
- **types**: mypy 白名单扩至 203 文件（10 目录 + 5 顶层）+ experts/config/dev 清零 + 修复 screener SECTOR_ETFS 静默失效与 dcf 双命名回归（v2.7 #1 收尾）
- **types**: fetchers/business mypy 50 错误清零 + strategies/refresh_pool reexport 配置 + 纳入 CI 白名单（v2.7 #1 扩展）
- **common**: mypy 21 错误清零（连接池/parse_url 标注、哨兵 isinstance、响应 None 守卫、atexit 防御）+ 纳入 CI/pre-commit 白名单（v2.7 #1）
- **technical**: P1-14 swing points 加 past-only confirm 模式 + P1-13/16 状态补记
- **experts**: P1-08 4:1 边界矩阵 + P1-10 verify --quiet + P1-11 zhao_laoge 龙虎榜/龙头排名接入 + 状态补记(P1-06/07/09)
- **fetchers**: P1-02 ths quote 加 is_minimal 标记 + P1-01/03/04/05 状态补记
- P0 组推进——校准公式无信息归零(P0-08)、CI 测试单一来源(P0-13)、sync boundary(P0-15)、权限收紧(P0-01)+状态补记(P0-02/12/14)
- **strategies**: valuation_score——PEG 3 年 CAGR 优先 + PS 真实市值/营收优先，保持双格式兼容（P2-H6）
- **data**: K 线本地缓存验证——get_kline/prefetch_kline_all 已接 common.cache，新增缓存命中测试（P0-01c）
- **portfolio**: cost_source 追溯 + 相关性窗口/显著性 + 行业重叠率（P1-03/P1-04/P2-04）
- **market**: 代码前缀 002/003→sz + macro 来源标注 + beta 置信度 + ETF 覆盖扩展 + 板块归属映射 + 轮动保守建议（P0-02/P0-03/P1-01/P2-02）
- **screener**: watchdog 超时 1800s + full_market 强制两阶段 + 退潮板块过滤（P0-01/P1-02）

### Documentation
- **review-issues**: v2.7 #1 边界既有结论 + P2-P5 env 补齐闭环 + P0-01 阶段进度闭环记录
- **changelog**: 记录 chan/ 包纳入 mypy 白名单（212 文件）
- **changelog**: v2.7 #1 收尾记录——mypy 白名单扩至 203 文件 + screener 主线警告静默失效 bug 修复 + dcf/cyclical 双命名回归
- **review-issues**: v2.7 #4 coverage 评估记录——低 ROI 维持现状
- **review-issues**: v2.7 #1 白名单扩展至 78 文件记录 + CHANGELOG 补录
- **review-issues**: v2.7 #1 标记完成（common/ mypy 21 错误清零 + CI 白名单）+ CHANGELOG 补录
- **review-issues**: P2-P1 标记完成（crud 拆分 4/4）+ CHANGELOG 补 v2.7 #2 与 crud 条目
- **review-issues**: 主表全量状态收敛——批量补记 12 项修复标记（6 列行修复脚本 bug）+ CHANGELOG 汇总
- **review-issues**: P1-24/25/28/29 skills/CI 组状态补记
- **review-issues**: P1-17/18/19/20/21/22 business 组状态补记（均已验证已修）
- **review-issues**: 补记 P0-05/06/03/04/07/09 已修复状态（基于代码+gittest 验证）
- **review**: 补齐修复 commit hash + full_market 端到端验证观察记录
- **skills**: 报告长度硬约束——表格上限 + 折叠披露（P2-03）
- **review**: 元复盘问题清单 + CHANGELOG 汇总 + screener/sector SKILL 指引（P1-02b/P2-01）

### Fixed
- **types**: 新增 CI/pre-commit mypy CLI 层检查（22 个顶层脚本）+ strategy_performance/perf_bench 改从 backtest 子模块精确导入（v2.7 #1 全仓覆盖）
- **types**: chan.py 兼容层加 mypy attr-defined 禁用注释，实现 standalone 零错误（白名单命令保持 chan/ 目录覆盖其逻辑）
- **types**: chan/ 模块 mypy 清零（beichi result dict 显式标注）并纳入白名单，白名单扩至 212 文件（v2.7 #1）
- **types**: mypy 白名单扩至 203 文件（10 目录 + 5 顶层）+ experts/config/dev 清零 + 修复 screener SECTOR_ETFS 静默失效与 dcf 双命名回归（v2.7 #1 收尾）
- **types**: fetchers/business mypy 50 错误清零 + strategies/refresh_pool reexport 配置 + 纳入 CI 白名单（v2.7 #1 扩展）
- **common**: mypy 21 错误清零（连接池/parse_url 标注、哨兵 isinstance、响应 None 守卫、atexit 防御）+ 纳入 CI/pre-commit 白名单（v2.7 #1）
- **technical**: P1-14 swing points 加 past-only confirm 模式 + P1-13/16 状态补记
- **experts**: P1-08 4:1 边界矩阵 + P1-10 verify --quiet + P1-11 zhao_laoge 龙虎榜/龙头排名接入 + 状态补记(P1-06/07/09)
- **fetchers**: P1-02 ths quote 加 is_minimal 标记 + P1-01/03/04/05 状态补记
- P0 组推进——校准公式无信息归零(P0-08)、CI 测试单一来源(P0-13)、sync boundary(P0-15)、权限收紧(P0-01)+状态补记(P0-02/12/14)
- **strategies**: valuation_score——PEG 3 年 CAGR 优先 + PS 真实市值/营收优先，保持双格式兼容（P2-H6）
- **data**: K 线本地缓存验证——get_kline/prefetch_kline_all 已接 common.cache，新增缓存命中测试（P0-01c）
- **portfolio**: cost_source 追溯 + 相关性窗口/显著性 + 行业重叠率（P1-03/P1-04/P2-04）
- **market**: 代码前缀 002/003→sz + macro 来源标注 + beta 置信度 + ETF 覆盖扩展 + 板块归属映射 + 轮动保守建议（P0-02/P0-03/P1-01/P2-02）
- **screener**: watchdog 超时 1800s + full_market 强制两阶段 + 退潮板块过滤（P0-01/P1-02）

### Documentation
- **review-issues**: v2.7 #1 记录 CLI 层 mypy 命令（22 脚本）+ P2-P5 .env.example 入库闭环
- **config**: .env.example 入库（.gitignore 加例外保留真实 .env 忽略）——补全 STOCK_DEBUG/STOCK_SCREENER_DEADLINE，16 个消费 env 变量全部声明，新用户可感知（P2-P5）
- **review-issues**: v2.7 #1 边界既有结论 + P2-P5 env 补齐闭环 + P0-01 阶段进度闭环记录
- **changelog**: 记录 chan/ 包纳入 mypy 白名单（212 文件）
- **changelog**: v2.7 #1 收尾记录——mypy 白名单扩至 203 文件 + screener 主线警告静默失效 bug 修复 + dcf/cyclical 双命名回归
- **review-issues**: v2.7 #4 coverage 评估记录——低 ROI 维持现状
- **review-issues**: v2.7 #1 白名单扩展至 78 文件记录 + CHANGELOG 补录
- **review-issues**: v2.7 #1 标记完成（common/ mypy 21 错误清零 + CI 白名单）+ CHANGELOG 补录
- **review-issues**: P2-P1 标记完成（crud 拆分 4/4）+ CHANGELOG 补 v2.7 #2 与 crud 条目
- **review-issues**: 主表全量状态收敛——批量补记 12 项修复标记（6 列行修复脚本 bug）+ CHANGELOG 汇总
- **review-issues**: P1-24/25/28/29 skills/CI 组状态补记
- **review-issues**: P1-17/18/19/20/21/22 business 组状态补记（均已验证已修）
- **review-issues**: 补记 P0-05/06/03/04/07/09 已修复状态（基于代码+gittest 验证）
- **review**: 补齐修复 commit hash + full_market 端到端验证观察记录
- **skills**: 报告长度硬约束——表格上限 + 折叠披露（P2-03）
- **review**: 元复盘问题清单 + CHANGELOG 汇总 + screener/sector SKILL 指引（P1-02b/P2-01）

### Documentation
- **tasks**: 新增 docs/next-tasks.md——后续任务详细描述与适配场景（P0 experts/ mypy 入库·0.5h 零改动，基于 2026-08-13 实测 MYPYPATH 根因）
- **review-issues**: v2.7 #1 记录 CLI 层 mypy 命令（22 脚本）+ P2-P5 .env.example 入库闭环
- **config**: .env.example 入库（.gitignore 加例外保留真实 .env 忽略）——补全 STOCK_DEBUG/STOCK_SCREENER_DEADLINE，16 个消费 env 变量全部声明，新用户可感知（P2-P5）
- **review-issues**: v2.7 #1 边界既有结论 + P2-P5 env 补齐闭环 + P0-01 阶段进度闭环记录
- **changelog**: 记录 chan/ 包纳入 mypy 白名单（212 文件）
- **changelog**: v2.7 #1 收尾记录——mypy 白名单扩至 203 文件 + screener 主线警告静默失效 bug 修复 + dcf/cyclical 双命名回归
- **review-issues**: v2.7 #4 coverage 评估记录——低 ROI 维持现状
- **review-issues**: v2.7 #1 白名单扩展至 78 文件记录 + CHANGELOG 补录
- **review-issues**: v2.7 #1 标记完成（common/ mypy 21 错误清零 + CI 白名单）+ CHANGELOG 补录
- **review-issues**: P2-P1 标记完成（crud 拆分 4/4）+ CHANGELOG 补 v2.7 #2 与 crud 条目
- **review-issues**: 主表全量状态收敛——批量补记 12 项修复标记（6 列行修复脚本 bug）+ CHANGELOG 汇总
- **review-issues**: P1-24/25/28/29 skills/CI 组状态补记
- **review-issues**: P1-17/18/19/20/21/22 business 组状态补记（均已验证已修）
- **review-issues**: 补记 P0-05/06/03/04/07/09 已修复状态（基于代码+gittest 验证）
- **review**: 补齐修复 commit hash + full_market 端到端验证观察记录
- **skills**: 报告长度硬约束——表格上限 + 折叠披露（P2-03）
- **review**: 元复盘问题清单 + CHANGELOG 汇总 + screener/sector SKILL 指引（P1-02b/P2-01）

### CI/CD
- **types**: 新增 mypy experts 层检查（MYPYPATH=scripts 29 文件全绿，规避根目录 data/ namespace 遮蔽 scripts/data/）——P0-A

### Maintenance
- **ignore**: 忽略运行时缓存 macro_snapshot.json（测试后 git status 不再脏）

### Documentation
- **tasks**: 标记任务 A/D 完成，P0 与 P1-D 收口
- **tasks**: 新增 docs/next-tasks.md——后续任务详细描述与适配场景（P0 experts/ mypy 入库·0.5h 零改动，基于 2026-08-13 实测 MYPYPATH 根因）
- **review-issues**: v2.7 #1 记录 CLI 层 mypy 命令（22 脚本）+ P2-P5 .env.example 入库闭环
- **config**: .env.example 入库（.gitignore 加例外保留真实 .env 忽略）——补全 STOCK_DEBUG/STOCK_SCREENER_DEADLINE，16 个消费 env 变量全部声明，新用户可感知（P2-P5）
- **review-issues**: v2.7 #1 边界既有结论 + P2-P5 env 补齐闭环 + P0-01 阶段进度闭环记录
- **changelog**: 记录 chan/ 包纳入 mypy 白名单（212 文件）
- **changelog**: v2.7 #1 收尾记录——mypy 白名单扩至 203 文件 + screener 主线警告静默失效 bug 修复 + dcf/cyclical 双命名回归
- **review-issues**: v2.7 #4 coverage 评估记录——低 ROI 维持现状
- **review-issues**: v2.7 #1 白名单扩展至 78 文件记录 + CHANGELOG 补录
- **review-issues**: v2.7 #1 标记完成（common/ mypy 21 错误清零 + CI 白名单）+ CHANGELOG 补录
- **review-issues**: P2-P1 标记完成（crud 拆分 4/4）+ CHANGELOG 补 v2.7 #2 与 crud 条目
- **review-issues**: 主表全量状态收敛——批量补记 12 项修复标记（6 列行修复脚本 bug）+ CHANGELOG 汇总
- **review-issues**: P1-24/25/28/29 skills/CI 组状态补记
- **review-issues**: P1-17/18/19/20/21/22 business 组状态补记（均已验证已修）
- **review-issues**: 补记 P0-05/06/03/04/07/09 已修复状态（基于代码+gittest 验证）
- **review**: 补齐修复 commit hash + full_market 端到端验证观察记录
- **skills**: 报告长度硬约束——表格上限 + 折叠披露（P2-03）
- **review**: 元复盘问题清单 + CHANGELOG 汇总 + screener/sector SKILL 指引（P1-02b/P2-01）

### CI/CD
- **types**: 新增 sync_ci_precommit.py——CI↔pre-commit mypy 白名单同步自校验（任务 D，缺失/漂移 exit 1 阻断）
- **types**: 新增 mypy experts 层检查（MYPYPATH=scripts 29 文件全绿，规避根目录 data/ namespace 遮蔽 scripts/data/）——P0-A

### Documentation
- **tasks**: 任务 B 进展标记——CI coverage 双 step + technical 89.9% 达标
- **tasks**: 标记任务 A/D 完成，P0 与 P1-D 收口
- **tasks**: 新增 docs/next-tasks.md——后续任务详细描述与适配场景（P0 experts/ mypy 入库·0.5h 零改动，基于 2026-08-13 实测 MYPYPATH 根因）
- **review-issues**: v2.7 #1 记录 CLI 层 mypy 命令（22 脚本）+ P2-P5 .env.example 入库闭环
- **config**: .env.example 入库（.gitignore 加例外保留真实 .env 忽略）——补全 STOCK_DEBUG/STOCK_SCREENER_DEADLINE，16 个消费 env 变量全部声明，新用户可感知（P2-P5）
- **review-issues**: v2.7 #1 边界既有结论 + P2-P5 env 补齐闭环 + P0-01 阶段进度闭环记录
- **changelog**: 记录 chan/ 包纳入 mypy 白名单（212 文件）
- **changelog**: v2.7 #1 收尾记录——mypy 白名单扩至 203 文件 + screener 主线警告静默失效 bug 修复 + dcf/cyclical 双命名回归
- **review-issues**: v2.7 #4 coverage 评估记录——低 ROI 维持现状
- **review-issues**: v2.7 #1 白名单扩展至 78 文件记录 + CHANGELOG 补录
- **review-issues**: v2.7 #1 标记完成（common/ mypy 21 错误清零 + CI 白名单）+ CHANGELOG 补录
- **review-issues**: P2-P1 标记完成（crud 拆分 4/4）+ CHANGELOG 补 v2.7 #2 与 crud 条目
- **review-issues**: 主表全量状态收敛——批量补记 12 项修复标记（6 列行修复脚本 bug）+ CHANGELOG 汇总
- **review-issues**: P1-24/25/28/29 skills/CI 组状态补记
- **review-issues**: P1-17/18/19/20/21/22 business 组状态补记（均已验证已修）
- **review-issues**: 补记 P0-05/06/03/04/07/09 已修复状态（基于代码+gittest 验证）
- **review**: 补齐修复 commit hash + full_market 端到端验证观察记录
- **skills**: 报告长度硬约束——表格上限 + 折叠披露（P2-03）
- **review**: 元复盘问题清单 + CHANGELOG 汇总 + screener/sector SKILL 指引（P1-02b/P2-01）

### Testing
- **technical**: 补 62 条评分/信号/涨跌停分支测试（technical 覆盖率 75.1%→89.9%）+ CI 核心目录覆盖率报告（任务 B，缓冲期仅报告）+ 清理 .coveragerc 过期 omit
- **circuit-breaker**: 新增 14 项确定性测试固化半开窗口期节流语义（v2.7 #2）
- **portfolio**: 健康检查测试注入临时持仓，隔离真实用户 portfolio.json 数据耦合

### Testing
- **data**: 补 chip/event/flow/zt/market_snapshot/pool 子域测试
- **data**: 补 data 域转换函数与 helpers 包装测试
- **coverage**: 补 common/config/monitor/circuit_breaker/fetcher/validators 边界测试
- **technical**: 补 technical 剩余模块分支测试并修复 wave_state 下跌浪不可达 bug
- **technical**: 补 62 条评分/信号/涨跌停分支测试（technical 覆盖率 75.1%→89.9%）+ CI 核心目录覆盖率报告（任务 B，缓冲期仅报告）+ 清理 .coveragerc 过期 omit
- **circuit-breaker**: 新增 14 项确定性测试固化半开窗口期节流语义（v2.7 #2）
- **portfolio**: 健康检查测试注入临时持仓，隔离真实用户 portfolio.json 数据耦合

### Maintenance
- **ignore**: 移除对运行时缓存 macro_snapshot.json 的 git 追踪
- **ignore**: 忽略运行时缓存 macro_snapshot.json（测试后 git status 不再脏）

## [Unreleased]

## [1.20.1] - 2026-08-12（screener 整体任务 watchdog + sector_summary CLI + CI 黑块修复 + 板块授权 + 数据快照）

### Added
- **screener**: 整体任务超时 watchdog + 新增 sector_summary CLI（akshare 同花顺 + 东财 push2 + sector_etf 拼接三级降级）
- **sector**: 板块涨跌幅排行榜 v1.20.1（`python3 scripts/sector_summary.py -j --top 30`），覆盖度高于 sector_etf.csv 的 15 个 ETF

### Fixed
- **ci**: black 19 个文件格式修复（CI 镜像 Python 3.12 下 AST 解析更严）
- **ci**: ruff F601 重复 dict key 修复（`portfolio/manager.py` 稀土条目去重）
- **ci**: ruff F821 未定义名称修复（`test_notification_manager.py` 顶部提前 import）
- **skills**: sector 授权 sector_summary（CI allowed-tools 收紧回归）
- **docs**: 指数代码映射修复 + monitor scanner 缺失回填

### Maintenance
- **data**: 刷新 macro_snapshot.json 数据快照（2026-08-11/12）
- **release**: v1.20.0 → v1.20.1 同步（package.json + plugin.json + marketplace.json + 12 个 SKILL.md + methodology.md + pyproject.toml + README + product-architecture + tests）

## [Unreleased] - 2026-08-08


### Added
- **market**: 数据时效三档 + 涨跌停合理性软校验
- **regime**: 新增 RANGE_CHOPPY 状态 + 高波震荡动量提权
- **screener**: 三段式漏斗输出 + 板块模式放宽容差
- **data**: 新增 akshare 行业补全 fetcher + Quote 接入 industry 字段
- **stock**: 宝丰能源 v2 修复报告 — 板块代理 + DCF + 员工持股解锁量化
- **skills**: 量化基线 CLI + 报告模板占位修复
- **portfolio**: health_report_markdown 渲染层（SKILL 模板标准化）
- **portfolio**: health_report 集成 technical.py（端到端破位判定）
- **portfolio**: health_report 7 项增强（5 行业 + 5 档 status + 真实 regime + 破位 OR）
- **portfolio**: health_report() 结构化报告 + 板块分类修复
- **backtest**: 索提诺落地+多基准对比+报告尾行，akshare防挂死

### Fixed
- **guardrails**: 评分统一脚注 + 报告 RPS 数据去重
- **stock**: 评级统一为单字母制 (B+ → B) + 风控评分映射说明
- **stock**: 评级口径合规 + [1/7] 三段式对比完整化
- **skills**: P2 修复 — 编码兜底+枚举集中+logger统一+emoji库
- **skills**: P0 修复 — 工作目录与多代码调用陷阱
- **skills**: 3 项低优先级修复（L1+L2+L3）
- **skills**: 3 项中优先级修复（M5+M6+M7）
- 修复指数代码映射错误 + monitor scanner 缺失导致监控/简报不可用
- 业绩预告API+财务yoy/roe+板块覆盖+CLI调试 5项修复
- **screener**: 全市场并发抓取 akshare/urllib 代理挂死导致永久卡死
- **quote**: CLI JSON 输出 Quote 对象未序列化导致崩溃

### Maintenance
- **release**: v1.20.0 版本号同步 + CHANGELOG 整理 + 数据快照
- **skills**: 4 skill 复盘 3 项修复
- **portfolio**: 后续推进 L10/L12/L14/L16（as_of 兜底 + 双时间戳文档化）
- 复盘审查修复（13 项）
- 清理监控模块残留引用 + 补推送链路测试
- 彻底移除监控模块（保留持仓 CRUD 推送）

### Other
- Merge fix: 指数代码映射 + monitor scanner 缺失（复盘发现）

### Added
- **screener**: 整体任务超时 watchdog + 新增 sector_summary CLI

### Maintenance
- **data**: 刷新 macro_snapshot.json 数据快照（2026-08-11）

## [1.20.0] - 2026-08-08（screener 三段式漏斗 + regime RANGE_CHOPPY + akshare 行业补全 + market 时效/涨跌停软校验 + research 信号冲突检测强化 + stock 宝丰 v2 报告）

### Added
- **screener**: 三段式漏斗输出（候选池 → 硬过滤 → 显示 Top），让"总输入"反映真实漏斗
- **screener**: 剔除原因 TOP3 列表（无符合条件时输出诊断方向）
- **screener**: 板块模式 `--no-board-strict` 放宽容差 0.7×（解决主题池 20 只被砍剩 2 只问题）
- **regime**: 新增 `RANGE_CHOPPY` 状态（高波震荡）+ `regime_weight_map.yaml` 配置（quality/valuation 1.1，momentum 0.85，volatility 1.1）
- **data**: 新增 akshare 行业补全 fetcher `scripts/fetchers/industry/akshare_industry.py`（60 天长缓存，失败静默回退空串）
- **data**: `Quote` 接入 `industry` 字段（异步 akshare 补全 + classifier keyword 兜底）
- **market**: 市场环境锚定新增数据时效三档（实时 <15min / 延迟 15-60min / 过期 >60min）
- **market**: 市场宽度新增涨跌停数据合理性软校验（总股票数 / 涨跌停与总数 / 涨跌家数覆盖 / 极端 0 信号 4 维度）
- **research**: 综合评分融合规则（系统评级+买卖信号+5维度）+ signal_conflict 章节模板
- **research**: 规则 3.5 信号冲突检测（v1.20.0 新增，防止机械上跳评级）
- **stock**: 宝丰能源 v2 修复报告 — 板块代理（化工ETF/煤炭ETF）+ DCF + 员工持股解锁量化（25% / 0.067% 总股本 / 不构成显著抛压）
- **stock**: sector_etf.csv +2 行（化工ETF BK0693 / 煤炭ETF BK0437）解决板块 ETF 覆盖盲区
- **stock**: sector_etf_strength.py 增加 4 个板块 ETF 代理映射（周期/煤化工/化工/煤炭）
- **guardrails**: 评分统一脚注（A+/A/B+/B/C 五档制与 A/B/C/D 单字母制关系，6 行映射表 + 两套不可混用）
- **scripts**: `data/macro_snapshot.json` 更新到 2026-08-08（treasury 4.66 / vix 14.9 / 锂 140000）

### Fixed
- **stock**: 评级统一为单字母制（B+ → B，3 处；B- → B，4 处）+ 风控评分映射说明
- **stock**: 报告 [1/7 市场环境锚定] 三段式对比完整化（个股 vs 板块 vs 大盘，RPS 双指标）
- **stock**: 报告 baofeng-energy-20260808.md 附录 A.3 RPS 数据去重（[1/7] 已呈现的不再重复，节省 9 行）
- **stock**: 报告行数 625 → 639（+14，三段式对比新增）

### Other
- 版本号同步：18 处文件更新到 1.20.0（plugin.json + marketplace.json + 13 个 SKILL.md + methodology.md + pyproject.toml + README + docs + tests）
- research/SKILL.md 版本号字段对齐 1.20.0（frontmatter + 7 处文档引用）














### Added
- **backtest**: 索提诺落地+多基准对比+报告尾行，akshare防挂死

### Fixed
- 修复指数代码映射错误 + monitor scanner 缺失导致监控/简报不可用
- 业绩预告API+财务yoy/roe+板块覆盖+CLI调试 5项修复
- **screener**: 全市场并发抓取 akshare/urllib 代理挂死导致永久卡死
- **quote**: CLI JSON 输出 Quote 对象未序列化导致崩溃

### Other
- Merge fix: 指数代码映射 + monitor scanner 缺失（复盘发现）

### Maintenance
- 彻底移除监控模块（保留持仓 CRUD 推送）

### Maintenance
- 清理监控模块残留引用 + 补推送链路测试
- 彻底移除监控模块（保留持仓 CRUD 推送）

### Maintenance
- 复盘审查修复（13 项）
- 清理监控模块残留引用 + 补推送链路测试
- 彻底移除监控模块（保留持仓 CRUD 推送）

### Added
- **portfolio**: health_report() 结构化报告 + 板块分类修复
- **backtest**: 索提诺落地+多基准对比+报告尾行，akshare防挂死

### Added
- **portfolio**: health_report 7 项增强（5 行业 + 5 档 status + 真实 regime + 破位 OR）
- **portfolio**: health_report() 结构化报告 + 板块分类修复
- **backtest**: 索提诺落地+多基准对比+报告尾行，akshare防挂死

### Maintenance
- **portfolio**: 后续推进 L10/L12/L14/L16（as_of 兜底 + 双时间戳文档化）
- 复盘审查修复（13 项）
- 清理监控模块残留引用 + 补推送链路测试
- 彻底移除监控模块（保留持仓 CRUD 推送）

### Added
- **portfolio**: health_report 集成 technical.py（端到端破位判定）
- **portfolio**: health_report 7 项增强（5 行业 + 5 档 status + 真实 regime + 破位 OR）
- **portfolio**: health_report() 结构化报告 + 板块分类修复
- **backtest**: 索提诺落地+多基准对比+报告尾行，akshare防挂死

### Added
- **portfolio**: health_report_markdown 渲染层（SKILL 模板标准化）
- **portfolio**: health_report 集成 technical.py（端到端破位判定）
- **portfolio**: health_report 7 项增强（5 行业 + 5 档 status + 真实 regime + 破位 OR）
- **portfolio**: health_report() 结构化报告 + 板块分类修复
- **backtest**: 索提诺落地+多基准对比+报告尾行，akshare防挂死

### Maintenance
- **skills**: 4 skill 复盘 3 项修复
- **portfolio**: 后续推进 L10/L12/L14/L16（as_of 兜底 + 双时间戳文档化）
- 复盘审查修复（13 项）
- 清理监控模块残留引用 + 补推送链路测试
- 彻底移除监控模块（保留持仓 CRUD 推送）

### Fixed
- **skills**: 3 项中优先级修复（M5+M6+M7）
- 修复指数代码映射错误 + monitor scanner 缺失导致监控/简报不可用
- 业绩预告API+财务yoy/roe+板块覆盖+CLI调试 5项修复
- **screener**: 全市场并发抓取 akshare/urllib 代理挂死导致永久卡死
- **quote**: CLI JSON 输出 Quote 对象未序列化导致崩溃

### Fixed
- **skills**: 3 项低优先级修复（L1+L2+L3）
- **skills**: 3 项中优先级修复（M5+M6+M7）
- 修复指数代码映射错误 + monitor scanner 缺失导致监控/简报不可用
- 业绩预告API+财务yoy/roe+板块覆盖+CLI调试 5项修复
- **screener**: 全市场并发抓取 akshare/urllib 代理挂死导致永久卡死
- **quote**: CLI JSON 输出 Quote 对象未序列化导致崩溃

### Added
- **skills**: 量化基线 CLI + 报告模板占位修复
- **portfolio**: health_report_markdown 渲染层（SKILL 模板标准化）
- **portfolio**: health_report 集成 technical.py（端到端破位判定）
- **portfolio**: health_report 7 项增强（5 行业 + 5 档 status + 真实 regime + 破位 OR）
- **portfolio**: health_report() 结构化报告 + 板块分类修复
- **backtest**: 索提诺落地+多基准对比+报告尾行，akshare防挂死

### Fixed
- **skills**: P0 修复 — 工作目录与多代码调用陷阱
- **skills**: 3 项低优先级修复（L1+L2+L3）
- **skills**: 3 项中优先级修复（M5+M6+M7）
- 修复指数代码映射错误 + monitor scanner 缺失导致监控/简报不可用
- 业绩预告API+财务yoy/roe+板块覆盖+CLI调试 5项修复
- **screener**: 全市场并发抓取 akshare/urllib 代理挂死导致永久卡死
- **quote**: CLI JSON 输出 Quote 对象未序列化导致崩溃

### Fixed
- **skills**: P2 修复 — 编码兜底+枚举集中+logger统一+emoji库
- **skills**: P0 修复 — 工作目录与多代码调用陷阱
- **skills**: 3 项低优先级修复（L1+L2+L3）
- **skills**: 3 项中优先级修复（M5+M6+M7）
- 修复指数代码映射错误 + monitor scanner 缺失导致监控/简报不可用
- 业绩预告API+财务yoy/roe+板块覆盖+CLI调试 5项修复
- **screener**: 全市场并发抓取 akshare/urllib 代理挂死导致永久卡死
- **quote**: CLI JSON 输出 Quote 对象未序列化导致崩溃

## [1.19.0] - 2026-08-05（数据源降级可观测性 + P1 健康度 + 五层 data_sources 透传 + 缓存命中 bug 修复 + 18 项 bug 修复）

### Added
- **business**: 五层分析 data_sources 透传真实数据源名
- **monitor**: p1 健康度集成（akshare 探活 + baostock IP 风险 + 跨源校验脚本）

### Fixed
- 修复 18 项数据源/导入/API/格式 Bug
- **kline**: akshare 列名容错 + baostock BSE 路由 + IP 退避 + tencent https/640 钳位
- **cache**: 修复 get_quote/get_kline 缓存命中时双重归一化 bug

### Maintenance
- **data**: 刷新宏观快照 + 新增数据源商用协议标注文档
- bump version to 1.19.0

## [1.17.0] - 2026-08-05（移除 `/monitor` skill + 数据层/战法因子扩容 + VWAP 监控 + 周期股期货修复）

### Added

- **scripts**: 新增题材概念板块数据层 `scripts/concept.py`（`ce331f9`）
- **data**: `FinanceRecord` 新增存货字段（周转率/天数/绝对额）`bcd00c0`
- **monitor**: 新增 VWAP 分时均价线、涨幅减仓与均线止损预警 `1a19e34`
- **strategies**: 新增容量票与庄股识别因子 `730f13c`
- **strategies**: 新增断板反包战法与打分加权 `e55a42d`
- **technical**: 新增竹节法卖点、均线止跌买点与影线占比统计 `2c88f61`

### Changed

- **monitor**: 移除 `/monitor` CLI skill，监控能力下放 `/portfolio-web`（`/api/monitor` HTTP 端点 + 后台守护线程）。保留的内部模块（`scripts/monitor/channels/`、`manager.py`、`levels.py`、`notifier.py`、`rules.py`）继续供 portfolio-web 复用，外部行为完全兼容。数据源健康检查保留为 `python3 scripts/monitor.py --cache/--sources/--cleanup`（顶层工具，不属于 skill）。SKILL.md 数量 13 → 12。`758b1c2`
- **tests**: `tests/contracts/test_skill_metadata_sync.py::EXPECTED_SKILLS` 移除 `monitor`，`tests/smoke_test.sh` 与 `tests/integration/test_install.sh` 的 skill 列表同步从 13 → 12。
- **docs**: `CLAUDE.md`、`README.md`、`skills/_shared/references/{script-catalog,alert-thresholds}.md`、`skills/_shared/contracts/README.md`、`skills/{market,stock-help}/SKILL.md`、`skills/stock-help/references/skill-catalog.md`、`skills/portfolio/SKILL.md` 移除 `/monitor` 引用并改写相关文案，指向 `/portfolio-web`。
- **package.json**: skill 描述从"13 个 skill（9 核心 + 4 变体）"更新为"12 个 skill（8 核心 + 4 变体）"。
- **.claude/settings.json**: 移除 `Bash(python3 scripts/monitor/alert_engine.py *)` 与 `Bash(python3 scripts/monitor.py *)` 权限规则（顶层 monitor.py 健康检查不需要 Claude 工具调用）。

### Fixed

- **factors**: 修复周期股期货数据前置获取 + TTL 全局短路 `b49b2cc`

### Testing

- **e2e**: skill 数量断言 13 → 12，补 `758b1c2` 移除 `/monitor` 的遗漏 `237bad7`

### Maintenance

- **data**: 刷新宏观快照（10Y 国债 2.45% → 4.69%）`4767f7a`

## [1.16.1] - 2026-08-03（fetchers 深度审查 P0–P2 + 技术审查回归 + skill schema 清洗 + 测试/文档对齐）

### Fixed
- **fetchers**: 深度审查修复 27 项问题（5 P0 + 7 P1 + 8 P2）— 基类缺失、超时/重试策略、错误处理静默吞错、缓存键碰撞、字段映射、URL 拼接、单位口径、404 误判等 (`cac611b`)
- **fetchers**: 修复剩余 3 项 P1（PE 口径统一为 TTM + 单位统一为元/股 + fetcher 单元测试覆盖）(`35e5633`)
- **technical**: 技术模块审查修复 H1–H3 / M1–M5 / L1–L4 + 28 用例单元测试回归（PE 分位双实现统一 / 评分归一化中性 50 / macd bar_trend 透传 / 缩量窗口 off-by-one / breakout_check 重构 / 涨跌停 adj 仅一次 / 本土战法 local 权重 / sentiment 错误处理改 logger）(`703c799`)
- **skills**: 清理 skill schema 配置 + git 跟踪遗留 + 路径修正 (`f35dc93`)

### Changed
- **fetchers**: 修复剩余 4 项 P2（基类抽取 + URL 去重 + cb_cache + 装饰器清理）(`7c3626c`)

### Documentation
- 同步 v1.16.0 新模块到 CLAUDE/README/developer-guide/api-reference (`0075ade`)
- 同步 skill schema 单源化改造到技术全景与架构文档 (`550d02e`)
- 优化 CLAUDE.md 修复过时路径 + 提升信息密度 (`bcc029d`)
- 篡减 methodology.md 聚焦投资方法论（876 → 364 行，-58%）(`4f83bc7`)

### Maintenance
- **ci**: release.yml 测试步骤对齐 v1.16.0 测试框架重构（统一 `tests/integration/ tests/unit/ tests/contracts/` + `--timeout=60 -n auto --cov-fail-under=21`）(`b011762`)

### Other
- Merge `fix/skill-schema-cleanup` into main (`501e321`)

## [1.16.0] - 2026-07-28（finance 域 WP1-WP6 重构 + tests 框架重构 + 止损破位检测）

### Added
- **finance**: WP1-WP6 重构（删除 7 个 FinanceRecord 死字段 + 全量 Optional[float]=None + 多字段零值检测 + get_finance() 返 (records, FinanceMeta) 元组 + 全局 RateLimiter 与 429 指数退避 + 主板/科创板/北交所披露 board_overrides）
- **technical**: 止损位破位检测（breakdown 信号 + 报告层警示）
- **tools**: 新增 scripts/common/rate_limiter.py 全局限流器；scripts/dev/gen_changelog.py 改写为合并模式；scripts/common/exceptions/silent_fallback.py；scripts/dev/lint_silent_excepts.py
- **portfolio**: PortfolioManager god class 拆分为 crud/oplog/analytics/rebalance 4 模块 + facade
- **tests**: 新增 tests/unit/test_portfolio_manager.py（≥20 方法覆盖）+ tests/unit/test_vote_engine.py（aggregate_votes 8 场景）+ tests/unit/test_rate_limiter.py 增 6 个失败模式用例

### Changed
- **build**: 版本号统一升到 1.16.0（含 pyproject.toml/package.json/.claude-plugin/*/skills/*.md/methodology.md/README.md）
- **ci**: 覆盖率阈值统一为 .coveragerc=21 / ci.yml=21 / release.yml=21（消除三处不一致，原 60% 作为路线图长期目标 P2-X）
- **ci**: 新增 GitHub Actions checks：sync_agents_skill_versions + lint_silent_excepts
- **pre-commit**: 新增 4 个 local hook（mypy-allowlist / sync_version --check / check_allowed_tools --ci / validate_contracts）
- **deps**: pyproject.toml 新增 [project.dependencies] 段（声明运行时 12 个依赖）；新增 requirements.lock

### Fixed
- **P1-1**: RateLimiter acquire() 信号量泄漏（改为 @contextmanager 强制 try/finally）+ 与 circuit breaker 状态同步
- **P1-2**: 11 处 HIGH/MEDIUM 静默吞错改为专用 SilentFallbackError 或显式 logger.warning（universe_loader/dcf/backtest/metrics/helpers/rules 等）
- **N/A**: CHANGELOG.md 折叠 40 个堆叠的 [Unreleased] 区块为单个；gen_changelog.py 改为合并模式防止复发

### Docs
- **audit**: docs/audit-2026-07-28.md（19 项深度审查报告，含 9 问题 + 5 维度补充 + 11 维度附录）
- **regression**: docs/regression-2026-07-28.md（10 类回归 + 完整 pytest + 静态检查；1005/1005 测试通过）
- **env**: .env.example 补齐 13 个环境变量声明（Tushare / Eastmoney API / cache / TTL）

### Security
- **web**: scripts/portfolio/web/templates.py:671 innerHTML+TOKEN XSS sink 改为 DOM 节点 + textContent（防御性）
- **network**: scripts/fetchers/kline/eastmoney_kline.py + scripts/data/pool.py 把 ut token 改 urlencode 注入（防泄漏到 referer/proxy 日志）

## [1.15.0] - 2026-07-09（多轮审查修复 + 文档同步 + 数据域补齐）

### Added

- **phase4**: 港股跨市场支持 + 盘前简报增强 + 北向资金 Guardrail 修正
- **scripts**: add markdown_table and numbered_table formatters
- **portfolio**: add attribution_report() with Brinson integration
- **portfolio**: add risk_summary() with VaR/CVaR integration
- **screener**: apply user black list in pre_screen_quotes
- **monitor**: implement 6 notification rules from yaml config
- **phase4**: Brinson attribution + chan feature sequence + NB multi-source
- **profile,skills,install**: user profile + lhb skill doc + 3-step quick start
- **risk,quality**: VaR/CVaR metrics + A-share red flag indicators
- **dcf,cache,screener**: sector discount rates, TTL jitter, one-click analysis
- **portfolio**: add oplog + undo for all CRUD operations
- **validators**: expand NAME_TO_CODE to 50+ stocks across 5 sectors
- **experts,chan**: position floor, analyze_code delegation, dead code removal
- **screener,market**: brief as default, --full for detail; market default quick
- **experts**: merge value_anchor+institution → value_institution, buffett veto → warning
- **experts**: C1 维度名别名归一化 + B3 yaml schema 校验基础
- **docs**: 新增用户专家与视觉专家审查视角档案（user_expert.md / visual_expert.md）
- **backtest**: 50+ 只外样本回测 + 沪深 300/中证 500 基准
- **scripts**: CB 加 half_open_success_threshold 可选守卫
- **portfolio-web**: Origin 白名单 + IP 限流（127.0.0.1 防 CSRF）
- 用户保护三重防线（AI 免责 + 中文名解析 + 边界声明）

### Fixed

- 文件 IO 原子性加固 + calibration_sync 空数据防护 (P1)
- 统一 ST 检测逻辑为子串匹配 (P1)
- 修复中枢合并用并集（扩大范围）+ 双针探底死代码 (P0-5, P0-6)
- 修复回测 20cm 涨跌停检测 (P0-4)
- 校准数据 legacy->active 名迁移，修复静默数据丢失 (P0-3)
- 修复 tushare K 线北交所代码映射 + 日期格式 (P0-2)
- 修复 quote 行情 volume/amount 双重归一化 (P0-1)
- **experts**: C2 P2-11 未注册 profile 回退 proxy + P2-12 else 分支注释
- **experts**: B5 简化 _find_expert 为两级查找 + 修 value_institution 降权 bug
- **experts**: B4 短线组方向改均分驱动（P2-10）
- **experts**: P0 一致性修复——fallback 切分+投票阈值动态化+文档校正
- 修复架构审查剩余 9 项技术债+投资逻辑问题
- 修复第五轮剩余 4 个 P1 问题
- 修复第五轮回归审查发现的 9 个 P0 问题
- 修复第四轮审查 4 个剩余 P1 问题
- 修复第三轮深度审查发现的 7 个 P0+5 个 P1 问题
- 修复第三轮审查发现的 P0+P1 问题
- 修复第二轮审查发现的安全+准确性问题
- 修复全模块审查 24 项阻塞+重要问题
- **scripts**: factor normalization, rate-limit failover, chan params, sample warning
- **experts**: dimension key mismatch — align score() return keys with registry weights
- **experts**: linter fixes — amount unit, dead expr, buffett threshold
- **experts**: deep audit — 3 bugs + 8 logic fixes + 6 quality improvements
- **technical**: 审查优化技术分析模块 — 修死代码/除零/重复定义/冗余导入
- **monitor**: correct target_sell alert direction — price <= ts means stop-loss triggered
- **release**: 补全 .npmignore + package.json ! 反白名单排除敏感数据
- **scripts**: alert_engine.py 直接运行报 ModuleNotFoundError + 清理 patterns_local 残留引用
- **data**: sector fetch_sector_finance 解包 None 崩溃
- **p3**: 技术债修复（SSRF/scheme 白名单/CSV 路径注入/version 动态读取）
- **p1**: 修复 20 项高价值问题（字段契约/并发/指标/安全）
- **p0**: 修复 12 项数据正确性 hotfix 阻塞实盘使用
- **experts**: 产品/用户专家审查后修复 11 项 Critical/High 问题
- **experts**: 修复投票引擎 5 项严重/中等问题 + 估值纳入综合评分
- 深度审查后修复 7 个 Critical + 10 个 High 级别问题
- **ci**: CHANGELOG 过滤 auto-update 自引用与持仓流水
- **fetchers**: 删除 K 线伪装财务的 efinance_finance.py
- **scripts**: registry 加 RLock + sync_version 顶层锚定 + CB 文档一致
- **data**: 71.4 胜率 CLAIM 加样本内披露（5 处文档同步）
- **audit**: P0 健康度修复（数字漂移 / 并发数据竞争 / 文档同步）

### Changed

- **technical**: fix review findings -- dedup API call, config-externalize thresholds, restructure modules
- 全面深度优化——安全修复+消除重复+文档同步
- **chan**: unified aligned_macd() interface for DIF/DEA offset
- **arch**: 第 5 轮修复——参数对象化+测试补齐+异常收窄+CHANGELOG 合并
- **arch**: LazyFetcherRegistry 抽取 + 高复杂度拆分 + PEP562 修正 + 4 域工厂缓存
- **arch**: 深度审查后修复 90+ 项技术债
- **arch**: fetchers 子目录化 + 测试修复 + 兼容性记录
- **arch**: 胖入口下沉 + 补齐数据域 data 层

### Documentation

- 同步至 v1.15.0 并清理 CHANGELOG 重复段
- 更新第四轮审查计划文件
- 更新第三轮审查计划文件（标记完成）
- 记录本轮审查未处理项到 improvement-roadmap [skip ci]
- **experts**: A3 扩展——全仓库校正 9人/6长线/15份 残留引用
- **portfolio**: document risk_summary() and attribution_report() methods
- mark all 24 improvement items complete in architecture review
- update architecture review with execution status tracker
- **changelog**: 合并 2026-07-03 双 Unreleased 段并更新日期
- **docs**: 文档双视角审查后批量修正事实性错误
- 同步 6 种策略 9 因子（漏列 ma_volume_momentum）
- **experts**: 同步 9 人活跃圆桌替换过时 8 人表述

### Testing

- **experts**: B3 新增 test_yaml_consistency 锁死 yaml/硬编码漂移
- **experts**: B2 新增 TestActiveSetSemantics 锁定 active 集语义
- **chan**: add 3 tests for aligned_macd unified interface
- add unit tests for v2.4.0 new modules
- adapt assertions for v2.4.0 expert merge + sector thresholds + screener brief

### Maintenance

- **release**: 同步至 v1.14.3
- black 折行（backtest cli/metrics 无逻辑变化）
- **settings**: 合并 IDE 自动学习的权限 allowlist

### Other

- Merge remote-tracking branch 'origin/main'

## [1.14.2] - 2026-06-29（异常分类 + 输出模板统一 + backtest 解耦 + 文档对齐）

### Fixed

- 异常提示对内置异常做精细化分类（`JSONDecodeError` / `KeyError` / `TimeoutError` / `ConnectionError`）
- `stock.py` 接入统一输出模板（`render_text` 加 footer / `render_brief` 改用 `format_output`）
- `screener.py` ROE 列格式化：`str(x)[:6]` 截断改为 `:.1f` 控制小数位
- `backtest/engine.py` 不再依赖顶级 `screener.py`（解耦到 `strategies.factors.*`）

### Testing

- 补齐 6 类核心 fetcher 单元测试（15 个 case）

### Documentation

- 修复专家人设数字矛盾：8 人/4+4 统一为 9 active/6 长线+3 短线（15 份人设 = 9 active + 6 legacy 框架）
- CLAUDE.md 补齐 5 个未列出的辅助脚本（`calibration_sync` / `hot_rank` / `market_breadth` / `perf_bench` / `snapshots`）
- `scoring.yaml` 未被读取字段加 DEPRECATED 警告（`industry_defaults` / `experts.soros.market_liquidity_floor_yi`）
- 修复 CHANGELOG.md markdown lint 警告

## [1.14.0] - 2026-06-24（回测增强 + 估值模型 + 事件驱动 + 架构重构）

### 🌟 用户亮点

- **回测 ASCII 可视化**：`/backtest` 结果以终端图表展示，无需额外依赖
- **DCF 简易估值模型**：新增贴现现金流估值，辅助判断内在价值
- **EV/EBITDA 估值指标**：补充企业价值/息税折旧前利润估值维度
- **回测止损止盈**：支持设置止损/止盈比例，更贴近实盘交易
- **涨跌停过滤**：回测中可排除涨跌停无法买入的场景，结果更真实
- **事件驱动因子**：大股东增减持 + 监管处罚因子纳入回测引擎
- **盘前简报**：`/monitor briefing` 一键查看市场状态 + 持仓概要 + 关键价位
- **行业归因分析**：持仓收益按行业拆解归因，定位收益来源
- **筹码因子**：选股新增筹码集中度 + 宏观门控过滤

### Added

- **backtest**: 新增 ASCII 可视化模块 + CLI 集成
- **backtest**: 新增止损止盈逻辑 + 涨跌停过滤 + 筹码/分析师/事件因子集成
- **估值**: 新增 DCF 简易估值模型 + EV/EBITDA 估值指标
- **events**: 新增大股东增减持 + 监管处罚事件因子
- **screener**: 新增筹码因子 + 宏观门控模块
- **monitor**: 新增 `/monitor briefing` 盘前简报（市场状态+持仓概要+关键价位）
- **portfolio/performance**: 新增行业归因分析（SectorAttribution）
- **strategies/factors**: Phase 2 架构重构 + 因子增强
- **common**: 新增 CLI 基座模块 + FIELD_MAP 提升为模块级常量

### Fixed

- **scripts**: 修复静默异常捕获 + 清理未使用导入 + 补充测试覆盖
- **data/config**: 修复 `get_source_timeout()` NameError（缺少 ConfigLoader 导入）
- **experts/registry**: 补充 `from typing import Dict`（Python 3.11/3.12 兼容）
- **common**: CircuitBreaker 误触修复（None 返回不触发熔断，仅异常触发）
- **README**: 修复虚假安装命令（plugins marketplace → ./install.sh）
- **CLI**: quote/kline/finance/stock/screener 错误提示接入 format_error()
- **business/stock_analysis**: 数据缺失时显式提示（data_warnings）
- **screener**: 结果为空时提示 /screener init 引导
- **strategies/factors/dividend**: 分红率按行业差异化（银行30%、科技15%等）
- **experts/vote_engine**: 投票边界测试 + TradeLog 集成 + 注册表日志修复

### Changed

- **stock.py**: render_text 可视化增强（emoji+分隔线+颜色图标）
- **common/cache**: 缓存惰性清理（每 50 次写入检查，超 500MB 自动清理）
- **common**: 拆分 `__init__.py` 上帝模块为子模块
- **fetcher**: 工厂函数缓存单例化（性能优化）
- **methodology**: 策略权重文档对齐代码（五因子→七因子模型）
- **stock-help**: SKILL.md 分层展示（核心/进阶/辅助 13 个 skill）
- **learn**: SKILL.md 补全 `model: haiku`

### Documentation

- **skills/experts**: SKILL.md ↔ 脚本现状对齐 + 7 份辅助专家对 agent 可见
- **methodology**: 与 experts/ 单点权威对齐 + 新增 §一.4/§二.6 + 调和打板哲学
- **docs**: 修正 README/CLAUDE.md 元数据漂移（13 skills / 28 fetchers / 15 experts / python 3.11+ / pyyaml 依赖）

### Testing

- **backtest**: 补充策略表现校准模块测试（10 个用例）+ 性能压测（5 个用例）
- **screener**: 补充股票池刷新模块测试（25 个用例）
- **research**: 补充公告/研报模块测试（17 个用例）
- **strategies**: 补充分析师预期因子测试（19 个用例）
- **common**: 补充 metrics 模块测试（8 个用例）
- **data/strategies/fetchers**: 补充 data 层、regime detector、筹码 fetcher 测试
- 新增 13 个测试文件覆盖未测试模块 + 修复 cache DeprecationWarning
- **test_data_fetcher_manager_e2e**: 新增 `test_none_return_does_not_trigger_circuit_breaker`

### Maintenance

- **tests**: 更新 SKILL.md 版本一致性检查至 v1.13.1
- **version**: bump version to v1.14.0
- **ci**: 防止 SKILL.md 版本与测试常量不一致阻塞 release（新增 `scripts/dev/sync_skill_test_versions.py` + pre-commit hook + setup-test action step）
- **ci**: PR 触发集成测试和冒烟测试

## [1.13.0] - 2026-06-18（动量派专家 + 用户体验优化 + 10 模块深度审查）

### ⚠️ 升级须知

- **建议立即升级**：持仓管理存在死锁 bug（`atomic_update` 卡死 10 秒）、技术分析情绪指标无法使用（`sentiment.py` 双致命错误），本次修复后恢复正常
- 无需清理缓存，向后兼容
- 1733 项测试 100% 通过

### 🌟 用户亮点

- **新增第 15 位投资专家「动量派」**：基于利弗莫尔+海龟交易法则，专注价格行为 + 系统化止损纪律。通过 `/stock <代码> debate` 调用
- **新手引导优化**：`/help` 重写为"按目标选入口"表，`/learn` 补充更多概念触发词（PE/ROE/MACD/K线等）
- **持仓管理修复**：不再出现卡死，日报推送恢复正常
- **监控推送修复**：关键点位推送内容完整（之前会缺失持仓/自选信息）
- **回测修复**：`/stock --with-backtest` 胜率等指标正确显示
- **选股优化**：分红率按行业差异化（银行 30%、科技 15% 等），结果为空时自动引导 `/screener init`

### Changed · 用户体验优化

- 新增 `_shared/references/welcome.md` 统一欢迎卡，可被 `/help` 和 `/learn` 复用
- README.md 副标题改写为"把专业 A 股分析变成 9 条对话命令"
- `install.sh` 末尾新增"新手起步"提示

### Fixed · 10 模块深度审查

本次对 10 个核心模块进行深度代码审查，共修复 46+ 项问题。

<details>
<summary>🔴 8 项致命修复（点击展开）</summary>

| 模块     | 问题                                                           | 修复                                     |
| -------- | -------------------------------------------------------------- | ---------------------------------------- |
| 数据获取 | 同花顺 fetcher 返回 K 线收盘价而非实时行情                     | 优先级下调 + 注释说明                    |
| 数据获取 | 雪球行情字段映射错误                                           | 对齐 `prev_close`/`turnover`/`total_cap` |
| 技术分析 | `sentiment.py` 双致命错误（`HttpClient` 不存在 + `NameError`） | 改用 `http_get` + `urlencode`            |
| 技术分析 | `pipeline.py` 数组错位（closes/volumes 长度不一致）            | 统一过滤 `valid_bars`                    |
| 持仓管理 | `atomic_update()` 文件锁死锁                                   | 抽取 `_raw_write()` 避免重入             |
| 持仓管理 | `daily_report.py` 导入错误                                     | 改用 `http_get` + `parse_tencent_line`   |
| 监控     | `compute_key_levels` 返回值缺失                                | 增加 `position`/`watch` 键               |
| 回测     | `stock.py --with-backtest` 字段名映射错误                      | 4 个字段名对齐                           |

</details>

<details>
<summary>🟠 28 项重要修复（点击展开）</summary>

- **数据获取**：Baostock 模块级一次性 login、熔断器配置接入、连接池列表化、HTTP 客户端去重
- **技术分析**：量价评分方向性修复、背离检测容差优化、量价分析窗口优化、亏损公司 OCF 信号修复
- **持仓管理**：日报数据模型对齐 v2、`max_drawdown` 日期对齐、通知状态管理修复
- **监控**：支撑位强度分级、单例缓存、批量行情预取
- **缠论**：`closes` 索引对齐、三买回踩检测逻辑修复
- **筛选策略**：`_stdev` 一致化、分红年数回退逻辑修复、RSI 精度修复、归一化精确总和
- **业务层**：涨跌停判断修复、数组错位消除、PE 分位逻辑复用
- **分类器**：板块类型对齐、重试逻辑、diff guard
- **回测**：死分支删除、循环内导入提升
- **专家系统**：4:4 两极分化分支可达性修复

</details>

<details>
<summary>🟡 10 项轻微修复（点击展开）</summary>

- 清理 21 个 fetcher 文件的 `sys.path.insert` 样板代码
- 光头光脚阳线/阴线检测改用 0.1% 浮点容差
- `report.py` 安全访问 `meta.get('price_num', 0)`
- log 轮转检查频率优化（每次 → 每 10 次）
- `dingtalk.py` 动态导入改为顶层导入
- `merge` 合并后保留 `open`/`close` 字段
- `thresholds.py` 配置缺失时增加 warning 日志
- `classifier.py` 顶部统一导入
- 场景标签从年份改为时间窗口（近1月/近3月/近6月）
- `get_position`/`get_watch` 返回深拷贝副本

</details>

### 测试结果

```text
1733 passed, 45 skipped, 0 failed in ~35s
```

### 累计统计

| 维度           | 数值                                         |
| -------------- | -------------------------------------------- |
| 审查模块数     | 10                                           |
| 提交 commit 数 | 10                                           |
| 修复问题数     | 46+                                          |
| 代码变更       | 1277 insertions, 420 deletions（净 +857 行） |
| 测试通过率     | 100%                                         |

> **emoji 分级说明**：🔴 致命（功能不可用）🟠 重要（结果不准确）🟡 轻微（代码质量）

## [1.12.0] - 2026-06-17（统一版本：V2 量化策略平台 + V2.1 维护）

> 本版本将所有 Sprint 1-26 的 V2 改造合并发布为统一版本 v1.12.0
> 历史 tag（v1.1.0 - v1.11.0、v2.0.0、v2.1.0）已合并到此版本。

### 🌟 用户亮点

- **选股策略全面升级**：5 策略（均衡/质量价值/成长动量/防守低波/拐点修复）权重优化，选股更精准
- **市场状态自适应**：自动识别牛市/熊市/震荡/恐慌 4 种状态，动态调节策略权重
- **选股快照**：保存/对比/列出历史选股结果，方便回溯验证
- **跨策略对比**：`strategy_performance compare` 一键对比 5 策略的夏普/胜率/回撤
- **专家配置 YAML 化**：13 位专家配置从硬编码迁移到 YAML，便于自定义调参
- **选股性能提升**：K 线批量预拉 + 行情财务并行拉取，大幅减少等待时间

<details>
<summary>🔧 技术详情（点击展开）</summary>

### Added

- **Screener V2 量化策略平台**（Sprint 1-26 综合）：
  - 6 因子 z-score 标准化消除跨因子尺度差异
  - 4 状态市场状态机（bull/bear/range/panic）自动调节策略权重
  - 两阶段管线（Phase 1 无 K 线初筛 → Phase 2 仅对 Top N×3 拉 K 线精排）
  - 因子级精修：波动率窗口 20→60 / ROE 趋势下降占比 60% / 动量阈值 p75 / PEG 用 3y CAGR
  - turning_point 两阶段模型：超跌+量能+基本面三重过滤
  - ESG/分红 fetcher 字段映射
- **experts/yaml 机器可读版**：13 个 expert yaml 配置 + 加载器
- **screener.py main() 重构**：提取 `_build_parser()` 和 `_run_main(args)` 助手
- **统一版本号**：`scripts/common/version.py` 暴露 `__version__ = "1.12.0"`
- **C7 README 30s demo**：`scripts/demo.sh` 可重放脚本 + README demo 段

### Changed

- `compute_weighted_score` 支持 market regime overlay
- 策略权重从 V1 经验值升级到 V2
- `_dict_to_finance` 支持 5 个新字段

### Engineering

- 覆盖率 55% → 62.1%（fail-under 60% 达标）
- 168 测试 → 1780 测试（+1612 测试，0 失败）
- 5 个新模块（regime / filters / snapshots / strategy_performance / perf_bench）

</details>

## [1.11.0] - 2026-06-16（反追涨杀跌 + screener 重构 + yaml 迁移）

### Added

- **反追涨杀跌机制**：4 层估值约束嵌入决策引擎
  - `signals.py` 新增估值买卖信号（PE 行业分位底/顶、PEG 偏高）
  - `momentum.py` 新增估值衰减（PE>80%分位 → 动量×0.45，PE>65% → ×0.70）
  - `decide.py` 新增估值硬约束（长线组估值分<20 → 仓位×0.5，<30 → ×0.7）
- **短线专家估值权重提升**：徐翔/赵老哥/养家/作手新一估值权重从 5-8% 统一提升至 12%
- **估值数据注入**：`technical.py` 和 `stock_analysis.py` 自动计算 PE 行业分位并注入 features

### Changed

- **screener.py main() 重构**：提取 `_build_parser()` 和 `_run_main(args)` 助手，便于单测覆盖
- **统一版本号**：`scripts/common/version.py` 暴露 `__version__ = "2.1.0"`
- **性能基准持久化**：`perf_bench.py save` 子命令保存到 `data/perf_benchmarks.json`
- **v2.1.0 扩展视角 yaml 完整迁移**（Sprint 21）：5 个 expert yaml
- 短线组专家情绪/技术面权重相应下调（总权重保持 100%）
- 专家 md 文件权重表同步更新

### Documentation

- 全量更新文档同步至 v1.10.0 / 9 skill 结构

### Engineering

- 覆盖率 61.8% → 62.1%（+0.3%，新增 7 个 \_run_main 测试）
- 测试 1773 → 1780（+7）
- 20 → 21 个独立 commit

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

### 🌟 用户亮点

- **专家圆桌决策引擎**：`/stock <代码> debate` 时，8 位专家自动投票 + 冲突解决 + 仓位建议，输出结构化辩论报告
- **市场状态自动识别**：牛市/熊市/震荡/冰点/亢奋 5 种状态，自动调节专家权重（如冰点时防守专家加权）
- **文档全面修复**：12 个 SKILL.md 深度审查，修复数据路径错误、默认行为歧义等用户会踩的坑
- **新增用户指南**：`docs/user-guide.md`，按场景引导上手

<details>
<summary>🔧 技术详情（点击展开）</summary>

- 专家圆桌决策引擎 `experts/decide.py`（decide.md 代码化）：
  - `detect_market_state()` / `aggregate_votes()` / `format_debate_output()`
  - 双权重矩阵（市场状态 × 投资期限），支持短线/中线/长线
  - 冲突解决：巴菲特否决权、养家情绪周期降权、冰点特殊处理
- 数据层动态线程数与分类型缓存（按数据类型差异化 TTL）
- 文档一致性修复（P0-P3 全部）

### Fixed

- `skills/stock/SKILL.md`：移除 `debate` 双重"默认"声明
- `skills/portfolio/SKILL.md`（4 处）+ `skills/monitor/SKILL.md`（2 处）：数据路径修正
- `skills/stock/SKILL.md`：短线团专家首次出现补全全名

</details>

## [1.6.0] - 2026-06-12

### 🌟 用户亮点

- **美股数据接入**：`/market` 大盘分析新增美股参考（标普500/纳指/道指/VIX/SPY/QQQ），需安装 `yfinance` 包
- **全市场选股**：`/screener --full-market` 覆盖 ~5000 只 A 股，支持按板块筛选（主板/创业板/科创板/北交所）
- **专家量化评分**：`/stock debate` 新增量化基线参考，8 位专家各有专属评分函数，与 LLM 推理分差 >15 时自动提示
- **校准数据回写**：debate 后自动记录预测，下次分析时显示校准因子（如 `校准因子: +0.15`）
- **npm 自动发布**：`git tag v1.6.0 → git push --tags` 自动测试 → npm publish → GitHub Release

<details>
<summary>🔧 技术详情（点击展开）</summary>

- 专家评分硬编码体系：`experts/scoring.py` 8 位专家专属评分函数 + 信心指数计算
- 校准数据自动回写：`experts/calibration.py` 6 个 API，原子写入并发安全
- 全市场股票池：`refresh_pool.py --full-market` 按板块归档，`screener.py` 高效预筛
- 美股数据源：`yfinance_quote.py` / `yfinance_kline.py`，`NOT_HANDLED` 哨兵值隔离 A 股/美股
- 单元测试新增 ~126 个（calibration / scoring / yfinance / screener）

### Changed

- `skills/stock/SKILL.md` debate 流程新增「量化基线参考」和「记录校准数据」步骤
- `skills/market/SKILL.md` 新增「美股参考」段（VIX 避险阈值、美股板块映射 A 股）

</details>

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
  - `_score_fundamentals` 注释与实际权重不符（"加权"改为"均分"）
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

---

## 版本说明

- **主版本号**：不兼容的 API 变更
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

## 链接

- [GitHub 仓库](https://github.com/CurtisTong/stock-analyzer-skill)
- [问题反馈](https://github.com/CurtisTong/stock-analyzer-skill/issues)
- [发布页面](https://github.com/CurtisTong/stock-analyzer-skill/releases)

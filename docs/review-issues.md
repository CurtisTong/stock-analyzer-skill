# 项目深度审阅问题清单

> 版本：v1.15.0 | 生成日期：2026-07-09  
> 来源：4 个并行深度审阅 + 核心模块亲自核对  
> 规模：75 个编号问题（15 critical/important P0 + 30 important P1 + 30 nit P2） + 46 项架构审查（25 技术债 T1-T25 + 21 投资逻辑 I1-I21）  
> 关联文档：[product-architecture.md](product-architecture.md) · [developer-guide.md](developer-guide.md) · [improvement-roadmap.md](improvement-roadmap.md) · [review-verification.md](review-verification.md)（逐条源码验证报告）· [architecture-review-2026-07-07.md](architecture-review-2026-07-07.md)（46 项架构债审查）
>
> **2026-07-09 验证结果**：75 项逐条源码核对，65 项真实、8 项部分真实、2 项不真实（P0-08 降级、P1-10 record 已修复）。详见 [review-verification.md](review-verification.md)。
>
> **2026-07-09 修复进度**：
> - **Round 7（P0 全量）**：15 项 P0 已全部修复（10 项代码修复 + 5 项验证降级/文档对齐），2618 tests passed。
> - **Round 8（P1 全量）**：30 项 P1 已全部修复，分 5 阶段提交（A: fetcher 加固, B: experts 投票校准, C: technical/chan, D: business, E: skills/tests/CI/config），2639 tests passed。
> - **Round 9（P2 全量）**：28 项真实/部分真实 P2 已全部修复，分 5 阶段提交（A: experts 清理, B: strategies 治理, C: technical/fetcher, D: business/config, E: tests/docs/release），2663 tests passed。高风险架构项（P2-01/05/10/23）采用保守标注方案，留待 v2.0.0。
> - **Round 10（收尾深化）**：清理 20 个遗留 ruff 错误；P0-10 回测财务前瞻偏差修复（report_date+90天披露延迟过滤）；P0-11 walk-forward 回测框架（OOS 验证）；P1-15 composite_score 去魔数化（_SCORE_MAX 提取为模块级常量+YAML 可配置）；P1-27 13 skill E2E 测试扩展（frontmatter 校验+mock 工作流）。2698 tests passed。
> - **Round 11（架构债收官 2026-07-10）**：架构审查（[architecture-review-2026-07-07.md](architecture-review-2026-07-07.md)）剩余 9 项 T/I 全部清零，2725 tests passed / ruff 0 errors / 25 skipped（commit `ec4c290` 时点；截至本文件更新时为 2729 passed / 34 skipped）：
>   - **T3** `common/__init__.py` `__all__` 76→41（PEP 562 懒加载保留向后兼容）
>   - **T6** chip/flow/lhb/event 四域优先级从 yaml 驱动（`data_source.yaml` 新增 `flow_sources/lhb_sources/chip_sources/event_sources`）
>   - **T7** `risk_warning.py` docstring 澄清：仅筹码 emoji，宏观风控在 `macro/gate.py`，量化风控在 `risk_metrics.py`
>   - **T19** `common/http.py` `except Exception` 改具体异常类型（`RequestException` / `OSError`）
>   - **T22** 新增 `fetch_with_fallback(fetchers, *args, **kwargs)` 多源故障转移；`data/flow.py` 改用统一函数
>   - **I8** `chan/merge.py` K 线包含初始方向改前两根高低判断（缠论标准）
>   - **I9** `chan/maidian.py` 三买/三卖回踩容忍度改 ATR 动态（`ATR*0.5`）；新增 `technical/volatility.py` `compute_atr`/`atr_tolerance`
>   - **T24** 新增 `test_data_flow.py` + `test_data_lhb.py`（9 个测试）
>   - **T25** 新增 `test_monitor_extra.py`（8 个测试：briefing/render_briefing/ATR）
> - 高风险项（P1-14/19、P2-01/05/10/23）采用保守方案：标注而非改算法，避免回归风险。

---

## 架构审查 T/I 跟踪表（46 项 → 9 项收官）

> 来源：[architecture-review-2026-07-07.md](architecture-review-2026-07-07.md)
> 状态：2026-07-10 全部清零（Round 11）

| ID | 类型 | 描述 | 状态 | 修复方式 |
| :--- | :--- | :--- | :--- | :--- |
| T1 | 🔴 | screening_service 1000+ 行单文件 | ✅ | 拆分为 pipeline / universe_loader / screening_factors |
| T2 | 🔴 | ScreeningService 重复实例化 | ✅ | 模块级函数 + 单例 |
| **T3** | 🟡 | common/__init__.py 导出 99 个符号 | ✅ | **Round 11** `__all__` 精简 76→41，PEP 562 懒加载 |
| T4 | 🟡 | `_apply_factor_normalization` 硬编码 6 因子 | ✅ | 改用 `get_factor_keys()` |
| T5 | 🟡 | `apply_portfolio_constraints` 副作用 | ✅ | dict copy 后修改 |
| **T6** | 🟡 | fetcher 优先级硬编码 | ✅ | **Round 11** chip/flow/lhb/event 四域 yaml 驱动 |
| **T7** | 🟢 | risk_warning.py 职责模糊 | ✅ | **Round 11** docstring 澄清三模块边界 |
| T8 | 🟢 | beichi.py `_dif_offset` noqa 死代码 | ✅ | 移除 |
| T9 | 🔴 | RateLimitError 直接抛出 | ✅ | 改 on_failure + continue 换源 |
| T10 | 🔴 | analyze_code / _analyze_stock 重复 | ✅ | analyze_code 委托给 _analyze_stock |
| T11 | 🟡 | 缓存键缺版本前缀 | ✅ | `_DATA_FORMAT_VERSION=v2` |
| T12 | 🟡 | compute_features 双份实现 | ✅ | 统一 `technical.pipeline.compute_indicators()` |
| T13 | 🟡 | _FINANCE_FIELD_MAP 在 data 层 | ✅ | 迁入 `data/mappers.py` |
| T14 | 🟡 | 缓存雪崩风险 | ✅ | TTL 抖动 `base + random(0, base*0.1)` |
| T15 | 🟡 | ConfigLoader 非线程安全 | ✅ | `_lock` + 双重检查 |
| T16 | 🟡 | CircuitBreaker TOCTOU 竞态 | ✅ | 文档标注"乐观并发" |
| T17 | 🟡 | get_quotes 超时偏短 | ✅ | 按 `len(codes)` 动态调整 |
| T18 | 🟡 | 全市场选股内存压力 | ✅ | 分批获取+处理 |
| **T19** | 🟡 | except Exception 使用过多 | ✅ | **Round 11** http.py 改 `RequestException` / `OSError` |
| T20 | 🟡 | data/__init__.py 444 行混合职责 | ✅ | 字段映射迁入 `data/mappers.py` |
| T21 | 🟡 | data→common→data.config 循环 | ✅ | 线程池配置下沉到 common |
| **T22** | 🟢 | fetch_with_breaker 无多源故障 | ✅ | **Round 11** 新增 `fetch_with_fallback` |
| T23 | 🟢 | Quote 缺停牌/涨跌停字段 | ✅ | `is_suspended` + `limit_up/limit_down` |
| **T24** | 🟢 | chip/flow/lhb 域聚合无测试 | ✅ | **Round 11** `test_data_flow.py` + `test_data_lhb.py` |
| **T25** | 🟢 | monitor 模块测试不足 | ✅ | **Round 11** `test_monitor_extra.py` |
| I1 | 🔴 | 模式策略 71.4% 胜率为样本内拟合 | ✅ | CLAUDE.md + 策略输出加 "⚠️ 样本内" 警告 |
| I2 | 🔴 | 缠论分型识别简化过度 | ✅ | 放宽 fenxing 条件（v2.4.0） |
| I3 | 🟡 | 背驰检测 20% 容差硬编码 | ✅ | beichi `range_tolerance` 可配置 |
| I4 | 🟡 | DIF/DEA 偏移量映射复杂 | ✅ | `aligned_macd()` 统一接口 |
| I5 | 🟡 | DCF 折现率无行业差异化 | ✅ | sector_discount_rates |
| I6 | 🟡 | 风控模块过于简单 | ✅ | 扩展 VaR/CVaR/最大回撤 |
| I7 | 🟡 | 排雷指标未覆盖 A 股常见造假 | ✅ | 关联交易/商誉/存贷双高 4-6 项 |
| **I8** | 🟢 | K 线包含初始方向硬编码 "up" | ✅ | **Round 11** 前两根高低判断 |
| **I9** | 🟢 | 买卖点回踩容忍度 2% 硬编码 | ✅ | **Round 11** ATR 动态调整 |
| I10 | 🔴 | 巴菲特否决权过度主导 | ✅ | 改为"否决警示"——降信心不强制改方向 |
| I11 | 🔴 | value_anchor vs institution 90% 同构 | ✅ | 合并为 value_institution |
| I12 | 🔴 | 长线组 4/6 基本面共识集团 | ✅ | 合并 + 观点去相关 |
| I13 | 🟡 | 养家降权语义偏差 | ✅ | yangjia_sub_score 独立子评分 |
| I14 | 🟡 | 短线组 3 人投票不稳定 | ✅ | 增加短线权重稳定性 |
| I15 | 🟡 | 巴菲特+养家+估值否决叠加无地板 | ✅ | position_factor 地板值 min=0.3 |
| I16 | 🟡 | 综合分用简单平均 | ✅ | 校准率作为综合分权重因子 |
| I17 | 🟡 | sector_specialist 未实现差异化 | ✅ | 5 大行业类差异化阈值 |
| I18 | 🟡 | 缺成长可持续性+管理层量化维度 | ✅ | insider_buy / revenue_growth_trend_3y |
| I19 | 🟡 | 维度名别名不一致 | ✅ | normalize_dim 别名映射 |
| I20 | 🟢 | decide.md 否决评分 0 vs 20 不一致 | ✅ | 对齐 decide.md 文档 |
| I21 | 🟢 | _merge.py 否决阈值 10 未文档化 | ✅ | 补充文档说明 |

---

## 优先级说明

- **P0（必须优先）**：影响安全、数据可信度、发布可靠性或核心结论正确性；建议本周修复
- **P1（下一 sprint）**：影响模型可信度、可维护性、测试覆盖；建议 2 周内修复
- **P2（后续优化）**：架构债、性能、体验与文档治理；建议 1-2 月内清理

---

## P0：必须优先处理（15 项）

| ID | 模块 | 问题 | 位置 | 影响 | 修复建议 |
| --- | --- | --- | --- | --- | --- |
| **P0-01** | skills / 权限 | `.claude/settings.json` 中 `Bash(python3 scripts/**/*.py *)`、`Bash(git commit*)` 等权限过宽 | `.claude/settings.json` | Prompt injection 或误操作可执行任意 scripts、修改文件并提交 | 收紧为显式脚本白名单；限制 Edit/Write 到 `scripts/data/portfolio*.json` 等运行数据 |
| **P0-02** | business / 输出契约 | `StockAnalysisService.analyze` 未填充 `data_sources` / `data_failed` / `data_time` | `scripts/business/stock_analysis.py`、`scripts/stock.py` | 13 个 skill footer 显示的时间戳和数据源不可信 | 在 quote/kline/finance 成功或失败处记录来源、失败项、数据时间 |
| **P0-03** | fetcher / 配置 | `data_source.yaml` 的 `timeout` / `retry` 未被 `_apply_source_config` 使用 | `scripts/common/fetcher_base.py`、`scripts/config/data_source.yaml` | 用户改配置无效，数据源调优失效 | `BaseFetcher` 增加 `self.timeout/self.retry`，fetcher 调 `http_get(..., timeout=self.timeout, max_retries=self.retry)` |
| **P0-04** | fetcher / 熔断 | 429 限速被计入 `on_failure()`，会误触发熔断 | `scripts/common/fetcher_base.py` | 临时限速被当作数据源故障，导致可用数据源被跳过 | 引入独立 `RateLimitTracker`；429 只跳过当前源，不计入熔断失败 |
| **P0-05** | fetcher / 熔断 | `recovery_timeout=0` 会导致 OPEN/HALF_OPEN 高频抖动 | `scripts/common/circuit_breaker.py` | 配置错误时出现高频重试 | 初始化时校验 `recovery_timeout >= 1`，或设置最小值 |
| **P0-06** | experts / 三源漂移 | YAML 权重维度名未归一化，存在 `情绪/题材` vs `情绪` 键名漂移 | `experts/yaml_loader.py`、`experts/registry.py` | 投票和维度 breakdown 可能错位 | 加 `weights={normalize_dim(k): v for k, v in weights.items()}` |
| **P0-07** | experts / 决策文档 | `decide.md` 中"巴菲特否决"规则与代码不一致 | `experts/decide.md`、`experts/vote_engine.py` | LLM 根据文档会得出错误决策预期 | 改为"巴菲特警示：中长期信心 -15，不强制看空" |
| **P0-08** | experts / 校准公式 | 校准因子公式在 mean_rate=0.5 时给负校准，反直觉 | `experts/calibration.py`、`experts/decide.md` | 代码与文档一致（非不一致 bug），但 mean_rate=0.5（无信息）时给 -0.5 负惩罚属设计争议 | ~~P0~~ **降级 P2**：改为 `(mean_rate - 0.5) * 2 * (1 - min(cv, 0.5))`，mean_rate=0.5 时归零 |
| **P0-09** | experts / 投票 | `aggregate_group_votes` 中 `all(s <= 30)` 强烈看空分支永远不可达 | `experts/vote_engine.py` | 极端全空场景被标成普通看空 | 将 `all(s <= 30)` 判断提前到普通 bear 分支之前 |
| **P0-10** | strategies / 回测 | 回测 `quality` 因子使用最新财务快照，存在 lookahead bias | `scripts/backtest/engine.py` | 回测收益系统性高估 | 至少在 README 明示；更优是按财报披露日过滤可见财务数据 |
| **P0-11** | strategies / 过拟合 | MA+成交量战法胜率来自样本内拟合，无 walk-forward 验证 | `scripts/strategies/patterns/ma_volume_strategy.py`、`scripts/backtest/` | 用户可能误认为战法稳定有效 | 增加 walk-forward 验证，报告 IS/OOS Sharpe 退化比 |
| **P0-12** | strategies / 因子计算 | `event` / `analyst` 权重为 0 但仍默认计算，可能触发冗余网络请求 | `scripts/strategies/factors/`、`scripts/strategies/registry.py` | 全市场筛选浪费大量 IO | 加 feature flag，默认禁用这两个因子 |
| **P0-13** | CI / 发布 | `release.yml` 和 `ci.yml` 重复跑全量测试，且 release 标准更宽松 | `.github/workflows/release.yml`、`.github/workflows/ci.yml` | 发布版本可能绕过 CI 覆盖率门槛 | release 复用 CI 结果，或保持相同 pytest 参数 |
| **P0-14** | CI / CHANGELOG | `changelog.yml` 直接 push main，无并发控制 | `.github/workflows/changelog.yml` | 多 commit 并发时 push 冲突，且自动提交可能绕过 CI | 改 PR 模式，加 `concurrency` 和 rebase retry |
| **P0-15** | CI / 版本同步 | `sync_skill_test_versions.py` 用脆弱正则替换常量块 | `scripts/dev/sync_skill_test_versions.py` | 加注释/空行会导致版本同步失败，阻塞 release | 改 AST 解析，或用显式 sync boundary |

---

## P1：下一 sprint 建议处理（30 项）

| ID | 模块 | 问题 | 位置 | 修复建议 |
| --- | --- | --- | --- | --- |
| **P1-01** | fetcher | `TencentQuoteFetcher` 返回第一个非空记录，未按 code 精确匹配 | `scripts/fetchers/quote/tencent_quote.py` | 遍历响应时校验 `v_<code>` 或返回 code 与请求一致 |
| **P1-02** | fetcher | `ThsQuoteFetcher` 输出字段不完整，缺 PE/PB/市值等 | `scripts/fetchers/quote/ths_quote.py` | 补齐字段占位，或标记 `is_minimal=True` |
| **P1-03** | fetcher | `_try_import` 吞噬所有异常，掩盖 fetcher 模块 bug | `scripts/fetchers/__init__.py` | 只吞 `ImportError/ModuleNotFoundError`，其他异常打 warning |
| **P1-04** | fetcher | HTTP requests 失败后 fallback 到 http.client，可能造成超时叠加 | `scripts/common/http.py` | requests 超时直接抛 `NetworkError`，或 fallback 使用更短 timeout |
| **P1-05** | fetcher | `cache` TTL jitter 使用 Python `hash()`，跨进程不稳定 | `scripts/common/cache.py` | 改用 `hashlib.md5/sha1` 生成稳定 jitter |
| **P1-06** | experts | 三套 veto/否决机制混用 | `experts/scoring/_merge.py`、`experts/__init__.py`、`experts/vote_engine.py` | 抽象 `VetoPolicy`，文档说明维度否决/人工否决/巴菲特警示区别 |
| **P1-07** | experts | `apply_veto` 基本是死代码 | `experts/__init__.py` | 删除，或重构为返回触发项与惩罚后分数 |
| **P1-08** | experts | 双组投票中长线 4:1 + 短线临界值场景规则不清晰 | `experts/vote_engine.py` | 增加边界测试矩阵，明确 4:1 是否可视为强多数 |
| **P1-09** | experts | 单组/双组短线"均分驱动"语义不一致 | `experts/decide.md`、`experts/vote_engine.py` | 文档明确双组短线均分驱动，单组投票驱动 |
| **P1-10** | experts | 校准 verify 仍需人工触发，无法真正防漂移（record 已自动） | `experts/calibration.py`、`scripts/calibration.py` | record_prediction 已由 run_debate 自动调用（decide.py:87）；verify 自动拉价回调已具备但需人工跑 CLI | verify 增加定时调度/自动到期验证 |
| **P1-11** | experts | 龙头地位仅近似、龙虎榜未纳入（炸板率已纳入） | `experts/scoring/*` | 炸板率已纳入 chaogu_yangjia.py:46；龙头地位用回撤近似（zhao_laoge.py:7-9 自认缺陷）；龙虎榜全缺失 | 给 zhao_laoge 增加 dragon_tiger 输入；龙头地位接入板块横截面排名 |
| **P1-12** | technical | 缠论中枢缺少 GG/DD 边界 | `scripts/chan/zhongshu.py` | 增加 `gg=max(high)`、`dd=min(low)` |
| **P1-13** | technical | `chan/__init__.py` 声明"线段未使用特征序列"已过时（实际已启用） | `scripts/chan/__init__.py` | `__init__.py:7` 称"未使用特征序列"，但 `xianduan.py:45,89` 默认启用特征序列；其余条目（GG/DD 缺失等）准确 | 更新注释，区分"已修复"和"仍偏离标准"的部分 |
| **P1-14** | technical | `_find_swing_points` 依赖未来窗口，背离检测含前瞻性 | `scripts/technical/core.py` | 增加 past-only 版本；报告中标注 `lookahead_required` |
| **P1-15** | technical | `composite_score` 依赖 `_SCORE_MAX` 魔数归一化 | `scripts/technical/scoring.py` | 改 rank-based scoring 或 `_SCORE_TARGET` |
| **P1-16** | technical | `signals` 用字符串子串判断金叉/死叉/超买超卖 | `scripts/technical/signals.py` | 改结构化 dict，如 `{"golden_cross": true}` |
| **P1-17** | business | `_calculate_composite_score` 误传个股 quote 当指数 quote 做市场环境检测 | `scripts/business/stock_analysis.py` | analyze() 传 `index_quote=quote`（个股，:118），detect_market_environment 在个股 quote 上做市场环境判定（:233）；get_quote("sh000001") 成死代码 | 在 analyze() 并行拉取 sh000001 指数行情，显式传入 |
| **P1-18** | business | 行情/K线/财务统一 30s timeout，不区分数据类型 | `scripts/business/stock_analysis.py` | 行情 15s、K线 25s、财务 45s，或由 fetcher 配置控制 |
| **P1-19** | business | `_hard_filter` 把 warning 混入 rejected reasons | `scripts/business/screening_service.py` | 返回 `HardFilterResult(reasons, warnings)` |
| **P1-20** | business | `risk_warning.py` 几乎未被 portfolio/monitor 消费 | `scripts/business/risk_warning.py` | 删除或接入 monitor/portfolio 风控链路 |
| **P1-21** | business | `position_var_summary` 用 `CVaR = VaR * 1.2` 经验常数 | `scripts/business/risk_metrics.py` | 使用历史收益计算 historical VaR / CVaR |
| **P1-22** | business | ST 过滤在 `universe_loader` 和 `_hard_filter` 双轨实现 | `scripts/business/universe_loader.py`、`scripts/business/screening_service.py` | 统一调用 `data.pool.is_st()` |
| **P1-23** | skills | `script-catalog.md` 漏列 6 个顶层脚本，缺 CI 校验 | `skills/_shared/references/script-catalog.md` | 漏列 calibration_backfill/sync、market_breadth、multi_stock_backtest、perf_bench、portfolio_web（引用的脚本均存在）；现有测试不校验 catalog 与 scripts/ 双向一致 | 用脚本自动生成 catalog，并加 CI 校验 |
| **P1-24** | skills | `five-layer.md` 与 `stock/SKILL.md` 重复声明评级框架 | `skills/stock/SKILL.md`、`skills/_shared/references/five-layer.md` | 只保留共享文档为权威源 |
| **P1-25** | skills | `market briefing` 与 `monitor briefing` 定义重叠 | `skills/market/SKILL.md`、`skills/monitor/SKILL.md` | 明确 market=市场面，monitor=持仓面，并互相引用 |
| **P1-26** | tests | `StockAnalysisService.analyze` 缺测试覆盖 | `tests/test_business.py` | mock quote/kline/finance，覆盖成功、部分失败、全部失败 |
| **P1-27** | tests | 缺 13 个 skill 真实工作流端到端测试 | `tests/e2e/` | 新增 `test_skill_workflow.py` 参数化跑 13 个 skill 主命令 |
| **P1-28** | CI | `tests/conftest.py` autouse fixture 捕获所有异常并 pass | `tests/conftest.py` | 只捕获 `ImportError`，其他异常应暴露 |
| **P1-29** | CI | pre-commit 的核心 pytest hook 是 `manual`，默认不跑 | `.pre-commit-config.yaml` | 增加 quick test hook 到 pre-commit，完整测试保留 manual |
| **P1-30** | config | `scoring.yaml` 有 DEPRECATED 死配置，修改不生效 | `scripts/config/scoring.yaml` | 删除或加 `expiry_version` + CI linter |

---

## P2：后续优化与架构债（30 项）— ✅ Round 9 全量修复完成

> 28 项真实/部分真实项已在 Round 9 全部修复（5 阶段提交）。2 项已由 Round 7/8 提前修复（P2-08、P2-22）。

| ID | 模块 | 问题 | 建议 | 状态 |
| --- | --- | --- | --- | --- |
| **P2-01** | experts | registry.py + yaml + md 三源维护成本高 | 长期改为 YAML 单源，md 只保留叙事文档 | ✅ 标注 v2.0 TODO + 测试增强 |
| **P2-02** | experts | `LEGACY_ALIAS` 与 `display_name` 双轨 | 统一从 `ExpertProfile.display_name` 读取 | ✅ 删除死代码 |
| **P2-03** | experts | `value_institution.score` 对 `buffett_sub_score` 缺失静默回退 50 | 改为显式错误，避免巴菲特警示失效 | ✅ warning + 回退 35 |
| **P2-04** | experts | `momentum_trader` 未硬排 ST / 监管处罚股 | 增加 ST / 监管风险 veto | ✅ ST 硬 veto |
| **P2-05** | strategies | 因子间共线性未治理 | 增加 VIF 矩阵、factor decorrelation 或 PCA | ✅ 标注 v2.0 + 诊断工具 |
| **P2-06** | strategies | `industry_thresholds.json` 行业覆盖不足 | 扩展到 31 个申万一级行业 | ✅ 扩展到 39 条目 |
| **P2-07** | strategies | regime overlay 会改变策略语义但报告不提示 | 报告显示"已应用市场状态 overlay"，增加 `--no-overlay` | ✅ 报告标注 |
| **P2-08** | strategies | chip 因子生产/回测路径不一致 | 文档披露差异或统一回测动态/静态逻辑 | ✅ Round 8 修复 + 注册对齐 |
| **P2-09** | strategies | `_STRATEGIES_LOCK` 存在但多处仍直读 `STRATEGIES` | 改 `_STRATEGIES` 私有，强制走 `get_strategy()` | ✅ 迁移到 API + strategy_exists |
| **P2-10** | technical | `kdj_full` 冷启动与通达信/同花顺可能有偏差 | 增加 warmup 选项或文档说明 | ✅ 标注 v2.0 docstring |
| **P2-11** | technical | `volume_analysis` 只检测最近 5 日连续缩量 | 增加 `shrink_window` 参数 | ✅ 参数化 |
| **P2-12** | technical | `report.py` 渲染段落顺序硬编码 | 抽象 `RenderSection`，支持配置段落 | ✅ 列表驱动 |
| **P2-13** | technical | `classifier.infer_industry` 关键词推断容易误判 | 增加 fetcher_industry 缺失统计与更强行业映射 | ✅ fetcher_industry 接线 |
| **P2-14** | technical | `chan_fenxing` 等高点/等低点边界未处理 | 增加等高/等低中性分型规则 | ✅ >=/<= + equal_eps |
| **P2-15** | fetcher | `AkshareQuoteFetcher` DataFrame 线性扫描 | `set_index("代码")` 或构建 code->row 缓存 | ✅ set_index + loc |
| **P2-16** | fetcher | requests/http.client 重定向行为不一致 | 统一重定向策略，最多跟随 5 次 | ✅ allow_redirects=True |
| **P2-17** | fetcher | `decode_gbk(errors="replace")` 静默替换乱码 | 替换发生时记录 warning | ✅ U+FFFD warning |
| **P2-18** | fetcher | `DataFetcherManager._last_error` 多线程不安全 | 改 thread-local 或记录 per-request error | ✅ threading.Lock |
| **P2-19** | fetcher | `BaseFetcher.provider` 推断依赖硬编码 provider set | provider 常量模块化，或要求子类显式传 provider | ✅ debug 日志 + TODO |
| **P2-20** | business | `LongTermEvaluator` 权重硬编码 | 移入 YAML 配置 | ✅ scoring.yaml 加载 |
| **P2-21** | business | `StockAnalysisService` 基本无状态但实例化 | 可改 module-level function 或 dataclass config | ✅ 模块级 analyze() |
| **P2-22** | business | `max_drawdown` recovery_idx 无法区分未恢复 | 返回 `recovered: bool` 或 `recovery_idx=None` | ✅ None 语义 + 测试 |
| **P2-23** | config | `ConfigLoader` mtime 缓存并发边界复杂 | 简化为锁内完整读写，或加更严格测试 | ✅ 并发测试 + TODO |
| **P2-24** | data | `data/cache.py` 用 `sys.modules` 替换模块对象 | 删除 shim，统一 `from common import cache` | ✅ re-export 替换 |
| **P2-25** | tests | frontmatter parser 手写简化版 | 改 `yaml.safe_load` | ✅ yaml.safe_load |
| **P2-26** | tests | `DESCRIPTION_KEYWORDS` 含废弃 skill | 删除废弃 key，改为 description 长度/结构校验 | ✅ 清理 + 补充 |
| **P2-27** | docs | 缺 ADR | 增加 `docs/adr/`：零依赖、熔断器、专家系统、回测偏差 | ✅ 4 ADR + README |
| **P2-28** | docs | 本土战法样本内拟合提示不够机器可读 | `patterns/config.json` 增加 `oos_validated:false` | ✅ oos_validated 字段 |
| **P2-29** | docs | 脚本目录和实际 scripts 漂移 | 自动生成并加入 CI | ✅ gen_script_catalog + CI |
| **P2-30** | release | `sync_version.py` 多文件正则维护成本高 | 增加版本字面量扫描与允许位置白名单 | ✅ 声明式 VERSION_TARGETS |

---

## 建议的 GitHub Issue / 任务包

### Milestone v1.15.1：稳定性与可信度修复（10 项）

1. **修复 fetcher 配置漂移：timeout/retry 生效**（P0-03）
2. **区分 429 限速与数据源故障，避免误熔断**（P0-04）
3. **修复 experts YAML 维度归一化**（P0-06）
4. **修复 vote_engine 单组全空死代码**（P0-09）
5. **对齐 decide.md 与 vote_engine 的巴菲特警示（P0-07）；校准公式改进降级 P2（P0-08 验证为设计选择，非 bug）**
6. **StockAnalysisService 填充 data_sources/data_failed/data_time**（P0-02）
7. **收紧 `.claude/settings.json` 权限**（P0-01）
8. **release.yml 与 ci.yml 测试标准统一**（P0-13）
9. **changelog.yml 改 PR 模式或加 concurrency**（P0-14）
10. **关闭 event/analyst 因子默认计算**（P0-12）

### Milestone v1.16.0：回测与策略可信度（7 项）- ✅ 全部完成

1. ✅ **回测财务 lookahead bias 披露或修复**（P0-10）-- Round 10: report_date+90天披露延迟过滤
2. ✅ **新增 walk-forward 回测框架**（P0-11）-- Round 10: walk_forward.py OOS 验证框架
3. ✅ **本土战法增加 OOS 验证标记**（P0-11 / P2-28）-- Round 9: oos_validated:false 字段
4. ✅ **缠论中枢补 GG/DD**（P1-12）-- Round 8
5. ✅ **technical composite_score 去魔数化**（P1-15）-- Round 10: _SCORE_MAX 提取为模块级常量+YAML
6. ✅ **补 StockAnalysisService 单测**（P1-26）-- Round 8
7. ✅ **补 13 skill E2E 工作流测试**（P1-27）-- Round 10: frontmatter 校验+mock 工作流

### Milestone v2.0.0：架构治理（7 项）- ✅ 全部完成

1. ✅ **experts 三源合一为 YAML 单源**（P2-01）-- Round 11: registry.py 删除 490 行硬编码，YAML 单源加载
2. ✅ **策略因子共线性分析与去相关**（P2-05）-- Round 11: VIF 诊断 + decorrelate_factors 残差化变换
3. ✅ **Config DEPRECATED 段治理机制**（P1-30 / P2-23）-- Round 8/9: 死配置清理+并发测试
4. ✅ **ADR 文档体系**（P2-27）-- Round 9: 4 ADR + README
5. ✅ **script-catalog 自动生成**（P1-23 / P2-29）-- Round 9: gen_script_catalog.py + CI
6. ✅ **data/cache shim 清理**（P2-24）-- Round 9: re-export 替换
7. ✅ **STRATEGIES 全局直读迁移到 API**（P2-09）-- Round 9: strategy_exists() + get_strategy()

---

## 验收参考

- **运行测试**：`python3 -m pytest tests/ -x -q`（基线 2699 用例应全部通过）
- **覆盖率**：当前门槛 60%；建议 v1.16 提升到 75%，v2.0.0 提升到 85%
- **lint**：black + ruff 应无新增警告
- **回归检查**：每次修复 P0 后跑端到端冒烟测试 `./tests/smoke_test.sh`

---

**维护说明**：本清单由 `docs/review-issues.md` 维护；每次完成修复请更新对应行的 ✅/状态，并归档到 CHANGELOG。

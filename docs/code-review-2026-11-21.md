# 项目整体 Code Review（2026-11-21）

> 范围：`scripts/`（275 个 Python 文件 / 约 5.7 万行）、`tests/`（184 个 Python 文件 / 约 3.7 万行）、`experts/`、`skills/`、`.github/`、`install.sh`、根目录配置与文档。
> 方式：7 个独立审查域并行静态审查 + 审查负责人对全部 P0/P1 与关键 P2 二次核实（read / 本地纯函数复现 / CLI 实测）。
> 本次审查**未修改任何源码**。

> **2026-11-22 产品专家复核注记**：本报告为 2026-11-21 审查快照，第 9 节修复记录已实施。复核确认 §4.5 的 `CLAUDE.md` 版本号条目已随发版修复（现为 v1.33.1 / 2026-11-21）；其余结论未逐条复验，作为历史证据原样保留。另：产品架构中的 fetcher 数量口径冲突（对外 37 / 源码实测 39）已上报 lead，由文档维护责任人在发版时统一，不在本审查报告中改写。

---

## 1. 结论摘要

| 项目 | 结论 |
| :-- | :-- |
| 测试基线 | `pytest tests/ -q` → **3132 passed, 12 skipped**（130s）；`ruff check` 全绿；`compileall` 全绿；`sync_version --check` / `sync_skill_test_versions --check` 全绿 |
| 总体评价 | 工程化程度高于同类脚本仓库：熔断/限流/缓存/原子写/Origin 校验/数据质量信封/版本门禁都有明确设计。但存在**系统性“承诺与行为脱节”**——配置改了不生效、标记传了被丢弃、门禁写了不阻断、回测 OOS 名存实亡 |
| 严重度分布 | **P0 × 2**（数据口径 / 验证有效性）；**P1 × 27**；**P2/P3 × 30+** |
| 最需优先处理 | ① walk-forward OOS 窗口重叠；② 不复权 K 线源被配置顶到最高优先级；③ CI 覆盖率/Release/契约门禁“假绿”；④ 数据层空值与降级标记丢失 |

**一句话结论**：项目“看起来很稳”（测试全绿、门禁齐全、注释详尽），但有两类问题会静默产出错误结论——**数据口径与验证机制的结构性缺陷**，以及**质量门禁的假阳性**。修完 P0/P1 后，绿灯才有质量信号意义。

---

## 2. P0 — 必须立即修复

### P0-1 Walk-forward 的所有 OOS 窗口实际是同一段时间，样本外验证失效

- 位置：`scripts/backtest/walk_forward.py:180-210`、`scripts/backtest/engine.py:256, 336-339`
- 证据：`get_kline` 的 fetcher 取**最近 `datalen` 根**（`eastmoney_kline.py:41` 的 `lmt=datalen`、`tencent_kline.py:41` 的 `count=datalen`），bars 永远右对齐“今天”。引擎用 `datalen = MIN_HISTORY(60) + total_days + 10`，再把 `eval_start/eval_end` 当 **bars 下标**。walk-forward 的 IS/OOS 同时递增 `total_days` 与下标，两者相消：
  - 默认 `train_days=120, test_days=30, step=30`，本地纯索引复现结果：

    | 窗口 | IS 覆盖（距今天交易日） | OOS 覆盖（距今天交易日） |
    | :-- | :-- | :-- |
    | w0 | 69–189 | 69–99 |
    | w1 | 69–219 | 69–99 |
    | w2 | 69–249 | 69–99 |
    | w3 | 69–279 | 69–99 |
    | w4 | 69–309 | 69–99 |

- 影响：5 个窗口的 OOS 全是同一段行情的重复统计，且 IS 段完全覆盖 OOS；`oos_sharpe`、胜率、回撤、`--walk-forward` 的“样本外”承诺全部失真，并会误喂后续 OOS 状态升级（见 P1-11/12）。
- 建议：一次性拉取覆盖所有窗口的 bars，按 `bar.day` 切日历区间；IS 严格早于 OOS 首根，禁止用“数据深度”表达时间窗口。

### P0-2 不复权 K 线源被 YAML 顶到最高优先级，全量指标口径混杂

- 位置：`scripts/config/data_source.yaml:77-81` ↔ `scripts/fetchers/kline/sina_kline.py:3-6, 31`
- 证据：sina fetcher 文件头与类 docstring 明确写“新浪 API 不支持复权……优先级从 10 降为 3，让前复权源优先命中”，`__init__` 也传 `priority=3`；但 YAML 把 `kline_sources.sina.priority` 设为 **10**（全源最高），且 YAML 首行声明“运行时优先级以此文件为准”，`fetcher_base.py:333` 执行覆盖。实测 manager 顺序：

  ```
  SinaKlineFetcher priority=10 → Eastmoney 8 → Tencent 6 → Pytdx 5 → Efinance 4 → Akshare 3 → ...
  ```

- 影响：默认配置下 A 股 K 线优先取**不复权**数据，除权日 OHLC 跳变；一旦降级又切到东财/腾讯**前复权**数据，同一指标序列口径混杂，MA/MACD/回测收益全面失真。`KlineBar` 无复权口径字段，下游无法识别。
- 建议：把 `sina.priority` 降到 3 以下或禁用；在 `KlineBar` 与缓存键中显式记录 adjust 口径；清理代码注释与配置互相矛盾的现状。

---

## 3. P1 — 高优先级问题

### 3.1 数据基础设施与故障转移

| # | 位置 | 问题与影响 | 建议 |
| :-- | :-- | :-- | :-- |
| 1 | `scripts/common/cache.py:85-92` | `flock` 锁在 `mkstemp` 创建的**唯一临时 inode** 上，各进程锁不同文件，跨进程互斥从未生效；`os.replace` 只保证原子写不保证互斥 | 按 key 使用固定 `.lock` 文件，锁内完成检查/写入/replace |
| 2 | `scripts/data/__init__.py:375-388` | 防穿透写入 `cache.set_json(zero_key, [])`，读取却用 `if zero_cached:`——空列表 falsy，分支永不进入；主 key `if cached:` 同理。全源失败时 5 分钟短缓存完全失效，全市场预取放大为雪崩重试 | 用 `is not None` 区分“未命中”与“缓存了空列表”，为 None 设计独立哨兵 |
| 3 | `scripts/common/rate_limiter.py:167-193`（另见 85-112） | `slot()` 的退避 `time.sleep()` 在 `try/finally` 之外，中断即永久泄漏 permit（默认仅 8 个）；且持槽 sleep 把并发压到接近 1，与 docstring“KeyboardInterrupt 也能归还”相反 | acquire 成功后立刻进 try/finally；sleep 移到持槽之前或用独立退避锁 |
| 4 | `scripts/common/http.py:170-182, 212-214` | 响应超限 `break` 后未排空 socket 就把连接 `_return_connection` 回池；下次复用会把残留旧字节当新响应解析，产生随机错乱数据 | 截断分支关闭/丢弃连接，或 drain 至响应结束 |
| 5 | `scripts/common/fetcher_base.py:458-465` | `_archive_fallback_chain` 在空链时提前 return，健康请求沿用上次失败血缘，数据质量层持续把该标的标为 degraded | 无论链是否为空都按 code 覆盖归档（空链写 `[]`） |
| 6 | `scripts/common/fetcher_base.py:62-90` + `fetchers/flow,lhb,event,chip` | provider 隐式推断只认白名单最后一段，得到 `northbound/stock/lhb/earnings/margin` 等，与 YAML 键（`eastmoney/sina`）不匹配，4 个数据域 priority/timeout/retry/enabled 全部失效；两个北向 fetcher 同名共享熔断器 | 显式传 `provider="eastmoney"/"sina"`，两个 northbound fetcher 改不同 name |
| 7 | `scripts/fetchers/quote/ths_quote.py:83-85` + `data/__init__.py:473-505` | THS 设 `is_minimal=True` 并用 0 占位 PE/PB/市值/换手，但 `Quote` 无该字段、全仓无消费方；0 值被当真实估值进入 scoring，数据质量层也不标降级 | 透传 `is_minimal` 到 Quote/data_quality，或该源把估值字段置 None 并标 fallback |
| 8 | `scripts/fetchers/quote/eastmoney_quote.py:14-18, 50-64` | 核心字段为 `"-"` 时 `_div100` 返回 None，fetcher 仍返回 dict 被视为成功；`to_float(None)=0`，价格/PE/市值静默变 0，错误源不熔断不切源 | fetcher 层校验核心字段（至少 price），无效则 `None`/`ParseError` 让 manager 切源 |
| 9 | `scripts/common/parsers.py:96-98, 116-144` + `technical/astock.py:36-37, 75` | 腾讯字段定义了 `limit_up:47/limit_down:48` 且要求 `len>=50`，但返回 dict 未输出这两项；`limit_up_price>0` 真实涨跌停封板分支**永不可达**，ST/特殊波动误判 | 补输出 limit_up/limit_down 并在 data 层透传 |
| 10 | `scripts/fetchers/kline/baostock_kline.py:151-168` | 连续失败 3 次后**每次失败**同步 `sleep(60)`，次数不封顶；全市场 3323 只可拖到数十小时，直接撞 screener 1800s watchdog 真终止 | 改为基于时间的节流，或抛给 manager 由熔断器收敛 |
| 11 | `scripts/fetchers/event/eastmoney_event.py:220-232` | `change_num = to_float(..., 0)`，缺失 `"-"` 与真实 0 都被判 `"decrease"`，污染事件因子与排雷结论 | 用 `default=None` 四分支：unknown/increase/decrease/unchanged |
| 12 | `scripts/fetchers/quote/xueqiu_quote.py:15-23` | symbol 转换不处理 `.SH/.SZ` 后缀与 `us:/hk:` 前缀（`600989.SH → SH600989.SH`），且不校验返回 code；后缀代码在雪球源必然失败并被记为 empty | `plain_code()` 去后缀，跨市场返回 NOT_HANDLED，解析后校验 code |

### 3.2 回测与验证可信度

| # | 位置 | 问题与影响 | 建议 |
| :-- | :-- | :-- | :-- |
| 13 | `scripts/backtest/engine.py:56-59` | `pe = close/eps` 忽略 `period_type`；一季报 EPS 是单季口径，PE 高估约 4 倍，全年约 8 个月估值评分失真（val 权重 0.19–0.33）；`data/helpers.py:227-254` 已有正确 `compute_pe()` | 复用 `compute_pe(close, eps, period_type)`，未知口径置 0 走中性 |
| 14 | `scripts/backtest/engine.py:60, 66-69` | 回测 quote 的 `total_cap` 来自不存在的 `FinanceRecord.total_cap` 恒为 0，`turnover` 硬编码 0；流动性因子 28+24 分、momentum 6 分全废，大市值亏损惩罚永不触发 | 从 K 线+股本构造历史市值/换手，或在报告中显式标注因子降维 |
| 15 | `scripts/multi_stock_backtest.py:384, 448, 458` | OOS 的 `n_stocks` 用 `len(codes)`（请求数），但引擎会丢弃 K 线不足/末根陈旧股票（engine.py:264-269）；请求 280 只实际 20 只也能记 280 并升级 `oos_verified` | 引擎回传 `effective_universe_size`，用它作为 n_stocks |
| 16 | `scripts/strategies/oos_validation.py:148-191` + `multi_stock_backtest.py:143-146, 486-488` | 池宇宙指纹只打印不校验，`evaluate_multi_pool` 只检查池数 ≥2；同一批代码分别以 default/large 跑两次即可双池“通过” | 指纹纳入联合判定，相同或高度重合强制 `in_sample` |
| 17 | `scripts/backtest/engine.py:399-401` + `strategies/registry.py:32-93` | event 因子 6 策略均 0.05 权重但回测明确禁用，parts 填中性 50，5% 对排序零贡献；sentiment 因子权重为 0 是死代码。回测策略 ≠ 实盘策略 | 回测真实计算 event，或减去权重重新归一化并标注 event-free 口径 |

### 3.3 业务契约与 CLI 输出

| # | 位置 | 问题与影响 | 建议 |
| :-- | :-- | :-- | :-- |
| 18 | `scripts/classifier.py:74-77` | 读旧 schema 字段 `ROEJQ/PARENTNETPROFITTZ/XSMLL/ZCFZL`，但两个调用方（`classifier.py:510-521`、`technical/analyzer.py:189-197`）经 `finance.fetch()` 传入的是 `FinanceRecord.to_dict()`（标准字段 `roe/net_profit_yoy/gross_margin/debt_ratio`）。四特征恒 0，分类恒落“普通股” | 改读标准字段名 + None-aware |
| 19 | `scripts/init_pool.py:92-103, 158-177` | JSON 模式 stdout 混入进度 print；两个函数返回 bool，失败（False）仍包装成 `{"summary":"completed"}` 与 `"status":"ok"`，退出码 0 | 业务日志走 stderr；按返回值设 status 并 exit 1 |
| 20 | `scripts/calibration.py:243, 247, 251, 261` | 子命令 report/factor/pending/lessons 重复注册 `-j` 覆盖全局参数。实测 `calibration.py -j report` 输出 Markdown，`report -j` 才输出 JSON | 子命令去掉 `-j`，统一用父解析器全局参数 |
| 21 | `scripts/refresh_pool.py:144-146`、`scripts/snapshots.py:188, 198` | `--diff -j` / `-j diff A B` 同类混流与参数覆盖，JSON 契约失效 | 同 #20 处理；json 模式 diff 走 stderr |
| 22 | `scripts/screening_service.py:415-430` | 硬过滤警告把**实际值**当**阈值**显示（goodwill=45 输出 “>45%”，真实阈值 30） | 文案改用 `_goodwill_threshold()` / `_pledge_threshold()` |
| 23 | `scripts/long_term.py:309-310, 326-333` | `quote.get("pe_percentile")` 无数据源（Quote 无此字段）恒为 -1，PE 历史分位三分支永不触发，丢失宣称的 15 分调节 | 用 `score_utils.pe_percentile(pe, industry)` 现场计算 |
| 24 | `scripts/market_breadth.py:88-90, 117` | 东财无数据字段为 `"-"`，`"-"+"-"` 得 `"--"`，比较时 TypeError 被吞，全市场宽度静默降级 | 逐字段 `to_float` 判空 |

### 3.4 组合与风控

| # | 位置 | 问题与影响 | 建议 |
| :-- | :-- | :-- | :-- |
| 25 | `scripts/portfolio/crud.py:283-292` + `trade_log.py:131-136` + `guardrails.py:85-89, 339-353` | 清仓不传 `sell_price`，卖出记录 profit/profit_pct 恒 0，连亏/回撤熔断永不触发；实测连亏 3 笔仍 `triggered=False`。Web「清仓」是最常用退出路径，硬约束对此失效 | 采集卖价（无价按现价/成本估算并标注），`sync_breakers` 同时用绝对 profit 判连亏 |
| 26 | `scripts/portfolio/web/utils.py:92-99` + `dispatch.py:89-101` | `json.loads` 默认接受 `NaN/Infinity`，`float('nan') < 0` 为 False 绕过校验，`json.dump` 写出非法 JSON 并污染全部盈亏计算；已实测 POST NaN 返回 ok | 所有数值入口 `math.isfinite()`，`parse_constant` 拒绝 NaN/Infinity |
| 27 | `scripts/portfolio/health_report.py:676`（对比 689） | 技术破位但无行情时 `pnl_pct=None`，Markdown 用 `{:+.2f}` 格式化直接 TypeError，`/portfolio health` 崩溃 | 与 689 行一致做 None 判断 |

### 3.5 CI / 质量门禁

| # | 位置 | 问题与影响 | 建议 |
| :-- | :-- | :-- | :-- |
| 28 | `.github/workflows/ci.yml:130, 138-141` | `pytest ... \| tail -5` 吞掉退出码（工作流无 `shell:`/`pipefail`，默认 `bash -e` 取管道末尾状态）。全仓 48% 与核心 10 目录 57% 覆盖率门禁**从未 blocking**，覆盖率跌到 0 也绿 | 去掉 tail 或 `set -o pipefail`；核心门禁搬进 `test-suite.yml` 统一 blocking |
| 29 | `.github/workflows/release.yml:85` | `needs: [validate, publish]` 但 `if` 只判断 `validate.result`；test 失败 → publish skip → 仍创建 GitHub Release | `if` 同时判断 validate/test/publish 三者均为 success |
| 30 | `scripts/dev/sync_version.py:295` | `--check` 只判 mismatch 不判 missing；删掉任一 SKILL.md 的 version 字段或 README badge 仍 exit 0 | exit 条件加入 `result["missing"]` |
| 31 | `.github/actions/setup-test/action.yml:36` | pip 列表漏装 `jsonschema`，契约测试 `test_schema_is_loadable_by_jsonschema` 永远 skip（pyproject 明确列为测试依赖） | 改 `pip install -e '.[test]'`，并把该 skip 改为 `pytest.fail` |

---

## 4. P2 / P3 — 中低优先级精选

### 4.1 数据语义与健壮性

| 位置 | 问题 | 级别 |
| :-- | :-- | :-- |
| `common/http.py:35-54, 250` | 进程级共享 `requests.Session` 用于多线程 screener，官方不保证线程安全，与模块“线程安全”注释不符；建议 thread-local | P2 |
| `common/http.py:45, 266-292` | requests 路径硬编码 `Retry(total=3)`，`max_retries` 参数被忽略，YAML retry 调优全部失效；stdlib 回退路径又固定传 1 | P2 |
| `common/utils.py:26-29` | `@file` 白名单用字符串前缀判断，`scripts/data_backup/x.txt` 可绕过兄弟目录检查 | P2 |
| `common/exceptions/silent_fallback.py:98-125` | 按 (模块, 异常类型) 永久去重，一次早期瞬时错误会占掉告警名额，后续真实故障全部降为 debug 且 _SEEN 永不老化 | P2 |
| `data/sentiment_panel.py:151, 239-240` | 按日期做缓存 key 却共用单一 `_cache_ts`，拉新日期会无限续期旧日期缓存；无锁竞态 | P2 |
| `common/fetcher_base.py:411-425` | 429 重试分支 `except ...: pass` 吞掉所有异常，不记录血缘/日志/熔断，故障不可见 | P2 |
| `data/config.py:68-69` + `common/cache.py` | YAML `cache.max_size/max_age` 是死配置；`parallel_timeout` 误用 `http.read_timeout`，改单次读超时会意外改批量预算 | P2 |
| `fetchers/*/eastmoney_*` 等 5 处 | JSON 解析失败一律 `return None`，manager 记 `empty` 不累计熔断；反爬 HTML 错误页被当“无数据”，持续高频打失效源 | P2 |
| `fetchers/__init__.py:405-423` | 数据源配置加载失败静默退回默认（warning 都没有），整条 failover 行为突变且难排查 | P2 |

### 4.2 回测指标

| 位置 | 问题 | 级别 |
| :-- | :-- | :-- |
| `backtest/metrics.py:281-312, 326-379` + `engine.py:336-341` | 基准切片 off-by-one：首个选股日查不到基准，首期收益记 0，污染 IR/alpha/beta | P2 |
| `backtest/metrics.py:196, 211, 217, 221-223` | alpha / 超额夏普单位错配 100 倍（收益是百分数、rf 是小数），与 Sharpe 口径不一致 | P2 |
| `strategies/patterns/backtest_report.py:75-82, 241` | 夏普用逐笔收益 mean/std 不年化、无 rf；总收益用加总非复利；回撤基于线性权益 | P2 |
| `backtest/engine.py:264-269` | 用“末根距今 ≤30 天”过滤池，退市/长期停牌股被整体剔除，幸存者偏差高估收益 | P2 |
| `backtest/cli.py:494-498` | 提示“自动调整为 top=len(codes)”但未修改 args.top，指标按原值虚报 | P3 |

### 4.3 技术分析与板块

| 位置 | 问题 | 级别 |
| :-- | :-- | :-- |
| `technical/macd.py:107-111`（调用 87-90, 98-101） | 背离极值最近邻无距离上限，可跨很远 K 线误配对（`volume.py:202, 209` 的 OBV 背离有 ≤5 窗口约束）；误报直接进入 signals 与 ±8 分评分 | P2 |
| `sector_etf_strength.py:589-590` | `strong = ok_sorted[:3]` 与 `weak = ok_sorted[-3:]`，恰好 3 个 ETF 时两者是同一批，Markdown 同时列🔥强势与💀弱势 | P3 |
| `technical/candlestick.py:77, 101, 104` | 十字星 `body/total<0.1` 在前，T 字/倒 T 字 `<0.05` 是子集，**分支永不可达**；实测典型 T 字返回“十字星” | P3 |
| `technical/scoring.py:793, 884` | `if True:` 恒真、else 双重不可达（762-773 已提前 return） | P3 |
| `sector_etf_strength.py:367-371` | if/else 两分支输出完全相同的字符串，方向信息丢失 | P3 |
| `technical/trend.py:75-77` | 注释称整数关口“向下取整”，实现仍用 `round()`（银行家舍入），55/65/75 时锚点跳变 | P3 |

### 4.4 组合 / Web / 测试

| 位置 | 问题 | 级别 |
| :-- | :-- | :-- |
| `portfolio/health_report.py:486` + `crud.py:29-38` | 回撤把“当前持仓成本”当初始资金，与落盘的 `total_assets` 口径不一致；缺该字段时退化为“969% 假回撤”场景 | P2 |
| `portfolio/web/dispatch.py:282-299` | `target_buy="abc"` 经 `_parse_float`→None→`or 0`，静默清空原目标价并返回 ok；add_watch 同类输入却返回 400 | P2 |
| `portfolio/crud.py:125-136` + `manager.py:542-570` | 熔断无逃生口：错误提示建议 `force=True`，但 facade/dispatch 都不透传，全仓无调用点，10 天冷却期内无法加仓 | P2 |
| `portfolio/_file_utils.py:87-125` | 陈旧锁清理 TOCTOU 竞态：B 可删掉 A 新建的锁，双进程同时写；5 分钟会把活锁误判为 stale | P2 |
| `portfolio/health_report.py:363-365` | 报价存在但 price=0 时把全部成本记成真实亏损（pnl=-总成本），风险评级失真 | P2 |
| `portfolio_correlation.py:194-199` | 相关系数按序列头截断而非按交易日对齐，停牌/次新股 K 线数不同时配对错位，分散化结论失真 | P2 |
| `portfolio/web/app.py:170-190, 219-224` | 限流在鉴权之前且按单一 127.0.0.1 IP 计数，无效 token 可灌满窗口让合法页面 429 | P3 |
| `portfolio/_file_utils.py:141-154` | `raw_write` 无 `fsync`，断电可致空/截断的 portfolio.json | P3 |
| `.coveragerc:4-6` | omit 掉仍活跃的 `technical/sentiment.py`、`technical/report.py`，覆盖率门禁对其失明 | P2 |
| `tests/contracts/test_skill_metadata_sync.py:162-163` | `if "version" in fm:` 才断言——删掉字段即绕过版本契约 | P2 |
| `tests/integration/test_contracts_path.py:114-116` | 只断言 stdout/stderr 非空，traceback 也算通过 | P2 |
| `tests/integration/test_skill_index_code.py:82-83, 101-102, 130-131` + `nightly-network.yml` | 脚本失败一律 `pytest.skip`，全 skip 退出码 0 + `continue-on-error`，nightly 告警永不触发 | P2 |
| `tests/smoke_test.sh:160-172` | `output=$(cmd \|\| true)` 后判 `$?` 恒为 0，两个冒烟断言永真 | P2 |
| `scripts/dev/validate_contracts.py:80-82` | schema 文件被删光时返回 0 通过，契约门禁可绕过 | P2 |
| `tests/unit/test_rate_limiter.py:28-37` | 无断言测试，acquire/release 退化为 no-op 也不会失败 | P3 |
| `tests/unit/test_ci_simulate.py:34-46` | 依赖具体错误文案 + 3 次真实退避 sleep，约 4.5s 且脆弱 | P3 |

### 4.5 本次审查自身发现的文档/接线问题

| 位置 | 问题 | 级别 |
| :-- | :-- | :-- |
| `scripts/data/__init__.py:225` + 全仓调用点 | 新加的 `get_kline(require_date=...)`（防止 TTL 内复用盘中/旧 K 线）**只有测试调用，生产路径零使用**；screener 仍静默复用不新鲜缓存。`scheduled_task.py:193` 注释仍称“命中缓存不比对末根日期” | P2 |
| `CLAUDE.md:5` | 头部曾写 v1.23.1 / 2026-10-19，实际 package.json 为 **1.33.1**；`sync_version.py` 的 8 目标不含 CLAUDE.md，故门禁未捕获（**2026-11-22 复核：已修复**，现为 v1.33.1 / 2026-11-21） | P3（已修复） |
| `scripts/common/screener_watchdog.py:18` | 模块 docstring 示例调用 `wd.mark_done()`，实际 API 只有 `cancel()`；且“设事件后主线程抛异常退出”的旧设计描述与现在 `os._exit(2)` 实现矛盾 | P3 |
| `scripts/common/exceptions/silent_fallback.py:6-14` | docstring 声称存在 `SilentFallbackError` 且 HIGH 风险抛异常，实际只有 `log_silent_fallback`，CLAUDE.md 也明确未实现 | P3 |

---

## 5. 横切主题（根因分析）

1. **配置 / 注释 / 运行时三者脱节**：YAML 把不复权源顶到最高优先级（P0-2）、4 个数据域 provider 推断错误导致配置全失效（P1-6）、`max_retries` 与 cache YAML 是死配置、watchdog docstring 描述旧实现。代码里写好的防御意图在运行时并未生效。
2. **“空值 / 失败 / 降级”语义混淆**：空列表缓存用真值判断（P1-2）、`"-"` 转 0 价（P1-8）、0 变动判减持（P1-11）、THS 最小源标记被丢弃（P1-7）、JSON 解析失败记 empty 而非 error（P2）。这正是“静默错误数据”的主要来源——比崩溃更危险。
3. **验证机制只验证标签不验证内容**：walk-forward 时间窗口错位（P0-1）、OOS 用请求数当实际样本数（P1-15）、池宇宙指纹只打印不校验（P1-16）、覆盖率/Release/契约门禁假绿（P1-28~31）、永真断言与 skip 掩盖失败（P2）。
4. **契约漂移**：FinanceRecord schema 迁移后 classifier 未同步（P1-18）、CLI `-j` 被子命令覆盖（P1-20/21）、字段定义了不输出（P1-9）、文档版本号不参与同步（P3）。
5. **并发与资源**：缓存伪锁、permit 泄漏、连接污染、共享 Session、无 fsync、TOCTOU 锁清理。单线程 CLI 场景大多看不出问题，在 Web 服务/全市场并发跑批下会被放大。

---

## 6. 建议修复路线图

**阶段一（立即，1–2 天）— 恢复“结论可信”**
1. P0-1：walk-forward 按真实日历切窗口，IS/OOS 严格不重叠。
2. P0-2：sina K 线降优先级 + KlineBar 记录复权口径。
3. P1-28~31：修 CI 管道退出码、Release 门禁、`sync_version --check` missing、setup-test 补 jsonschema。此步做完，绿灯才重新成为质量信号。

**阶段二（近期，1–2 周）— 堵住“静默错误数据”**
4. P1-2/3/4/5/6/7/8/9：缓存空值、限流器泄漏、连接污染、降级链、provider 显式声明、最小源标记、0 价行情、涨跌停价字段。
5. P1-13~17：回测 PE 口径、市值/换手、OOS 真实样本数与池独立性、event 权重口径。
6. P1-18~24：classifier 字段、JSON 输出契约（建议加“stdout 必须是纯 JSON + 失败退出码”的通用测试）、筛选文案与 PE 分位。
7. P1-25~27：清仓喂熔断、NaN 输入校验、health_report 空值渲染。

**阶段三（持续）— 清理假绿与死代码**
8. 修 P2 中 5 处“skip/永真/文案”测试、`.coveragerc` omit、契约 CLI 无 schema 返回 0。
9. 处理死代码与重复分支：T 字线、`if True:`、相同 if/else、pe_percentile、`require_date` 接线或删除。
10. 引入并发测试与“降级态”冒烟测试（行情部分失败 + 技术破位、NaN 输入、多进程写缓存/portfolio）。

---

## 7. 分层质量评价

| 层 | 评价 |
| :-- | :-- |
| `common` / `config` / `data` | 设计意图清晰、注释详细，但“锁/空值/退避/血缘”四处落地失真；并发场景健壮度不足，是所有上层问题的放大源 |
| `fetchers` | 数据源覆盖广、故障转移框架完整；但配置优先级与 provider 声明的系统性断裂会造成**静默错数据**，风险最高 |
| `business` / CLI | 防御性设计与数据质量信封扎实；主要短板是 schema 漂移和 JSON 输出契约 |
| `strategies` / `backtest` | 财务披露时点、涨跌停、T+1、最低佣金都做了正经工作；但 OOS 与回测数据同源于实盘因子的承诺未兑现，验证结论不可直接采信 |
| `portfolio` / `monitor` | 工程化程度高（Origin 白名单、Bearer token、原子写、双层锁、通知去重）；保护机制与真实交易链路接线不完整是主要缺口 |
| `technical` / `chan` | 算法与边界处理扎实，未发现前视偏差；残余风险是极值匹配缺时间约束与不可达分支 |
| `tests` / CI / 工具 | 数量与仪式感充足，但多个关键门禁不 blocking、多处测试把失败伪装成通过；修好门禁比再加测试更重要 |

## 8. 正面结论（本次未发现的问题）

- 技术分析层未发现使用未来数据的前视偏差；摆动点/分型均为右侧确认（滞后而非预知）。
- 无硬编码密钥/token，无 `eval`/`exec`/`shell=True`/`os.system` 用法。
- 测试基线、静态编译、ruff、版本与 skill 元数据同步门禁在当前代码上全部通过。
- Web 层做了 Origin 白名单、Bearer token 常量时间比较、模板 XSS 转义、tempfile+os.replace 原子写等真实防护。
- 项目对历史事故的复盘记录在注释中保存完整，具备良好的“可审计性”传统——建议把这次审查的修复同样以“实测复现 → 修复 → 回归测试”的方式记录。

---

## 9. 修复记录（2026-11-21 同日实施）

用户确认“进行修复”后，本报告第 2–4 节的 **P0 × 2 + P1 × 27 + 精选 P2/P3** 已全部实施，未修改业务语义之外的接口，未提交 commit。

### 9.1 已落地的关键修复

| 条目 | 修复摘要 |
| :-- | :-- |
| P0-1 | walk-forward 所有窗口统一 `total_days=max_total_days`，eval 边界仍逐窗推进；新增测试断言 5 个 OOS 区间互不相交、按时间递进且 IS 不覆盖 OOS |
| P0-2 | sina K 线优先级 10→0（代码默认值同步），`KlineBar.adjust` 元信息 + 显式 `adjust` 参数隔离缓存桶；实测首个 K 线源已是 Eastmoney(8) |
| P1-1/2/3/4 | 缓存按 key 固定 `.lock` 文件实现真正跨进程互斥；财务空值缓存改 `is not None` 并修复 zero_key 双重失效；限流器退避移出临界区并用 try/finally 包裹；超限响应连接丢弃而非回池 |
| P1-5~12 | 降级链空链也覆盖归档；flow/lhb/event/chip 显式 provider + 北向 fetcher 独立熔断器；THS 最小源标记透传并中和 0 占位估值；东财无效价切源；腾讯涨跌停价输出；baostock 退避改时间节流；增减持方向四分支；雪球后缀/跨市场代码处理；JSON 解析失败统一 `ParseError`（含 sina） |
| P1-13~17 | 回测 PE 复用 `compute_pe`；市值/换手从净资产反推并带降维披露；OOS 样本数用真实入池数；池宇宙指纹纳入多池联合判定；event 权重剔除后重新归一化 |
| P1-18~24 | classifier 改标准财务字段；init_pool/calibration/refresh_pool/snapshots 的 JSON 契约与退出码；筛选警告显示真实阈值；PE 分位现场计算；市场宽度逐字段判空 |
| P1-25~27 | 清仓卖价喂给连亏/回撤熔断；Web 数值入口拒绝 NaN/Infinity；破位报告空值渲染不崩溃 |
| P1-28~31 | CI 覆盖率去 `| tail`；Release 校验 test/publish；`sync_version --check` 判 missing；setup-test 补 jsonschema |
| 精选 P2/P3 | 基准 off-by-one、alpha 单位、夏普年化、MACD 背离距离约束、T 字线死分支、`if True`、强弱板块自相矛盾、组合回撤口径/锁 TOCTOU/相关性按日对齐/限流在鉴权后、测试假绿（skip/永真/文案）等 |

### 9.2 验证证据

- 全量测试：**3365 passed, 12 skipped**（修复前基线 3132 passed / 12 skipped，新增 27 个回归测试文件、233 条用例）。
- 覆盖率门禁：全仓 **57.5% ≥ 48%**；核心 10 目录 **66.8% ≥ 57%**（移除 `.coveragerc` 的 omit 后仍达标）。
- `ruff check scripts tests experts`：**All checks passed**；`compileall`、`sync_version --check`、`sync_skill_test_versions --check`、`validate_contracts.py` 均通过。
- 端到端冒烟（先按文档跑 `install.sh` 建 symlink）：**79 通过 / 0 失败**；其中 `hot_rank.py` 因缺少生成物 `all_stocks.json` 被**显式标为跳过**（旧版 `$?` 恒真断言会把它误报为通过）。
- 各修复均先写回归测试并在旧代码上验证失败（技术层 10 failed、组合层 23 failed、回测核心 16 failed 等），再修代码至全绿。

### 9.3 未覆盖 / 遗留风险

- K 线复权口径：仅 sina 显式标 `adjust="none"`、eastmoney/tencent 推断 `qfq`；其它 fetcher 返回 `adjust=""`（未知），manager 尚无按口径路由能力。
- 东财行情只校验核心价格字段，PE/市值等其它 `"-"` 字段仍会转成 0。
- 回测 turnover 用总股本近似（缺流通股本字段），且退市/长期停牌过滤仍存在幸存者偏差（已新增披露字段，未改选池逻辑）。
- walk-forward 统一数据深度后，数据源若给不到 `60+max_total_days+10` 根 K 线，所有窗口会一起失败。
- 组合 `force` 逃生口仅 API 可用（UI 未加勾选框），依赖 Bearer token；文件锁改用 `fcntl.flock`，为 Unix 语义。
- 修复引入约 83 个文件修改 / 27 个新增回归测试文件；本轮未做 commit，建议按模块拆成多个 Conventional Commit 提交。

<!-- markdownlint-disable MD024 -->

# Changelog

本文件记录 stock-analyzer-skill 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.7.0] - 2026-06-12

### Added

- 专家圆桌决策引擎 `experts/decide.py`（decide.md 代码化）：
  - `detect_market_state()`：市场环境检测（牛市/熊市/震荡/冰点/亢奋），基于价格均线偏移、量能比、市场宽度指标综合判定
  - `aggregate_votes()`：8 位专家加权投票聚合，整合市场状态权重 × 投资期限权重，输出净多/净空/方向/强度/共识度/仓位建议/信心指数
  - `aggregate_group_votes()`：长线-only / 短线-only 单组模式投票聚合（decide.md §七）
  - `format_debate_output()`：结构化辩论报告格式化，含方向分布、共识评估、仓位上沿/下沿
  - `_MARKET_WEIGHTS` / `_HORIZON_WEIGHTS`：双权重矩阵（市场状态 × 投资期限），支持短线/中线/长线三种周期
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

- 支持更多数据源（如雪球、同花顺）
- 添加历史回测功能
- 支持港股和美股分析
- 添加更多本土战法形态
- 优化缠论算法
- 添加自动化测试

---

## 版本说明

- **主版本号**：不兼容的 API 变更
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

## 链接

- [GitHub 仓库](https://github.com/CurtisTong/stock-analyzer-skill)
- [问题反馈](https://github.com/CurtisTong/stock-analyzer-skill/issues)
- [发布页面](https://github.com/CurtisTong/stock-analyzer-skill/releases)

# 项目架构深度审查报告（2026-07-07）

> 三方专家联合审查：技术架构师 + 投资专家 + 产品经理

---

## 一、项目概况

| 指标 | 数值 |
|:---|:---|
| Python 文件 | ~244 个（含 tests 123） |
| Markdown 文件 | ~107 个 |
| 核心模块 | scripts/（112 .py）、experts/（27 .py + 15 .md + 15 .yaml） |
| Skills | 13 个（9 核心 + 4 变体） |
| 测试文件 | 107 个 |
| 数据源 Fetcher | 28 个模块 × 7 数据域 |
| 专家人设 | 15 份（9 active + 6 legacy 已合并） |
| 外部运行时依赖 | 零（仅 stdlib + PyYAML） |

---

## 二、技术架构审查

### 2.1 架构设计 ✅ 优秀

**三层分离架构**执行良好：

```
SKILL.md（交互层）→ scripts/*.py（入口层）→ business/（业务层）→ fetchers/（数据层）
```

- `common/` 基础设施层提供了完整的 HTTP/编码/字段映射/缓存/熔断器抽象
- `business/` 与 `fetchers/` 解耦彻底，通过 `DataFetcherManager` 统一接口
- PEP 562 `__getattr__` 延迟加载避免循环依赖
- 配置外部化到 YAML，支持点分路径访问

### 2.2 熔断器实现 ✅ 健壮

[circuit_breaker.py](scripts/common/circuit_breaker.py) 实现质量高：

- 线程安全（`threading.Lock` 保护所有状态变更）
- 完整的三态机：closed → open → half_open → closed
- 可配置的 `half_open_success_threshold` 严格守卫
- 全局命名单例模式（`get_circuit_breaker()`）
- 半开期试探次数限制 + 超时重置

### 2.3 异常体系 ✅ 完善

[exceptions/__init__.py](scripts/common/exceptions/__init__.py)：

```
StockAnalyzerError
├── DataError → NetworkError / RateLimitError / ParseError / HTTPStatusError / DataUnavailableError / InsufficientDataError
├── BusinessError → ValidationError / StrategyError
└── ConfigurationError
```

- `USER_FRIENDLY_MESSAGES` 字典提供用户友好错误映射
- `is_retryable_error()` 区分可重试/不可重试错误
- 向后兼容别名（`DataSourceUnavailableError = NetworkError`）

### 2.4 技术问题清单

| # | 严重度 | 问题 | 位置 | 建议 |
|:--|:-------|:-----|:-----|:-----|
| T1 | 🔴 | **`screening_service.py` 超 1100 行**，职责过重 | [screening_service.py](scripts/business/screening_service.py) | 拆分为 `screening_pipeline.py`（编排）、`screening_factors.py`（因子计算）、`screening_utils.py`（辅助） |
| T2 | 🔴 | **`screening_service.py` 中 `ScreeningService` 类被 `analyze_code()` 和 `analyze_code_phase1()` 以 `ScreeningService()._hard_filter()` 方式实例化**，每次调用创建新实例 | [screening_service.py:701](scripts/business/screening_service.py#L701) | 改为模块级函数或单例 |
| T3 | 🟡 | **`common/__init__.py` 导出 99 个符号**，PEP 562 懒加载映射表过长 | [common/__init__.py](scripts/common/__init__.py) | 考虑子包直接导入（`from common.utils import ...`），减少顶层 re-export |
| T4 | 🟡 | **`_apply_factor_normalization()` 硬编码 6 因子键**，与 `get_factor_keys()` 注册表不同步 | [screening_service.py:778](scripts/business/screening_service.py#L778) | 统一使用 `get_factor_keys()` |
| T5 | 🟡 | **`apply_portfolio_constraints()` 直接修改输入 `rows`**（`stock["score"] *= trend_penalty`），存在副作用 | [screening_service.py:944](scripts/business/screening_service.py#L944) | 返回新列表或深拷贝后修改 |
| T6 | 🟡 | **fetcher 优先级硬编码在 Python 类中**，而非完全由 `data_source.yaml` 驱动 | `fetchers/quote/*.py` | 已有 `_load_cb_config()` 加载 YAML，但 priority 仍需显式传参 |
| T7 | 🟢 | **`risk_warning.py` 过于简单**（52 行，3 个函数），与 `macro/gate.py` 职责边界模糊 | [risk_warning.py](scripts/business/risk_warning.py) | 合并到 `strategies/macro/` 或升级为独立风控模块 |
| T8 | 🟢 | **`chan/beichi.py` 中 `_dif_offset` 赋值后 `noqa: F841` 未使用** | [beichi.py:41](scripts/chan/beichi.py#L41) | 移除或注释说明保留理由 |
| T9 | 🔴 | **`RateLimitError` 直接向上抛出不换源**：最高优先级源 429 限速时直接 raise，不尝试低优先级源 | [fetcher_base.py:199-201](scripts/common/fetcher_base.py#L199-L201) | `RateLimitError` 也应 `on_failure()` + continue 到下一个源 |
| T10 | 🔴 | **`analyze_code()` 和 `_analyze_stock()` 重复逻辑**：硬过滤+因子+评分+拐点流程几乎完全相同 | [screening_service.py:325-380 vs 671-732](scripts/business/screening_service.py#L325) | `analyze_code()` 应委托给 `_analyze_stock()`，避免双份逻辑 |
| T11 | 🟡 | **缓存键缺少数据格式版本前缀**：`data/__init__.py` 用 `f"quote_{code}"` 而非 `cache_key_for_stock()` | [data/__init__.py:90,144,169](scripts/data/__init__.py#L90) | 改用 `cache_key_for_stock()` 生成缓存键，`_DATA_FORMAT_VERSION` 升级时自动失效 |
| T12 | 🟡 | **`compute_features()` 双份实现**：screening_service 和 stock_analysis 各有独立实现 | [screening_service.py:134-211](scripts/business/screening_service.py#L134) vs [stock_analysis.py:128-156](scripts/business/stock_analysis.py#L128) | 统一使用 `technical.pipeline.compute_indicators()` |
| T13 | 🟡 | **`_FINANCE_FIELD_MAP` 硬编码东财字段名在 data 层**：80+ 行映射表应属 fetcher 层 | [data/__init__.py:264-346](scripts/data/__init__.py#L264) | 迁入 `fetchers/finance/` 或独立 `data/mappers.py` |
| T14 | 🟡 | **缓存雪崩风险**：所有缓存条目统一 TTL，大量股票同时过期 | [data/config.py:30-38](scripts/data/config.py#L30) | TTL 添加随机抖动 `ttl = base + random(0, base*0.1)` |
| T15 | 🟡 | **`ConfigLoader._cache` 非线程安全**：多线程首次调用可能竞态 | [config/loader.py:29-30](scripts/config/loader.py#L29) | 加 `threading.Lock` |
| T16 | 🟡 | **`CircuitBreaker` TOCTOU 竞态**：`can_execute()` 和 `record_*()` 分两步调用 | [fetcher_base.py:109-116](scripts/common/fetcher_base.py#L109) | 文档标注"乐观并发"策略，或合并为原子操作 |
| T17 | 🟡 | **`get_quotes()` 超时偏短**：`parallel_map` 30 秒，全市场 5000 只可能部分结果 | [data/__init__.py:111-116](scripts/data/__init__.py#L111) | 根据 `len(codes)` 动态调整超时 |
| T18 | 🟡 | **全市场选股内存压力**：`prefetch_finance_all/kline_all` 一次性约 300MB | [data/helpers.py:85-123](scripts/data/helpers.py#L85) | 分批获取+处理 |
| T19 | 🟡 | **`except Exception` 使用过多**：stock_analysis.py/screening_service.py/http.py | 多处 | 改为具体异常类型（`DataError`/`RequestException`） |
| T20 | 🟡 | **`data/__init__.py` 444 行混合职责**：获取 API + 字段映射 + dict 转换 + re-export | [data/__init__.py](scripts/data/__init__.py) | 字段映射和转换函数迁入 `data/mappers.py` |
| T21 | 🟡 | **`data → common → data.config` 间接循环依赖** | [common/utils.py:228-231](scripts/common/utils.py#L228) | 线程池配置下沉到 common 或参数注入 |
| T22 | 🟢 | **`fetch_with_breaker` 无多源故障转移**：chip/event/flow/lhb 域线性遍历单 fetcher | [fetcher_base.py:119-145](scripts/common/fetcher_base.py#L119) | 未来添加多源时改用 manager |
| T23 | 🟢 | **`Quote` 缺少停牌/涨跌停价字段**：无法区分停牌还是收盘后 | [data/types.py:7-34](scripts/data/types.py#L7) | 添加 `is_suspended: bool` 和 `limit_up/limit_down: float` |
| T24 | 🟢 | **chip/flow/lhb 域 data 层聚合逻辑无测试** | `tests/` | 补充 mock fetcher 的聚合测试 |
| T25 | 🟢 | **monitor 模块测试不足**：10+ 源文件仅 3 个测试 | `scripts/monitor/` | 加强规则引擎/通知渠道的单元测试 |

**screening_service.py 拆分方案**（来自 T1 + T2 详细分析）：

```
screening_service.py (1100+ 行)
├── screening_service.py    ← 核心服务类（_hard_filter 拆为子方法）
├── screening_pipeline.py   ← 管线编排（run_screening + 两阶段流程）
├── screening_factors.py    ← 因子计算（compute_factor_parts + normalize）
└── universe_loader.py      ← 股票池加载（load_universe + pre_screen）
```

`_hard_filter` 进一步拆为：`_check_delisting_risk()` / `_check_st_risk()` / `_check_board_constraints()` / `_check_price_limit()`

---

## 三、投资逻辑审查

### 3.1 专家系统设计 ✅ 成熟

**vote_engine.py** 的投票整合算法设计精良：

- **分组投票**：6 长线 + 3 短线，67% 多数阈值
- **冲突解决**：8 种分支覆盖（从"两极分化"到"全面分歧"）
- **否决权机制**：巴菲特否决权 + 一票否决（veto_results）
- **估值硬约束**：估值分 <20 时仓位 ×0.5，<30 时 ×0.7
- **养家情绪冰点**：情绪分 ≥80 但综合分 <30 时标记"冰点机会"
- **校准因子**：`calibration_factor` 支持历史胜率校准
- **市场状态权重**：`market_detector.py` 动态调整长线/短线权重

### 3.2 投资逻辑问题清单

| # | 严重度 | 问题 | 位置 | 建议 |
|:--|:-------|:-----|:-----|:-----|
| I1 | 🔴 | **模式策略 71.4% 胜率为样本内拟合**，仅 5 只股票、平均持仓 59.7%，无样本外验证 | [ma_volume_strategy.py](scripts/strategies/patterns/ma_volume_strategy.py) | CLAUDE.md 已标注警告，但策略代码本身无显式警告。建议在策略输出中加"⚠️ 样本内回测，未经外样本验证" |
| I2 | 🔴 | **缠论分型识别简化过度**：`fenxing.py` 的顶底分型要求中间 K 线的高低点"同时"为最高/最低，这比缠论原文更严格，可能漏识分型 | [fenxing.py:17-33](scripts/chan/fenxing.py#L17-L33) | 缠论原文定义：顶分型只需中间 K 线高点最高（低点不要求最高），建议放宽条件 |
| I3 | 🟡 | **背驰检测的 20% 容差硬编码**：`exit_area < entry_area * 0.8` 没有理论依据 | [beichi.py:140](scripts/chan/beichi.py#L140) | 应从配置文件读取，或基于波动率动态调整 |
| I4 | 🟡 | **DIF/DEA 偏移量映射复杂**：`_dea_offset` + `_mapped_idx()` 多层偏移，容易出错 | [beichi.py:36-47](scripts/chan/beichi.py#L36-L47) | 建议在 `technical/core.py` 提供 `aligned_macd(closes)` 统一计算接口 |
| I5 | 🟡 | **DCF 折现率/WACC 缺少行业差异化**：不同行业的资本结构、beta、风险溢价差异大，但当前 DCF 使用统一折现率 | [factors/dcf.py](scripts/strategies/factors/dcf.py) | 引入行业 beta 差异化（`sector_specialist` 的 5 行业分类可作为输入） |
| I6 | 🟡 | **风控模块过于简单**：`risk_warning.py` 仅 52 行 3 个函数，缺少 VaR/CVaR/最大回撤等量化风控指标 | [risk_warning.py](scripts/business/risk_warning.py) | 扩展为独立风控模块，增加组合 VaR、相关性矩阵、尾部风险检测 |
| I7 | 🟡 | **排雷指标未覆盖 A 股常见造假手法**：如关联交易占比、商誉/净资产比、存贷双高、经营现金流/净利润背离 | [factors/quality.py](scripts/strategies/factors/quality.py) | 增加 4-6 项 A 股特有排雷指标 |
| I8 | 🟢 | **K 线包含处理的默认方向硬编码为 "up"**：第一根 K 线无法判断方向 | [merge.py:32](scripts/chan/merge.py#L32) | 应根据前两根 K 线的高低判断初始方向 |
| I9 | 🟢 | **买卖点识别的回踩容忍度 2% 硬编码** | [maidian.py:84](scripts/chan/maidian.py#L84) | 应基于 ATR 或波动率动态调整 |
| I10 | 🔴 | **巴菲特否决权过度主导**：1 个 legacy 专家推翻 5 人投票共识，降级力度(×0.7)是升级(×1.1)的 2.7 倍 | [vote_engine.py:114-126](experts/vote_engine.py#L114) | 改为"否决警示"而非"否决权"——降低信心指数但不强制改方向 |
| I11 | 🔴 | **value_anchor 与 institution 高度同质化**：90% 权重同构，实测评分仅差 0.5 分 | [registry.py:313-438](experts/registry.py#L313) | 合并为单一"价值机构锚"，释放名额给真正独立视角 |
| I12 | 🔴 | **长线组 4/6 基本面共识集团**：基本面驱动专家占 67%，自动达到多数阈值 | [registry.py](experts/registry.py) | 合并 value_anchor+institution 或增加观点去相关机制 |
| I13 | 🟡 | **养家降权在合并场景语义偏差**：养家独立情绪被作手新一稀释，冰点判定失败 | [vote_engine.py:415-456](experts/vote_engine.py#L415) | 为养家增加 yangjia_sub_score 独立子评分 |
| I14 | 🟡 | **短线组 3 人投票统计天然不稳定**：1 人翻转即变分歧 | [vote_engine.py:49](experts/vote_engine.py#L49) | 增加短线组至 4-5 人，或改用加权平均替代投票 |
| I15 | 🟡 | **巴菲特+养家+估值否决叠加无地板值**：叠加仓位 ×0.49 | [vote_engine.py:114-501](experts/vote_engine.py#L114) | 增加 position_factor 地板值 min=0.3 |
| I16 | 🟡 | **综合分使用简单平均而非校准加权**：校准率不影响方向判断 | [vote_engine.py:397,464](experts/vote_engine.py#L397) | 校准率作为综合分权重因子 |
| I17 | 🟡 | **sector_specialist 行业差异化未实现**：md 承诺 5 行业阈值但代码无分支 | [scoring/sector_specialist.py](experts/scoring/sector_specialist.py) | score() 增加行业分类参数和差异化阈值 |
| I18 | 🟡 | **缺少成长可持续性和管理层量化维度** | [types.py:20](experts/types.py#L20) | 增加 insider_buy/revenue_growth_trend_3y 等字段 |
| I19 | 🟡 | **维度名别名不一致**：momentum_trader 用"情绪/资金"而非标准"情绪" | [registry.py:483](experts/registry.py#L483), [scoring/_utils.py:73](experts/scoring/_utils.py#L73) | 增加维度名别名映射机制 |
| I20 | 🟢 | **decide.md 否决评分 0 vs 实现评分 20**，文档与代码不一致 | [decide.md:94](experts/decide.md#L94), [vote_engine.py:366](experts/vote_engine.py#L366) | 更新 decide.md |
| I21 | 🟢 | **_merge.py 否决阈值 10 未文档化** | [scoring/_merge.py:14](experts/scoring/_merge.py#L14) | 补充文档说明 |

### 3.3 专家系统"伪多元化"评估

**这是本次审查最重要的发现之一**。9 位 active 专家名义上提供 9 个独立视角，但实际上存在严重的观点相关性：

| 问题 | 影响 | 实测 |
|:-----|:-----|:-----|
| value_anchor vs institution | 90%权重同构，评分仅差0.5分 | 66.5 vs 66.0 |
| 长线组4/6基本面共识 | 自动达到67%多数阈值 | ROE≥15%+PE≤25时5/6看多 |
| 短线组3人高度相关 | 投票统计不稳定，1人翻转即变分歧 | 技术面+情绪权重65-70.5% |
| 巴菲特否决权过度 | 1个legacy专家推翻5人共识 | 方向降一级+仓位×0.7 |
| 养家降权语义偏差 | 独立情绪被作手新一稀释 | 冰点判定失败 |

**核心建议**：合并 value_anchor + institution 为"价值机构锚"，释放名额给量化因子或宏观策略专家；巴菲特否决权改为"否决警示"而非"否决权"。

### 3.4 缠论实现忠实度评估

| 模块 | 忠实度 | 说明 |
|:-----|:-------|:-----|
| merge.py | 85% | 核心逻辑正确，但初始方向硬编码和 max_merge 限制偏离原文 |
| fenxing.py | 70% | ⚠️ 分型条件过于严格（要求高低点同时满足），会漏识 |
| bi.py | 80% | 笔的连接逻辑基本正确，但简化了"新笔"判定 |
| zhongshu.py | 75% | 中枢识别简化了"至少 3 笔重叠"的判定 |
| beichi.py | 80% | 背驰检测核心逻辑正确，但 20% 容差和面积比方法非原文 |
| maidian.py | 75% | 三类买卖点框架正确，但回踩判定简化 |
| xianduan.py | 70% | 线段划分简化最多，缺少特征序列分析 |

---

## 四、产品体验审查

### 4.1 Skill 交互设计

| # | 严重度 | 问题 | 建议 |
|:--|:-------|:-----|:-----|
| P1 | 🔴 | **`/market` 默认模式为 `full`**，首次用户信息过载 | 改默认为 `quick`，`full` 需显式指定 |
| P2 | 🔴 | **portfolio 操作无撤销机制**，误操作清仓不可恢复 | 增加操作历史 + `/portfolio undo` 命令 |
| P3 | 🔴 | **screener → stock 数据传递依赖人工**，无一键分析 | 增加 screener Top3 一键分析模式 |
| P4 | 🟡 | **stock debate 信息过载**（9 人逐一评分 + 投票 + 冲突 + 仓位 >2000 字） | 增加 `--brief` 选项仅输出方向+信心+仓位 |
| P5 | 🟡 | **screener 默认输出 17 列**，终端宽度不足时换行混乱 | 精简为 10 列核心信息，详细模式 `--full` |
| P6 | 🟡 | **降级后未降低置信度标识**，数据缺失时结论可靠性不可感知 | 在输出中增加 `confidence` 标识 |
| P7 | 🟡 | **首次使用无渐进引导**，13 个 skill 面对新用户无从下手 | 安装后自动输出 3 行快速上手 |
| P8 | 🟡 | **4 个变体 skill 概念重叠**（`/stock-technical` vs `/stock technical`） | 考虑隐藏变体，仅展示核心 9 命令 |
| P9 | 🟡 | **中文名映射仅覆盖约 25 只** | 扩充 `NAME_TO_CODE` 到 50-80 只板块龙头 |
| P10 | 🟢 | **`sector.py` 表格格式与 `stock.py` 分段文本风格不统一** | 统一为 Markdown 表格 |

### 4.2 场景覆盖缺口

| 缺失场景 | 严重度 | 影响 | 建议 |
|:---------|:-------|:-----|:-----|
| 公告解读 | 🔴 | A 股信息驱动型交易核心需求 | `announcements.py` 已存在，升级为独立子命令 |
| 龙虎榜 | 🟡 | 短线交易者核心数据源 | `lhb/` fetcher 已存在，需接入 skill 层 |
| 北向资金 | 🟡 | 判断市场风格的重要参考 | 需新增 fetcher |
| 港股/美股 | 🟡 | 跨市场分析需求 | 当前仅占位，需打通分析链路 |
| 组合归因 | 🟡 | 无法回答"跑输大盘是选股还是仓位" | 增加 Brinson 归因子命令 |
| 盘前准备 | 🟡 | 仅 `/monitor briefing`，不在推荐路径 | 增加 `/market briefing` 整合隔夜信息 |

### 4.3 竞品差异化

| 核心差异化 | 竞品对比 | 商业价值 |
|:---------|:---------|:---------|
| **9 人专家圆桌辩论 + 历史校准** | 同花顺/东财无，AI 工具通常单一模型 | 🔴 最高（无可替代） |
| **零配置对话式交互** | 传统 GUI 工具需学习 | 🟢 高 |
| **开源 + 数据源标注 + 可审计** | 多数 AI 投资工具闭源 | 🟢 高 |
| **5 策略回测 + 权重优化** | 同类工具功能较单一 | 🟡 中 |

---

## 五、综合改进计划

### Phase 1：紧急修复（1-2 天）

| 优先级 | 改进项 | 涉及文件 | 工作量 |
|:-------|:-------|:---------|:-------|
| 🔴 P0 | `/market` 默认改 `quick` | `skills/market/SKILL.md` | 0.5h |
| 🔴 P0 | 模式策略输出加"样本内"警告 | `scripts/strategies/patterns/ma_volume_strategy.py` | 0.5h |
| 🔴 P0 | `_apply_factor_normalization` 硬编码 6 因子改用 `get_factor_keys()` | `scripts/business/screening_service.py:778` | 1h |
| 🔴 P0 | `apply_portfolio_constraints` 副作用修复 | `scripts/business/screening_service.py:944` | 1h |
| 🔴 P0 | `RateLimitError` 换源策略（on_failure + continue） | `scripts/common/fetcher_base.py:199` | 1h |
| 🔴 P0 | 巴菲特否决权改为"否决警示"（降信心不强制改方向） | `experts/vote_engine.py:114-126` | 2h |
| 🔴 P0 | 缓存键改用 `cache_key_for_stock()` 加版本前缀 | `scripts/data/__init__.py:90,144,169` | 1h |

### Phase 2：核心改进（1 周）

| 优先级 | 改进项 | 涉及文件 | 工作量 |
|:-------|:-------|:---------|:-------|
| 🔴 P1 | 拆分 `screening_service.py`（1100+ 行） | `scripts/business/` | 4h |
| 🔴 P1 | 合并 value_anchor + institution 为"价值机构锚" | `experts/registry.py`, `experts/scoring/` | 4h |
| 🔴 P1 | `analyze_code()` 委托给 `_analyze_stock()` 消除重复 | `scripts/business/screening_service.py` | 2h |
| 🔴 P1 | portfolio 操作历史 + undo | `scripts/portfolio/manager.py`, `skills/portfolio/SKILL.md` | 4h |
| 🔴 P1 | screener → stock 一键分析 | `scripts/screener.py`, `skills/screener/SKILL.md` | 3h |
| 🟡 P1 | 缠论分型条件放宽 | `scripts/chan/fenxing.py` | 2h |
| 🟡 P1 | debate brief 模式 | `scripts/business/stock_analysis.py`, `experts/formatter.py` | 2h |
| 🟡 P1 | 养家增加 yangjia_sub_score 独立子评分 | `experts/vote_engine.py`, `experts/scoring/emotion_tech.py` | 2h |
| 🟡 P1 | position_factor 地板值 min=0.3 | `experts/vote_engine.py` | 0.5h |
| 🟡 P1 | sector_specialist 实现行业差异化阈值 | `experts/scoring/sector_specialist.py` | 2h |
| 🟡 P1 | 降级置信度标识 | `scripts/common/formatters.py`, `scripts/business/stock_analysis.py` | 2h |
| 🟡 P1 | 背驰容差、回踩容忍度配置化 | `scripts/chan/beichi.py`, `scripts/chan/maidian.py` | 2h |
| 🟡 P2 | DCF 行业差异化折现率 | `scripts/strategies/factors/dcf.py` | 3h |
| 🟡 P2 | `compute_features()` 统一实现 | `scripts/business/screening_service.py`, `scripts/business/stock_analysis.py` | 2h |
| 🟡 P2 | ConfigLoader 加线程锁 | `scripts/config/loader.py` | 1h |

### Phase 3：体验提升（2 周）

| 优先级 | 改进项 | 涉及文件 | 工作量 |
|:-------|:-------|:---------|:-------|
| 🟡 P2 | 龙虎榜接入 skill 层 | `scripts/data/lhb.py`, `skills/stock/SKILL.md` | 3h |
| 🟡 P2 | 公告解读独立子命令 | `scripts/announcements.py`, `skills/research/SKILL.md` | 4h |
| 🟡 P2 | screener 输出精简（默认 10 列） | `scripts/screener.py` | 2h |
| 🟡 P2 | 安装后快速上手指引 | `install.sh`, `skills/stock-help/SKILL.md` | 1h |
| 🟡 P3 | 扩充中文名映射到 50+ 只 | `scripts/common/validators.py` | 2h |
| 🟡 P3 | 用户偏好配置文件 | 新增 `config/user_profile.yaml` + 加载器 | 4h |
| 🟢 P3 | 输出风格统一（Markdown 表格） | `scripts/sector.py`, `scripts/common/formatters.py` | 2h |
| 🟢 P3 | 盘前简报场景入口 | `skills/market/SKILL.md`, `scripts/monitor/briefing.py` | 2h |

### Phase 4：能力扩展（1 月）

| 优先级 | 改进项 | 涉及文件 | 工作量 |
|:-------|:-------|:---------|:-------|
| 🟡 P3 | 风控模块扩展（VaR/CVaR/最大回撤） | `scripts/business/risk_warning.py` → 重构 | 8h |
| 🟡 P3 | A 股排雷指标增强（关联交易/商誉/存贷双高） | `scripts/strategies/factors/quality.py` | 4h |
| 🟡 P4 | 北向资金数据接入 | 新增 fetcher + skill 子命令 | 8h |
| 🟡 P4 | 组合归因分析（Brinson） | `scripts/portfolio/` 新增模块 | 8h |
| 🟢 P4 | 缠论线段划分增强（特征序列分析） | `scripts/chan/xianduan.py` | 4h |
| 🟢 P4 | DIF/DEA 偏移量统一接口 | `scripts/technical/core.py` | 3h |

---

## 六、技术债务评估

| 类别 | 等级 | 说明 |
|:-----|:-----|:-----|
| 代码行数 | 🟡 中 | `screening_service.py` 超 1100 行，需拆分 |
| 循环依赖 | 🟡 低 | PEP 562 懒加载 + 函数内延迟导入，但 data→common→data.config 间接循环 |
| 测试覆盖 | 🟡 中 | 107 个测试文件覆盖广，但 `chan/`、`strategies/patterns/`、`monitor/`、chip/flow/lhb 聚合覆盖较薄 |
| 硬编码 | 🟡 中 | 背驰容差、回踩容忍度、初始方向、_FINANCE_FIELD_MAP 等硬编码 |
| 配置外部化 | 🟢 低 | YAML 配置 + 代码级默认值，基本合理 |
| 类型标注 | 🟡 中 | 部分函数缺少返回类型标注，dataclass 使用良好 |
| 专家多元化 | 🔴 高 | value_anchor/institution 同质化、长线组基本面共识集团、巴菲特否决权过度 |

---

## 七、结论

**项目整体架构质量优秀**——三层分离、多源故障转移、统一输出模板、专家校准机制都是同类产品中罕见的高质量设计。投票引擎（vote_engine.py）的 8 种冲突分支、否决权机制、估值硬约束等投资逻辑也经过精心设计。

**最需解决的 3 个问题**：

1. 🔴 **专家系统"伪多元化"**：value_anchor/institution 90%权重同构、长线组4/6基本面共识集团自动达标、巴菲特否决权推翻5人投票、养家降权被合并稀释——这是影响投资决策质量的最核心问题
2. 🔴 **用户体验断点**：`/market` 默认信息过载 + portfolio 无撤销 + screener→stock 人工衔接
3. 🟡 **代码可维护性**：`screening_service.py` 过大 + 重复逻辑 + 缓存版本缺失 + 配置硬编码

**最大的商业机会**：9 人专家圆桌辩论 + 历史校准是无可替代的差异化，但"伪多元化"问题正在侵蚀这个核心卖点的可信度。必须先解决同质化和否决权过度问题，才能让专家辩论真正成为可靠的决策工具而非"看起来多元"的自确认系统。

---

## 八、改进执行状态（2026-07-07 更新）

### Phase 1：紧急修复 ✅ 全部完成

| 改进项 | 状态 | Commit |
| :------ | :--- | :------ |
| `/market` 默认改 `quick` | ✅ | `14687f6` |
| 模式策略输出加"样本内"警告 | ✅ | `afaae1e` |
| `_apply_factor_normalization` 硬编码改用 `get_factor_keys()` | ✅ | `afaae1e` |
| `apply_portfolio_constraints` 副作用修复（dict copy） | ✅ | `afaae1e` |
| `RateLimitError` 换源策略 | ✅ | `afaae1e` |
| 巴菲特否决权 → 否决警示 | ✅ | `b6db17a` |
| 缓存键版本前缀 | ✅ 已实现 | `_DATA_FORMAT_VERSION=v2` |

### Phase 2：核心改进 ✅ 大部分完成

| 改进项 | 状态 | Commit |
| :------ | :--- | :------ |
| 拆分 `screening_service.py` | ✅ | pipeline.py + universe_loader.py |
| 合并 value_anchor + institution → value_institution | ✅ | `b6db17a` |
| `analyze_code()` 委托 `_analyze_stock()` | ✅ | `a7eddb2` |
| 缠论分型条件放宽 | ✅ | 已实现（fenxing.py v2.4.0） |
| debate brief 模式 | ✅ | `format_debate_brief()` 已实现 |
| 养家 yangjia_sub_score | ✅ | emotion_tech.py 已添加 |
| position_factor 地板值 min=0.3 | ✅ | `a7eddb2` |
| sector_specialist 行业差异化阈值 | ✅ | 已实现（5 大行业类） |
| 降级置信度标识 | ✅ | formatters.py confidence<60 标识 |
| 背驰容差/回踩容忍度配置化 | ✅ | beichi `range_tolerance` + maidian `pullback_pct` |
| `compute_features()` 统一 | ✅ | stock_analysis 引用 screening_service |
| ConfigLoader 线程锁 | ✅ | 已实现 `_lock` + 双重检查 |
| decide.md 文档与代码对齐 | ✅ | `a7eddb2` |
| beichi.py 移除 `_dif_offset` | ✅ | `a7eddb2` |
| DIF/DEA 偏移量统一接口 | ✅ | `dcf1844` aligned_macd() |
| screener 默认精简模式 | ✅ | `14687f6` --full 切换完整 |
| 中文名映射扩充到 50+ | ✅ | `01a48e8` |

### 未完成项

| 改进项 | 优先级 | 说明 |
|:-------|:-------|:-----|
| portfolio 操作历史 + undo | 🟡 P1 | 需设计操作日志 schema + undo 命令 |
| screener → stock 一键分析 | 🟡 P1 | 需 SKILL.md 集成 |
| DCF 行业差异化折现率 | 🟡 P2 | 需 5 行业 beta 参数 |
| `_FINANCE_FIELD_MAP` 迁入 fetcher 层 | 🟡 P2 | 80+ 行映射表位置调整 |
| 缓存雪崩 TTL 抖动 | 🟡 P2 | TTL + random(0, base*0.1) |
| 风控模块扩展（VaR/CVaR） | 🟡 P3 | 8h 工作量 |
| A 股排雷指标增强 | 🟡 P3 | 4h 工作量 |

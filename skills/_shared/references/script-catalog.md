# 脚本目录

> 31 个脚本，自动生成（`scripts/dev/gen_script_catalog.py`）。
> **Claude Code 运行时工作目录即为项目根目录**（含 `scripts/`），无须 `cd`。

## 多代码批量调用约定（重要）

不同脚本对"批量代码"的语法支持不一致，三股/多股分析时务必按下表选择：

| 脚本 | 批量语法 | 说明 |
|------|----------|------|
| `quote.py` | 位置参数：`sh600519,sh600036` | 内部并行；返回 list |
| `finance.py` | `-c sh600519,sh600036` | **必须用 `-c`**，位置参数只取第一个 |
| `kline.py` | ❌ **不支持批量** | 必须逐个调用，或用 `xargs`/循环包装 |
| `announcements.py` | 位置参数：`sh600519,sh600036` | 串行调用后拼接 |
| `events.py` | 单个代码 | 逐个调用 |
| `technical.py` | 单个代码 | 逐个调用 |
| `market_anchor.py` | 单个代码 | 逐个调用（每只票单独拿个股 RPS） |

**常见反模式**：`python3 scripts/finance.py sh600519,sh600036 -j` 会**静默只处理第 1 只**，因为 `nargs="?"` 只取第一个参数。

**批量调用 helper**（推荐）：

```bash
# finance/kline/technical 批量取数（串行）
for code in sh600519 sh600036 sh000858; do
  python3 scripts/finance.py -c "$code" -j
done
```

| 脚本 | 用途 | 常用参数 |
|------|------|----------|
| `python3 scripts/announcements.py` | 东方财富公告 + 研报 | -j |
| `python3 scripts/backtest.py` | 多因子选股策略回测（thin wrapper） | — |
| `python3 scripts/calibration.py` | 专家校准数据管理 CLI | -j |
| `python3 scripts/calibration_backfill.py` | 校准数据回填与管理 CLI（第六轮审查 v2.4.3 新增） | -v |
| `python3 scripts/calibration_sync.py` | 校准数据 GitHub Gist 双向同步 | — |
| `python3 scripts/chan.py` | 缠中说禅理论（缠论）实现 | — |
| `python3 scripts/chip.py` | 资金面分析 CLI 入口 | -j |
| `python3 scripts/classifier.py` | A 股个股类型分类器 | — |
| `python3 scripts/events.py` | 个股事件日历查询 | -j |
| `python3 scripts/finance.py` | 财务数据查询（多数据源自动切换） | -c、-j |
| `python3 scripts/hot_rank.py` | 热度榜（活跃 Top N） | -j、-v |
| `python3 scripts/industry_beta.py` | 个股 beta 系数计算（v2.6.0 新增） | -j |
| `python3 scripts/init_pool.py` | 首次安装初始化脚本 — 为每个板块拉取前 20 只股票 | -j |
| `python3 scripts/kline.py` | K 线数据查询（多数据源自动切换） | -j |
| `python3 scripts/macro_indicators.py` | 宏观指标获取模块（v2.5.x 新增） | -j |
| `python3 scripts/market_anchor.py` | 市场环境锚定编排器（v2.5.0 新增） | -j |
| `python3 scripts/market_breadth.py` | 市场宽度分析脚本 | — |
| `python3 scripts/multi_stock_backtest.py` | 外样本多股票回测 + 基准对比（PR-G：解决 71.4% CLAIM 单股过拟合问题） | — |
| `python3 scripts/perf_bench.py` | 性能压测脚本：测量 screener / backtest 端到端耗时 | — |
| `python3 scripts/portfolio_correlation.py` | 组合相关性矩阵（v2.6.0 新增） | -j |
| `python3 scripts/portfolio_web.py` | 持仓录入 Web 服务（零依赖 stdlib http.server） | — |
| `python3 scripts/quote.py` | 实时行情查询（多数据源自动切换） | -j |
| `python3 scripts/refresh_pool.py` | 股票池自动刷新脚本 — 从东财 push2 API 拉取板块成分股 | -j |
| `python3 scripts/screener.py` | A 股多因子选股器 | -h、-j、-v |
| `python3 scripts/sector.py` | 板块查询——根据股票代码查找所属板块及板块内标的行情 | -j |
| `python3 scripts/sector_summary.py` | 板块涨跌幅汇总（**v1.20.1 新增，替代 ETF 拼接的板块榜**） | -j、--source ths\|eastmoney\|auto、--top N、--sector |
| `python3 scripts/sector_etf_strength.py` | 板块 ETF 横向强度对比 + 个股相对位置（RPS） | -j |
| `python3 scripts/snapshots.py` | 选股快照系统（review#16） | -j |
| `python3 scripts/stock.py` | 个股五层分析（v1.3.2 接入 business/StockAnalysisService） | -j |
| `python3 scripts/strategy_performance.py` | 策略表现校准（review#17）：定期回测并记录到 strategy_performance.json | -j |
| `python3 scripts/technical.py` | 兼容入口：import technical 包后转发 CLI | — |

## JSON 输出

所有数据获取脚本支持 `-j` 输出 JSON，便于二次计算（排序、过滤、聚合）。

## 开发辅助脚本（`scripts/dev/`，不纳入自动生成表）

| 脚本 | 用途 | 常用参数 |
|------|------|----------|
| `python3 scripts/dev/multi_fetch.py` | 批量取数 helper：串行调用 finance/kline/technical/market_anchor/events 并合并为单 JSON dict | `finance`/`kline`/`technical`/`market_anchor`/`events` 子命令 |
| `python3 scripts/dev/experts_cli.py` | 8 位 active 专家量化评分 CLI（debate 模式基线）：自动取数 + 跑 score_expert_precise + 跨股对比 | `--long`/`--short`/`-j` |

> 这些脚本是 SKILL.md 推荐用法的"快捷方式"，上层 skill 可直接调用。

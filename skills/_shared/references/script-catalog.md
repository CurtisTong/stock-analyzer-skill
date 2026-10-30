# 脚本目录

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

## 脚本清单

<!-- BEGIN GENERATED: python3 scripts/dev/gen_script_catalog.py -->
> 41 个脚本，自动生成（`scripts/dev/gen_script_catalog.py`）。

| 脚本 | 用途 | 常用参数 |
|------|------|----------|
| `python3 scripts/announcements.py` | 东方财富公告 + 研报 | -j、--json、--sources、--no-cache、--debug |
| `python3 scripts/backtest.py` | 多因子选股策略回测（thin wrapper） | -v、-h、-j、--version、--help |
| `python3 scripts/block_trade.py` | 大宗交易查询 | -j、--days、--json、--sources、--no-cache |
| `python3 scripts/calibration.py` | 专家校准数据管理 CLI | -j、--stock、--direction、--scores、--composite |
| `python3 scripts/calibration_backfill.py` | 校准数据回填与管理 CLI（v2.4.3 引入） | -v、-j、--days、--no-price、--verbose |
| `python3 scripts/calibration_sync.py` | 校准数据 GitHub Gist 双向同步 | -j、--pull、--push、--auto、--status |
| `python3 scripts/cb.py` | 可转债行情查询 | -j、--top、--json、--sources、--no-cache |
| `python3 scripts/chan.py` | 缠中说禅理论（缠论）实现 | — |
| `python3 scripts/chip.py` | 资金面分析 CLI 入口 | -j、--margin、--holders、--top-holders、--chip |
| `python3 scripts/chip_dist.py` | 成本分布（筹码分布）分析——获利盘/套牢盘、平均成本、主密集区、上方抛压 | -j、--codes、--pool、--window、--bins |
| `python3 scripts/classifier.py` | A 股个股类型分类器 | — |
| `python3 scripts/concept.py` | 题材概念板块数据层 | -j、--top、--board、--arbitrage、--scan |
| `python3 scripts/events.py` | 个股事件日历查询 | -j、--days、--json、--sources、--no-cache |
| `python3 scripts/finance.py` | 财务数据查询（多数据源自动切换） | -c、-j、--codes、--periods、--json |
| `python3 scripts/hot_rank.py` | 热度榜（活跃 Top N） | -v、-j、--version、--top、--days |
| `python3 scripts/indicator_env_backtest.py` | 指标信号 × 市场环境 条件回测（逐日重放，与 technical 模块同源） | --codes、--datalen、--output、--json-out |
| `python3 scripts/industry_beta.py` | 个股 beta 系数计算（v2.6.0 新增） | -j、--index、--window、--json、--sources |
| `python3 scripts/init_pool.py` | 首次安装初始化脚本 — 为每个板块拉取前 20 只股票 | -f、-n、-d、-j、--force |
| `python3 scripts/ipo_calendar.py` | 新股/新债日历查询 | -j、--days、--json、--sources、--no-cache |
| `python3 scripts/kline.py` | K 线数据查询（多数据源自动切换） | -j、--days、--json、--sources、--no-cache |
| `python3 scripts/limit_up.py` | 涨停池与涨停原因归因查询 | -j、--date、--json、--sources、--no-cache |
| `python3 scripts/macro_indicators.py` | 宏观指标获取模块（v2.5.x 新增） | -j、--json、--sources、--no-cache、--debug |
| `python3 scripts/market_anchor.py` | 市场环境锚定编排器（v2.5.0 新增） | -j、--no-sector、--no-portfolio、--no-rotation、--no-northbound |
| `python3 scripts/market_breadth.py` | 市场宽度分析脚本 | --json |
| `python3 scripts/monitor.py` | 数据源健康检查和缓存监控 | --cache、--sources、--cleanup、--json、--log-json |
| `python3 scripts/multi_stock_backtest.py` | 外样本多股票回测 + 基准对比（PR-G：解决 71.4% CLAIM 单股过拟合问题） | -j、--codes、--top、--holding-days、--total-days |
| `python3 scripts/perf_bench.py` | 性能压测脚本：测量 screener / backtest 端到端耗时 | -j、--codes、--rounds、--json、--sources |
| `python3 scripts/portfolio_correlation.py` | 组合相关性矩阵（v2.6.0 新增） | -j、--stock、--window、--list、--risk-weights |
| `python3 scripts/portfolio_web.py` | 持仓录入 Web 服务（零依赖 stdlib http.server） | — |
| `python3 scripts/quote.py` | 实时行情查询（多数据源自动切换） | -j、--json、--sources、--no-cache、--debug |
| `python3 scripts/refresh_pool.py` | 股票池自动刷新脚本 — 从东财 push2 API 拉取板块成分股 | -s、-j、--sector、--json、--sources |
| `python3 scripts/screener.py` | A 股多因子选股器 | -v、-h、-q、-j、--version |
| `python3 scripts/sector.py` | 板块查询——根据股票代码查找所属板块及板块内标的行情 | -j、--list、--json、--sources、--no-cache |
| `python3 scripts/sector_etf_strength.py` | 板块 ETF 横向强度对比 + 个股相对位置（RPS） | -j、--no-index、--json、--sources、--no-cache |
| `python3 scripts/sector_momentum.py` | 板块动量工具（v1.21.0 ）：基于行业 ETF 动量判断板块退潮 | — |
| `python3 scripts/sector_summary.py` | 板块涨跌幅汇总 CLI（v1.20.1 新增） | -j、--source、--top、--sector、--json |
| `python3 scripts/sentiment_panel.py` | 情绪面板 CLI（v1.26 阶段 1） | -j、--date、--top、--json、--sources |
| `python3 scripts/snapshots.py` | 选股快照系统（review#16） | -j、--strategy、--limit、--json、--sources |
| `python3 scripts/stock.py` | 个股五层分析（v1.3.2 接入 business/StockAnalysisService） | -j、--no-finance、--no-technical、--no-chan、--with-backtest |
| `python3 scripts/strategy_performance.py` | 策略表现校准（review#17）：定期回测并记录到 strategy_performance.json | -j、--days、--top、--codes、--month |
| `python3 scripts/technical.py` | 兼容入口：import technical 包后转发 CLI | -s、-q、-j、--scale、--quick |
<!-- END GENERATED -->

## JSON 输出

所有数据获取脚本支持 `-j` 输出 JSON，便于二次计算（排序、过滤、聚合）。

## 开发辅助脚本（`scripts/dev/`，不纳入自动生成表）

| 脚本 | 用途 | 常用参数 |
|------|------|----------|
| `python3 scripts/dev/multi_fetch.py` | 批量取数 helper：串行调用 finance/kline/technical/market_anchor/events 并合并为单 JSON dict | `finance`/`kline`/`technical`/`market_anchor`/`events` 子命令 |
| `python3 scripts/dev/experts_cli.py` | 8 位 active 专家量化评分 CLI（debate 模式基线）：自动取数 + 跑 score_expert_precise + 跨股对比 | `--long`/`--short`/`-j` |

> 这些脚本是 SKILL.md 推荐用法的"快捷方式"，上层 skill 可直接调用。

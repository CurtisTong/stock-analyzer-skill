# 脚本目录

> 26 个脚本，自动生成（`scripts/dev/gen_script_catalog.py`）。
> Claude Code 运行时工作目录即为项目根目录。

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
| `python3 scripts/init_pool.py` | 首次安装初始化脚本 — 为每个板块拉取前 20 只股票 | -j |
| `python3 scripts/kline.py` | K 线数据查询（多数据源自动切换） | -j |
| `python3 scripts/market_breadth.py` | 市场宽度分析脚本 | — |
| `python3 scripts/monitor.py` | 数据源健康检查和缓存监控 | — |
| `python3 scripts/multi_stock_backtest.py` | 外样本多股票回测 + 基准对比（PR-G：解决 71.4% CLAIM 单股过拟合问题） | — |
| `python3 scripts/perf_bench.py` | 性能压测脚本：测量 screener / backtest 端到端耗时 | — |
| `python3 scripts/portfolio_web.py` | 持仓录入 Web 服务（零依赖 stdlib http.server） | — |
| `python3 scripts/quote.py` | 实时行情查询（多数据源自动切换） | -j |
| `python3 scripts/refresh_pool.py` | 股票池自动刷新脚本 — 从东财 push2 API 拉取板块成分股 | -j |
| `python3 scripts/screener.py` | A 股多因子选股器 | -h、-j、-v |
| `python3 scripts/sector.py` | 板块查询——根据股票代码查找所属板块及板块内标的行情 | -j |
| `python3 scripts/snapshots.py` | 选股快照系统（review#16） | -j |
| `python3 scripts/stock.py` | 个股五层分析（v1.3.2 接入 business/StockAnalysisService） | -j |
| `python3 scripts/strategy_performance.py` | 策略表现校准（review#17）：定期回测并记录到 strategy_performance.json | -j |
| `python3 scripts/technical.py` | 兼容入口：import technical 包后转发 CLI | — |

## JSON 输出

所有数据获取脚本支持 `-j` 输出 JSON，便于二次计算（排序、过滤、聚合）。

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

A-share 股票分析 Claude Code 插件，提供 11 个 skill（`/stock`、`/market`、`/sector`、`/portfolio`、`/screener`、`/technical`、`/monitor`、`/stock-init`、`/financial-analyst`、`/investment-researcher`、`/help`）。核心脚本零外部依赖（纯 stdlib），数据源为国内 API（腾讯、东方财富、新浪）。

## 常用命令

```bash
# 单元测试
python3 -m pytest tests/ -x -q

# 包含网络请求的测试
python3 -m pytest tests/ -x -q --run-network

# 端到端冒烟测试
./tests/smoke_test.sh
# 或
npm test

# 运行单个脚本（从项目根目录）
python3 scripts/quote.py sh600989
python3 scripts/finance.py sh600989
python3 scripts/kline.py sh600989
python3 scripts/technical.py sh600989
python3 scripts/screener.py balanced
python3 scripts/chan.py sh600989
python3 scripts/classifier.py sh600989
python3 scripts/backtest.py sh600989
python3 scripts/patterns_local.py sh600989
python3 scripts/monitor.py
python3 scripts/init_pool.py
```

## 三层架构

```
scripts/
├── api/          # CLI 入口层（quote_cli.py, screener_cli.py）
├── business/     # 业务逻辑层（stock_analysis.py, screening_service.py）
├── common/       # 基础设施层（HTTP、编码、字段映射、BaseFetcher、CircuitBreaker）
├── config/       # 外部化配置（YAML）— scoring/data_source/limits/industry_thresholds
├── data/         # 数据类型（Quote, KlineBar, FinanceRecord）+ 磁盘缓存
├── fetchers/     # 多数据源 Fetcher（21 个模块，优先级故障转移）
├── strategies/   # 筛选策略系统（5 策略 × 5 因子维度）
├── technical/    # 技术分析（MACD/KDJ/BOLL/RSI/均线/量能/缠论）
├── monitor/      # 实时监控
├── portfolio/    # 持仓管理
└── *.py          # 顶层 CLI 脚本
```

**数据流**: SKILL.md → Claude Code 调用 `scripts/*.py` → `fetchers/` 多源获取（自动故障转移）→ `business/` 业务逻辑 → 输出分析结果

## 关键抽象

- **BaseFetcher / DataFetcherManager** (`scripts/common/__init__.py`): 数据源抽象基类 + 优先级故障转移管理器，集成 CircuitBreaker
- **CircuitBreaker** (`scripts/common/__init__.py`): 线程安全熔断器（closed/open/half-open）
- **异常体系** (`scripts/common/exceptions/__init__.py`): `StockAnalyzerError` → `DataError` / `BusinessError`
- **ConfigLoader** (`scripts/config/loader.py`): YAML 配置加载器，支持点分路径访问和缓存
- **数据类型** (`scripts/data/types.py`): `Quote`、`KlineBar`、`FinanceRecord` dataclass
- **策略注册表** (`scripts/strategies/registry.py`): 5 种内置策略（balanced/quality_value/growth_momentum/defensive/turning_point）
- **专家系统** (`experts/`): 8 位投资专家人设 + `decide.md` 决策整合规则

## 开发约定

### Python

- 核心脚本零外部依赖（stdlib only），PyYAML 仅用于配置加载
- 避免循环导入：使用函数内延迟导入模式（`_get_common_helpers()`）
- 从项目根目录运行脚本，`pyproject.toml` 已配置 `pythonpath = ["scripts"]`
- 可选第三方库（akshare, efinance, baostock 等）运行时自动检测，缺失时静默跳过

### Skill 开发

- Skill 定义在 `skills/<name>/SKILL.md`，包含 YAML frontmatter（`name`、`description`）+ markdown 指令
- 通过符号链接同步到 `.claude/skills/` 和 `.agents/skills/`
- SKILL.md 中的路径不要使用相对 `cd` 命令，Claude Code 从项目根目录运行

### Git

- Commit: Conventional Commits，中文主题（≤50 字），动词开头，无尾句号
- Scope 值: `stock`, `market`, `sector`, `portfolio`, `screener`, `technical`, `scripts`, `data`, `docs`, `ci`, `deps`
- 分支: `<type>/<short-desc>`（小写英文 + 连字符），如 `feat/stock-debate-mode`
- 版本: SemVer

### 权限

- `.claude/settings.json` 使用通配符模式如 `Bash(python3 scripts/quote.py *)`
- 禁止 `sudo`、`rm -rf`、`chmod 777`

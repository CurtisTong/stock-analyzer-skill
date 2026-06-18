# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

A-share 股票分析 Claude Code 插件，提供 13 个 skill（9 核心 + 4 变体）：`/stock`、`/market`、`/sector`、`/portfolio`、`/screener`、`/monitor`、`/backtest`、`/research`、`/stock-help` 以及变体 `/stock-technical`、`/portfolio-web`、`/portfolio-natural`、`/learn`。`/technical` 已合并至 `/stock technical`，`/stock-init` 已合并至 `/screener init`，`/financial-analyst` 和 `/investment-researcher` 已合并至 `/research`。运行时零外部依赖（仅 stdlib + PyYAML 配置加载），数据源为国内 API（腾讯、东方财富、新浪）+ 28 个 fetcher 适配器跨 7 数据域故障转移。

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
python3 scripts/screener.py --strategy balanced
python3 scripts/chan.py sh600989
python3 scripts/classifier.py sh600989
python3 scripts/backtest.py sh600989
python3 scripts/patterns_local.py sh600989
python3 scripts/monitor.py
python3 scripts/monitor/alert_engine.py scan/levels/check
python3 scripts/init_pool.py
python3 scripts/init_pool.py --default  # 离线模式
python3 scripts/refresh_pool.py
python3 scripts/calibration.py record/verify/report/pending
python3 scripts/portfolio_web.py --port 8765
python3 scripts/stock.py sh600989          # 五层分析业务层入口（JSON 友好）
python3 scripts/chip.py sh600989           # 资金面：融资融券 / 股东户数 / 十大流通
```

## 三层架构

```
scripts/
├── business/     # 业务逻辑层（stock_analysis.py, screening_service.py）
├── common/       # 基础设施层（HTTP、编码、字段映射、BaseFetcher、CircuitBreaker）
├── config/       # 外部化配置（YAML）— scoring/data_source/limits/industry_thresholds
├── data/         # 数据类型（Quote, KlineBar, FinanceRecord）+ 磁盘缓存
├── fetchers/     # 多数据源 Fetcher（28 个模块 × 7 数据域，优先级故障转移）
├── strategies/   # 筛选策略系统（5 策略 × 5 因子维度）
├── technical/    # 技术分析（MACD/KDJ/BOLL/RSI/均线/量能/缠论）
├── monitor/      # 实时监控
├── portfolio/    # 持仓管理
└── *.py          # 顶层 CLI 脚本（SKILL.md 直接调用的入口）
```

**数据流**: SKILL.md → Claude Code 调用 `scripts/*.py` → `fetchers/` 多源获取（自动故障转移）→ `business/` 业务逻辑 → 输出分析结果

## 关键抽象

- **BaseFetcher / DataFetcherManager** (`scripts/common/__init__.py`): 数据源抽象基类 + 优先级故障转移管理器，集成 CircuitBreaker
- **CircuitBreaker** (`scripts/common/__init__.py`): 线程安全熔断器（closed/open/half-open）
- **异常体系** (`scripts/common/exceptions/__init__.py`): `StockAnalyzerError` → `DataError` / `BusinessError`
- **ConfigLoader** (`scripts/config/loader.py`): YAML 配置加载器，支持点分路径访问和缓存
- **数据类型** (`scripts/data/types.py`): `Quote`、`KlineBar`、`FinanceRecord` dataclass
- **策略注册表** (`scripts/strategies/registry.py`): 5 种内置策略（balanced/quality_value/growth_momentum/defensive/turning_point）
- **专家系统** (`experts/`): 15 份投资专家人设（6 legacy active=False + 9 active=True；含合并型 `value_anchor` / `topic_leader` / `emotion_tech`，补盲区 `sector_specialist` / `institution` / `risk_manager`，v2.2.0 新增 `momentum_trader`）+ `decide.md` 决策整合规则 + `vote_engine.py` 投票整合

## Skill 索引表（13 个）

| Skill | 触发场景 | 主入口脚本 | 备注 |
| :--- | :--- | :--- | :--- |
| `/stock` | 单股五层分析 + 8 人圆桌辩论 | `scripts/stock.py` | 业务层 JSON 友好入口 |
| `/stock-technical` | 纯技术面（均线/MACD/KDJ/BOLL/RSI/缠论/战法） | `scripts/technical.py` | stock 子模块 |
| `/market` | 大盘快评 / 完整复盘 / 盘中分时 | `scripts/quote.py` + `scripts/kline.py` | 指数/ETF/美股 |
| `/sector` | 板块全景 / 标的对比 / 板块内筛选 | `scripts/sector.py` + `scripts/refresh_pool.py` | |
| `/portfolio` | 持仓 CRUD + 自选 + 健康检查 + 调仓 | `scripts/portfolio_web.py` + `scripts/portfolio/*.py` | Web 服务 :8765 |
| `/portfolio-web` | Web 录入服务（HTTP API） | `scripts/portfolio_web.py` | portfolio 子模块 |
| `/portfolio-natural` | 自然语言 → 命令映射（NL → API） | `scripts/portfolio_web.py` | portfolio 子模块 |
| `/screener` | 5 策略 × 6 因子批量选股 + 股票池初始化 | `scripts/screener.py` + `scripts/init_pool.py` | |
| `/monitor` | 盘中异动 + 策略关键点位 + 多通道推送 | `scripts/monitor.py` + `scripts/monitor/alert_engine.py` | |
| `/backtest` | 策略历史回测（11 项指标 + 5 策略对比） | `scripts/backtest.py` + `scripts/strategy_performance.py` | |
| `/research` | 财务建模 / 排雷 / DCF / 全维度研究报告 | `scripts/stock.py --with-backtest` + `scripts/announcements.py` + `scripts/events.py` | |
| `/learn` | 学习助手（PE/ROE/MACD/K 线/缠论/新手入门） | 无脚本调用 | 纯教学 |
| `/stock-help` | 帮助索引（场景入口 + skill 一句话表） | 无脚本调用 | meta 索引（f4b3ad7 由 `/help` 重命名） |

## Experts 全表（15 份）

| Expert | 类型 | 状态 | 简介 |
| :--- | :--- | :--- | :--- |
| `buffett` | 价值 | legacy | 高 ROE + 低 PE + 强 FCF + 长期持有 |
| `lynch` | 成长 | active | Buy What You Know + PEG < 1 + 6 类股票分类 |
| `soros` | 宏观 | active | 反身性理论 + 凯利公式 + 趋势跟踪 |
| `duan_yongping` | 价值 | legacy | 商业模式 + 本分企业文化 + "PE 就是 PE" |
| `xu_xiang` | 短线 | legacy | 涨停板战法 + T+1 次日出 + 5% 硬止损 |
| `zhao_laoge` | 短线 | legacy | 二板定龙头 + MA 多头排列 + 强者恒强 |
| `chaogu_yangjia` | 短线 | legacy | 情绪周期四阶段 + 涨停家数/炸板率/昨涨停溢价 |
| `zuoshou_xinyi` | 短线 | legacy | 二波低吸 + K 线反转 + 不加仓纪律 |
| `value_anchor` | 价值合并 | active | 巴菲特 0.55 + 段永平 0.45 双锚 |
| `topic_leader` | 短线合并 | active | 徐翔 0.5 + 赵老哥 0.5 龙头战法 |
| `emotion_tech` | 短线合并 | active | 养家 0.5 + 新一 0.5 情绪技术复合 |
| `sector_specialist` | 行业 | active | 按 5 大行业类差异化阈值（消费/科技/医药/周期/金融） |
| `institution` | 机构 | active | 高瓴/红杉框架 + 5-10 年产业投资 + 14 项阈值 |
| `risk_manager` | 风控 | active | Howard Marks 二阶思维 + 风险预算 + 集中度约束 |
| `momentum_trader` | 动量 | active | 利弗莫尔关键转折 + 海龟交易法则（v2.2.0 新增） |

> `legacy active=False` 6 人已合并入 active 专家；`active` 9 人由 `experts/registry.py` 注册并被 `experts/vote_engine.py` 在 debate 模式调用。

## CI 防漂移机制

- **SKILL.md 版本同步**：`scripts/dev/sync_skill_test_versions.py` 扫描所有 `skills/*/SKILL.md` 的 `version:` 字段，自动构建 `VERSION_OVERRIDES` 同步到 `tests/test_skill_metadata.py::EXPECTED_SKILLS`；`--check` 模式作为提交前门禁
- **pre-commit hook**（`.pre-commit-config.yaml`）：`sync-skill-test-versions`（pre-commit stage）自动同步；`check-skill-test-versions`（pre-commit stage）作为提交前验证
- **GitHub Action**（`.github/actions/setup-test/action.yml`）：CI 测试 job 在 `pip install` 之后跑 `sync_skill_test_versions.py`，确保 release workflow 的 test job 不会因版本漂移而阻塞 publish
- **三处版本号同步**：`scripts/dev/sync_version.py` 同步 `pyproject.toml` + `package.json` + README badge，避免发版时手动三处修改
- **手动验证**：`python3 scripts/dev/sync_skill_test_versions.py --check`（commit 0 状态：已通过）

## 开发约定

### Python

- 运行时零外部依赖（仅 stdlib + PyYAML 配置加载）；测试与 lint 阶段可选依赖（pytest / black / flake8 / hypothesis 等，详见 `[project.optional-dependencies.test]`）
- 避免循环导入：使用函数内延迟导入模式（`_get_common_helpers()`）
- 从项目根目录运行脚本，`pyproject.toml` 已配置 `pythonpath = ["scripts"]`
- 可选第三方库（akshare, efinance, baostock 等）运行时自动检测，缺失时静默跳过

### Skill 开发

- Skill 定义在 `skills/<name>/SKILL.md`，包含 YAML frontmatter（`name`、`description`）+ markdown 指令
- 通过符号链接同步到 `.claude/skills/` 和 `.agents/skills/`
- SKILL.md 中的路径不要使用相对 `cd` 命令，Claude Code 从项目根目录运行

### Git

- Commit: Conventional Commits，中文主题（≤50 字），动词开头，无尾句号
- Scope 值: `stock`, `market`, `sector`, `portfolio`, `screener`, `monitor`, `backtest`, `research`, `technical`, `experts`, `scripts`, `data`, `docs`, `ci`, `deps`
- 分支: `<type>/<short-desc>`（小写英文 + 连字符），如 `feat/stock-debate-mode`
- 版本: SemVer

### 权限

- `.claude/settings.json` 使用通配符模式如 `Bash(python3 scripts/quote.py *)`
- 禁止 `sudo`、`rm -rf`、`chmod 777`

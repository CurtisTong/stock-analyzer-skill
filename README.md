# stock-analyzer-skill

独立的股票分析 skill 包，提供 12 个股票分析相关 skill + 完整方法论 + 工具脚本。

> **🎯 零配置可用**：内置预置默认股票池数据，首次使用无需任何 token 或 API 密钥，`/stock-init` 一键初始化即可开始分析。

## 股票代码格式

支持以下格式输入股票代码：

| 格式        | 示例       | 说明           |
| ----------- | ---------- | -------------- |
| `sh` + 代码 | `sh600519` | 上海证券交易所 |
| `sz` + 代码 | `sz000858` | 深圳证券交易所 |
| 纯数字      | `600519`   | 自动推断交易所 |
| 股票名称    | `贵州茅台` | 按名称模糊匹配 |

## 包含的 Skill

| Skill                     | 命令                                          | 用途           | 模式                             |
| ------------------------- | --------------------------------------------- | -------------- | -------------------------------- |
| **stock**                 | `/stock <代码或名称> [quick\|full\|debate]`   | 单股分析       | 五层框架 + 8人专家圆桌           |
| **market**                | `/market [full\|quick\|intraday]`             | 大盘复盘       | 指数+板块+风格+资金              |
| **sector**                | `/sector <板块> [overview\|compare\|stock]`   | 板块分析       | 标的对比+多空博弈                |
| **portfolio**             | `/portfolio [health\|rebalance\|compare]`     | 持仓健康检查   | 涨跌+支撑+风险预警               |
| **screener**              | `/screener [--sector 板块] [--strategy 策略]` | 选股策略系统   | 多因子筛选+硬过滤+候选池         |
| **technical**             | `/technical <代码> [quick\|full]`             | 纯技术分析     | 均线+MACD/KDJ/BOLL+缠论+本土战法 |
| **stock-init**            | `/stock-init [force\|default\|top N]`         | 初始化股票池   | 零配置可用，支持离线模式         |
| **financial-analyst**     | `/financial-analyst <任务>`                   | 财务分析 agent | 建模+预测+场景分析               |
| **investment-researcher** | `/investment-researcher <任务>`               | 投资研究 agent | 市场研究+尽调+估值               |
| **backtest**              | `/backtest [--strategy 策略] [--all]`         | 策略回测       | 历史胜率+收益验证                |
| **monitor**               | `/monitor [start\|stop]`                      | 盘中监控       | 持仓异动+价格预警推送            |
| **help**                  | `/help`                                       | 帮助信息       | 显示所有可用 skills 和使用说明   |

> **术语说明**：
>
> - **五层框架**：基本面/估值/技术面/板块/风险收益比，详见 [methodology.md](methodology.md)
> - **8人专家圆桌**：长线 4 人（巴菲特/林奇/索罗斯/段永平）+ 短线 4 人（徐翔/赵老哥/炒股养家/作手新一），debate 模式下多空辩论
> - **硬过滤**：排除 ST 股、低成交额、低市值标的的预筛选规则

### v1.3.2 改进

- 12 个 skill frontmatter 全面升级：新增 `model` / `allowed-tools` / `version` 字段；3 个命令式 skill 设 `disable-model-invocation: true`
- 共享约定集中到 [`skills/_shared/references/`](skills/_shared/references/)：代码前缀、脚本目录、五层框架按需加载
- `install.sh` 全局同步改用软链（单源真相）
- 新增 [tests/test_skill_metadata.py](tests/test_skill_metadata.py) 防止 skill 元数据退化（100 个测试）

## 安装

### 方式一：Claude Code Plugin 安装（推荐）

```bash
# 添加 marketplace
claude plugins marketplace add /path/to/stock-analyzer-skill

# 安装 plugin
claude plugins install stock-analyzer
```

或者一行命令：

```bash
claude plugins marketplace add . && claude plugins install stock-analyzer
```

### 方式二：npm 全局安装

```bash
npm install -g stock-analyzer-skill
```

安装后会自动添加 marketplace 并安装 plugin。

### 方式三：手动安装（传统方式）

```bash
cd stock-analyzer-skill
./install.sh
```

这会在 `~/.claude/skills/` 下创建 symlink。需要重启 Claude Code 才能生效。

## 验证安装

```bash
# 查看已安装的 plugins
claude plugins list

# 查看可用的 skills
claude skills list

# 测试 help skill
/help
```

## 目录结构

```text
stock-analyzer-skill/
├── .claude-plugin/                 # Claude Code plugin 配置
│   ├── plugin.json                 # plugin 元数据
│   └── marketplace.json            # marketplace 配置
├── skills/                         # 12 个 skill
│   ├── stock/SKILL.md
│   ├── market/SKILL.md
│   ├── sector/SKILL.md
│   ├── portfolio/SKILL.md
│   ├── screener/SKILL.md
│   ├── technical/SKILL.md
│   ├── stock-init/SKILL.md
│   ├── monitor/SKILL.md
│   ├── backtest/SKILL.md
│   ├── financial-analyst/SKILL.md
│   ├── investment-researcher/SKILL.md
│   └── help/SKILL.md
├── scripts/                        # 工具脚本（Python stdlib only）
│   ├── business/                   # 业务逻辑层
│   │   ├── stock_analysis.py       # 个股分析服务
│   │   └── screening_service.py    # 选股服务
│   ├── common/                     # 基础设施层
│   │   ├── __init__.py             # HTTP 请求、编码转换、字段映射
│   │   ├── validators.py           # 输入验证器
│   │   └── exceptions/             # 统一异常类
│   ├── config/                     # 配置外部化
│   │   ├── loader.py               # YAML 配置加载器
│   │   ├── data_source.yaml        # 数据源端点配置
│   │   ├── industry_thresholds.yaml # 行业差异化阈值
│   │   ├── scoring.yaml            # 评分权重配置
│   │   └── limits.yaml             # 限流与超时配置
│   ├── data/                       # 数据层
│   │   ├── types.py                # 数据类型定义
│   │   ├── cache.py                # 缓存管理
│   │   ├── config.py               # 数据配置
│   │   ├── industry_thresholds.json # 行业阈值数据
│   │   ├── sector_etf.csv          # 板块 ETF 清单
│   │   ├── sector_stocks.json      # 板块核心标的库（动态更新）
│   │   ├── sector_stocks.default.json # 预置默认股票池（离线可用）
│   │   ├── sector_mapping.json     # 板块映射关系
│   │   └── portfolio_example.json  # 持仓配置示例
│   ├── fetchers/                   # 数据获取层（多数据源适配，21+ 模块）
│   │   ├── tencent_quote.py        # 腾讯实时行情
│   │   ├── eastmoney_quote.py      # 东财实时行情
│   │   ├── eastmoney_finance.py    # 东财财务数据
│   │   ├── eastmoney_kline.py      # 东财 K 线
│   │   ├── eastmoney_chip.py       # 东财资金面（融资融券/股东户数/十大流通股东）
│   │   ├── eastmoney_flow.py       # 东财资金流向
│   │   ├── eastmoney_lhb.py        # 东财龙虎榜
│   │   ├── eastmoney_event.py      # 东财事件日历
│   │   ├── sina_quote.py           # 新浪行情
│   │   ├── sina_kline.py           # 新浪 K 线
│   │   ├── xueqiu_quote.py         # 雪球行情（v1.3.1）
│   │   ├── ths_quote.py            # 同花顺行情（v1.3.1）
│   │   ├── akshare_quote.py        # AkShare 行情
│   │   ├── akshare_finance.py      # AkShare 财务
│   │   ├── akshare_kline.py        # AkShare K 线
│   │   ├── efinance_*.py           # efinance 适配
│   │   ├── baostock_kline.py       # baostock K 线
│   │   ├── pytdx_*.py              # pytdx 适配
│   │   ├── tushare_*.py            # tushare 适配
│   │   └── yfinance_kline.py       # yfinance K 线（港股/美股）
│   ├── strategies/                 # 选股策略系统
│   │   ├── registry.py             # 策略注册中心
│   │   ├── thresholds.py           # 阈值管理
│   │   └── factors/                # 因子实现
│   ├── technical/                  # 技术分析模块
│   │   ├── macd.py / kdj.py / boll.py / rsi.py  # 指标计算
│   │   ├── moving_average.py       # 均线系统
│   │   ├── volume.py               # 量价分析
│   │   ├── trend.py                # 趋势判断
│   │   ├── candlestick.py          # K 线形态
│   │   ├── astock.py               # A 股特色指标
│   │   ├── signals.py              # 信号生成
│   │   ├── scoring.py              # 综合评分（含资金面因子 v1.3.1）
│   │   └── report.py               # 报告生成
│   ├── chan/                       # 缠论模块（v1.3.1 重构，9 个子模块）
│   │   ├── merge.py / fenxing.py / bi.py
│   │   ├── xianduan.py / zhongshu.py / macd.py
│   │   ├── beichi.py / maidian.py
│   │   └── __init__.py             # 统一导出
│   ├── monitor/                    # 实时监控
│   │   ├── health.py               # 健康检查（v1.3.1 支持缓存清理与阈值告警）
│   │   ├── manager.py              # 监控管理器
│   │   └── channels/               # 通知通道
│   │       ├── base.py / bark.py   # Bark 推送
│   │       ├── wechat.py           # 企业微信 webhook（v1.3.1）
│   │       └── dingtalk.py         # 钉钉 webhook（v1.3.1）
│   ├── portfolio/                  # 持仓管理
│   ├── infrastructure/             # 基础设施（预留）
│   ├── announcements.py            # 东财公告/研报
│   ├── backtest.py                 # 历史回测引擎（v1.3.1 改为 8 线程并发）
│   ├── chan.py                     # 缠论结构（兼容层，已迁移至 chan/）
│   ├── chip.py                     # 资金面分析 CLI（v1.3.1 新增）
│   ├── classifier.py               # 个股类型分类
│   ├── finance.py                  # 财务数据入口
│   ├── init_pool.py                # 候选池初始化
│   ├── kline.py                    # K 线数据入口
│   ├── monitor.py                  # 实时监控入口
│   ├── patterns_local.py           # A 股本土战法形态
│   ├── quote.py                    # 行情数据入口
│   ├── refresh_pool.py             # 候选池刷新
│   ├── screener.py                 # A 股多因子选股器
│   └── technical.py                # 技术分析入口
├── data/                           # 输出数据
│   └── reports/                    # 分析报告
├── experts/                        # 8 人专家定义
│   ├── buffett.md / lynch.md / soros.md / duan_yongping.md
│   ├── xu_xiang.md / zhao_laoge.md / chaogu_yangjia.md / zuoshou_xinyi.md
│   └── decide.md                   # 决策整合规则
├── tests/                          # 测试套件
│   ├── conftest.py                 # pytest 配置与 fixtures
│   ├── smoke_test.sh               # 端到端冒烟测试
│   ├── test_*.py                   # 单元测试
│   └── unit/                       # 更多单元测试
├── docs/                           # 详细文档
│   ├── quick-start.md              # 快速入门
│   ├── user-guide.md               # 使用者指南
│   ├── developer-guide.md          # 开发者指南
│   ├── methodology.md              # 方法论文档
│   ├── api-reference.md            # API 参考
│   ├── implementation-plan.md      # 实现计划
│   └── improvement-roadmap.md      # 改进路线图
├── package.json                    # npm 发布配置
├── pyproject.toml                  # Python 项目配置
├── install-plugin.js               # npm postinstall 脚本
├── install.sh                      # 传统安装脚本
├── README.md                       # 本文件
├── CHANGELOG.md                    # 版本变更记录
├── CONTRIBUTING.md                 # 贡献指南
├── workflow.md                     # 12 个 skill 的协作流程
└── methodology.md                  # 完整投资方法论
```

## 使用示例

### 快速个股分析

```text
/stock sh600989
```

返回：基本面+估值+技术面 3 分钟快评。

### 大盘快评

```text
/market quick
```

返回：主要指数涨跌+最强最弱板块+一句话结论。

### 持仓健康检查

```text
/portfolio
```

读取 `scripts/data/portfolio_example.json`（可复制为 `portfolio.json` 自定义持仓）。

### 多因子选股

```text
/screener --sector 资源 --strategy quality_value --top 5
```

返回：硬过滤结果 + 多因子评分 + 候选池 + 跟踪条件。

### 技术面确认

```text
/technical sh600989 --quick
```

返回：趋势、量价、支撑阻力、技术触发和失效条件。

### 完整五层 + 专家辩论

```text
/stock sh600989 debate
```

返回：五层分析 + 8人圆桌多空辩论 + 最终折中方案。

### 查看帮助

```text
/help
```

返回：所有可用 skills 和使用说明。

## 自定义持仓

```bash
cp scripts/data/portfolio_example.json scripts/data/portfolio.json
# 编辑 portfolio.json，修改 codes 字段
```

`/portfolio` 命令默认读取 `scripts/data/portfolio.json`（或 `scripts/data/portfolio_example.json` 作为回退）。

## 数据源

- **腾讯** `qt.gtimg.cn`：实时行情、PE/PB/市值（GBK 编码，scripts/ 自动处理）
- **东方财富** `emweb.securities.eastmoney.com`：财务摘要（type=0/1/2/3/4）
- **新浪** `money.finance.sina.com.cn`：K线（5/15/30/240 分钟）
- **东方财富** `np-anotice-stock.eastmoney.com`：`company 公告`
- **东方财富** `reportapi.eastmoney.com`：券商研报

所有数据 API 在国内直连，无须代理。

## 方法论

完整投资方法论见 [`methodology.md`](methodology.md)：

- §1 数据源
- §2 五层分析框架（ROE/PE/PEG/技术面/风险收益比，行业差异化阈值）
- §3 8 人专家圆桌（巴菲特/林奇/索罗斯/段永平 + 徐翔/赵老哥/炒股养家/作手新一）
- §4 仓位管理（凯利公式 + 仓位分级 + 集中度控制 + 时间止损 + 极端预案）
- §5 决策流程
- §6 选股策略系统（5 种策略 + 行业差异化阈值 + 板块差异化流动性）
- §7 数据获取工具详解
- §8 快捷启动命令
- §9 关键经验

12 个 skill 的衔接流程见 [`workflow.md`](workflow.md)：支持快速/标准/深度 3 种链路长度，市场 → 板块 → 选股 → 个股 → 技术 → 组合，也支持持仓再平衡、实时监控、策略回测和深度研究四条工作流。

## 文档

- [快速入门](docs/quick-start.md) - 5 分钟上手
- [使用者指南](docs/user-guide.md) - 8 个技能详细用法
- [开发者指南](docs/developer-guide.md) - 项目结构与扩展开发
- [投资方法论](docs/methodology.md) - 五层框架、专家圆桌、仓位管理
- [API 参考](docs/api-reference.md) - 脚本命令行与数据源

## 解耦特性

✅ **零项目依赖**：不引用任何业务项目内文件（`src/`、`data_provider/`、`AGENTS.md` 等）
✅ **零外部 Python 库**：只用 stdlib（`urllib` + `json` + `pathlib` + `yaml`）
✅ **三层架构**：API 层（CLI 入口）→ Business 层（业务逻辑）→ Data 层（数据获取/缓存），职责清晰
✅ **配置外部化**：行业阈值、评分权重、数据源端点等均通过 YAML 配置，无需改代码
✅ **多数据源适配**：fetchers/ 下统一接口，腾讯/东财/新浪/AkShare 等可自由切换
✅ **单源真理**：方法论、数据、脚本各自集中在一处
✅ **可移植**：可打包为 git 仓库或 npm 包分发

## 贡献与 Git 规范

提交信息、分支命名、Tag 版本号等约定详见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
一句话：标题与正文使用中文，type 沿用 Conventional Commits（`feat` / `fix` / `docs` / `refactor` / `chore` 等），分支统一 `<type>/<短描述>` 格式。

## 卸载

```bash
# 方式一：通过 Claude Code plugin 卸载
claude plugins uninstall stock-analyzer

# 方式二：手动删除 symlink
rm -f ~/.claude/skills/stock ~/.claude/skills/market ~/.claude/skills/sector ~/.claude/skills/portfolio ~/.claude/skills/screener ~/.claude/skills/technical ~/.claude/skills/financial-analyst ~/.claude/skills/investment-researcher ~/.claude/skills/help
```

## 近期改进

### v1.3.1 (2026-06-10) - 技术架构优化

- **数据源扩展**：新增雪球（`xueqiu_quote.py`）和同花顺（`ths_quote.py`）两个行情 Fetcher，行情源从 7 个扩展到 9 个
- **多渠道告警**：新增企业微信（`wechat.py`）和钉钉（`dingtalk.py`）webhook 通道，Bark 之外更多选择
- **资金面数据模块**：新增 `scripts/data/chip.py` + `scripts/chip.py` CLI，集成融资融券/股东户数/十大流通股东三个数据源；评分引擎新增资金面因子（+10 / -5 区间）
- **缠论代码重构**：`chan.py`（591 行）拆分为 `chan/` 包下 9 个独立模块（merge/fenxing/bi/xianduan/zhongshu/macd/beichi/maidian），保持 API 向后兼容
- **回测性能优化**：`backtest.py` 数据获取改为 8 线程并发，批量回测显著提速
- **健康检查增强**：`monitor/health.py` 新增 `--cleanup` 缓存清理命令、最大文件数/大小阈值告警（可通过 `STOCK_CACHE_MAX_SIZE_MB` 调整）
- **数据类型扩展**：`FinanceRecord` 新增 `goodwill`（商誉，亿元）和 `pledge_ratio`（质押比例，%）字段

### v1.3.0 (2026-06-10) - 零配置股票池

- **零配置股票池**：新增预置默认股票池数据（`sector_stocks.default.json`），`/stock-init` 无需 token 即可使用，API 失败自动 fallback
- **三层架构重构**：scripts/ 拆分为 API 层（cli 入口）、Business 层（分析/选股服务）、Data 层（fetchers/缓存/配置），职责清晰、易扩展
- **配置外部化**：行业阈值、评分权重、数据源端点等提取为 YAML 配置（`scripts/config/`），无需改代码即可调整

### v1.2.0 (2026-06-08) - 基础能力

- **多数据源适配**：新增 fetchers/ 统一接口层，支持腾讯/东财/新浪/AkShare/eFinance/baostock/pytdx/tushare/yfinance 等 9+ 数据源自由切换
- **统一异常与验证**：新增 `common/exceptions/` 统一异常类、`common/validators.py` 输入验证器
- **Plugin 化分发**：支持通过 Claude Code plugin 系统一键安装，无需重启
- **帮助系统**：新增 `/help` skill，显示所有可用 skills 和使用说明
- **回测引擎**：新增 `backtest.py`，支持策略历史回测验证
- **候选池管理**：新增 `init_pool.py` / `refresh_pool.py`，支持候选池初始化与定期刷新
- **实时监控**：新增 `monitor.py`，支持持仓和关注标的实时监控
- **行业差异化阈值**：五层分析框架按行业分档（金融/消费/科技/周期/医药/制造/能源/地产），避免一刀切误判
- **风控体系强化**：集中度控制（单只≤15%、单行业≤30%）、时间止损、极端情景预案、加仓规则
- **专家权重优化**：长短线权重随投资期限变化，巴菲特否决权限定中长期模式
- **工作流增强**：交接字段补充投资期限/催化剂/论点破灭条件，决策门槛量化

## 已知限制

- 实时数据依赖外部 API 端点稳定性；如遇变更，修改 `scripts/fetchers/` 中端点即可
- 预置默认股票池数据为静态快照，如需最新数据需联网刷新
- portfolio skill 默认读取 `scripts/data/portfolio_example.json` 作为示例，实际使用前需自定义
- 部分 API（如东财公告）可能有反爬限制，已加超时和重试
- 多因子权重基于经验设定，尚未经过历史回测验证
- 资金面数据（融资融券/股东户数）每日更新，市场实时性受交易所披露节奏限制

<!-- markdownlint-disable MD040 -->

# 使用者指南

> **你不需要看完整份指南**——挑一个目标进去就行，剩下的按需翻。

## 🎯 TL;DR · 核心 skill 一句话表

命令列都是**可直接复制**的示例（换成你关心的股票/板块即可）：

| 你的目标              | 命令                                  | 一句话价值                              |
| --------------------- | ------------------------------------- | --------------------------------------- |
| 🔍 找几只值得关注的股票 | `/screener`                           | 6 策略 × 9 因子维度 → 候选池 + 跟踪清单 |
| 📊 看今天大盘涨跌     | `/market quick`                       | 三大指数 + 板块 Top3 + 一句话策略       |
| 💼 看看我的持仓       | `/portfolio health`                   | 涨跌 + 板块集中度 + 风险预警 + 调仓建议 |
| 🎯 分析一只股票       | `/stock sh600519 quick`               | 单股 5 层分析 / 8 位专家圆桌 / 纯技术面 |
| 🌐 某个板块怎么样     | `/sector 白酒 overview`               | 板块全景 + 标的对比 + 板块内筛选        |
| 🔬 深度研究一只股票   | `/research financial 分析贵州茅台财务质量` | 财务建模 + 排雷 + DCF + 投资建议   |
| 🧪 验证选股策略       | `/backtest --all`                     | 胜率 + 收益 + 夏普 + 回撤 + 基准对比    |
| 📚 学投资基础         | `/learn 什么是PE`                     | PE/ROE/MACD/均线/缠论 系统化学习路径    |
| ❓ 不知道哪个命令      | `/stock-help`                         | 场景入口 + 全部命令一览                 |

> ⚠️ **风险提示**：本指南及所有输出示例中出现"买入 / 卖出 / 止损 / 仓位 / 目标价"等字样，均为演示，**仅供参考，不构成投资建议**。投资有风险，决策需谨慎。

## 🗺️ 4 个组合使用场景

> **逐级加深，别跳级**：`quick`（3 分钟看结论）→ `full`（+板块与风险收益比）→ `debate`（+专家投票）→ `technical`（+指标体系）→ `research`（+财务建模）。每升一级只新增 1 个概念；不熟悉上一级时先别往下跳。

### 场景 A：自上而下选股（最常用）

```
market → sector → screener → stock → technical → portfolio
```

1. `/market quick` — 了解市场状态（进攻 / 均衡 / 防守）
2. `/sector AI算力 overview` — 找当前资金偏好
3. `/screener --sector AI算力 --strategy quality_value` — 板块内筛选
4. `/stock sh600519 quick` — 快速分析候选
5. `/stock sh600519 technical` — 确认买点 / 止损位
6. `/portfolio` — 决定是否纳入持仓、仓位多少

### 场景 B：诊断现有持仓

```
portfolio → stock → technical
```

1. `/portfolio health` — 持仓健康度（涨跌 + 板块集中度 + 风险）
2. `/stock sh600519 debate` — 听 8 位 active 专家辩论
3. `/stock sh600519 technical` — 确认技术面是否破位

### 场景 C：挖掘板块机会

```
market → sector → screener
```

1. `/market` — 看今日板块 Top3 / Bot3
2. `/sector 白酒 overview` — 板块全景
3. `/sector 白酒 compare` — 板块内核心标的横向对比

### 场景 D：深度研究单股

```
stock debate → research financial → research report
```

1. `/stock sh600519 debate` — 8 位专家圆桌 + 最终方向
2. `/research financial 分析贵州茅台财务质量` — 财务建模 / 杜邦 / DCF
3. `/research report 研究贵州茅台，给一份完整投资报告` — 全维度投资研究报告

> 想看"持仓再平衡"等更多流程？见下方 [完整使用流程](#完整使用流程自下而上--再平衡--研究报告) 段。

## 股票代码格式

支持以下格式输入股票代码：

| 格式        | 示例       | 说明           |
| ----------- | ---------- | -------------- |
| `sh` + 代码 | `sh600519` | 上海证券交易所 |
| `sz` + 代码 | `sz000858` | 深圳证券交易所 |
| 纯数字      | `600519`   | 自动推断交易所 |
| 股票名称    | `贵州茅台` | 按名称模糊匹配 |

## 技能概览

| Skill     | 命令（可复制示例）                       | 用途         | 模式 / 更多选项                           |
| --------- | ---------------------------------------- | ------------ | ----------------------------------------- |
| stock     | `/stock sh600519 quick`                  | 单股分析     | 五层框架¹ + 专家圆桌²；另有 full / debate |
| market    | `/market quick`                          | 大盘复盘     | 指数+板块+风格+资金；另有 full / intraday |
| sector    | `/sector 白酒 overview`                  | 板块分析     | 标的对比+多空博弈；另有 compare / stock   |
| portfolio | `/portfolio health`                      | 持仓健康检查 | 涨跌+支撑+风险预警；另有 rebalance        |
| screener  | `/screener --strategy balanced --top 5`  | 选股策略系统 | 多因子筛选+硬过滤³+候选池；另有 init      |
| research  | `/research financial 分析贵州茅台财务质量` | 深度研究   | 财务建模 / 市场研究 / 尽调 / 估值         |
| backtest  | `/backtest --all`                        | 策略回测     | 历史胜率+收益验证；另有 --strategy / --days |
| stock-help | `/stock-help`                            | 使用说明     | 场景入口 + 显示所有可用 skills            |
| stock-technical | `/stock-technical sh600519`        | 纯技术分析   | 均线/MACD/KDJ/BOLL/RSI/缠论/战法          |
| portfolio-web | `/portfolio web`                     | Web 录入     | HTTP API :8765，浏览器/手机录入           |
| portfolio-natural | 自然语言持仓操作                  | 持仓 NL 映射 | 我买了/减仓/破位止损 → 命令               |
| learn     | `/learn 什么是PE`                        | 投资学习     | PE/ROE/MACD/缠论 系统化学习路径           |

> **术语说明**：
>
> - ¹ **五层框架**：基本面/估值/技术面/板块/风险收益比，详见 [../methodology.md](../methodology.md)
> - ² **专家圆桌**：16 份专家人设（8 active + 8 legacy），`debate` 实际跑 8 位 active 专家各 1 票（5 长线 + 3 短线）；8 位 legacy 已合并入 active 视角
> - ³ **硬过滤**：排除 ST 股、低成交额（主板≥5000万、创业板/科创板≥3000万、北交所≥1000万）、低市值（主板≥40亿、创业板/科创板≥20亿、北交所≥10亿）标的
> - ⁴ **缠论**：基于走势中枢和买卖点的技术分析方法
> - ⁵ **本土战法**：A 股特色 K 线形态（如涨停板、连板、断板等）
> - **PE（市盈率）**：股价 ÷ 每股盈利，粗略理解成"按当前利润多少年回本"，要和同行比才有意义。**ROE（净资产收益率）**：公司用股东的钱赚钱的效率，价值派最看重的单一指标。**PEG**：PE ÷ 盈利增速，通常 <1 视为增长与估值匹配。三者详见 [methodology.md](../methodology.md) 附录，或随时用 `/learn`。
> - **胜率**：历史信号中盈利次数占比。⚠️ **样本内胜率不能外推**——目前多数策略的外样本状态仍为 `in_sample`，详见 [strategy-validation.md](strategy-validation.md)。

## 初始化股票池 (/screener init)

命令格式：`/screener init [force|default|top N]`

为 A 股各板块初始化前 20 只活跃股票，供选股、板块分析等 skill 使用。

### 自动初始化（推荐）

```
/screener init
```

首次运行自动初始化，已有数据时跳过。**零配置可用**：无需任何 token 或 API 密钥。

### 强制刷新

```
/screener init force
```

强制重新初始化，联网获取最新数据。

### 离线模式

```
/screener init default
```

使用预置默认数据，不访问 API，适合离线环境。

### 自定义数量

```
/screener init top 30
```

每板块取 Top 30 只股票（默认 20）。

### 数据源优先级

1. 东方财富 push2 API（联网获取最新数据）
2. 预置默认数据（`sector_stocks.default.json`，离线可用）

无 token 时自动尝试免费访问 API，失败时自动 fallback 到预置数据。

## 单股分析 (/stock)

用法：`/stock sh600519 full`（把 sh600519 换成你的股票；模式可用 quick / full / debate）

### quick 模式（3 分钟快评）

```
/stock sh600989 quick
```

返回：基本面+估值+技术面快速评估。

### full 模式（五层分析）

```
/stock sh600989 full
```

返回：五层分析（基本面/估值/技术面/板块/风险收益比）。

### debate 模式（专家辩论）

```text
/stock sh600989 debate         # 全模式：8 人专家圆桌（5 长线 + 3 短线）
/stock sh600989 debate 长线    # 仅长线组（林奇/索罗斯/价值机构锚/行业专家/风控）
/stock sh600989 debate 短线    # 仅短线组（题材龙头/情绪技术/动量派）
```

返回：五层分析 + 专家圆桌多空辩论 + 最终折中方案。长线/短线子模式仅调用对应组别专家。

## 大盘复盘 (/market)

命令格式：`/market [full|quick|intraday]`

### full 模式（完整复盘）

```
/market full
```

返回：主要指数+板块+风格+资金流向完整分析。

### quick 模式（快评）

```
/market quick
```

返回：主要指数涨跌+最强最弱板块+一句话结论。

### intraday 模式（盘中分时）

```
/market intraday
```

返回：盘中分时复盘。

## 板块分析 (/sector)

用法：`/sector 白酒 overview`（把"白酒"换成你的板块；模式可用 overview / compare / stock）

### overview 模式（板块全景）

```
/sector 资源 overview
```

返回：板块全景分析。

### compare 模式（核心标的对比）

```
/sector 资源 compare
```

返回：核心标的横向对比。

### stock 模式（板块内个股深度分析）

```
/sector 资源 stock               # 板块内筛选
/sector 医药 stock 恒瑞医药      # 板块内指定个股深度分析
```

返回：板块内个股筛选或指定个股的五层分析（含板块内横向对比）。

## 持仓管理 (/portfolio)

命令格式：`/portfolio [health|rebalance|compare]`

### 自定义持仓

```bash
cp scripts/data/portfolio_example.json scripts/data/portfolio.json
# 编辑 portfolio.json，修改 codes 字段
```

> **说明**：`/portfolio` 命令读取 `scripts/data/portfolio.json`，如果不存在则回退到 `scripts/data/portfolio_example.json` 作为示例。

### health 模式（健康检查）

```
/portfolio health
```

返回：持仓实时涨跌、仓位/板块集中度、风险预警。

### rebalance 模式（调仓再平衡）

```
/portfolio rebalance
```

返回：调仓建议、再平衡方案。

> `compare` 模式未实现——持仓/标的对比由 `/stock` 多股对比或 `/sector` 覆盖。

## 多因子选股 (/screener)

命令格式：`/screener [--sector 板块] [--strategy 策略]`

### 6 种策略

| 策略            | 市场环境          | 说明     |
| --------------- | ----------------- | -------- |
| balanced        | 震荡/方向不明     | 均衡精选 |
| quality_value   | 价值修复/防守     | 质量价值 |
| growth_momentum | 进攻行情/主线题材 | 成长动量 |
| defensive       | 缩量弱市/避险     | 防守低波 |
| turning_point   | 超跌修复/拐点     | 拐点修复 |
| ma_volume_momentum | 量价配合/趋势跟涨 | 量价动量 |

### 参数说明

- `--sector 白酒`：板块名称（换成你关心的板块）
- `--strategy balanced`：策略名称（6 选 1，见下表）
- `--top 5`：返回前 5 个候选（换成你想要的个数）
- `--codes sh600519,sz000858`：自定义股票池（逗号分隔）
- `--exclude-loss`：剔除亏损股
- `--json`：JSON 格式输出

### 使用示例

```
/screener --sector 资源 --strategy quality_value --top 5
```

返回：硬过滤结果 + 多因子评分 + 候选池 + 跟踪条件。

## 纯技术分析 (/stock technical)

用法：`/stock sh600519 technical`（可加 `--quick` 快速版或 `--classify` 分类版）

### 快速模式

```
/stock sh600989 technical --quick
```

返回：趋势、量价、支撑阻力、技术触发和失效条件。

### 完整模式（默认）

```
/stock sh600989 technical
```

返回：完整技术分析（均线/MACD/KDJ/BOLL/缠论/本土战法）。

### 分类模式

```
/stock sh600989 technical --classify
```

返回：完整分析 + 个股类型分类 + 缠论结构 + 市场环境自适应。

## 财务分析 (/research financial)

用法：`/research financial 分析贵州茅台财务质量`（换成你想研究的公司）

用途：建模、预测、场景分析。

```
/research financial 分析宝丰能源的财务质量
```

## 投资研究 (/research report)

用法：`/research report 研究贵州茅台，给一份完整投资报告`（换成你想研究的公司）

用途：市场研究、尽调、估值。

```text
/research report 宝丰能源投资价值研究
```

## 策略回测 (/backtest)

命令格式：`/backtest [--strategy 策略] [--all] [--days N]`

验证选股策略的历史胜率和收益。

```text
/backtest                            # 默认均衡精选，60 天回测
/backtest --strategy quality_value   # 质量价值策略
/backtest --all                      # 比较所有 6 种策略
/backtest --days 120                 # 回测 120 天
/backtest --codes 600519,000858      # 指定股票池
```

返回：策略胜率、平均收益、最大回撤等统计指标。

## 数据源健康检查

```text
python3 scripts/monitor.py --cache       # 显示缓存状态
python3 scripts/monitor.py --sources     # 显示数据源状态
python3 scripts/monitor.py --cleanup     # 清理过期缓存
```

数据源故障转移与缓存管理工具，无持仓推送功能。持仓 CRUD 推送通过
`/portfolio web --no-notify` 关闭。

## 完整使用流程（自下而上 / 再平衡 / 研究报告）

> 顶部 TL;DR 已覆盖最常见的 4 个场景（A/B/C/D）。这里是补充流程：自下而上验证、持仓再平衡、深度研究报告。

### 自下而上验证

`stock` → `research financial` → `sector` → `technical` → `portfolio`

适合用户已经给定个股。先判断公司质量和估值，再看板块是否配合，最后确认技术触发。

### 持仓再平衡

`portfolio` → `market` → `technical` → `screener` → `stock`

1. 先找组合风险，再确认市场风格
2. 对弱势持仓跑 `technical` 判破位
3. 用 `screener` 找替代候选，再用 `stock` 精筛

### 深度研究报告

`research report` 作为总控，按需调用：

- `market`：宏观市场和风格
- `sector`：行业景气和竞争格局
- `research financial`：财务质量、预测、场景
- `stock`：投资结论和风险收益比
- `technical`：交易窗口和失效条件

## 常见问题

### 数据源是否稳定？

```text
【症状】某类数据（行情 / K 线 / 财务）突然全部为空或报错。
【根因】上游 API 端点变更或限频。37 个 fetcher 会自动故障转移，但整类数据源同时变更时会一起失效。
【下一步】① 先跑 python3 scripts/monitor.py --sources 看各源状态；② 再按下面「如何处理 API 变更」定位；③ 急用可切预置快照 python3 scripts/init_pool.py --default。
```

### 如何处理 API 变更？

端点**不在** `scripts/common/__init__.py`（那里只是 re-export），而在各 fetcher 源文件顶部常量（如 `scripts/fetchers/quote/tencent_quote.py` 的 `TENCENT_URL`）与 `scripts/config/data_source.yaml`：

1. 定位端点：查 `scripts/config/data_source.yaml` 或在 `scripts/fetchers/` 下搜索 `URL`
2. 更新端点 URL
3. 验证数据格式是否变化：`python3 scripts/quote.py sh600519`
4. 更新字段映射

### 如何自定义选股策略？

当前策略权重在 `scripts/config/scoring.yaml` 中定义。如需自定义：

1. 修改策略权重配置
2. 添加新因子定义
3. 更新评分逻辑

### API 返回空数据怎么办？

```text
【症状】命令返回空表、"未找到标的"，或字段全是 N/A。
【根因】三种常见原因：网络不通、股票代码前缀写错、上游临时限频——先按顺序排查前两种（都是输入/环境问题，不是分析结果）。
【下一步】
 ① 查网络：curl -s "https://qt.gtimg.cn/q=sh600519"，有行情文本即网络正常；
 ② 查代码：sh600519（沪）/ sz000858（深），用 python3 scripts/quote.py sh600519 验证；
 ③ 查源状态：python3 scripts/monitor.py --sources；系统会自动 fallback 到备用源；
 ④ 仍为空：python3 scripts/init_pool.py --default 切预置快照。
```

### 股票名称有多个匹配怎么办？

系统会返回第一个匹配结果。建议使用股票代码（如 `sh600519`）而非名称，避免歧义。

### 为什么某些股票被排除？

选股器默认排除：

- ST 股（风险警示）
- 成交额低于阈值（主板≥5000万，创业板/科创板≥3000万，北交所≥1000万）
- 市值低于阈值（主板≥40亿，创业板/科创板≥20亿，北交所≥10亿）

如需包含这些股票，可使用 `--codes` 参数手动指定。

## Skill 边界说明

| Skill                 | 定位   | 适用场景         |
| --------------------- | ------ | ---------------- |
| `/stock`              | 判断   | 买/卖/持有决策   |
| `/stock technical`    | 技术面 | 买入时机、止损位 |
| `/research financial` | 建模   | 估值、预测、场景 |
| `/research report`    | 报告   | 深度研究、存档   |
| `/screener`           | 筛选   | 批量选股、候选池 |
| `/backtest`           | 验证   | 策略历史表现     |
